"""
Mapa Folium del dashboard MOUNTS-Chile.

build_map: mapa de Chile con los 7 volcanes coloreados por severidad overall.
Escribe map.html (embebido via iframe en el dashboard principal).

Extraido de generar_html.py (refactor C2) sin cambios de logica.
"""

from .config import ROOT, VOLCANES, COORDS, SEV_COLOR, STATUS_PRODUCTS
from .status import fmt_value


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

    out = ROOT / "map.html"
    m.save(str(out))
    return f'''
<div class="map-section">
  <h2>Mapa de actividad</h2>
  <iframe src="map.html" loading="lazy"></iframe>
</div>'''
