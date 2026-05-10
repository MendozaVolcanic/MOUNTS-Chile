"""
Base de datos SQLite para MOUNTS-Chile.

Persiste el catalogo historico completo:
  observations    todas las muestras de todas las trazas (idempotente)
  anomalies       anomalias detectadas (con detected_at para auditoria)
  events          flags tbar_* de GVP/USGS (ground truth)
  status_history  snapshots periodicos del status board

Queries comunes (ver al final de este archivo):
    python db.py summary
    python db.py recent       # ultimas 20 anomalias
    python db.py top --n 30   # top 30 anomalias historicas
    python db.py validate     # cruza detector vs eventos GVP

Integrado al pipeline via update.py.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "mounts.db"
TS_DIR   = BASE_DIR / "timeseries"

VOLCANES_META = [
    ("lascar",             "Lascar",             355100, -23.37, -67.73),
    ("planchon-peteroa",   "Planchon-Peteroa",   357040, -35.24, -70.57),
    ("laguna-del-maule",   "Laguna del Maule",   357061, -36.10, -70.49),
    ("nevados-de-chillan", "Nevados de Chillan", 357070, -36.86, -71.38),
    ("copahue",            "Copahue",            357090, -37.85, -71.17),
    ("llaima",             "Llaima",             357110, -38.69, -71.73),
    ("villarrica",         "Villarrica",         357120, -39.42, -71.93),
]

PRODUCT_TRACES = {
    "swir":     ("S2Pix",         "Sentinel-2"),
    "so2":      ("tons",          "Sentinel-5P"),
    "def_asc":  ("m_LOS",         "Sentinel-1"),
    "def_desc": ("m_LOS",         "Sentinel-1"),
    "coh_asc":  ("Npix_coh<0.5",  "Sentinel-1"),
    "coh_desc": ("Npix_coh<0.5",  "Sentinel-1"),
    "int_asc":  ("placeholder",   "Sentinel-1"),
    "int_desc": ("placeholder",   "Sentinel-1"),
}

EVENT_TRACES = {"tbar_so2", "tbar_nir", "tbar_disp", "tbar_int", "tbar_coh"}


# --- Schema -----------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS volcanoes (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    smithsonian_id INTEGER,
    lat REAL,
    lon REAL
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volcano_key TEXT NOT NULL REFERENCES volcanoes(key),
    product TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    unit TEXT,
    sensor TEXT,
    image_path TEXT,
    UNIQUE(volcano_key, product, date)
);
CREATE INDEX IF NOT EXISTS idx_obs_vol_prod_date ON observations(volcano_key, product, date);
CREATE INDEX IF NOT EXISTS idx_obs_date          ON observations(date);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volcano_key TEXT NOT NULL REFERENCES volcanoes(key),
    product TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    baseline_median REAL,
    baseline_mad REAL,
    zscore REAL,
    severity TEXT,
    detected_at TEXT NOT NULL,
    UNIQUE(volcano_key, product, date)
);
CREATE INDEX IF NOT EXISTS idx_anom_date     ON anomalies(date);
CREATE INDEX IF NOT EXISTS idx_anom_zscore   ON anomalies(zscore DESC);
CREATE INDEX IF NOT EXISTS idx_anom_volcano  ON anomalies(volcano_key);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volcano_key TEXT NOT NULL REFERENCES volcanoes(key),
    date TEXT NOT NULL,
    track_type TEXT NOT NULL,
    value REAL,
    UNIQUE(volcano_key, date, track_type)
);
CREATE INDEX IF NOT EXISTS idx_evt_date    ON events(date);
CREATE INDEX IF NOT EXISTS idx_evt_volcano ON events(volcano_key);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at TEXT NOT NULL,
    volcano_key TEXT NOT NULL,
    product TEXT NOT NULL,
    latest_value REAL,
    latest_date TEXT,
    zscore REAL,
    severity TEXT,
    age_hours REAL
);
CREATE INDEX IF NOT EXISTS idx_status_snap ON status_history(snapshot_at);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


# --- Helpers ----------------------------------------------------------------

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Crea schema y popula tabla volcanoes si esta vacia."""
    conn.executescript(SCHEMA)
    cur = conn.execute("SELECT COUNT(*) FROM volcanoes")
    if cur.fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO volcanoes(key, name, smithsonian_id, lat, lon) VALUES(?,?,?,?,?)",
            VOLCANES_META,
        )
    conn.commit()


# --- Ingestion --------------------------------------------------------------

