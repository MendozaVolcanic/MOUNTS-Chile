"""
Genera latest.html — replica el layout de MOUNTS con las 5 graficas y las
imagenes mas recientes para los 7 volcanes chilenos.
Todo embebido en un HTML estatico (no requiere servidor).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

BASE   = "http://www.mounts-project.com/static"
TS_DIR = Path(__file__).parent / "timeseries"
OUT    = Path(__file__).parent / "latest.html"

VOLCANES = [
    ("lascar",             "Lasear",              355100),
    ("planchon-peteroa",   "Planchon-Peteroa",    357040),
    ("laguna-del-maule",   "Laguna del Maule",    357061),
    ("nevados-de-chillan", "Nevados de Chillan",  357070),
    ("copahue",            "Copahue",             357090),
    ("llaima",             "Llaima",              357110),
    ("villarrica",         "Villarrica",          357120),
]

# Sufijos de imagen -> (etiqueta, orden)
IMG_PRODUCTS = [
    ("_SO2_PBL",       "SO2 TROPOMI"),
    ("_B12B11B8A_nir", "S2 SWIR"),
    ("_VV_disp",       "S1 InSAR disp"),
    ("_VV_int_fcnn",   "S1 Intensidad"),
    ("_VV_coh",        "S1 Coherencia"),
]

# Mapa de trazas: nombre -> (yaxis_id, color, mode, dash, symbol, fill)
# Replicando exactamente el layout de mounts-project.com
TRACES_CFG = {
    # Panel 1 (top): SO2 mass [tons] - log  - y3 domain [0.80-1.00]
    "so2":       ("y3", "#9467bd", "markers",       None,   None,          None),
    "tbar_so2":  ("y3", "red",     "lines+markers", None,   None,          None),
    # Panel 2: Thermal anomalies [N pix] - log - y2 domain [0.60-0.795]
    "swir":      ("y2", "#ff7f0e", "markers",       None,   None,          None),
    "tbar_nir":  ("y2", "red",     "lines+markers", None,   None,          None),
    # Panel 3: SAR placeholders - linear - y4 domain [0.40-0.595]
    "int_asc":   ("y4", "#d3d3d3", "markers",       None,   "circle-open", None),
    "int_desc":  ("y4", "#808080", "markers",       None,   "circle",      None),
    "tbar_int":  ("y4", "red",     "lines+markers", None,   None,          None),
    # Panel 4: Deformation st.dev [m] - linear - y5 domain [0.20-0.395]
    "def_asc":   ("y5", "#ea898a", "lines+markers", None,   "circle-open", None),
    "def_desc":  ("y5", "#c0392b", "lines+markers", None,   "circle",      None),
    "tbar_disp": ("y5", "red",     "lines+markers", None,   None,          None),
    # Panel 5 (bottom): Coherence (N pix<0.5) - linear - y domain [0.01-0.195]
    "coh_asc":   ("y1", "#aed6f1", "lines+markers", None,   "circle-open", None),
    "coh_desc":  ("y1", "#2980b9", "lines+markers", None,   "circle",      None),
    "tbar_coh":  ("y1", "red",     "lines+markers", None,   None,          None),
}

YAXES_CFG = {
    "y3": {"title": "SO2 [tons]",           "type": "log",    "domain": [0.80, 1.00], "color": "#9467bd"},
    "y2": {"title": "Thermal [N pix]",      "type": "log",    "domain": [0.60, 0.795],"color": "#ff7f0e"},
    "y4": {"title": "SAR placeholders",     "type": "linear", "domain": [0.40, 0.595],"color": "#d3d3d3"},
    "y5": {"title": "Deform st.dev [m]",    "type": "linear", "domain": [0.20, 0.395],"color": "#ea898a"},
    "y1": {"title": "Coherence (N<0.5)",    "type": "linear", "domain": [0.01, 0.195],"color": "#2980b9"},
}


def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def load_ts(key):
    f = TS_DIR / f"{key}.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    return {t["name"]: t for t in data.get("traces", []) if t.get("name")}


def get_latest_imgs(ts_by_name):
    """Recorre los textos de todas las trazas y extrae la ultima imagen de cada producto."""
    imgs = {}
    # Recopilar (fecha, path) de todas las trazas que tengan texto
    all_items = []
    for td in ts_by_name.values():
        texts = td.get("text") or []
        xs    = td.get("x") or []
        for path, x in zip(texts, xs):
            if path:
                all_items.append((x or "", path))
    # Ordenar desc por fecha
    all_items.sort(key=lambda t: t[0], reverse=True)
    for date_x, path in all_items:
        for suffix, label in IMG_PRODUCTS:
            if suffix in path and suffix not in imgs:
                imgs[suffix] = {
                    "url":   f"{BASE}/{path}",
                    "label": label,
                    "date":  (date_x or "")[:10],
                }
        if len(imgs) == len(IMG_PRODUCTS):
            break
    return imgs


def build_plotly_call(div_id, ts_by_name):
    if not ts_by_name:
        return f"document.getElementById('{div_id}').innerHTML='<p style=\"color:#6e7681;padding:16px\">Sin datos</p>';"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    traces_js = []

    for tname, (yaxis_id, color, mode, dash, symbol, fill) in TRACES_CFG.items():
        td = ts_by_name.get(tname)
        if td is None:
            continue
        xs = td.get("x") or []
        ys = td.get("y") or []
        if not xs:
            continue

        # Mapear yaxis_id al key de Plotly
        yaxis_key = "y" if yaxis_id == "y1" else yaxis_id

        is_tbar = tname.startswith("tbar_")
        marker_size = 3 if is_tbar else (4 if "coh" in tname or "def" in tname else 4)

        marker = {"color": json.dumps(color), "size": marker_size}
        if symbol:
            marker["symbol"] = json.dumps(symbol)

        line_props = f"color:{json.dumps(color)},width:1"
        if dash:
            line_props += f",dash:{json.dumps(dash)}"

        show_legend = not is_tbar

        # Nombre legible para leyenda
        labels = {
            "so2": "SO2", "swir": "Thermal",
            "def_asc": "Def asc", "def_desc": "Def desc",
            "int_asc": "Int asc", "int_desc": "Int desc",
            "coh_asc": "Coh asc", "coh_desc": "Coh desc",
        }
        label = labels.get(tname, tname)

        marker_js = "{" + ",".join(f"{k}:{v}" for k,v in marker.items()) + "}"

        traces_js.append(f"""{{
  name:{json.dumps(label)},
  x:{json.dumps(xs)},
  y:{json.dumps(ys)},
  mode:{json.dumps(mode)},
  type:'scatter',
  yaxis:{json.dumps(yaxis_key)},
  marker:{marker_js},
  line:{{{line_props}}},
  showlegend:{str(show_legend).lower()},
  hovertemplate:'%{{x}}<br>%{{y:.3g}}<extra>{label}</extra>'
}}""")

    # Linea roja vertical "hoy" en todos los paneles (usando y3 como referencia)
    traces_js.append(f"""{{
  x:['{today}','{today}'],y:[0.001,1e9],
  mode:'lines',type:'scatter',yaxis:'y3',
  line:{{color:'#e74c3c',width:1.5,dash:'dot'}},
  name:'Hoy',showlegend:false,hoverinfo:'none'
}}""")

    # Layout con los 5 ejes
    yaxes_layout = {}
    for yid, cfg in YAXES_CFG.items():
        plotly_key = "yaxis" if yid == "y1" else f"yaxis{yid[1:]}"
        yaxes_layout[plotly_key] = {
            "title": {"text": cfg["title"], "font": {"size": 9, "color": cfg["color"]}},
            "type": cfg["type"],
            "domain": cfg["domain"],
            "gridcolor": "#21262d",
            "zeroline": False,
            "tickfont": {"size": 8, "color": cfg["color"]},
            "color": cfg["color"],
        }
        if cfg["type"] == "log":
            yaxes_layout[plotly_key]["rangemode"] = "tozero"

    layout = {
        "height": 500,
        "margin": {"l": 60, "r": 10, "t": 10, "b": 35},
        "paper_bgcolor": "#161b22",
        "plot_bgcolor": "#161b22",
        "font": {"color": "#8b949e", "size": 9},
        "legend": {"x": 1.01, "y": 1, "font": {"size": 8}, "bgcolor": "rgba(0,0,0,0)",
                   "xanchor": "left"},
        "xaxis": {"gridcolor": "#21262d", "zeroline": False,
                  "tickfont": {"size": 8}, "color": "#8b949e"},
        "hovermode": "x unified",
    }
    layout.update(yaxes_layout)

    traces_str = "[\n" + ",\n".join(traces_js) + "\n]"
    layout_str = json.dumps(layout)

    return (f"Plotly.newPlot({json.dumps(div_id)},{traces_str},{layout_str},"
            f"{{responsive:true,displayModeBar:false}});")


def build_section(key, nombre, sid):
    mounts_url = f"http://www.mounts-project.com/timeseries/{sid}"
    ts = load_ts(key)
    imgs = get_latest_imgs(ts)
    chart_call = build_plotly_call(f"chart-{key}", ts)

    # Imagenes
    cells = ""
    for suffix, label in IMG_PRODUCTS:
        info = imgs.get(suffix)
        if info:
            cells += (
                f'<div class="ic">'
                f'<div class="il">{esc(info["label"])}</div>'
                f'<a href="{esc(info["url"])}" target="_blank">'
                f'<img src="{esc(info["url"])}" alt="{esc(info["label"])}" loading="lazy"'
                f' onerror="this.style.opacity=\'0.15\'">'
                f'</a>'
                f'<div class="id">{esc(info["date"])}</div>'
                f'</div>'
            )

    n_traces = len([t for t in TRACES_CFG if t in ts])
    no_img = '' if cells else '<p style="color:#6e7681;font-size:.78rem;padding:8px">Sin imagenes</p>'

    return f"""
