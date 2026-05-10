"""
Genera imagenes diff antes/despues para SWIR.

Para cada volcan, busca las 2 imagenes SWIR (_B12B11B8A_nir) mas recientes en
data/, computa la diferencia absoluta y guarda un PNG en latest/<vol>/diff/.
Tambien copia las 2 originales a latest/<vol>/diff/ para slider antes/despues.

Uso:
    python image_diff.py
"""

import shutil
from pathlib import Path

import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LATEST   = BASE_DIR / "latest"

VOLCANES = ["lascar", "planchon-peteroa", "laguna-del-maule",
            "nevados-de-chillan", "copahue", "llaima", "villarrica"]

PRODUCT_SUFFIX = "_B12B11B8A_nir"   # solo SWIR — donde mas valor tiene el diff


def get_latest_two(vol_dir: Path, suffix: str):
    """Devuelve las 2 imagenes mas recientes (por nombre, que tiene timestamp)."""
    if not vol_dir.exists():
        return []
    pngs = sorted(vol_dir.rglob(f"*{suffix}*.png"), reverse=True)
    return pngs[:2]


def compute_diff(img_new: Path, img_old: Path, out: Path):
    """
    |new - old| pixel-wise. Si las imagenes tienen distinto tamano, redimensiona
    la vieja a tamano de la nueva. Resalta cambios.
    """
    a = np.array(Image.open(img_new).convert("RGB"), dtype=np.int16)
    b_img = Image.open(img_old).convert("RGB")
    if b_img.size != (a.shape[1], a.shape[0]):
        b_img = b_img.resize((a.shape[1], a.shape[0]), Image.BILINEAR)
    b = np.array(b_img, dtype=np.int16)

    diff = np.abs(a - b)
    # Escalar para resaltar: cambios pequenos -> visibles
    # Usar percentil 95 como max para evitar saturar con 1 pixel ruidoso
    p95 = np.percentile(diff, 95)
    if p95 < 5:
        p95 = 5
    diff_scaled = np.clip(diff * (255.0 / p95), 0, 255).astype(np.uint8)

    # Componer: rojo donde el cambio es alto (canal R amplificado)
    composite = np.zeros_like(diff_scaled)
    intensity = diff_scaled.mean(axis=2).astype(np.uint8)
    composite[..., 0] = intensity         # R
    composite[..., 1] = intensity // 4    # G (mas oscuro)
    composite[..., 2] = intensity // 8    # B

    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(composite).save(out, "PNG", optimize=True)


def process_volcano(key: str) -> dict | None:
    vol_dir = DATA_DIR / key
    imgs = get_latest_two(vol_dir, PRODUCT_SUFFIX)
    if len(imgs) < 2:
        return None

    new_img, old_img = imgs[0], imgs[1]
    diff_dir = LATEST / key / "diff"
    diff_dir.mkdir(parents=True, exist_ok=True)

    # Copiar nuevas y viejas
    new_dst = diff_dir / f"new_{new_img.name}"
    old_dst = diff_dir / f"old_{old_img.name}"
    diff_dst = diff_dir / "diff.png"

    shutil.copy2(new_img, new_dst)
    shutil.copy2(old_img, old_dst)
    compute_diff(new_img, old_img, diff_dst)

    return {
        "new":  new_dst.relative_to(BASE_DIR).as_posix(),
        "old":  old_dst.relative_to(BASE_DIR).as_posix(),
        "diff": diff_dst.relative_to(BASE_DIR).as_posix(),
        "new_date": new_img.name.split("_")[1][:8] if "_" in new_img.name else "",
        "old_date": old_img.name.split("_")[1][:8] if "_" in old_img.name else "",
    }


def main():
    import json
    results = {}
    for key in VOLCANES:
        res = process_volcano(key)
        if res:
            results[key] = res
            print(f"  {key:22s} new={res['new_date']} old={res['old_date']} OK")
        else:
            print(f"  {key:22s} (sin par de imagenes)")
    out = BASE_DIR / "diffs.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n{len(results)}/{len(VOLCANES)} volcanes con diff generado.")
    print(f"Indice: {out}")


if __name__ == "__main__":
    main()
