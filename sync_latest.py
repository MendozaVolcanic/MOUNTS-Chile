"""
Sincroniza latest/<volcan>/ con la imagen mas reciente de cada producto.

Lee los timeseries JSONs y para cada (volcan, producto) busca la imagen mas
reciente en data/ y la copia a latest/ con paths estables para servir desde
GitHub Pages.

Productos cubiertos: ver IMG_PRODUCTS.

Uso:
    python sync_latest.py
"""

import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent
TS_DIR   = BASE_DIR / "timeseries"
DATA_DIR = BASE_DIR / "data"
LATEST   = BASE_DIR / "latest"

VOLCANES = [
    "lascar", "planchon-peteroa", "laguna-del-maule",
    "nevados-de-chillan", "copahue", "llaima", "villarrica",
]

IMG_PRODUCTS = [
    "_B4B3B2+B12B11B8A",   # RGB visible
    "_SO2_PBL",
    "_B12B11B8A_nir",
    "_VV_disp",
    "_VV_int_fcnn",
    "_VV_coh",
    "_VV_int.png",         # raw VV intensity (sin CNN)
]


def get_latest_per_product(volcano: str) -> dict:
    """De los traces.text, encontra la imagen mas reciente por sufijo de producto."""
    f = TS_DIR / f"{volcano}.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))

    # Recopilar (fecha, path) de todos los text arrays
    all_items = []
    for t in data.get("traces", []):
        texts = t.get("text") or []
        xs = t.get("x") or []
        for path, x in zip(texts, xs):
            if path:
                all_items.append((x or "", path))
    all_items.sort(key=lambda t: t[0], reverse=True)

    found = {}
    for date, path in all_items:
        fn = path.split("/")[-1]
        for suffix in IMG_PRODUCTS:
            # _VV_int.png hay que matchear ANTES que _VV_int_fcnn para evitar
            # match incorrecto: _VV_int es subset de _VV_int_fcnn
            if suffix == "_VV_int.png":
                if "_VV_int." in fn and "_fcnn" not in fn:
                    if suffix not in found:
                        found[suffix] = (date, fn, path)
            else:
                if suffix in path and suffix not in found:
                    found[suffix] = (date, fn, path)
        if len(found) == len(IMG_PRODUCTS):
            break
    return found


def sync_volcano(volcano: str) -> int:
    latest_imgs = get_latest_per_product(volcano)
    vol_latest = LATEST / volcano
    vol_latest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for suffix, (date, fn, path) in latest_imgs.items():
        # Buscar el archivo en data/
        src = None
        for p in DATA_DIR.rglob(fn):
            src = p
            break
        if src and src.exists():
            dst = vol_latest / fn
            if not dst.exists():
                shutil.copy2(src, dst)
                copied += 1
                print(f"  + {volcano}/{fn}")
    return copied


def main():
    LATEST.mkdir(exist_ok=True)
    total = 0
    for v in VOLCANES:
        n = sync_volcano(v)
        total += n
        if n == 0:
            print(f"  · {v}: ya sincronizado")
    print(f"\nCopiadas {total} imagenes nuevas a latest/")


if __name__ == "__main__":
    main()
