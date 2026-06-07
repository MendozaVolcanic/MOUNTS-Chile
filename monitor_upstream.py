"""
Monitorea cambios en mounts-project.com upstream:

1. /news        — changelog manual. Si cambia, MOUNTS publico un cambio de
                  calibracion (baseline S2, ATBD, etc) que puede invalidar
                  series previas. Critico para integridad cientifica.

2. /about       — metodologia, citacion, papers. Si cambia, actualizar README.

3. /targets     — lista de 100 volcanes. Si aparece un nuevo volcan chileno,
                  alerta para extender el scraper.

4. Schema timeseries — validar que el JSON Plotly mantiene las 13 trazas
                  esperadas. Si MOUNTS rename/quita una traza, fallar fuerte.

5. HTML raw     — guardar copia comprimida de cada fetch en raw/<volcan>/
                  para reproducibilidad total.

Salidas:
  upstream_state.json   estado actual (hashes, citation, lista volcanes)
  upstream_changes.json log de cambios detectados
  raw/<volcan>/<fecha>.html.gz versionado del HTML extraido
  raw/news_<fecha>.html.gz cambios documentados

Uso:
    python monitor_upstream.py
    python monitor_upstream.py --skip-archive   # no versiona HTMLs (solo monitor)
"""

import argparse
import gzip
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "http://www.mounts-project.com"
BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
STATE_FILE = BASE_DIR / "upstream_state.json"
CHANGES_FILE = BASE_DIR / "upstream_changes.json"

USER_AGENT = (
    "MOUNTS-Chile-Mirror/1.0 "
    "(+https://github.com/MendozaVolcanic/MOUNTS-Chile) "
    "(contact: SERNAGEOMIN-OVDAS)"
)

CHILEAN_VOLCANOES = {
    "lascar":             355100,
    "planchon-peteroa":   357040,
    "laguna-del-maule":   357061,
    "nevados-de-chillan": 357070,
    "copahue":            357090,
    "llaima":             357110,
    "villarrica":         357120,
}

# Trazas esperadas en cada timeseries (schema validation)
EXPECTED_TRACES = {
    "swir", "so2",
    "def_asc", "def_desc",
    "coh_asc", "coh_desc",
    "int_asc", "int_desc",
    "tbar_nir", "tbar_so2", "tbar_disp", "tbar_int", "tbar_coh",
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html,application/xhtml+xml",
    })
    return s


def fetch(sess, url):
    r = sess.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def content_hash(text: str) -> str:
    """SHA-256 del contenido normalizado (sin whitespace ni timestamps)."""
    # Quitar timestamps generados por el server (fechas comunes)
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}T?\d{0,2}:?\d{0,2}:?\d{0,2}', '', text)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def archive_html(text: str, name: str) -> Path:
    """Comprime y guarda HTML en raw/."""
    RAW_DIR.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = RAW_DIR / f"{name}_{today}.html.gz"
    if not out.exists():
        out.write_bytes(gzip.compress(text.encode("utf-8")))
    return out


