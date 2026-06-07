"""
Calidad del scraping: gap analysis + drift detection.

GAP ANALYSIS
  Para cada (volcan, producto), detecta huecos temporales mayores a 3x el
  revisit esperado del sensor. Util para detectar nubes sostenidas, fallas
  upstream, o cambios de cadencia.

DRIFT DETECTION
  Compara observaciones actuales vs version anterior en la DB. Si MOUNTS
  modifica valores historicos (re-procesa con baseline distinto), lo
  registra en tabla data_changes.

Output: quality.json con metricas + escribe en mounts.db tabla data_changes.

Uso:
    python quality.py
"""

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
TS_DIR   = BASE_DIR / "timeseries"
DB_PATH  = BASE_DIR / "mounts.db"
OUT_JSON = BASE_DIR / "quality.json"

VOLCANES = [
    "lascar", "planchon-peteroa", "laguna-del-maule",
    "nevados-de-chillan", "copahue", "llaima", "villarrica",
]

# Revisit esperado en dias por producto
EXPECTED_REVISIT = {
    "swir":     5,   # Sentinel-2 A+B
    "so2":      1,   # Sentinel-5P diario
    "def_asc":  12,  # Sentinel-1 single sat post-S1B failure
    "def_desc": 12,
    "coh_asc":  12,
    "coh_desc": 12,
}


def parse_iso(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def load_trace(volcano, trace_name):
    f = TS_DIR / f"{volcano}.json"
    if not f.exists():
        return []
    data = json.loads(f.read_text(encoding="utf-8"))
    for t in data.get("traces", []):
        if t.get("name") == trace_name:
            xs = t.get("x") or []
            ys = t.get("y") or []
            return [(x, y) for x, y in zip(xs, ys) if y is not None]
    return []


def analyze_gaps(volcano, trace_name, expected_revisit):
    """Detecta gaps en una traza."""
    pairs = load_trace(volcano, trace_name)
    if len(pairs) < 2:
        return None
    # Ordenar y deduplicar por fecha
    dates = sorted({parse_iso(x) for x, _ in pairs if parse_iso(x)})
    if len(dates) < 2:
        return None

    gaps = []
    threshold = timedelta(days=expected_revisit * 3)
    for i in range(1, len(dates)):
        dt = dates[i] - dates[i-1]
        if dt > threshold:
            gaps.append({
                "from": dates[i-1].isoformat(),
                "to":   dates[i].isoformat(),
                "days": dt.days,
            })

    total_span = (dates[-1] - dates[0]).days
    # Cobertura: cuantos datos vs cuantos esperaba el sensor
    expected = max(1, total_span / expected_revisit)
    coverage = len(dates) / expected
    return {
        "n_observations": len(dates),
        "first_date":     dates[0].isoformat(),
        "last_date":      dates[-1].isoformat(),
        "total_span_days": total_span,
        "coverage_pct":   round(coverage * 100, 1),
        "n_gaps":         len(gaps),
        "largest_gap_days": max((g["days"] for g in gaps), default=0),
        "gaps_top5":      sorted(gaps, key=lambda g: g["days"], reverse=True)[:5],
    }


def gap_analysis_all():
    """Gap analysis para todos los (volcan, producto)."""
    result = {}
    for vol in VOLCANES:
        result[vol] = {}
        for prod, revisit in EXPECTED_REVISIT.items():
            ga = analyze_gaps(vol, prod, revisit)
            if ga:
                result[vol][prod] = ga
    return result


def detect_drift():
    """
    Compara observations en la DB vs los JSONs actuales.
    Si un (volcan, producto, date) tiene valor distinto al guardado, registra.

    Retorna lista de cambios + crea tabla data_changes si no existe.
    """
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volcano_key TEXT NOT NULL,
            product TEXT NOT NULL,
            date TEXT NOT NULL,
            old_value REAL,
            new_value REAL,
            detected_at TEXT NOT NULL,
            UNIQUE(volcano_key, product, date, detected_at)
        )
    """)
    conn.commit()

    detected_at = datetime.now(timezone.utc).isoformat()
    changes = []

    for vol in VOLCANES:
        f = TS_DIR / f"{vol}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        traces = {t.get("name"): t for t in data.get("traces", []) if t.get("name")}

        for prod in EXPECTED_REVISIT.keys():
            t = traces.get(prod)
            if not t:
                continue
            xs = t.get("x") or []
            ys = t.get("y") or []
            current = {x: y for x, y in zip(xs, ys) if y is not None}

            # Comparar con DB
            cur = conn.execute("""
                SELECT date, value FROM observations
                WHERE volcano_key=? AND product=?
            """, (vol, prod))
            db_rows = {date: value for date, value in cur}

            for date, val in current.items():
                if date in db_rows and db_rows[date] != val:
                    diff_pct = abs(val - db_rows[date]) / max(abs(db_rows[date]), 0.1) * 100
                    if diff_pct < 0.1:  # ruido floating point
                        continue
                    changes.append({
                        "volcano": vol, "product": prod, "date": date,
                        "old_value": db_rows[date], "new_value": val,
                        "diff_pct": round(diff_pct, 2),
                    })
                    conn.execute("""
                        INSERT OR IGNORE INTO data_changes
                        (volcano_key, product, date, old_value, new_value, detected_at)
                        VALUES (?,?,?,?,?,?)
                    """, (vol, prod, date, db_rows[date], val, detected_at))

    conn.commit()
    conn.close()
    return changes


def main():
    print("=== Gap analysis ===")
    gaps = gap_analysis_all()
    for vol, prods in gaps.items():
        for prod, ga in prods.items():
            if ga["coverage_pct"] < 50 or ga["largest_gap_days"] > 60:
                flag = "⚠" if ga["coverage_pct"] < 30 else " "
                print(f"  {flag} {vol:22} {prod:8} "
                      f"cov={ga['coverage_pct']:5.1f}% "
                      f"gaps={ga['n_gaps']:>3} "
                      f"max_gap={ga['largest_gap_days']:>4}d")

    print()
    print("=== Drift detection ===")
    drift = detect_drift()
    print(f"  {len(drift)} valores modificados retroactivamente upstream")
    for d in drift[:10]:
        print(f"  {d['volcano']:22} {d['product']:8} {d['date'][:10]} "
              f"old={d['old_value']:.3g} new={d['new_value']:.3g} "
              f"({d['diff_pct']:.1f}%)")

    OUT_JSON.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gaps":   gaps,
        "drift":  drift,
        "summary": {
            "volcanoes_analyzed": len(VOLCANES),
            "drift_events":       len(drift),
            "products_with_low_coverage": sum(
                1 for v in gaps.values() for ga in v.values()
                if ga["coverage_pct"] < 50
            ),
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado: {OUT_JSON.name}")


if __name__ == "__main__":
    main()
