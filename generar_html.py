"""
Genera latest.html — replica el layout de MOUNTS con las 5 graficas y las
imagenes mas recientes para los 7 volcanes chilenos.
Todo embebido en un HTML estatico (no requiere servidor).

Las imagenes se sirven desde latest/<volcan>/ (paths relativos, funciona en
GitHub Pages sin problemas de mixed-content).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

BASE      = "https://www.mounts-project.com/static"
TS_DIR    = Path(__file__).parent / "timeseries"
LATEST    = Path(__file__).parent / "latest"
DATA_DIR  = Path(__file__).parent / "data"
OUT       = Path(__file__).parent / "latest.html"

VOLCANES = [
    ("lascar",             "Lascar",              355100),
    ("planchon-peteroa",   "Planchon-Peteroa",    357040),
    ("laguna-del-maule",   "Laguna del Maule",    357061),
    ("nevados-de-chillan", "Nevados de Chillan",  357070),
    ("copahue",            "Copahue",             357090),
    ("llaima",             "Llaima",              357110),
    ("villarrica",         "Villarrica",          357120),
]

# Coordenadas (lat, lon) de cada volcan — para mapa
COORDS = {
    "lascar":             (-23.37, -67.73),
    "planchon-peteroa":   (-35.24, -70.57),
    "laguna-del-maule":   (-36.10, -70.49),
    "nevados-de-chillan": (-36.86, -71.38),
    "copahue":            (-37.85, -71.17),
    "llaima":             (-38.69, -71.73),
    "villarrica":         (-39.42, -71.93),
}

# Colores por severidad — consistentes con anomalies.py
SEV_COLOR = {
    "red":    "#e74c3c",
    "orange": "#e67e22",
    "yellow": "#f1c40f",
    "green":  "#2ecc71",
    "stale":  "#7f8c8d",
    "gray":   "#3a3f47",
}

# Productos en el status matrix
STATUS_PRODUCTS = ["SWIR", "SO2", "DEF", "COH"]

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


def get_latest_imgs(ts_by_name, vol_key):
    """
    Recorre los textos de todas las trazas y extrae la ultima imagen de cada
    producto. Prefiere la version local en latest/<vol_key>/ (path relativo,
    compatible con GitHub Pages). Si no existe localmente usa la URL HTTP
    solo como fallback (no visible en GitHub Pages por mixed-content).
    """
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
        fn = path.split("/")[-1]
        for suffix, label in IMG_PRODUCTS:
            if suffix in path and suffix not in imgs:
                # ¿Existe localmente en latest/?
                local = LATEST / vol_key / fn
                if local.exists():
                    url = f"latest/{vol_key}/{fn}"
                else:
                    url = f"{BASE}/{path}"   # fallback HTTP (no visible en Pages)
                imgs[suffix] = {
                    "url":   url,
                    "label": label,
                    "date":  (date_x or "")[:10],
                    "local": local.exists(),
                }
        if len(imgs) == len(IMG_PRODUCTS):
            break
    return imgs


def compute_baseline_for_trace(trace):
    """
    Devuelve listas (xs, lower, upper, anomaly_xs, anomaly_ys) para overlay
    sobre una traza. lower = mediana - 3*MAD, upper = mediana + 3*MAD.
    Reusa logica de anomalies.py.
    """
    try:
        from anomalies import robust_baseline, detect_anomalies, parse_iso
    except ImportError:
        return [], [], [], [], []
    if not trace or not trace.get("y"):
        return [], [], [], [], []
    xs = trace.get("x") or []
    ys = trace.get("y") or []

    # Limpiar None y ordenar por fecha
    pairs = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if len(pairs) < 5:
        return [], [], [], [], []
    pairs_sorted = sorted(pairs, key=lambda p: parse_iso(p[0]) or p[0])
    xs_clean = [p[0] for p in pairs_sorted]
    ys_clean = [p[1] for p in pairs_sorted]

    medians, mads = robust_baseline(xs_clean, ys_clean)
    lower = []
    upper = []
    for m, d in zip(medians, mads):
        if (m != m) or (d != d):       # NaN check
            lower.append(None)
            upper.append(None)
        else:
            lower.append(max(0.001, m - 3 * d))   # log scale safe
            upper.append(m + 3 * d)

    anoms = detect_anomalies(xs_clean, ys_clean)
    a_xs = [a["date"] for a in anoms]
    a_ys = [a["value"] for a in anoms]

    return xs_clean, lower, upper, a_xs, a_ys


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

    # Bandas baseline ±3 MAD + markers de anomalias para SWIR (y2) y SO2 (y3)
    for tname, yaxis_id in [("swir", "y2"), ("so2", "y3")]:
        td = ts_by_name.get(tname)
        if not td:
            continue
        xs_b, lower, upper, a_xs, a_ys = compute_baseline_for_trace(td)
        if not xs_b:
            continue

        # Banda inferior (invisible, base para fill)
        traces_js.append(f"""{{
  x:{json.dumps(xs_b)},y:{json.dumps(lower)},
  mode:'lines',type:'scatter',yaxis:{json.dumps(yaxis_id)},
  line:{{color:'rgba(255,255,255,0)',width:0}},
  showlegend:false,hoverinfo:'none'
}}""")
        # Banda superior con fill al inferior (banda baseline ±3MAD)
        traces_js.append(f"""{{
  x:{json.dumps(xs_b)},y:{json.dumps(upper)},
  mode:'lines',type:'scatter',yaxis:{json.dumps(yaxis_id)},
  line:{{color:'rgba(255,255,255,0)',width:0}},
  fill:'tonexty',fillcolor:'rgba(120,120,120,0.18)',
  name:'baseline ±3σ',showlegend:false,hoverinfo:'none'
}}""")
        # Markers anomalias
        if a_xs:
            traces_js.append(f"""{{
  x:{json.dumps(a_xs)},y:{json.dumps(a_ys)},
  mode:'markers',type:'scatter',yaxis:{json.dumps(yaxis_id)},
  marker:{{color:'#e74c3c',size:9,symbol:'star',
           line:{{color:'#fff',width:0.5}}}},
  name:'anomalia',showlegend:false,
  hovertemplate:'<b>ANOMALIA</b><br>%{{x}}<br>%{{y:.3g}}<extra></extra>'
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


def load_diffs():
    f = Path(__file__).parent / "diffs.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def build_diff_panel(key, diff_info):
    """Panel antes/despues + diff para SWIR."""
    if not diff_info:
        return ""
    new_url = esc(diff_info["new"])
    old_url = esc(diff_info["old"])
    diff_url = esc(diff_info["diff"])
    new_d = esc(diff_info.get("new_date", ""))
    old_d = esc(diff_info.get("old_date", ""))
    return f'''
<div class="diff-panel">
  <div class="diff-title">SWIR — comparación temporal</div>
  <div class="diff-grid">
    <div class="diff-item">
      <div class="diff-label">ANTES — {old_d}</div>
      <a href="{old_url}" target="_blank"><img src="{old_url}" loading="lazy"></a>
    </div>
    <div class="diff-item">
      <div class="diff-label">DESPUÉS — {new_d}</div>
      <a href="{new_url}" target="_blank"><img src="{new_url}" loading="lazy"></a>
    </div>
    <div class="diff-item">
      <div class="diff-label" style="color:#e67e22">|DIFF|</div>
      <a href="{diff_url}" target="_blank"><img src="{diff_url}" loading="lazy"></a>
    </div>
  </div>
</div>'''


def build_section(key, nombre, sid):
    mounts_url = f"https://www.mounts-project.com/timeseries/{sid}"
    ts = load_ts(key)
    imgs = get_latest_imgs(ts, key)
    chart_call = build_plotly_call(f"chart-{key}", ts)
    diffs = load_diffs()
    diff_panel = build_diff_panel(key, diffs.get(key))

    # Imagenes
    cells = ""
    for suffix, label in IMG_PRODUCTS:
        info = imgs.get(suffix)
        if info:
            # Para links externos usamos la URL de MOUNTS; para locales el mismo src
            link_url = info["url"] if info.get("local") else f"https://www.mounts-project.com/static/data_mounts/{key}/"
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
  {diff_panel}
</div>
<script>window.addEventListener('load',function(){{ {chart_call} }});</script>
"""


def build_map(status):
    """Genera mapa Folium con los 7 volcanes coloreados por severidad."""
    try:
        import folium
    except ImportError:
        return '<div class="map-section"><h2>Mapa</h2><p>folium no instalado.</p></div>'

    # Centro Chile
    m = folium.Map(
        location=[-33.0, -70.5],
        zoom_start=4,
        tiles="CartoDB dark_matter",
        attr="© OpenStreetMap, © CartoDB",
    )

    for key, name, sid in VOLCANES:
        if key not in COORDS:
            continue
        lat, lon = COORDS[key]
        v = status.get("volcanoes", {}).get(key, {}) if status else {}
        overall = v.get("overall", "gray")
        color = SEV_COLOR.get(overall, "#3a3f47")

        # Tooltip con resumen de productos
        prods = v.get("products", {})
        rows_html = ""
        for p in STATUS_PRODUCTS:
            ps = prods.get(p)
            if ps is None:
                rows_html += f'<tr><td>{p}</td><td style="color:#888">—</td></tr>'
            else:
                z = ps.get("zscore_now")
                z_str = f"{z:+.1f}σ" if z is not None else "—"
                pcolor = SEV_COLOR.get(ps.get("severity", "gray"), "#888")
                val = fmt_value(ps.get("latest_value"), "")
                rows_html += (
                    f'<tr><td>{p}</td>'
                    f'<td style="color:{pcolor};font-family:monospace">{val} ({z_str})</td></tr>'
                )

        popup_html = (
            f'<div style="font-family:system-ui;font-size:12px;min-width:180px">'
            f'<b style="font-size:13px;color:#222">{name}</b><br>'
            f'<span style="color:#666;font-size:11px">Smithsonian {sid}</span>'
            f'<table style="margin-top:6px;font-size:11px;border-collapse:collapse">{rows_html}</table>'
            f'<a href="https://mendozavolcanic.github.io/MOUNTS-Chile/#v-{key}" '
            f'style="font-size:11px;color:#0969da">Ver detalle &rarr;</a>'
            f'</div>'
        )

        folium.CircleMarker(
            location=[lat, lon],
            radius=10,
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=0.85,
            weight=2,
            tooltip=f"{name} — {overall}",
            popup=folium.Popup(popup_html, max_width=240),
        ).add_to(m)

        # label
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=f'<div style="font-size:10px;color:#fff;text-shadow:1px 1px 2px #000;'
                     f'transform:translate(12px,-6px);white-space:nowrap;font-weight:600">'
                     f'{name}</div>',
            ),
        ).add_to(m)

    out = Path(__file__).parent / "map.html"
    m.save(str(out))
    return f'''
<div class="map-section">
  <h2>Mapa de actividad</h2>
  <iframe src="map.html" loading="lazy"></iframe>
</div>'''


def load_status():
    """Carga status.json (generado por anomalies.py)."""
    f = Path(__file__).parent / "status.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def load_alerts():
    f = Path(__file__).parent / "alerts.json"
    if not f.exists():
        return {"alerts": [], "count": 0}
    return json.loads(f.read_text(encoding="utf-8"))


def sparkline_svg(xs, ys, color="#58a6ff", width=110, height=28):
    """SVG sparkline inline. xs=fechas (ignoradas, usamos indice), ys=valores."""
    if not ys or len(ys) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    ymin, ymax = min(ys), max(ys)
    rng = ymax - ymin if ymax != ymin else 1.0
    pts = []
    n = len(ys)
    for i, y in enumerate(ys):
        px = i * (width - 2) / (n - 1) + 1
        py = height - 2 - (y - ymin) / rng * (height - 4)
        pts.append(f"{px:.1f},{py:.1f}")
    path = " ".join(pts)
    last_x = (n - 1) * (width - 2) / (n - 1) + 1
    last_y = height - 2 - (ys[-1] - ymin) / rng * (height - 4)
    return (
        f'<svg width="{width}" height="{height}" style="display:block">'
        f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def fmt_age(age_hours):
    if age_hours is None:
        return "—"
    if age_hours < 24:
        return f"{age_hours:.0f}h"
    days = age_hours / 24
    if days < 30:
        return f"{days:.0f}d"
    return f"{days/30:.0f}mo"


def fmt_value(v, unit):
    """Formato compacto del valor segun unidad."""
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:.0f}"
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.3g}"


def build_status_matrix(status):
    """Tabla 7x4 con sparklines y colores."""
    if not status or "volcanoes" not in status:
        return '<p style="color:#6e7681;padding:14px">Status no disponible. Corre anomalies.py</p>'

    headers = "".join(f'<th>{p}</th>' for p in STATUS_PRODUCTS)
    rows = []
    for key, name, sid in VOLCANES:
        v = status["volcanoes"].get(key, {})
        prods = v.get("products", {})
        overall = v.get("overall", "gray")
        ov_color = SEV_COLOR.get(overall, "#3a3f47")

        cells = []
        for p in STATUS_PRODUCTS:
            ps = prods.get(p)
            if ps is None:
                cells.append(
                    f'<td class="cell-empty"><div class="cell-inner">'
                    f'<div class="cell-val">—</div></div></td>'
                )
                continue
            sev = ps.get("severity", "gray")
            color = SEV_COLOR.get(sev, "#3a3f47")
            z = ps.get("zscore_now")
            z_str = f"{z:+.1f}σ" if z is not None else "—"
            val = fmt_value(ps.get("latest_value"), "")
            age = fmt_age(ps.get("age_hours"))
            spark = sparkline_svg(ps.get("sparkline_x", []), ps.get("sparkline_y", []),
                                  color=color, width=110, height=24)
            cells.append(
                f'<td class="cell" style="border-left:3px solid {color}">'
                f'<div class="cell-inner">'
                f'<div class="cell-top">'
                f'<span class="cell-val" style="color:{color}">{val}</span>'
                f'<span class="cell-z">{z_str}</span>'
                f'</div>'
                f'<div class="cell-spark">{spark}</div>'
                f'<div class="cell-age">{age}</div>'
                f'</div></td>'
            )
        rows.append(
            f'<tr>'
            f'<th class="vol-cell" style="border-left:5px solid {ov_color}">'
            f'<a href="#v-{key}">{esc(name)}</a>'
            f'</th>'
            + "".join(cells)
            + '</tr>'
        )

    return f'''
<div class="status-section">
  <h2>Status board</h2>
  <p class="status-help">
    Color = severidad (z-score MAD-robusto, baseline 90 d).
    <span style="color:{SEV_COLOR['green']}">●</span> normal
    <span style="color:{SEV_COLOR['yellow']}">●</span> atención
    <span style="color:{SEV_COLOR['orange']}">●</span> elevado
    <span style="color:{SEV_COLOR['red']}">●</span> alto
    <span style="color:{SEV_COLOR['stale']}">●</span> dato atrasado
  </p>
  <table class="status-matrix">
    <thead><tr><th>Volcán</th>{headers}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</div>
'''


def build_history_panel(top_n=20):
    """
    Lee mounts.db y construye una tabla con el catalogo historico de
    anomalias (top N por z-score, todas las fechas).
    """
    db_path = Path(__file__).parent / "mounts.db"
    if not db_path.exists():
        return ""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("""
        SELECT a.date, v.name, v.key, a.product, a.value, a.zscore, a.severity, a.detected_at
        FROM anomalies a JOIN volcanoes v ON v.key = a.volcano_key
        ORDER BY a.zscore DESC LIMIT ?
    """, (top_n,))
    rows_data = cur.fetchall()

    # Stats globales
    n_total = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    n_obs   = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    n_evt   = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    # Validacion vs eventos GVP (ventana 7d)
    tp = conn.execute("""
        SELECT COUNT(DISTINCT a.id) FROM anomalies a
        WHERE EXISTS (
          SELECT 1 FROM events e
          WHERE e.volcano_key = a.volcano_key
            AND ABS(julianday(e.date) - julianday(a.date)) <= 7
        )
    """).fetchone()[0]
    precision = f"{tp/n_total:.0%}" if n_total else "—"

    conn.close()

    if not rows_data:
        return ""

    rows_html = ""
    for dt, name, key, prod, val, z, sev, det in rows_data:
        color = SEV_COLOR.get(sev, "#888")
        rows_html += (
            f'<tr style="border-left:3px solid {color}">'
            f'<td>{esc(dt[:10])}</td>'
            f'<td><a href="#v-{esc(key)}">{esc(name)}</a></td>'
            f'<td>{esc(prod.upper())}</td>'
            f'<td style="font-family:monospace">{val:.3g}</td>'
            f'<td style="color:{color};font-weight:600">+{z:.1f}σ</td>'
            f'<td style="font-size:.65rem;color:#6e7681">{esc(det[:16])}</td>'
            f'</tr>'
        )

    return f'''
<div class="history-section">
  <h2>Catálogo histórico de anomalías</h2>
  <div class="history-stats">
    <span><b>{n_total}</b> anomalías</span>
    <span><b>{n_obs:,}</b> observaciones</span>
    <span><b>{n_evt}</b> eventos GVP</span>
    <span>Validación detector vs GVP (±7 d): <b style="color:{SEV_COLOR['green']}">{precision}</b> precisión</span>
    <span><a href="anomalies.csv">📄 anomalies.csv</a></span>
    <span><a href="mounts.db">💾 mounts.db</a></span>
  </div>
  <details>
    <summary>Top {top_n} por z-score (click para expandir)</summary>
    <table class="history-table">
      <thead><tr><th>Fecha</th><th>Volcán</th><th>Producto</th><th>Valor</th><th>Z</th><th>Detectado</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </details>
</div>'''


def build_alerts_panel(alerts_obj):
    """Lista de las top alertas recientes."""
    alerts = alerts_obj.get("alerts", [])[:8]
    if not alerts:
        return f'''
<div class="alerts-section">
  <h2>Alertas recientes ({alerts_obj.get("lookback_days", 30)} d)</h2>
  <p style="color:{SEV_COLOR['green']};padding:8px 0">Sin anomalías. Todo en baseline.</p>
</div>'''

    rows = []
    for a in alerts:
        z = a["zscore"]
        sev = "red" if z >= 6 else ("orange" if z >= 3 else "yellow")
        color = SEV_COLOR[sev]
        rows.append(
            f'<tr style="border-left:3px solid {color}">'
            f'<td>{esc(a["date"][:16])}</td>'
            f'<td><a href="#v-{a["volcano_key"]}">{esc(a["volcano"])}</a></td>'
            f'<td>{esc(a["product"])}</td>'
            f'<td>{a["value"]:.3g} {esc(a["unit"])}</td>'
            f'<td style="color:{color};font-weight:600">+{z:.1f}σ</td>'
            f'</tr>'
        )

    return f'''
<div class="alerts-section">
  <h2>Alertas recientes ({alerts_obj.get("lookback_days", 30)} d) — {alerts_obj.get("count", 0)} eventos</h2>
  <table class="alerts-table">
    <thead><tr><th>Fecha</th><th>Volcán</th><th>Producto</th><th>Valor</th><th>Z-score</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</div>'''


def main():
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nav = " &middot; ".join(
        f'<a href="#v-{k}">{n}</a>' for k, n, _ in VOLCANES
    )
    status = load_status()
    alerts = load_alerts()
    status_html = build_status_matrix(status)
    alerts_html = build_alerts_panel(alerts)
    history_html = build_history_panel(top_n=20)
    map_html = build_map(status)
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
.cell-age{{font-size:.6rem;color:#6e7681;text-align:right}}

/* === Alerts === */
.alerts-section{{padding:14px;border-bottom:2px solid #21262d}}
.alerts-section h2{{font-size:.95rem;font-weight:600;color:#f0f6fc;margin-bottom:8px}}
.alerts-table{{width:100%;border-collapse:collapse;font-size:.78rem}}
.alerts-table th{{text-align:left;padding:5px 8px;color:#8b949e;font-weight:500;
                  font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;
                  border-bottom:1px solid #30363d}}
.alerts-table td{{padding:5px 8px;border-bottom:1px solid #21262d}}
.alerts-table tr:hover{{background:#161b22}}

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
  <button class="upd" onclick="location.reload()">&#8635; Actualizar</button>
</div>
{status_html}
{alerts_html}
{history_html}
{map_html}
{sections}
<div class="foot">
  Fuente: <a href="https://www.mounts-project.com" target="_blank">mounts-project.com</a>
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