def ingest_timeseries(conn: sqlite3.Connection) -> tuple[int, int]:
    """
    Lee todos los timeseries/*.json y hace UPSERT en observations + events.
    Devuelve (n_obs_nuevas, n_events_nuevas).
    """
    n_obs = 0
    n_evt = 0
    for key, name, sid, _, _ in VOLCANES_META:
        f = TS_DIR / f"{key}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))

        for trace in data.get("traces", []):
            tname = trace.get("name")
            if not tname:
                continue
            xs = trace.get("x") or []
            ys = trace.get("y") or []
            texts = trace.get("text") or []
            n = min(len(xs), len(ys))
            texts = (texts + [""] * n)[:n] if texts else [""] * n

            if tname in PRODUCT_TRACES:
                unit, sensor = PRODUCT_TRACES[tname]
                rows = [
                    (key, tname, x, y, unit, sensor, txt or None)
                    for x, y, txt in zip(xs[:n], ys[:n], texts)
                    if y is not None
                ]
                if rows:
                    cur = conn.executemany(
                        """INSERT OR IGNORE INTO observations
                           (volcano_key, product, date, value, unit, sensor, image_path)
                           VALUES (?,?,?,?,?,?,?)""",
                        rows,
                    )
                    n_obs += cur.rowcount

            elif tname in EVENT_TRACES:
                track = tname.replace("tbar_", "")
                rows = [
                    (key, x, track, y)
                    for x, y in zip(xs[:n], ys[:n])
                    if y is not None
                ]
                if rows:
                    cur = conn.executemany(
                        """INSERT OR IGNORE INTO events
                           (volcano_key, date, track_type, value) VALUES (?,?,?,?)""",
                        rows,
                    )
                    n_evt += cur.rowcount

    conn.commit()
    return n_obs, n_evt