def extract_citation(about_html: str) -> dict:
    """Saca papers/DOIs/contacto del HTML /about."""
    # DOIs
    dois = list(set(re.findall(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', about_html, re.I)))
    # Email contacto
    emails = list(set(re.findall(r'[\w._%-]+@[\w.-]+\.[a-z]{2,}', about_html, re.I)))
    # Anio del paper mas reciente
    years = re.findall(r'\b(20\d{2})\b', about_html)
    return {
        "dois": sorted(dois)[:5],
        "contacts": [e for e in emails if "mounts" in e.lower() or "valade" in e.lower()][:3],
        "max_year": max(years) if years else None,
    }


def extract_target_volcanoes(targets_html: str) -> list:
    """Lista los volcanes en /targets. Devuelve [(id, name, country_code), ...]."""
    # Patron real: link a /timeseries/<id> con nombre + flag-icon-<cc> en la siguiente cell
    pattern = re.compile(
        r'/timeseries/(\d+)["\'][^>]*>\s*([^<]+?)\s*</a>.{0,500}?flag-icon-(\w+)',
        re.DOTALL
    )
    return [(int(m.group(1)), m.group(2).strip(), m.group(3).lower())
            for m in pattern.finditer(targets_html)]


def validate_timeseries_schema(html: str, volcano: str) -> dict:
    """Verifica que el JSON Plotly mantenga las trazas esperadas."""
    match = re.search(r'var\s+graph\s*=\s*(\{.+?\});\s*Plotly', html, re.DOTALL)
    if not match:
        return {"valid": False, "reason": "No var graph found"}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        return {"valid": False, "reason": f"JSON parse: {e}"}

    raw = data.get("data", [])
    if raw and isinstance(raw[0], list):
        raw = raw[0]
    trace_names = {t.get("name") for t in raw if isinstance(t, dict)}
    missing = EXPECTED_TRACES - trace_names
    new = trace_names - EXPECTED_TRACES
    return {
        "valid": not missing and not new,
        "n_traces": len(trace_names),
        "missing": sorted(missing),
        "new": sorted(new),
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def append_change(change: dict):
    """Agrega entrada al log de cambios."""
    changes = []
    if CHANGES_FILE.exists():
        try:
            changes = json.loads(CHANGES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    change["detected_at"] = datetime.now(timezone.utc).isoformat()
    changes.append(change)
    CHANGES_FILE.write_text(json.dumps(changes, indent=2, ensure_ascii=False),
                            encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-archive", action="store_true",
                        help="No guardar HTMLs comprimidos en raw/")
    args = parser.parse_args()

    sess = get_session()
    state = load_state()
    new_state = {"checked_at": datetime.now(timezone.utc).isoformat()}
    changes_detected = 0

    # 1. /news — changelog upstream
    log.info("Checking /news...")
    try:
        news = fetch(sess, f"{BASE}/news")
        h = content_hash(news)
        new_state["news_hash"] = h
        old_h = state.get("news_hash")
        if old_h and old_h != h:
            log.warning(f"  ⚠ /news CAMBIO. hash {old_h} -> {h}")
            archive_html(news, "news")
            append_change({"page": "/news", "old_hash": old_h, "new_hash": h,
                          "severity": "high"})
            changes_detected += 1
        elif old_h is None:
            log.info("  Primer fetch /news (baseline establecido)")
            if not args.skip_archive:
                archive_html(news, "news")
        else:
            log.info(f"  /news sin cambios (hash {h})")
    except Exception as e:
        log.error(f"  /news fail: {e}")

    # 2. /about — citacion
    log.info("Checking /about...")
    try:
        about = fetch(sess, f"{BASE}/about")
        h = content_hash(about)
        new_state["about_hash"] = h
        citation = extract_citation(about)
        new_state["citation"] = citation
        if state.get("about_hash") and state["about_hash"] != h:
            log.warning(f"  ⚠ /about CAMBIO")
            archive_html(about, "about")
            append_change({"page": "/about", "old_hash": state["about_hash"],
                          "new_hash": h, "citation": citation, "severity": "medium"})
            changes_detected += 1
        log.info(f"  citation: {citation['dois'][:2]} contacto={citation['contacts']}")
    except Exception as e:
        log.error(f"  /about fail: {e}")

    # 3. /targets — volcanes monitoreados
    log.info("Checking /targets...")
    try:
        targets = fetch(sess, f"{BASE}/targets")
        vols = extract_target_volcanoes(targets)
        new_state["n_volcanoes_global"] = len(vols)
        chileans_in_mounts = [v for v in vols if v[2] == "cl"]
        new_state["chilean_volcanoes_in_mounts"] = chileans_in_mounts
        log.info(f"  {len(vols)} volcanes globales, {len(chileans_in_mounts)} chilenos en MOUNTS")
        # Detectar nuevo volcan chileno
        old_cl = {v[0] for v in (state.get("chilean_volcanoes_in_mounts") or [])}
        new_cl = {v[0] for v in chileans_in_mounts}
        added = new_cl - old_cl
        if added:
            log.warning(f"  ⚠ Nuevo(s) volcan(es) chileno(s) en MOUNTS: {added}")
            append_change({"page": "/targets", "new_chilean_volcanoes": list(added),
                          "severity": "high"})
            changes_detected += 1
    except Exception as e:
        log.error(f"  /targets fail: {e}")

    # 4. Schema validation timeseries
    log.info("Validating timeseries schemas...")
    schemas = {}
    for vol, sid in CHILEAN_VOLCANOES.items():
        try:
            html = fetch(sess, f"{BASE}/timeseries/{sid}")
            result = validate_timeseries_schema(html, vol)
            schemas[vol] = result
            if not result["valid"] and vol != "laguna-del-maule":  # LDM siempre vacio
                if result.get("missing"):
                    log.warning(f"  ⚠ {vol}: trazas faltantes {result['missing']}")
                if result.get("new"):
                    log.warning(f"  ⚠ {vol}: trazas NUEVAS {result['new']}")
                append_change({
                    "page": f"/timeseries/{sid}",
                    "volcano": vol,
                    "schema_issue": result,
                    "severity": "high",
                })
                changes_detected += 1
            # archive HTML raw
            if not args.skip_archive:
                archive_html(html, f"timeseries_{vol}")
        except Exception as e:
            log.error(f"  {vol} fail: {e}")
            schemas[vol] = {"valid": False, "reason": str(e)}
    new_state["schemas"] = schemas

    save_state(new_state)

    log.info("")
    log.info(f"Estado guardado en {STATE_FILE.name}")
    log.info(f"Cambios detectados este run: {changes_detected}")
    if changes_detected:
        log.info(f"Detalles en {CHANGES_FILE.name}")


if __name__ == "__main__":
    main()
