"""
MOUNTS-Chile — Capa 1: Mirror de imágenes satelitales
======================================================
Extrae series temporales y descarga imágenes de los volcanes chilenos
desde mounts-project.com (Sentinel-1 InSAR, Sentinel-2 SWIR, Sentinel-5P SO₂).

Los datos de Plotly están embebidos directamente en el HTML — no se necesita
ejecución de JavaScript.

Productos por volcán:
  S2  → _B12B11B8A_nir.png   (hot-spot SWIR, ~5 días)
  S5P → _SO2_PBL.png          (SO₂ columnar, diario)
  S1  → _VV_ifg.png           (interferograma)
        _VV_int_fcnn.png       (intensidad + CNN)
        _VV_coh.png            (coherencia)

Uso:
    python scraper.py                        # todos los volcanes
    python scraper.py --volcano villarrica   # un volcán
    python scraper.py --dry-run              # muestra URLs sin descargar
    python scraper.py --years 2024 2025      # solo esos años
    python scraper.py --product s2           # solo un tipo de producto
"""

import argparse
import csv
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://www.mounts-project.com"
STATIC_URL = f"{BASE_URL}/static"
DATA_DIR = Path(__file__).parent / "data"
CATALOG_FILE = Path(__file__).parent / "catalog.csv"
TIMESERIES_DIR = Path(__file__).parent / "timeseries"

CATALOG_COLUMNS = [
    "volcano_name",
    "smithsonian_id",
    "product_type",
    "sensor",
    "image_timestamp",
    "filename",
    "url",
    "local_path",
    "downloaded_at",
]

# Volcanes chilenos en MOUNTS (actualizado 2026-04-29)
CHILEAN_VOLCANOES = {
    "lascar":             355100,
    "planchon-peteroa":   357040,
    "laguna-del-maule":   357061,
    "nevados-de-chillan": 357070,
    "copahue":            357090,   # Argentina-Chile
    "llaima":             357110,
    "villarrica":         357120,
}

# Clasificación de productos por sufijo de nombre de archivo
PRODUCT_MAP = {
    "_B12B11B8A_nir":  ("S2_hotspot",  "Sentinel-2"),
    "_B4B3B2+B12B11B8A": ("S2_RGB_NIR", "Sentinel-2"),
    "_SO2_PBL":        ("S5P_SO2",     "Sentinel-5P"),
    "_VV_ifg":         ("S1_ifg",      "Sentinel-1"),
    "_VV_int_fcnn":    ("S1_intensity","Sentinel-1"),
    "_VV_coh":         ("S1_coherence","Sentinel-1"),
    "_VV_disp":        ("S1_disp",     "Sentinel-1"),
}

PRODUCT_FILTER = {
    "s2":  ["S2_hotspot", "S2_RGB_NIR"],
    "s5p": ["S5P_SO2"],
    "s1":  ["S1_ifg", "S1_intensity", "S1_coherence", "S1_disp"],
    "all": None,
}

REQUEST_DELAY = 0.5  # segundos entre requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────────

def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    })
    return s


def check_connectivity(session: requests.Session) -> bool:
    try:
        r = session.get(f"{BASE_URL}/home", timeout=10)
        return r.status_code < 500
    except requests.RequestException:
        return False


