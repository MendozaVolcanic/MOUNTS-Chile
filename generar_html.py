"""
Genera latest.html — replica el layout de MOUNTS con las graficas y las
imagenes mas recientes para los 7 volcanes chilenos.
Todo embebido en un HTML estatico (no requiere servidor).

Las imagenes se sirven desde latest/<volcan>/ (paths relativos, funciona en
GitHub Pages sin problemas de mixed-content).

Refactor C2: la logica de armado vive en el paquete dashboard/. Este archivo
es solo el orquestador: carga datos, pide cada fragmento a su modulo, ensambla
con la plantilla y escribe los HTML. El output es identico al de la version
monolitica previa. El entrypoint (`python generar_html.py`) no cambia.
"""

from datetime import datetime, timezone
from pathlib import Path

from dashboard.config import OUT, VOLCANES
from dashboard.status import load_status, load_alerts, build_status_matrix, build_bulletin
from dashboard.sections import (
    build_section, build_alerts_panel, build_multi_alerts_panel,
    build_history_panel, build_upstream_status_panel,
)
from dashboard.charts import build_streamgraph
from dashboard.map import build_map
from dashboard.template import render_page


def main():
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nav = " &middot; ".join(
        f'<a href="#v-{k}">{n}</a>' for k, n, _ in VOLCANES
    )
    status = load_status()
    alerts = load_alerts()
    status_html = build_status_matrix(status)
    bulletin_html = build_bulletin(status)
    upstream_html = build_upstream_status_panel()
    alerts_html = build_alerts_panel(alerts)
    history_html = build_history_panel(top_n=20)
    multi_html = build_multi_alerts_panel(top_n=15)
    stream_so2 = build_streamgraph("so2", "SO2 multi-volcán", "tons")
    stream_swir = build_streamgraph("swir", "Térmico SWIR multi-volcán", "S2Pix")
    map_html = build_map(status)
    sections = "\n".join(build_section(k, n, s) for k, n, s in VOLCANES)

    html = render_page(
        generated, nav, status_html, bulletin_html, upstream_html,
        alerts_html, multi_html, history_html, stream_so2, stream_swir,
        map_html, sections,
    )

    OUT.write_text(html, encoding="utf-8")
    # Tambien sobreescribir index.html para GitHub Pages
    index = Path(__file__).parent / "index.html"
    index.write_text(html, encoding="utf-8")
    size_kb = OUT.stat().st_size // 1024
    print(f"Generado: {OUT}  ({size_kb} KB)")
    print(f"GitHub Pages: https://mendozavolcanic.github.io/MOUNTS-Chile/")


if __name__ == "__main__":
    main()
