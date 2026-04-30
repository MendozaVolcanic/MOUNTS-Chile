"""
MOUNTS-Chile Dashboard
======================
Vista unificada de los volcanes chilenos monitoreados por MOUNTS
(Sentinel-1 InSAR, Sentinel-2 SWIR, Sentinel-5P SO₂).

Uso:
    streamlit run dashboard.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# ─── Configuración ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TIMESERIES_DIR = BASE_DIR / "timeseries"
CATALOG_FILE = BASE_DIR / "catalog.csv"
MOUNTS_BASE = "http://www.mounts-project.com"

VOLCANO_NAMES = {
    "lascar":             "Láscar",
    "planchon-peteroa":   "Planchón-Peteroa",
    "laguna-del-maule":   "Laguna del Maule",
    "nevados-de-chillan": "Nevados de Chillán",
    "copahue":            "Copahue",
    "llaima":             "Llaima",
    "villarrica":         "Villarrica",
}

VOLCANO_IDS = {
    "lascar": 355100, "planchon-peteroa": 357040,
    "laguna-del-maule": 357061, "nevados-de-chillan": 357070,
    "copahue": 357090, "llaima": 357110, "villarrica": 357120,
}

TRACE_META = {
    "swir":    {"label": "S2 SWIR Hot-spot [npix]", "color": "#e8501a", "product": "s2"},
    "so2":     {"label": "SO₂ [toneladas]",          "color": "#f5c518", "product": "s5p"},
    "def_asc": {"label": "Deformación Asc [m std]",  "color": "#1a78c2", "product": "s1"},
    "def_desc":{"label": "Deformación Desc [m std]", "color": "#6fb1e8", "product": "s1"},
    "int_asc": {"label": "Intensidad Asc",            "color": "#52b788", "product": "s1"},
    "coh_asc": {"label": "Coherencia Asc",            "color": "#95d5b2", "product": "s1"},
}

PRODUCT_ICONS = {"S2_hotspot": "🌡️", "S5P_SO2": "💨", "S1_ifg": "📡",
                 "S1_intensity": "📡", "S1_coherence": "📡", "S1_disp": "📡", "S2_RGB_NIR": "🌡️"}

# ─── Carga de datos ──────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_catalog() -> pd.DataFrame:
    if not CATALOG_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(CATALOG_FILE, parse_dates=["image_timestamp"])
    df["image_timestamp"] = pd.to_datetime(df["image_timestamp"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_timeseries(volcano_key: str) -> dict | None:
    f = TIMESERIES_DIR / f"{volcano_key}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


@st.cache_data(ttl=600)
def load_home_stats() -> pd.DataFrame:
    """Lee estadísticas actuales de mounts-project.com/home."""
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(f"{MOUNTS_BASE}/home", timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tr")
        data = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            country = cells[2].get_text(strip=True)
            if "Chile" not in country:
                continue
            link = cells[1].find("a")
            data.append({
                "id":      cells[0].get_text(strip=True),
                "name":    cells[1].get_text(strip=True),
                "country": country,
                "so2":     cells[3].get_text(strip=True) or "0",
                "thermal": cells[4].get_text(strip=True) or "0",
                "deform":  cells[5].get_text(strip=True) or "0",
                "latest":  cells[6].get_text(strip=True),
                "url":     link["href"] if link else "",
            })
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def get_local_image(volcano_key: str, product_type: str, n: int = 1) -> list[Path]:
    """Devuelve las N imágenes más recientes de un volcán y producto."""
    vol_dir = DATA_DIR / volcano_key
    if not vol_dir.exists():
        return []
    pngs = sorted(vol_dir.rglob("*.png"), reverse=True)
    filtered = [p for p in pngs if product_type.lower() in p.name.lower()]
    return filtered[:n]


# ─── Componentes de UI ───────────────────────────────────────────────────────

def render_status_badge(value: str | float, thresholds: tuple) -> str:
    try:
        v = float(value)
    except (ValueError, TypeError):
        return "⚪"
    if v == 0:
        return "🟢"
    if v <= thresholds[0]:
        return "🟡"
    if v <= thresholds[1]:
        return "🟠"
    return "🔴"


def render_timeseries_chart(ts_data: dict, selected_traces: list[str]) -> go.Figure:
    fig = make_subplots(
        rows=len(selected_traces), cols=1,
        shared_xaxes=True,
        subplot_titles=[TRACE_META.get(t, {}).get("label", t) for t in selected_traces],
        vertical_spacing=0.04,
    )
    traces_map = {t["name"]: t for t in ts_data.get("traces", [])}

    for i, tname in enumerate(selected_traces, 1):
        trace = traces_map.get(tname)
        if trace is None:
            continue
        meta = TRACE_META.get(tname, {})
        color = meta.get("color", "#888")
        x = trace.get("x", [])
        y = trace.get("y", [])
        text = trace.get("text", [])

        hover = [
            f"<b>{xi}</b><br>Valor: {yi}"
            + (f"<br><a href='{MOUNTS_BASE}/static/{tx}'>Ver imagen</a>" if tx else "")
            for xi, yi, tx in zip(x, y, text or [""] * len(x))
        ]

        fig.add_trace(
            go.Scatter(
                x=x, y=y,
                name=meta.get("label", tname),
                mode="markers+lines",
                line={"color": color, "width": 1},
                marker={"size": 4, "color": color},
                hovertext=hover,
                hoverinfo="text",
                showlegend=False,
            ),
            row=i, col=1,
        )

    fig.update_layout(
        height=250 * len(selected_traces),
        margin={"l": 50, "r": 20, "t": 30, "b": 30},
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font={"color": "#e0e0e0"},
    )
    fig.update_xaxes(gridcolor="#333", zeroline=False)
    fig.update_yaxes(gridcolor="#333", zeroline=False)
    return fig


# ─── Páginas ─────────────────────────────────────────────────────────────────

def page_resumen():
    st.title("🌋 MOUNTS-Chile — Resumen")
    st.caption("Volcanes chilenos monitoreados por Sentinel-1/2/5P · Actualizado en tiempo real")

    # Tabla live desde mounts-project.com
    with st.spinner("Cargando estado actual desde MOUNTS…"):
        df_live = load_home_stats()

    if df_live.empty:
        st.warning("No se pudo conectar a mounts-project.com. Mostrando datos locales.")
    else:
        st.subheader("Estado actual (live)")

        # Colorear con emojis
        df_display = df_live.copy()
        df_display["SO₂"] = df_display.apply(
            lambda r: render_status_badge(r["so2"], (100, 1000)) + " " + r["so2"] + " t", axis=1)
        df_display["Térmico"] = df_display.apply(
            lambda r: render_status_badge(r["thermal"], (10, 100)) + " " + r["thermal"] + " px", axis=1)
        df_display["Deformación"] = df_display.apply(
            lambda r: render_status_badge(r["deform"], (0.005, 0.03)) + " " + r["deform"] + " m", axis=1)
        df_display["Último dato"] = df_display["latest"]
        df_display["Volcán"] = df_display.apply(
            lambda r: f"[{r['name']}]({r['url']})" if r["url"] else r["name"], axis=1)
        df_display["País"] = df_display["country"]

        st.dataframe(
            df_display[["Volcán", "País", "SO₂", "Térmico", "Deformación", "Último dato"]],
            use_container_width=True, hide_index=True,
        )

    # Catálogo local
    catalog = load_catalog()
    if catalog.empty:
        st.info("Catálogo local vacío. Ejecuta `python scraper.py` para descargar imágenes.")
        return

    st.subheader("Imágenes descargadas localmente")
    summary = (
        catalog.groupby(["volcano_name", "product_type"])
        .size().reset_index(name="count")
        .pivot(index="volcano_name", columns="product_type", values="count")
        .fillna(0).astype(int)
    )
    st.dataframe(summary, use_container_width=True)

    total = len(catalog)
    st.metric("Total imágenes locales", total)


def page_volcan(volcano_key: str):
    name_display = VOLCANO_NAMES.get(volcano_key, volcano_key)
    sid = VOLCANO_IDS.get(volcano_key, "")
    st.title(f"🌋 {name_display}")
    st.caption(f"Smithsonian ID: {sid} · [Ver en MOUNTS]({MOUNTS_BASE}/timeseries/{sid})")

    ts_data = load_timeseries(volcano_key)
    catalog = load_catalog()

    # ── Series temporales
    st.subheader("📈 Series temporales")
    if ts_data is None:
        st.warning("Sin datos de series temporales. Ejecuta el scraper primero.")
    else:
        available_traces = [t["name"] for t in ts_data["traces"] if t.get("y")]
        display_traces = [t for t in ["swir", "so2", "def_asc", "def_desc"] if t in available_traces]

        with st.expander("Seleccionar trazas", expanded=False):
            selected = st.multiselect(
                "Trazas a mostrar",
                options=available_traces,
                default=display_traces,
                format_func=lambda t: TRACE_META.get(t, {}).get("label", t),
            )
        if selected:
            fig = render_timeseries_chart(ts_data, selected)
            st.plotly_chart(fig, use_container_width=True)
            fetched = ts_data.get("fetched_at", "")
            if fetched:
                st.caption(f"Datos descargados: {fetched[:19]} UTC")

    # ── Imágenes locales más recientes
    st.subheader("🖼️ Imágenes recientes (local)")
    vol_df = catalog[catalog["volcano_name"] == volcano_key] if not catalog.empty else pd.DataFrame()

    if vol_df.empty:
        st.info("Sin imágenes locales. Ejecuta `python scraper.py`.")
    else:
        product_types = vol_df["product_type"].unique().tolist()
        tab_labels = [PRODUCT_ICONS.get(p, "📷") + " " + p for p in product_types]
        tabs = st.tabs(tab_labels)

        for tab, ptype in zip(tabs, product_types):
            with tab:
                prod_df = (
                    vol_df[vol_df["product_type"] == ptype]
                    .dropna(subset=["image_timestamp"])
                    .sort_values("image_timestamp", ascending=False)
                )
                n_show = st.slider(f"Nº imágenes ({ptype})", 1, min(20, len(prod_df)), 4, key=f"{volcano_key}_{ptype}")
                cols = st.columns(min(n_show, 4))
                for i, (_, row) in enumerate(prod_df.head(n_show).iterrows()):
                    img_path = Path(row["local_path"])
                    ts = str(row["image_timestamp"])[:10]
                    with cols[i % 4]:
                        if img_path.exists():
                            st.image(str(img_path), caption=ts, use_container_width=True)
                        else:
                            st.markdown(f"[{ts}]({row['url']})")

    # ── Enlace directo MOUNTS
    st.divider()
    st.markdown(f"🔗 [Abrir en MOUNTS]({MOUNTS_BASE}/timeseries/{sid})")


# ─── App principal ────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="MOUNTS-Chile",
        page_icon="🌋",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    with st.sidebar:
        st.title("🌋 MOUNTS-Chile")
        st.caption("Volcanes chilenos · Sentinel 1/2/5P")
        st.divider()

        page = st.radio(
            "Vista",
            ["Resumen general"] + [VOLCANO_NAMES[k] for k in VOLCANO_NAMES],
            label_visibility="collapsed",
        )
        st.divider()
        st.markdown("**Fuente**: [mounts-project.com](http://www.mounts-project.com)")
        st.markdown("**Repo**: VRP-Chile / MOUNTS")
        st.caption(f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")

        if st.button("🔄 Limpiar caché"):
            st.cache_data.clear()
            st.rerun()

    if page == "Resumen general":
        page_resumen()
    else:
        key = {v: k for k, v in VOLCANO_NAMES.items()}[page]
        page_volcan(key)


if __name__ == "__main__":
    main()