def fetch_page(session: requests.Session, url: str, retries: int = 3) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            log.warning(f"Intento {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(REQUEST_DELAY * attempt * 2)
    return None


def download_image(session: requests.Session, url: str, dest: Path, retries: int = 3) -> bool:
    if dest.exists():
        log.debug(f"Skip (existe): {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=60, stream=True)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=16384):
                    f.write(chunk)
            return True
        except requests.RequestException as e:
            log.warning(f"Error descarga {dest.name}: {e}")
            if attempt < retries:
                time.sleep(REQUEST_DELAY * attempt)
    return False


def classify_product(path: str) -> tuple[str, str]:
    """Devuelve (product_type, sensor) según el nombre del archivo."""
    for suffix, (ptype, sensor) in PRODUCT_MAP.items():
        if suffix in path:
            return ptype, sensor
    return "unknown", "unknown"


def parse_timestamp(path: str) -> str:
    """Extrae timestamp ISO del nombre de archivo."""
    filename = path.split("/")[-1]
    # Patrón: YYYYMMDDTHHMMSS o YYYYMMDD
    m = re.search(r'(\d{8}T\d{6})', filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").isoformat()
        except ValueError:
            pass
    m = re.search(r'(\d{8})', filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    return ""


# ─── Extracción ─────────────────────────────────────────────────────────────

def extract_image_paths(html: str) -> list[str]:
    """
    Los paths data_mounts están embebidos directamente en el HTML
    como strings en el JSON de Plotly. Los extraemos con regex.
    """
    paths = re.findall(r'data_mounts/[^\s\"\'<>\\]+\.png', html)
    # Deduplicar manteniendo orden
    seen = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def extract_timeseries_json(html: str, volcano_name: str, smithsonian_id: int) -> dict:
    """
    Extrae el JSON de Plotly (var graph = {...}) para guardar las
    series temporales numéricas además de las imágenes.
    """
    # Buscar el bloque var graph = { ... };
    match = re.search(r'var\s+graph\s*=\s*(\{.+?\});\s*Plotly', html, re.DOTALL)
    if not match:
        return {}
    try:
        graph = json.loads(match.group(1))
        # Simplificar: solo x, y, name, text por traza
        traces = []
        for trace in graph.get("data", []):
            traces.append({
                "name":  trace.get("name"),
                "x":     trace.get("x", []),
                "y":     trace.get("y", []),
                "text":  trace.get("text", []),
            })
        return {
            "volcano": volcano_name,
            "id":      smithsonian_id,
            "traces":  traces,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f"No se pudo parsear JSON Plotly: {e}")
        return {}


# ─── Core ───────────────────────────────────────────────────────────────────

def load_catalog() -> dict[str, dict]:
    catalog = {}
    if not CATALOG_FILE.exists():
        return catalog
    with open(CATALOG_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            catalog[row["filename"]] = row
    return catalog


def save_catalog(catalog: dict[str, dict]) -> None:
    with open(CATALOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOG_COLUMNS)
        writer.writeheader()
        writer.writerows(
            sorted(catalog.values(), key=lambda r: (r["volcano_name"], r["image_timestamp"]))
        )
    log.info(f"Catálogo: {CATALOG_FILE.name} ({len(catalog)} registros)")


def scrape_volcano(
    session: requests.Session,
    name: str,
    sid: int,
    dry_run: bool,
    years_filter: list[str] | None,
    product_filter: list[str] | None,
    catalog: dict[str, dict],
    save_timeseries: bool,
) -> int:
    url = f"{BASE_URL}/timeseries/{sid}"
    log.info(f"── {name.upper()} ({sid})")

    html = fetch_page(session, url)
    if html is None:
        log.error(f"  No se pudo obtener {url}")
        return 0

    # Guardar JSON de series temporales
    if save_timeseries and not dry_run:
        ts_data = extract_timeseries_json(html, name, sid)
        if ts_data:
            TIMESERIES_DIR.mkdir(exist_ok=True)
            ts_file = TIMESERIES_DIR / f"{name}.json"
            ts_file.write_text(json.dumps(ts_data, indent=2, ensure_ascii=False), encoding="utf-8")
            log.info(f"  Timeseries guardada: {ts_file.name} ({len(ts_data['traces'])} trazas)")

    # Extraer paths de imágenes
    all_paths = extract_image_paths(html)
    log.info(f"  {len(all_paths)} imágenes únicas en HTML")

    # Filtros
    filtered = all_paths
    if years_filter:
        filtered = [p for p in filtered if any(yr in p for yr in years_filter)]
    if product_filter:
        filtered = [p for p in filtered if classify_product(p)[0] in product_filter]

    if years_filter or product_filter:
        log.info(f"  → {len(filtered)} tras filtros (años={years_filter}, producto={product_filter})")

    downloaded = 0
    skipped = 0

    for path in filtered:
        filename = path.split("/")[-1]
        img_url  = f"{STATIC_URL}/{path}"

        # Año desde la ruta  (data_mounts/<volcan>/<YYYY>/...)
        parts   = path.split("/")
        year    = parts[2] if len(parts) >= 3 else "misc"
        local   = DATA_DIR / name / year / filename
        ptype, sensor = classify_product(path)
        ts      = parse_timestamp(path)

        if dry_run:
            log.info(f"  [DRY] {ptype:15} {filename}")
            continue

        if local.exists():
            skipped += 1
            # Actualizar catálogo igual si no existe
            if filename not in catalog:
                catalog[filename] = {
                    "volcano_name":    name,
                    "smithsonian_id":  sid,
                    "product_type":    ptype,
                    "sensor":          sensor,
                    "image_timestamp": ts,
                    "filename":        filename,
                    "url":             img_url,
                    "local_path":      str(local),
                    "downloaded_at":   "pre-existing",
                }
            continue

        ok = download_image(session, img_url, local)
        time.sleep(REQUEST_DELAY)

        if ok:
            catalog[filename] = {
                "volcano_name":    name,
                "smithsonian_id":  sid,
                "product_type":    ptype,
                "sensor":          sensor,
                "image_timestamp": ts,
                "filename":        filename,
                "url":             img_url,
                "local_path":      str(local),
                "downloaded_at":   datetime.now(timezone.utc).isoformat(),
            }
            downloaded += 1

    if not dry_run:
        log.info(f"  ✓ {downloaded} nuevas | {skipped} ya existían")
    return downloaded


# ─── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Mirror MOUNTS volcanes chilenos")
    parser.add_argument(
        "--volcano", choices=list(CHILEAN_VOLCANOES.keys()) + ["all"],
        default="all", help="Volcán específico o 'all' (default)"
    )
    parser.add_argument(
        "--years", nargs="+", metavar="YYYY",
        help="Filtrar por año(s), ej: --years 2024 2025"
    )
    parser.add_argument(
        "--product", choices=["s1", "s2", "s5p", "all"],
        default="all", help="Filtrar por sensor (default: all)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostrar sin descargar"
    )
    parser.add_argument(
        "--no-timeseries", action="store_true",
        help="No guardar JSON de series temporales"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Logging detallado"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    volcanoes = (
        CHILEAN_VOLCANOES if args.volcano == "all"
        else {args.volcano: CHILEAN_VOLCANOES[args.volcano]}
    )
    product_filter = PRODUCT_FILTER.get(args.product)  # None = sin filtro

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog()
    session = get_session()

    if not args.dry_run:
        log.info("Verificando conectividad…")
        if not check_connectivity(session):
            log.error(f"No se puede conectar a {BASE_URL}. Verificá conexión.")
            raise SystemExit(1)

    log.info(f"Volcanes: {len(volcanoes)} | Producto: {args.product} | Años: {args.years or 'todos'}")
    total = 0

    for name, sid in volcanoes.items():
        n = scrape_volcano(
            session, name, sid,
            dry_run=args.dry_run,
            years_filter=args.years,
            product_filter=product_filter,
            catalog=catalog,
            save_timeseries=not args.no_timeseries,
        )
        total += n

    if not args.dry_run and total > 0:
        save_catalog(catalog)

    log.info(f"{'[DRY-RUN] ' if args.dry_run else ''}Total: {total} imágenes nuevas.")


if __name__ == "__main__":
    main()