<div class="vsec" id="v-{key}">
  <div class="vhdr">
    <span class="vname">{esc(nombre)}</span>
    <span class="vmeta">ID {sid} &middot; {n_traces} trazas &middot; {len(imgs)} productos</span>
    <a class="vlink" href="{esc(mounts_url)}" target="_blank">MOUNTS &nearr;</a>
  </div>
  <div class="vcontent">
    <div class="vimgs">{cells}{no_img}</div>
    <div class="vchart" id="chart-{key}"></div>
  </div>
</div>
<script>window.addEventListener('load',function(){{ {chart_call} }});</script>
"""


def main():
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nav = " &middot; ".join(
        f'<a href="#v-{k}">{n}</a>' for k, n, _ in VOLCANES
    )
    sections = "\n".join(build_section(k, n, s) for k, n, s in VOLCANES)

    html = f"""<!DOCTYPE html>
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

.vchart{{width:100%;min-height:500px}}

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
  <button class="upd" onclick="location.reload()">&#8635; Actualizar</button>
</div>
{sections}
<div class="foot">
  Fuente: <a href="http://www.mounts-project.com" target="_blank">mounts-project.com</a>
  (Valade et al. 2019, TU Berlin / GFZ Potsdam) &middot; Sentinel-1/2/5P &copy; Copernicus/ESA
</div>
</body>
</html>"""

    OUT.write_text(html, encoding="utf-8")
    # Tambien sobreescribir index.html para GitHub Pages
    index = Path(__file__).parent / "index.html"
    index.write_text(html, encoding="utf-8")
    size_kb = OUT.stat().st_size // 1024
    print(f"Generado: {OUT}  ({size_kb} KB)")
    print(f"GitHub Pages: https://mendozavolcanic.github.io/MOUNTS-Chile/")


if __name__ == "__main__":
    main()
