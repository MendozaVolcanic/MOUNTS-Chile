"""
Graficos Plotly del dashboard MOUNTS-Chile.

- build_plotly_call: 4 paneles por volcan (SO2/Thermal/Deform/Coherence) con
  baseline +-3 MAD y estrellas de anomalia.
- build_streamgraph: serie regional apilada (SO2 / SWIR) por volcan.

Extraido de generar_html.py (refactor C2) sin cambios de logica.
"""

import json
from datetime import datetime, timezone

from .config import TS_DIR, VOLCANES, TRACES_CFG, YAXES_CFG, esc


def load_ts(key):
    f = TS_DIR / f"{key}.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    return {t["name"]: t for t in data.get("traces", []) if t.get("name")}


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
        "height": 440,
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


def build_streamgraph(product_trace="so2", title="SO2 multi-volcan",
                       unit="tons", height=320):
    """
    Streamgraph: 7 trazas stacked (una por volcan) del producto especificado.
    Util para detectar eventos regionales (ej. multiples volcanes con SO2
    elevado simultaneo).

    Resamplea a binning mensual para suavizar y reducir size del payload.
    """
    from collections import defaultdict
    from datetime import datetime as _dt

    # Bin mensual: para cada volcan, sumar values dentro del mes
    series = {}    # vol_key -> {YYYY-MM: sum}
    for key, name, sid in VOLCANES:
        f = TS_DIR / f"{key}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        traces = {t.get("name"): t for t in data.get("traces", [])}
        t = traces.get(product_trace)
        if not t or not t.get("y"):
            continue
        bins = defaultdict(float)
        for x, y in zip(t.get("x", []), t.get("y", [])):
            if y is None or y <= 0.5:   # ignorar no-detecciones (=0.1)
                continue
            try:
                dt = _dt.fromisoformat(str(x).replace("Z", "+00:00"))
                ym = dt.strftime("%Y-%m")
                bins[ym] += y
            except (ValueError, AttributeError):
                continue
        if bins:
            series[key] = (name, dict(bins))

    if not series:
        return ""

    # Eje X comun: todos los meses entre min y max
    all_months = sorted({m for _, b in series.values() for m in b.keys()})
    if len(all_months) < 6:
        return ""

    # Colores por volcan
    palette = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71",
               "#3498db", "#9b59b6", "#1abc9c"]
    traces_js = []
    for i, (key, (name, bins)) in enumerate(series.items()):
        ys = [bins.get(m, 0) for m in all_months]
        color = palette[i % len(palette)]
        traces_js.append(f"""{{
  name: {json.dumps(name)},
  x: {json.dumps(all_months)},
  y: {json.dumps(ys)},
  stackgroup: 'one',
  mode: 'lines',
  line: {{width: 0.5, color: {json.dumps(color)}}},
  fillcolor: {json.dumps(color + 'cc')},
  hovertemplate: '%{{x}}<br>{name}: %{{y:.0f}} {unit}<extra></extra>'
}}""")

    layout = {
        "height": height,
        "margin": {"l": 50, "r": 10, "t": 10, "b": 35},
        "paper_bgcolor": "#161b22",
        "plot_bgcolor": "#161b22",
        "font": {"color": "#8b949e", "size": 9},
        "legend": {"orientation": "h", "y": -0.2, "font": {"size": 9}},
        "xaxis": {"gridcolor": "#21262d", "tickfont": {"size": 8}, "color": "#8b949e"},
        "yaxis": {"title": f"{title} [{unit}]", "gridcolor": "#21262d",
                  "tickfont": {"size": 8}, "color": "#8b949e",
                  "type": "linear"},
        "hovermode": "x unified",
    }

    traces_str = "[\n" + ",\n".join(traces_js) + "\n]"
    layout_str = json.dumps(layout)
    div_id = f"streamgraph-{product_trace}"
    chart_call = (f"Plotly.newPlot({json.dumps(div_id)},{traces_str},{layout_str},"
                  f"{{responsive:true,displayModeBar:false}});")

    return f'''
<div class="streamgraph-section">
  <h2>{esc(title)} — vista regional</h2>
  <p class="stream-help">
    Suma mensual por volcán (apilada). Detecta eventos regionales sincrónicos
    o transferencias entre volcanes vecinos. Excluye no-detecciones (y≤0.5).
  </p>
  <div id="{div_id}" class="streamgraph"></div>
</div>
<script>window.addEventListener("load",function(){{ {chart_call} }});</script>'''
