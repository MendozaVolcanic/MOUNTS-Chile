"""
Status board y bulletin operacional del dashboard MOUNTS-Chile.

- build_status_matrix: tabla 7x4 (volcan x producto) con sparklines, severidad,
  edad del dato y badge de diff vs ~24h atras.
- build_bulletin: resumen textual auto-generado, una linea por volcan.

Tambien carga status.json / alerts.json / status_history (mounts.db) y expone
helpers de formato (sparkline_svg, fmt_age, fmt_value) usados por otros modulos.

Extraido de generar_html.py (refactor C2) sin cambios de logica.
"""

import json

from .config import (
    ROOT, VOLCANES, SEV_COLOR, SEV_RANK, STATUS_PRODUCTS, esc,
)


def load_status():
    """Carga status.json (generado por anomalies.py)."""
    f = ROOT / "status.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def load_previous_status():
    """
    Lee el snapshot anterior (>20h atras) por (volcan, producto) de
    status_history. Devuelve dict[(vol_key, product)] -> {severity, zscore}.
    Usado para calcular diff vs ayer en cada celda del status board.
    """
    db_path = ROOT / "mounts.db"
    if not db_path.exists():
        return {}
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        # Para cada (vol, prod), buscar el snapshot mas reciente que sea >20h atras
        # respecto al ahora. Asi capturamos la version "de ayer" / "hace ~1 dia"
        cur = conn.execute("""
            SELECT volcano_key, product, severity, zscore, snapshot_at
            FROM status_history
            WHERE snapshot_at < datetime('now', '-20 hours')
            ORDER BY snapshot_at DESC
        """)
        # Tomar el primero (mas reciente) por (vol, prod)
        result = {}
        for vol, prod, sev, z, snap in cur:
            key = (vol, prod)
            if key not in result:
                result[key] = {"severity": sev, "zscore": z, "snapshot_at": snap}
        return result
    finally:
        conn.close()


def load_alerts():
    f = ROOT / "alerts.json"
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
    """Tabla 7x4 con sparklines, colores y diff vs ~24h atras."""
    if not status or "volcanoes" not in status:
        return '<p style="color:#6e7681;padding:14px">Status no disponible. Corre anomalies.py</p>'

    previous = load_previous_status()
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

            # Diff vs ~24h atras
            prev = previous.get((key, p))
            diff_badge = ""
            if prev and z is not None and prev.get("zscore") is not None:
                dz = z - prev["zscore"]
                prev_sev = prev.get("severity", "gray")
                if prev_sev != sev:
                    # cambio de severidad: lo mas notable
                    arrow = "↑" if SEV_RANK.get(sev, 0) > SEV_RANK.get(prev_sev, 0) else "↓"
                    arrow_color = "#e74c3c" if arrow == "↑" else "#2ecc71"
                    diff_badge = (
                        f'<span class="diff-badge" '
                        f'style="background:{arrow_color};color:#fff" '
                        f'title="ayer {prev_sev}, hoy {sev}">'
                        f'{arrow} {prev_sev}→{sev}</span>'
                    )
                elif abs(dz) >= 0.5:
                    # mismo nivel pero cambio significativo en z
                    arrow = "↑" if dz > 0 else "↓"
                    diff_badge = (
                        f'<span class="diff-badge" '
                        f'style="color:#8b949e" '
                        f'title="cambio z-score vs ~24h">'
                        f'{arrow}{abs(dz):.1f}σ</span>'
                    )
            cells.append(
                f'<td class="cell" style="border-left:3px solid {color}">'
                f'<div class="cell-inner">'
                f'<div class="cell-top">'
                f'<span class="cell-val" style="color:{color}">{val}</span>'
                f'<span class="cell-z">{z_str}</span>'
                f'</div>'
                f'<div class="cell-spark">{spark}</div>'
                f'<div class="cell-bottom">'
                f'<span class="cell-age">{age}</span>'
                f'{diff_badge}'
                f'</div>'
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


def build_bulletin(status):
    """
    Bulletin textual auto-generado, una linea por volcan estilo GVP Smithsonian.
    Lectura completa del estado en 30s.

    Ejemplo:
      Villarrica: SWIR estable, SO2 +2.1σ ultimos dias, sin deformacion InSAR.
      Llaima: SWIR +5.8σ (transient), todo lo demas estable.
    """
    if not status or "volcanoes" not in status:
        return ""

    # Pesos para "redactar" en orden de severidad
    def severity_phrase(p_label, ps):
        if ps is None:
            return None
        sev = ps.get("severity", "gray")
        z = ps.get("zscore_now")
        if sev == "stale":
            return f"<span style='color:{SEV_COLOR['stale']}'>{p_label} dato atrasado</span>"
        if sev == "gray":
            return None
        if z is None:
            return None
        if sev == "green":
            return f"<span style='color:{SEV_COLOR['green']}'>{p_label} en baseline</span>"
        # Senal real
        color = SEV_COLOR.get(sev, "#888")
        z_disp = f">+50σ" if z > 50 else f"{z:+.1f}σ"
        return f"<span style='color:{color}'><b>{p_label} {z_disp}</b></span>"

    rows = []
    for key, name, sid in VOLCANES:
        v = status["volcanoes"].get(key, {})
        prods = v.get("products", {})
        overall = v.get("overall", "gray")
        ov_color = SEV_COLOR.get(overall, "#3a3f47")

        # Ordenar productos por severidad descendente para que lo importante salga primero
        order = sorted(
            STATUS_PRODUCTS,
            key=lambda p: SEV_RANK.get((prods.get(p) or {}).get("severity", "gray"), 0),
            reverse=True,
        )

        phrases = []
        for p in order:
            phrase = severity_phrase(p, prods.get(p))
            if phrase:
                phrases.append(phrase)

        if not phrases:
            text = '<span style="color:#6e7681">sin datos disponibles</span>'
        else:
            text = ", ".join(phrases) + "."

        rows.append(
            f'<div class="bull-row">'
            f'<a class="bull-vol" href="#v-{esc(key)}" '
            f'style="border-left:4px solid {ov_color}">{esc(name)}</a>'
            f'<span class="bull-text">{text}</span>'
            f'</div>'
        )

    return f'''
<div class="bulletin-section">
  <h2>Bulletin operacional</h2>
  <p class="bull-help">Resumen automático por volcán. Lectura completa en 30s.</p>
  <div class="bulletin-list">
    {"".join(rows)}
  </div>
</div>'''
