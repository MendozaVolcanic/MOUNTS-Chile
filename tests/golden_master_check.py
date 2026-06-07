"""
Characterization test (golden master) para el refactor C2 de generar_html.py.

POR QUE ESTE SCRIPT EXISTE
--------------------------
El refactor descompone generar_html.py (monolito) en el paquete dashboard/.
La garantia que queremos es: el HTML renderizado NO cambia. La forma de
probarlo sin tests unitarios previos es un "golden master": generar el output
con el codigo viejo, generarlo con el codigo nuevo, y exigir que sean iguales.

EL PROBLEMA DEL NO-DETERMINISMO
-------------------------------
El output NO es byte-identico entre dos corridas cualesquiera, ni siquiera sin
refactor, porque el codigo (viejo y nuevo) inyecta:
  1. timestamp "generated"  -> "%Y-%m-%d %H:%M UTC"   (cambia cada minuto)
  2. timestamp "today" en cada chart -> "%Y-%m-%dT%H:%M:%S" (cambia cada seg)
  3. Folium genera UUIDs aleatorios en map.html y en su iframe.
Por eso comparamos tras NORMALIZAR esas tres fuentes. Si lo demas es identico,
el refactor preserva el render.

COMO FUNCIONA
-------------
1. Extrae la version original de generar_html.py desde git (HEAD) a un dir temp
   que reusa los datos del repo (timeseries/, *.json, mounts.db, latest/).
2. Genera el golden (index.html + map.html) con el codigo original.
3. Genera el output nuevo con el codigo refactorizado (import del paquete).
4. Normaliza timestamps + UUIDs en ambos y compara byte a byte.

Uso:
    python tests/golden_master_check.py

Sale 0 si el output normalizado es identico; 1 si difiere (imprime el diff).
"""

import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------------
# Normalizacion: enmascara las fuentes de no-determinismo conocidas
# ----------------------------------------------------------------------------
def normalize(html: str) -> str:
    # 1. timestamp "generated" -> <span class="meta">YYYY-MM-DD HH:MM UTC</span>
    html = re.sub(
        r'(<span class="meta">)\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC(</span>)',
        r"\1<GENERATED>\2", html,
    )
    # 2. timestamps "today" en los charts: 'YYYY-MM-DDTHH:MM:SS'
    html = re.sub(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
        "<TODAY>", html,
    )
    # 3. Folium: UUIDs hex de 32 chars (map_<hex>, etc.) y los ids derivados
    html = re.sub(r"[0-9a-f]{32}", "<UUID>", html)
    return html


def gen_original(workdir: Path) -> tuple[str, str]:
    """Genera index.html/map.html con el generar_html.py de HEAD."""
    original_src = subprocess.check_output(
        ["git", "show", "HEAD:generar_html.py"], cwd=str(ROOT),
        text=True, encoding="utf-8",
    )
    # El original usa Path(__file__).parent como raiz de datos; lo dejamos en
    # ROOT para que vea timeseries/, *.json, mounts.db, latest/ reales.
    tmp = ROOT / "_golden_original_tmp.py"
    tmp.write_text(original_src, encoding="utf-8")
    try:
        subprocess.check_call([sys.executable, str(tmp)], cwd=str(ROOT))
        idx = (ROOT / "index.html").read_text(encoding="utf-8")
        mp = (ROOT / "map.html").read_text(encoding="utf-8")
        return idx, mp
    finally:
        tmp.unlink(missing_ok=True)


def gen_refactored() -> tuple[str, str]:
    """Genera index.html/map.html con el codigo refactorizado (paquete)."""
    subprocess.check_call(
        [sys.executable, str(ROOT / "generar_html.py")], cwd=str(ROOT),
    )
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    mp = (ROOT / "map.html").read_text(encoding="utf-8")
    return idx, mp


def main() -> int:
    print("== Golden master: generando con codigo ORIGINAL (HEAD) ==")
    g_idx, g_map = gen_original(ROOT)
    print("== Golden master: generando con codigo REFACTORIZADO ==")
    n_idx, n_map = gen_refactored()

    ok = True
    for label, golden, new in [("index.html", g_idx, n_idx),
                               ("map.html", g_map, n_map)]:
        gn = normalize(golden)
        nn = normalize(new)
        if gn == nn:
            print(f"  [OK] {label}: identico tras normalizar timestamps/UUIDs")
        else:
            ok = False
            print(f"  [DIFF] {label}: difiere. Primeras lineas:")
            diff = difflib.unified_diff(
                gn.splitlines(), nn.splitlines(),
                fromfile=f"golden/{label}", tofile=f"refactor/{label}",
                lineterm="", n=2,
            )
            for i, line in enumerate(diff):
                if i > 60:
                    print("    ... (truncado)")
                    break
                print("   ", line)

    print("\nRESULTADO:", "PASS (output preservado)" if ok else "FAIL (revisar diff)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
