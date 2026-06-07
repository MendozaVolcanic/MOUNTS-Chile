"""
Secciones HTML del dashboard MOUNTS-Chile (todo lo que no es status/charts/map).

- build_section: bloque por volcan (imagenes recientes + chart Plotly + diff SWIR).
- build_alerts_panel: alertas recientes (alerts.json).
- build_multi_alerts_panel: alertas multi-producto cross-sensor (mounts.db).
- build_history_panel: catalogo historico de anomalias (mounts.db).
- build_upstream_status_panel: estado upstream MOUNTS (citation, cambios, calidad).

Helpers de imagenes (get_latest_imgs) y diffs (load_diffs, build_diff_panel)
viven aca porque solo los usa build_section.

Extraido de generar_html.py (refactor C2) sin cambios de logica.
"""

import json

from .config import ROOT, BASE, LATEST, TRACES_CFG, IMG_PRODUCTS, SEV_COLOR, esc
from .charts import load_ts, build_plotly_call


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


def load_diffs():
    f = ROOT / "diffs.json"
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


def build_upstream_status_panel():
    """
    Panel con estado upstream:
    - Citation actual (del /about)
    - Cambios detectados en /news desde ultimo check
    - Gap analysis summary
    """
    state_f = ROOT / "upstream_state.json"
    changes_f = ROOT / "upstream_changes.json"
    quality_f = ROOT / "quality.json"

    state = {}
    if state_f.exists():
        try:
            state = json.loads(state_f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    citation = state.get("citation", {})
    dois = citation.get("dois", [])

    n_changes = 0
    last_change = None
    if changes_f.exists():
        try:
            changes = json.loads(changes_f.read_text(encoding="utf-8"))
            n_changes = len(changes)
            if changes:
                last_change = changes[-1]
        except (json.JSONDecodeError, IndexError):
            pass

    low_cov = 0
    drift_n = 0
    if quality_f.exists():
        try:
            q = json.loads(quality_f.read_text(encoding="utf-8"))
            low_cov = q.get("summary", {}).get("products_with_low_coverage", 0)
            drift_n = q.get("summary", {}).get("drift_events", 0)
        except json.JSONDecodeError:
            pass

    dois_html = " ".join(
        f'<a href="https://doi.org/{esc(d)}" target="_blank" '
        f'style="font-family:monospace;font-size:.68rem">{esc(d)}</a>'
        for d in dois[:3]
    )

    change_badge = ""
    if last_change:
        sev = last_change.get("severity", "low")
        color = "#e74c3c" if sev == "high" else "#e67e22"
        change_badge = (
            f'<span style="background:{color};color:#fff;padding:2px 6px;'
            f'border-radius:3px;font-size:.65rem">'
            f'⚠ {n_changes} cambios upstream detectados</span>'
        )
    else:
        change_badge = (
            f'<span style="background:#2ecc71;color:#fff;padding:2px 6px;'
            f'border-radius:3px;font-size:.65rem">'
            f'✓ Upstream sin cambios</span>'
        )

    return f'''
<div class="upstream-section">
  <h2>Estado upstream MOUNTS</h2>
  <div class="upstream-grid">
    <div>
      <div class="up-label">Citación oficial</div>
      <div>{dois_html or '<i>no disponible</i>'}</div>
      <div class="up-label" style="margin-top:6px">Contacto</div>
      <div style="font-family:monospace;font-size:.7rem">{esc(', '.join(citation.get('contacts', [])))}</div>
    </div>
    <div>
      <div class="up-label">Monitor upstream</div>
      <div>{change_badge}</div>
      <div class="up-label" style="margin-top:6px">Calidad de datos</div>
      <div style="font-size:.7rem">
        {low_cov} producto/s con cobertura &lt;50% ·
        {drift_n} valores modificados retroactivamente
      </div>
    </div>
  </div>
  <p class="up-help">
    El scraper monitorea <a href="http://www.mounts-project.com/news" target="_blank">/news</a> +
    <a href="http://www.mounts-project.com/about" target="_blank">/about</a> + schema de cada
    timeseries. Si MOUNTS cambia calibración (ej. baseline S2), se detecta y se loguea en
    <a href="upstream_changes.json">upstream_changes.json</a>.
    <a href="quality.json">quality.json</a> tiene el gap analysis completo.
  </p>
</div>'''


def build_multi_alerts_panel(top_n=15):
    """
    Panel de alertas multi-producto: cuando >=2 productos del mismo volcan
    muestran anomalia dentro de ventana 14d. Mas confiable que single-product.
    """
    db_path = ROOT / "mounts.db"
    if not db_path.exists():
        return ""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("""
        SELECT mc.date_center, v.name, v.key, mc.products, mc.n_products,
               mc.zscore_max, mc.confidence
        FROM multi_alerts mc JOIN volcanoes v ON v.key = mc.volcano_key
        ORDER BY mc.n_products DESC, mc.zscore_max DESC LIMIT ?
    """, (top_n,))
    rows = cur.fetchall()
    n_total = conn.execute("SELECT COUNT(*) FROM multi_alerts").fetchone()[0]
    conn.close()

    if not rows:
        return ""

    rows_html = ""
    for date, name, key, products_json, n_prods, z_max, conf in rows:
        try:
            products = json.loads(products_json)
            prods_str = ", ".join(p.upper() for p in products)
        except (ValueError, TypeError):
            prods_str = products_json
        # color por confianza
        color = "#e74c3c" if conf == "high" else "#e67e22"
        # clippear z para display
        z_str = f">{50}σ" if z_max > 50 else f"+{z_max:.1f}σ"
        rows_html += (
            f'<tr style="border-left:3px solid {color}">'
            f'<td>{esc(date[:10])}</td>'
            f'<td><a href="#v-{esc(key)}">{esc(name)}</a></td>'
            f'<td><b>{n_prods}</b></td>'
            f'<td style="font-family:monospace;font-size:.7rem">{esc(prods_str)}</td>'
            f'<td style="color:{color};font-weight:600">{z_str}</td>'
            f'<td><span style="background:{color};color:#fff;padding:1px 5px;border-radius:3px;font-size:.6rem">{conf}</span></td>'
            f'</tr>'
        )

    return f'''
<div class="multi-section">
  <h2>Alertas multi-producto (cross-sensor)</h2>
  <p class="multi-help">
    Cuando ≥2 productos satelitales del mismo volcán muestran anomalía dentro de 14 días.
    Mucho más confiable que single-product (descarta nubes/incendios).
    <b>{n_total}</b> alertas totales en histórico.
  </p>
  <table class="multi-table">
    <thead><tr><th>Fecha</th><th>Volcán</th><th>N</th><th>Productos</th><th>Z máx</th><th>Conf</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>'''


def build_history_panel(top_n=20):
    """
    Lee mounts.db y construye una tabla con el catalogo historico de
    anomalias (top N por z-score, todas las fechas).
    """
    db_path = ROOT / "mounts.db"
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