def ingest_anomalies(conn: sqlite3.Connection) -> int:
    """
    Lee alerts.json y status.json (productos con baseline) e inserta en anomalies.
    Solo agrega anomalias nuevas (UPSERT por (vol, prod, date)).
    """
    alerts_f = BASE_DIR / "alerts.json"
    if not alerts_f.exists():
        return 0
    alerts = json.loads(alerts_f.read_text(encoding="utf-8"))
    detected_at = datetime.now(timezone.utc).isoformat()

    rows = []
    for a in alerts.get("alerts", []):
        z = a.get("zscore", 0)
        sev = "red" if z >= 6 else ("orange" if z >= 3 else "yellow")
        rows.append((
            a["volcano_key"],
            a["product"].lower() if a["product"] not in ("DEF", "COH") else (
                "def_desc" if a["product"] == "DEF" else "coh_desc"
            ),
            a["date"],
            a["value"],
            a.get("baseline"),
            None,                         # mad no esta en alerts.json (esta en status.json)
            z,
            sev,
            detected_at,
        ))

    cur = conn.executemany(
        """INSERT OR IGNORE INTO anomalies
           (volcano_key, product, date, value, baseline_median, baseline_mad,
            zscore, severity, detected_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    return cur.rowcount


def ingest_status(conn: sqlite3.Connection) -> int:
    """Snapshot del status actual a status_history."""
    status_f = BASE_DIR / "status.json"
    if not status_f.exists():
        return 0
    s = json.loads(status_f.read_text(encoding="utf-8"))
    snap_at = s.get("generated_at", datetime.now(timezone.utc).isoformat())

    rows = []
    for vol_key, vol in s.get("volcanoes", {}).items():
        for product, ps in vol.get("products", {}).items():
            if ps is None:
                continue
            rows.append((
                snap_at, vol_key, product,
                ps.get("latest_value"),
                ps.get("latest_date"),
                ps.get("zscore_now"),
                ps.get("severity"),
                ps.get("age_hours"),
            ))
    cur = conn.executemany(
        """INSERT INTO status_history
           (snapshot_at, volcano_key, product, latest_value, latest_date,
            zscore, severity, age_hours)
           VALUES (?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    return cur.rowcount


# --- Queries ----------------------------------------------------------------

def cmd_summary(conn):
    print(f"DB: {DB_PATH}  ({DB_PATH.stat().st_size//1024} KB)")
    print()
    for table in ["volcanoes", "observations", "anomalies", "events", "status_history"]:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        n = cur.fetchone()[0]
        print(f"  {table:18} {n:>10}")
    print()
    # Por volcan
    print("Observaciones por volcan:")
    cur = conn.execute("""
        SELECT v.name, COUNT(o.id), MIN(o.date), MAX(o.date)
        FROM volcanoes v LEFT JOIN observations o ON o.volcano_key = v.key
        GROUP BY v.key ORDER BY v.smithsonian_id
    """)
    for name, n, mn, mx in cur:
        print(f"  {name:22} {n:>6}  {(mn or '')[:10]} .. {(mx or '')[:10]}")
    print()
    print("Anomalias por volcan:")
    cur = conn.execute("""
        SELECT v.name, COUNT(a.id), MAX(a.zscore)
        FROM volcanoes v LEFT JOIN anomalies a ON a.volcano_key = v.key
        GROUP BY v.key ORDER BY v.smithsonian_id
    """)
    for name, n, mz in cur:
        mz_str = f"max z={mz:.1f}" if mz else ""
        print(f"  {name:22} {n:>4}  {mz_str}")


def cmd_recent(conn, n=20):
    print(f"Ultimas {n} anomalias detectadas (por detected_at):")
    cur = conn.execute("""
        SELECT a.detected_at, a.date, v.name, a.product, a.value, a.zscore, a.severity
        FROM anomalies a JOIN volcanoes v ON v.key = a.volcano_key
        ORDER BY a.detected_at DESC, a.zscore DESC LIMIT ?
    """, (n,))
    print(f"  {'Detected':16} {'Event date':10} {'Volcan':22} {'Prod':4} {'Value':>10} {'Z':>6}  Sev")
    for det, dt, name, prod, val, z, sev in cur:
        print(f"  {det[:16]} {dt[:10]} {name:22} {prod:4} {val:>10.3g} {z:>6.1f}  {sev}")


def cmd_top(conn, n=30):
    print(f"Top {n} anomalias historicas (por z-score):")
    cur = conn.execute("""
        SELECT a.date, v.name, a.product, a.value, a.zscore, a.severity
        FROM anomalies a JOIN volcanoes v ON v.key = a.volcano_key
        ORDER BY a.zscore DESC LIMIT ?
    """, (n,))
    print(f"  {'Date':10} {'Volcan':22} {'Prod':4} {'Value':>10} {'Z':>6}  Sev")
    for dt, name, prod, val, z, sev in cur:
        print(f"  {dt[:10]} {name:22} {prod:4} {val:>10.3g} {z:>6.1f}  {sev}")


def cmd_validate(conn, window_days=7):
    """
    Valida el detector cruzando anomalias con eventos GVP/USGS (tbar_*).
    True positive: anomalia con un evento dentro de ±window_days.
    """
    cur = conn.execute("SELECT COUNT(*) FROM anomalies")
    n_anom = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM events")
    n_evt = cur.fetchone()[0]

    if n_anom == 0:
        print("Sin anomalias para validar.")
        return

    cur = conn.execute(f"""
        SELECT COUNT(DISTINCT a.id) FROM anomalies a
        WHERE EXISTS (
          SELECT 1 FROM events e
          WHERE e.volcano_key = a.volcano_key
            AND ABS(julianday(e.date) - julianday(a.date)) <= ?
        )
    """, (window_days,))
    tp = cur.fetchone()[0]
    fp = n_anom - tp

    print(f"Validacion detector vs eventos GVP (ventana ±{window_days}d):")
    print(f"  Total anomalias: {n_anom}")
    print(f"  Total eventos:   {n_evt}")
    print(f"  TP (anomalia con evento cercano):   {tp}")
    print(f"  FP (anomalia sin evento cercano):   {fp}")
    if n_anom:
        print(f"  Precision (TP / (TP+FP)):           {tp/n_anom:.2%}")


def cmd_export_anomalies(conn, out_csv: str = "anomalies.csv"):
    """Exporta tabla anomalies a CSV."""
    import csv as csv_mod
    cur = conn.execute("""
        SELECT a.date, v.name, a.product, a.value, a.baseline_median,
               a.zscore, a.severity, a.detected_at
        FROM anomalies a JOIN volcanoes v ON v.key = a.volcano_key
        ORDER BY a.zscore DESC
    """)
    rows = cur.fetchall()
    out = BASE_DIR / out_csv
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv_mod.writer(f)
        w.writerow(["date", "volcano", "product", "value", "baseline",
                    "zscore", "severity", "detected_at"])
        w.writerows(rows)
    print(f"Exportado: {out} ({len(rows)} filas)")


# --- Pipeline integration ---------------------------------------------------

def update_all(verbose=True) -> dict:
    """Pipeline completo de DB. Llamado desde update.py."""
    conn = connect()
    init_db(conn)

    n_obs, n_evt = ingest_timeseries(conn)
    n_anom = ingest_anomalies(conn)
    n_stat = ingest_status(conn)

    # Marca timestamp ultima actualizacion
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?,?)",
        ("last_update", datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    result = {"observations": n_obs, "events": n_evt,
              "anomalies": n_anom, "status_snapshots": n_stat}
    if verbose:
        print(f"  observations new:  {n_obs}")
        print(f"  events new:        {n_evt}")
        print(f"  anomalies new:     {n_anom}")
        print(f"  status snapshots:  {n_stat}")
    return result


# --- CLI --------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("update",   help="Ingest desde timeseries/ + alerts.json + status.json")
    sub.add_parser("summary",  help="Estadisticas de la DB")
    s = sub.add_parser("recent",   help="Ultimas anomalias detectadas")
    s.add_argument("--n", type=int, default=20)
    s = sub.add_parser("top",      help="Top anomalias historicas")
    s.add_argument("--n", type=int, default=30)
    s = sub.add_parser("validate", help="TPR del detector vs eventos GVP")
    s.add_argument("--days", type=int, default=7)
    sub.add_parser("export",   help="Exportar anomalies.csv")

    args = p.parse_args()

    if args.cmd is None or args.cmd == "update":
        update_all()
    else:
        conn = connect()
        init_db(conn)
        if args.cmd == "summary":   cmd_summary(conn)
        elif args.cmd == "recent":  cmd_recent(conn, args.n)
        elif args.cmd == "top":     cmd_top(conn, args.n)
        elif args.cmd == "validate":cmd_validate(conn, args.days)
        elif args.cmd == "export":  cmd_export_anomalies(conn)


if __name__ == "__main__":
    main()
