"""
Plantilla HTML base + CSS del dashboard MOUNTS-Chile.

render_page() recibe los fragmentos ya construidos por los demas modulos
(status, charts, sections, map) y los ensambla en el documento final, con
el <head>, los estilos y el script del filtro temporal.

Extraido de generar_html.py (refactor C2): es el mismo f-string base, solo
reubicado. No introduce Jinja2 ni cambia el markup.
"""

from .config import esc


def render_page(generated, nav, status_html, bulletin_html, upstream_html,
                alerts_html, multi_html, history_html, stream_so2, stream_swir,
                map_html, sections):
    """Ensambla el documento HTML completo a partir de los fragmentos."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MOUNTS-Chile</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;font-size:13px}}
a{{color:#58a6ff;text-decoration:none}}
a:hover{{text-decoration:underline}}

.topbar{{background:#161b22;border-bottom:1px solid #30363d;padding:9px 14px;
         position:sticky;top:0;z-index:100;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.topbar h1{{font-size:.95rem;color:#f0f6fc;white-space:nowrap;font-weight:600}}
.topbar .nav{{font-size:.72rem;color:#8b949e;flex:1}}
.topbar .nav a{{color:#58a6ff}}
.topbar .meta{{font-size:.68rem;color:#6e7681}}
.upd{{font-size:.7rem;padding:3px 9px;background:#21262d;border:1px solid #30363d;
      border-radius:5px;cursor:pointer;color:#58a6ff}}
.upd:hover{{background:#30363d}}
.time-filter{{display:flex;gap:3px;align-items:center}}
.time-filter button{{font-size:.7rem;padding:3px 8px;background:#21262d;
                     border:1px solid #30363d;border-radius:4px;color:#8b949e;cursor:pointer}}
.time-filter button:hover{{background:#30363d;color:#e6edf3}}
.time-filter button.active{{background:#1f6feb;color:#fff;border-color:#1f6feb}}

.vsec{{border-bottom:2px solid #21262d;padding:12px 14px}}
.vhdr{{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}}
.vname{{font-size:1.05rem;font-weight:700;color:#e2a44a}}
.vmeta{{font-size:.7rem;color:#6e7681}}
.vlink{{font-size:.7rem;padding:2px 7px;border:1px solid #30363d;border-radius:4px;
        background:#1c2128;margin-left:auto}}

.vcontent{{display:grid;grid-template-columns:190px 1fr;gap:10px;align-items:start}}
@media(max-width:800px){{.vcontent{{grid-template-columns:1fr}}}}

.vimgs{{display:flex;flex-direction:column;gap:6px}}
.ic{{display:flex;flex-direction:column;align-items:center}}
.il{{font-size:.62rem;color:#8b949e;margin-bottom:2px;text-align:center}}
.ic a{{display:block;width:100%}}
.ic img{{width:100%;border-radius:3px;border:1px solid #30363d;display:block}}
.ic img:hover{{border-color:#58a6ff}}
.id{{font-size:.6rem;color:#6e7681;margin-top:1px}}

.vchart{{width:100%;min-height:440px}}

/* === Status board === */
.status-section{{padding:14px;border-bottom:2px solid #21262d;background:#0a0d11}}
.status-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:6px}}
.status-help{{font-size:.7rem;color:#8b949e;margin-bottom:10px}}
.status-help span{{margin:0 4px;font-size:1rem}}
.status-matrix{{width:100%;border-collapse:collapse;font-size:.78rem}}
.status-matrix th{{text-align:left;padding:6px 8px;color:#8b949e;font-weight:500;font-size:.7rem;
                   text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #30363d}}
.status-matrix tbody tr{{border-bottom:1px solid #21262d}}
.status-matrix tbody tr:hover{{background:#161b22}}
.status-matrix .vol-cell{{padding:8px 10px;font-weight:600;color:#e2a44a;
                          background:#0d1117;font-size:.82rem}}
.status-matrix .vol-cell a{{color:inherit}}
.status-matrix .cell{{padding:6px 8px;background:#0d1117;vertical-align:middle}}
.status-matrix .cell-empty{{padding:6px 8px;background:#0d1117;color:#3a3f47;text-align:center}}
.cell-inner{{display:flex;flex-direction:column;gap:1px}}
.cell-top{{display:flex;justify-content:space-between;align-items:baseline;gap:6px}}
.cell-val{{font-family:'SF Mono',Monaco,monospace;font-weight:600;font-size:.82rem}}
.cell-z{{font-size:.65rem;color:#6e7681;font-family:'SF Mono',Monaco,monospace}}
.cell-spark{{margin-top:1px}}
.cell-bottom{{display:flex;justify-content:space-between;align-items:center;gap:4px}}
.cell-age{{font-size:.6rem;color:#6e7681}}
.diff-badge{{font-size:.58rem;padding:1px 4px;border-radius:3px;font-family:'SF Mono',Monaco,monospace}}

/* === Alerts === */
.alerts-section{{padding:14px;border-bottom:2px solid #21262d}}
.alerts-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:8px}}
.alerts-table{{width:100%;border-collapse:collapse;font-size:.78rem}}
.alerts-table th{{text-align:left;padding:5px 8px;color:#8b949e;font-weight:500;
                  font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;
                  border-bottom:1px solid #30363d}}
.alerts-table td{{padding:5px 8px;border-bottom:1px solid #21262d}}
.alerts-table tr:hover{{background:#161b22}}

/* === Bulletin operacional === */
.bulletin-section{{padding:14px;border-bottom:2px solid #21262d}}
.bulletin-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:4px}}
.bull-help{{font-size:.68rem;color:#6e7681;margin-bottom:10px}}
.bulletin-list{{display:flex;flex-direction:column;gap:5px}}
.bull-row{{display:grid;grid-template-columns:160px 1fr;gap:14px;align-items:center;
          padding:6px 0;border-bottom:1px solid #1c2128}}
.bull-row:last-child{{border-bottom:none}}
.bull-vol{{font-size:.82rem;font-weight:700;color:#e2a44a;padding-left:8px}}
.bull-vol:hover{{color:#f0c875}}
.bull-text{{font-size:.78rem;color:#c8d2dc;line-height:1.4}}
@media(max-width:700px){{.bull-row{{grid-template-columns:1fr}}}}

/* === Upstream status === */
.upstream-section{{padding:14px;border-bottom:2px solid #21262d;background:#0a0d11}}
.upstream-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:10px}}
.upstream-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
@media(max-width:700px){{.upstream-grid{{grid-template-columns:1fr}}}}
.up-label{{font-size:.62rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}}
.up-help{{font-size:.7rem;color:#6e7681;margin-top:10px}}

/* === Streamgraph === */
.streamgraph-section{{padding:14px;border-bottom:2px solid #21262d}}
.streamgraph-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:6px}}
.stream-help{{font-size:.72rem;color:#8b949e;margin-bottom:10px}}
.streamgraph{{width:100%;min-height:320px}}

/* === Multi-product alerts === */
.multi-section{{padding:14px;border-bottom:2px solid #21262d;background:#10141a}}
.multi-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:6px}}
.multi-help{{font-size:.72rem;color:#8b949e;margin-bottom:10px}}
.multi-help b{{color:#e6edf3}}
.multi-table{{width:100%;border-collapse:collapse;font-size:.78rem}}
.multi-table th{{text-align:left;padding:5px 8px;color:#8b949e;font-weight:500;
                 font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;
                 border-bottom:1px solid #30363d}}
.multi-table td{{padding:5px 8px;border-bottom:1px solid #21262d}}
.multi-table tr:hover{{background:#161b22}}

/* === Historico === */
.history-section{{padding:14px;border-bottom:2px solid #21262d;background:#0a0d11}}
.history-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:8px}}
.history-stats{{display:flex;flex-wrap:wrap;gap:14px;font-size:.75rem;color:#8b949e;
                margin-bottom:8px;align-items:center}}
.history-stats b{{color:#e6edf3;font-weight:600}}
.history-section details{{margin-top:6px}}
.history-section summary{{font-size:.78rem;color:#58a6ff;cursor:pointer;padding:4px 0}}
.history-section summary:hover{{text-decoration:underline}}
.history-table{{width:100%;border-collapse:collapse;font-size:.76rem;margin-top:6px}}
.history-table th{{text-align:left;padding:5px 8px;color:#8b949e;font-weight:500;
                   font-size:.66rem;text-transform:uppercase;letter-spacing:.05em;
                   border-bottom:1px solid #30363d}}
.history-table td{{padding:5px 8px;border-bottom:1px solid #21262d}}
.history-table tr:hover{{background:#161b22}}

/* === Map === */
.map-section{{padding:14px;border-bottom:2px solid #21262d}}
.map-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:8px}}
.map-section iframe{{width:100%;height:420px;border:1px solid #30363d;border-radius:5px}}

/* === Diff panel === */
.diff-panel{{margin-top:10px;padding:8px;background:#0a0d11;border:1px solid #21262d;border-radius:4px}}
.diff-title{{font-size:.72rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}}
.diff-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}
.diff-item{{display:flex;flex-direction:column}}
.diff-label{{font-size:.62rem;color:#6e7681;margin-bottom:2px;text-align:center}}
.diff-item img{{width:100%;border-radius:3px;border:1px solid #30363d;display:block}}
.diff-item img:hover{{border-color:#58a6ff}}
@media(max-width:700px){{.diff-grid{{grid-template-columns:1fr}}}}

.foot{{padding:10px 14px;font-size:.68rem;color:#6e7681;
       border-top:1px solid #30363d;text-align:right}}
.foot a{{color:#58a6ff}}
</style>
</head>
<body>
<div class="topbar">
  <h1>&#127755; MOUNTS-Chile</h1>
  <div class="nav">{nav}</div>
  <span class="meta">{esc(generated)}</span>
  <span class="time-filter">
    <span style="font-size:.65rem;color:#6e7681">Rango:</span>
    <button onclick="setTimeRange(30)">30d</button>
    <button onclick="setTimeRange(90)">90d</button>
    <button onclick="setTimeRange(365)">1a</button>
    <button onclick="setTimeRange(0)" class="active">todo</button>
  </span>
  <button class="upd" onclick="location.reload()">&#8635; Actualizar</button>
</div>

<script>
// Filtro temporal global: ajusta el rango X de todos los Plotly charts
function setTimeRange(days) {{
  document.querySelectorAll('.time-filter button').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  const charts = document.querySelectorAll('.vchart');
  let xrange = null;
  if (days > 0) {{
    const now = new Date();
    const past = new Date(now.getTime() - days * 86400000);
    const fmt = d => d.toISOString().slice(0,19);
    xrange = [fmt(past), fmt(now)];
  }}
  charts.forEach(div => {{
    if (div.data) {{   // ya inicializado por Plotly
      Plotly.relayout(div, {{ 'xaxis.range': xrange, 'xaxis.autorange': xrange === null }});
    }}
  }});
}}
</script>
{status_html}
{bulletin_html}
{upstream_html}
{alerts_html}
{multi_html}
{history_html}
{stream_so2}
{stream_swir}
{map_html}
{sections}
<div class="foot">
  Fuente: <a href="https://www.mounts-project.com" target="_blank">mounts-project.com</a>
  (Valade et al. 2019, TU Berlin / GFZ Potsdam) &middot; Sentinel-1/2/5P &copy; Copernicus/ESA
</div>
</body>
</html>"""
