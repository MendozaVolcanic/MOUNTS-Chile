"""
Carga rápida de MOUNTS-Chile
-----------------------------
1. Descarga los JSONs de series temporales para todos los volcanes (7 requests).
2. Descarga las N imágenes más recientes por producto por volcán.

Mucho más rápido que el scraper completo — ideal para ver el estado actual.

Uso:
    python fetch_latest.py          # últimas 5 imágenes por producto
    python fetch_latest.py --n 10   # últimas 10
    python fetch_latest.py --only-timeseries
"""

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL  = "http://www.mounts-project.com"
STATIC    = f"{BASE_URL}/static"
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
TS_DIR    = BASE_DIR / "timeseries"
CATALOG   = BASE_DIR / "catalog.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

CHILEAN_VOLCANOES = {
    "lascar":             355100,
    "planchon-peteroa":   357040,
    "laguna-del-maule":   357061,
    "nevados-de-chillan": 357070,
    "copahue":            357090,
    "llaima":             357110,
    "villarrica":         357120,
}

PRODUCT_MAP = {
    "_B12B11B8A_nir":     ("S2_hotspot",   "Sentinel-2"),
    "_B4B3B2+B12B11B8A":  ("S2_RGB_NIR",   "Sentinel-2"),
    "_SO2_PBL":           ("S5P_SO2",      "Sentinel-5P"),
    "_VV_ifg":            ("S1_ifg",       "Sentinel-1"),
    "_VV_int_fcnn":       ("S1_intensity", "Sentinel-1"),
    "_VV_coh":            ("S1_coherence", "Sentinel-1"),
    "_VV_disp":           ("S1_disp",      "Sentinel-1"),
    "_VV_int.png":        ("S1_intensity_raw", "Sentinel-1"),
}


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    return s


def fetch_html(sess, url):
    r = sess.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def classify(path: str) -> tuple[str, str]:
    for suffix, (pt, sensor) in PRODUCT_MAP.items():
        if suffix in path:
            return pt, sensor
    return "unknown", "unknown"


def parse_ts(path: str) -> str:
    fn = path.split("/")[-1]
    m = re.search(r'(\d{8}T\d{6})', fn)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").isoformat()
        except ValueError:
            pass
    m = re.search(r'(\d{8})', fn)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    return ""


def save_timeseries(html: str, volcano: str, sid: int) -> bool:
    match = re.search(r'var\s+graph\s*=\s*(\{.+?\});\s*Plotly', html, re.DOTALL)
    if not match:
        log.warning(f"  No se encontró JSON Plotly en {volcano}")
        return False
    try:
        graph = json.loads(match.group(1))
        raw_data = graph.get("data", [])
        # MOUNTS puede anidar las trazas en una lista extra
        if raw_data and isinstance(raw_data[0], list):
            raw_data = raw_data[0]
        traces = [
            {"name": t.get("name"), "x": t.get("x", []), "y": t.get("y", []), "text": t.get("text", [])}
            for t in raw_data if isinstance(t, dict)
        ]
        out = {"volcano": volcano, "id": sid, "traces": traces,
               "fetched_at": datetime.now(timezone.utc).isoformat()}
        TS_DIR.mkdir(exist_ok=True)
        (TS_DIR / f"{volcano}.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info(f"  ✓ timeseries/{volcano}.json  ({len(traces)} trazas, {sum(len(t['x']) for t in traces)} puntos)")
        return True
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f"  Error parseando Plotly: {e}")
        return False


def download_latest(sess, html: str, volcano: str, sid: int, n: int) -> int:
    # Extraer todos los paths y clasificarlos
    all_paths = list(dict.fromkeys(re.findall(r'data_mounts/[^\s\"\'<>\\]+\.png', html)))

    # Agrupar por product_type, ordenar por timestamp desc
    by_product: dict[str, list] = {}
    for path in all_paths:
        pt, sensor = classify(path)
        ts = parse_ts(path)
        by_product.setdefault(pt, []).append((ts, path, sensor))

    for pt in by_product:
        by_product[pt].sort(key=lambda x: x[0], reverse=True)  # más recientes primero

    total = 0
    for pt, items in by_product.items():
        recent = items[:n]
        for ts, path, sensor in recent:
            parts   = path.split("/")
            year    = parts[2] if len(parts) >= 3 else "misc"
            fn      = parts[-1]
            dest    = DATA_DIR / volcano / year / fn
            img_url = f"{STATIC}/{path}"

            if dest.exists():
                log.debug(f"  skip {fn}")
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                r = sess.get(img_url, timeout=30, stream=True)
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(16384):
                        f.write(chunk)
                log.info(f"  ✓ {pt:15} {fn}")
                total += 1
                time.sleep(0.3)
            except requests.RequestException as e:
                log.warning(f"  ✗ {fn}: {e}")

    return total


def update_catalog(volcano: str, sid: int) -> None:
    """Recorre data/<volcano>/ y actualiza/crea catalog.csv con las imágenes presentes."""
    import csv

    vol_dir = DATA_DIR / volcano
    if not vol_dir.exists():
        return

    rows: dict[str, dict] = {}
    if CATALOG.exists():
        with open(CATALOG, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows[row["filename"]] = row

    for img in vol_dir.rglob("*.png"):
        fn = img.name
        if fn in rows:
            continue
        pt, sensor = classify(fn)
        ts = parse_ts(fn)
        parts = img.parts
        year = img.parent.name
        rows[fn] = {
            "volcano_name":    volcano,
            "smithsonian_id":  sid,
            "product_type":    pt,
            "sensor":          sensor,
            "image_timestamp": ts,
            "filename":        fn,
            "url":             f"{STATIC}/data_mounts/{volcano}/{year}/{fn}",
            "local_path":      str(img),
            "downloaded_at":   datetime.now(timezone.utc).isoformat(),
        }

    cols = ["volcano_name","smithsonian_id","product_type","sensor",
            "image_timestamp","filename","url","local_path","downloaded_at"]
    with open(CATALOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["volcano_name"], r["image_timestamp"])))

    log.info(f"  Catálogo actualizado: {len(rows)} registros totales")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5, help="Últimas N imágenes por producto (default: 5)")
    parser.add_argument("--only-timeseries", action="store_true", help="Solo series temporales, sin imágenes")
    parser.add_argument("--volcano", choices=list(CHILEAN_VOLCANOES.keys()) + ["all"], default="all")
    args = parser.parse_args()

    vols = CHILEAN_VOLCANOES if args.volcano == "all" else {args.volcano: CHILEAN_VOLCANOES[args.volcano]}
    sess = session()
    DATA_DIR.mkdir(exist_ok=True)

    log.info(f"Cargando {len(vols)} volcanes · últimas {args.n} imágenes/producto")

    total_imgs = 0
    for volcano, sid in vols.items():
        log.info(f"── {volcano.upper()} ({sid})")
        try:
            html = fetch_html(sess, f"{BASE_URL}/timeseries/{sid}")
        except requests.RequestException as e:
            log.error(f"  Error: {e}")
            continue

        save_timeseries(html, volcano, sid)

        if not args.only_timeseries:
            n = download_latest(sess, html, volcano, sid, args.n)
            total_imgs += n
            update_catalog(volcano, sid)

    log.info(f"Listo. {total_imgs} imágenes nuevas descargadas.")
    log.info(f"Series temporales en: {TS_DIR}")
    if not args.only_timeseries:
        log.info(f"Catálogo: {CATALOG}")
    log.info("Lanzá el dashboard con: streamlit run dashboard.py")


if __name__ == "__main__":
    main()
