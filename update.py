"""
Pipeline completo de actualizacion MOUNTS-Chile.

Ejecuta en orden:
  1. fetch_latest.py    — bajar JSONs + imagenes recientes
  2. anomalies.py       — calcular status y alertas
  3. image_diff.py      — generar diff antes/despues SWIR
  4. export_csv.py      — exportar a CSVs
  5. generar_html.py    — regenerar index.html con todo

Uso:
    python update.py
    python update.py --skip-fetch     # si ya bajaste, solo regenerar
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent

STEPS = [
    ("fetch_latest.py", "Descargar timeseries + imagenes",   True),
    ("anomalies.py",    "Calcular status y alertas",         False),
    ("image_diff.py",   "Generar imagen diffs",              False),
    ("export_csv.py",   "Exportar CSVs",                     False),
    ("generar_html.py", "Regenerar dashboard HTML",          False),
]


def run_step(script: str, description: str, skip: bool = False) -> bool:
    print(f"\n{'='*60}")
    print(f"[{description}]  python {script}")
    print('='*60)
    if skip:
        print("  (skipped)")
        return True
    t0 = time.time()
    r = subprocess.run([sys.executable, str(BASE / script)], cwd=str(BASE))
    dt = time.time() - t0
    if r.returncode != 0:
        print(f"  FAIL ({dt:.1f}s)")
        return False
    print(f"  OK ({dt:.1f}s)")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Saltar fetch_latest.py (usar JSONs/imagenes existentes)")
    args = parser.parse_args()

    print(f"MOUNTS-Chile pipeline · {Path.cwd()}")

    t0 = time.time()
    for script, desc, is_fetch in STEPS:
        skip = args.skip_fetch and is_fetch
        if not run_step(script, desc, skip):
            print(f"\nABORT: fallo {script}")
            sys.exit(1)

    dt = time.time() - t0
    print(f"\n{'='*60}\nTotal: {dt:.1f}s")
    print(f"\nProximo: git add . && git commit -m 'update' && git push")


if __name__ == "__main__":
    main()
