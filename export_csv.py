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
from datetime import datetime, timezone
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

COLS = ["date", "value", "detection", "unit", "product", "sensor", "image_path", "image_url"]

# No-detecciones: en SWIR (conteo de pixeles termicos) y SO2 (masa), MOUNTS
# publica un valor placeholder (~0.1) cuando no hay senal sobre el umbral. NO
# es una medicion: promediarlo contamina cualquier estadistica aguas abajo.
#
# Se conserva el valor crudo tal como lo publica MOUNTS (integridad de datos:
# no se altera el dato de origen) y se agrega la columna `detection` para que
# quien consuma el CSV pueda filtrar. En def_/coh_ no aplica: ahi un valor
# chico (8e-05 m) SI es una medicion real.
NONDETECT_TRACES = {"swir", "so2"}
NONDETECT_THRESHOLD = 0.5


def is_detection(trace_name: str, value) -> bool:
    """False si el valor representa ausencia de senal en vez de una medicion."""
    if value is None:
        return False
    if trace_name not in NONDETECT_TRACES:
        return True
    return abs(value) > NONDETECT_THRESHOLD


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
                    det = "true" if is_detection(tname, y) else "false"
                    w.writerow([x, y, det, unit, product, sensor, txt, img_url])
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
    cols = ["date", "volcano", "value", "detection", "unit", "track", "product",
            "sensor", "image_path"]

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
                    det = "true" if is_detection(tname, y) else "false"
                    rows.append([x, name, y, det, unit, track, product, sensor, txt])
        rows.sort(key=lambda r: (r[0], r[1]))   # por fecha, volcan
        out = CSV_DIR / f"{fname}.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"  {out.name:30s} ({len(rows)} filas)")


def export_events():
    """
    Marcadores tbar_* de MOUNTS. ⚠ NO son eventos eruptivos.

    Son las lineas verticales que MOUNTS dibuja en sus graficos para marcar la
    ultima observacion de cada producto (3 puntos con el mismo x, valores
    fijos 0.1/0.0 que son los minimos del eje-y, y una frecuencia que sigue el
    revisit del sensor). Se exportan por fidelidad al upstream, pero NO sirven
    como ground truth: no cruzarlos contra anomalias para medir precision.
    Ver la nota de la cabecera de db.py.
    """
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


def export_activity_json():
    """
    Un solo JSON con las dos series de actividad de los volcanes chilenos:
    anomalia termica (SWIR) y masa de SO2. Es el endpoint pensado para que
    alguien de afuera consuma los datos sin tener que juntar 14 CSVs.

    Cada punto lleva `detection`: en SWIR y SO2 un valor <=0.5 es el
    placeholder de no-deteccion de MOUNTS, no una medicion (ver
    NONDETECT_TRACES). Se conserva el valor crudo y se marca el flag, para
    que quien analice decida — promediar sin filtrar contamina la estadistica.
    """
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "mounts-project.com (Valade et al. 2019, TU Berlin / GFZ)",
        "notes": {
            "swir": ("N de pixeles termicos anomalos sobre Sentinel-2 L1C TOA "
                     "(Massimetti+ 2020). NO son watts radiantes: no es "
                     "comparable con el VRP de MIROVA."),
            "so2": ("Masa de SO2 columnar integrada en el AOI, TROPOMI perfil "
                    "PBL. El perfil PBL subestima 2-4x en volcanes andinos "
                    "altos (Lascar 5592 m, Llaima 3125 m)."),
            "detection": ("false = no-deteccion (MOUNTS publica ~0.1 como "
                          "placeholder bajo el umbral). Filtrar por "
                          "detection=true antes de promediar."),
        },
        "volcanoes": {},
    }

    for key, name, sid in VOLCANES:
        data = load_ts(key)
        entry = {"name": name, "smithsonian_id": sid, "series": {}}
        traces = {t.get("name"): t for t in (data or {}).get("traces", []) if t.get("name")}
        for tname in ("swir", "so2"):
            t = traces.get(tname)
            product, unit, sensor, desc = TRACE_MAP[tname]
            pts = []
            if t:
                xs, ys = t.get("x") or [], t.get("y") or []
                texts = t.get("text") or []
                n = min(len(xs), len(ys))
                texts = (texts + [""] * n)[:n] if texts else [""] * n
                for x, y, txt in zip(xs[:n], ys[:n], texts):
                    if y is None:
                        continue
                    pts.append({"date": x, "value": y,
                                "detection": is_detection(tname, y),
                                "image_path": txt})
            n_det = sum(1 for p in pts if p["detection"])
            entry["series"][tname] = {
                "product": product, "unit": unit, "sensor": sensor,
                "description": desc,
                "n_points": len(pts), "n_detections": n_det,
                "first_date": pts[0]["date"] if pts else None,
                "last_date":  pts[-1]["date"] if pts else None,
                "data": pts,
            }
        payload["volcanoes"][key] = entry

    out = BASE_DIR / "actividad_termica_so2.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(s["n_points"] for v in payload["volcanoes"].values()
              for s in v["series"].values())
    print(f"  {out.name:30s} ({tot} puntos, {out.stat().st_size//1024} KB)")


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
    print("JSON de actividad (termico + SO2)")
    print("-" * 60)
    export_activity_json()
    print()
    print(f"Listo. Salida en {CSV_DIR}/")


if __name__ == "__main__":
    main()
