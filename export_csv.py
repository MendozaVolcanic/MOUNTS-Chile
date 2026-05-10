"""
Exporta los timeseries de MOUNTS a CSVs estructurados.

Estilo VRP: una fila por (volcan, producto, fecha) con valor + unidad + path
imagen + flag tbar (evento de erupcion/actividad).

Salidas en csv/:
    csv/<volcan>_<producto>.csv      — un CSV por (volcan, producto)
    csv/all_thermal.csv              — SWIR S2Pix consolidado todos los volcanes
    csv/all_so2.csv                  — SO2 toneladas consolidado todos los volcanes
    csv/all_deformation.csv          — DEF asc+desc consolidado
    csv/all_coherence.csv            — COH asc+desc consolidado
    csv/events.csv                   — flags tbar_* (eventos)

Uso:
    python export_csv.py
"""

import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
TS_DIR   = BASE_DIR / "timeseries"
CSV_DIR  = BASE_DIR / "csv"
MOUNTS_BASE = "http://www.mounts-project.com/static"

VOLCANES = [
    ("lascar",             "Lascar",             355100),
    ("planchon-peteroa",   "Planchon-Peteroa",   357040),
    ("laguna-del-maule",   "Laguna del Maule",   357061),
    ("nevados-de-chillan", "Nevados de Chillan", 357070),
    ("copahue",            "Copahue",            357090),
    ("llaima",             "Llaima",             357110),
    ("villarrica",         "Villarrica",         357120),
]

# Mapeo trace_name -> (producto canonico, unidad, sensor, descripcion)
TRACE_MAP = {
    "swir":     ("thermal_swir",  "S2Pix",       "Sentinel-2",  "N pixeles termicos anomalos (Massimetti+ 2020)"),
    "so2":      ("so2_mass",      "tons",        "Sentinel-5P", "SO2 columnar integrado AOI, perfil PBL TROPOMI"),
    "def_asc":  ("def_asc",       "m_LOS",       "Sentinel-1",  "Std fase desenrollada ascendente"),
    "def_desc": ("def_desc",      "m_LOS",       "Sentinel-1",  "Std fase desenrollada descendente"),
    "coh_asc":  ("coh_asc",       "Npix_coh<0.5","Sentinel-1",  "N pixeles con coherencia <0.5 ascendente"),
    "coh_desc": ("coh_desc",      "Npix_coh<0.5","Sentinel-1",  "N pixeles con coherencia <0.5 descendente"),
    "int_asc":  ("int_asc",       "placeholder", "Sentinel-1",  "Intensidad VV ascendente (placeholder)"),
    "int_desc": ("int_desc",      "placeholder", "Sentinel-1",  "Intensidad VV descendente (placeholder)"),
}

EVENT_TRACES = {"tbar_so2", "tbar_nir", "tbar_disp", "tbar_int", "tbar_coh"}

COLS = ["date", "value", "unit", "product", "sensor", "image_path", "image_url"]


def load_ts(key):
    f = TS_DIR / f"{key}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def export_per_volcano():
    """Un CSV por (volcan, producto). 7 x 8 = 56 archivos potenciales."""
    written = 0
    for key, name, sid in VOLCANES:
        data = load_ts(key)
        if not data:
            print(f"  skip {key}: sin JSON")
            continue
        traces = {t.get("name"): t for t in data.get("traces", []) if t.get("name")}

        for tname, (product, unit, sensor, _desc) in TRACE_MAP.items():
            t = traces.get(tname)
            if not t or not t.get("y"):
                continue
            xs = t.get("x") or []
            ys = t.get("y") or []
            texts = t.get("text") or []
            # alinear longitudes
            n = min(len(xs), len(ys))
            texts = (texts + [""] * n)[:n] if texts else [""] * n

            out = CSV_DIR / f"{key}_{product}.csv"
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(COLS)
                for x, y, txt in zip(xs[:n], ys[:n], texts):
                    if y is None:
                        continue
                    img_url = f"{MOUNTS_BASE}/{txt}" if txt else ""
                    w.writerow([x, y, unit, product, sensor, txt, img_url])
            written += 1
            print(f"  {out.name:50s} ({n} filas)")
    print(f"Per-volcan/producto: {written} CSVs en {CSV_DIR}")


def export_consolidated():
    """CSVs consolidados por producto (todos los volcanes juntos)."""
    consolidations = {
        "all_thermal":      ["swir"],
        "all_so2":          ["so2"],
        "all_deformation":  ["def_asc", "def_desc"],
        "all_coherence":    ["coh_asc", "coh_desc"],
    }
    cols = ["date", "volcano", "value", "unit", "track", "product", "sensor", "image_path"]

    for fname, trace_names in consolidations.items():
        rows = []
        for key, name, sid in VOLCANES:
            data = load_ts(key)
            if not data:
                continue
            traces = {t.get("name"): t for t in data.get("traces", []) if t.get("name")}
            for tname in trace_names:
                t = traces.get(tname)
                if not t or not t.get("y"):
                    continue
                product, unit, sensor, _ = TRACE_MAP[tname]
                track = "asc" if "asc" in tname else ("desc" if "desc" in tname else "")
                xs = t.get("x") or []
                ys = t.get("y") or []
                texts = t.get("text") or []
                n = min(len(xs), len(ys))
                texts = (texts + [""] * n)[:n] if texts else [""] * n
                for x, y, txt in zip(xs[:n], ys[:n], texts):
                    if y is None:
                        continue
                    rows.append([x, name, y, unit, track, product, sensor, txt])
        rows.sort(key=lambda r: (r[0], r[1]))   # por fecha, volcan
        out = CSV_DIR / f"{fname}.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"  {out.name:30s} ({len(rows)} filas)")


def export_events():
    """Eventos tbar_* — banderas de erupcion/actividad de GVP+USGS."""
    out = CSV_DIR / "events.csv"
    cols = ["date", "volcano", "track_type", "value", "image_path", "image_url"]
    rows = []
    for key, name, sid in VOLCANES:
        data = load_ts(key)
        if not data:
            continue
        for t in data.get("traces", []):
            tname = t.get("name", "")
            if tname not in EVENT_TRACES:
                continue
            track_type = tname.replace("tbar_", "")
            xs = t.get("x") or []
            ys = t.get("y") or []
            texts = t.get("text") or []
            n = min(len(xs), len(ys))
            texts = (texts + [""] * n)[:n] if texts else [""] * n
            for x, y, txt in zip(xs[:n], ys[:n], texts):
                if y is None:
                    continue
                img_url = f"{MOUNTS_BASE}/{txt}" if txt else ""
                rows.append([x, name, track_type, y, txt, img_url])
    rows.sort(key=lambda r: (r[0], r[1]))
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print(f"  {out.name:30s} ({len(rows)} eventos)")


def main():
    CSV_DIR.mkdir(exist_ok=True)
    print("Per-volcan / producto")
    print("-" * 60)
    export_per_volcano()
    print()
    print("Consolidados")
    print("-" * 60)
    export_consolidated()
    print()
    print("Eventos (tbar_*)")
    print("-" * 60)
    export_events()
    print()
    print(f"Listo. Salida en {CSV_DIR}/")


if __name__ == "__main__":
    main()
