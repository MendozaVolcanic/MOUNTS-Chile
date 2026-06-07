"""
Constantes compartidas y helpers basicos del dashboard MOUNTS-Chile.

Centraliza paths, catalogo de volcanes, paletas de severidad y configuracion
de trazas/ejes Plotly para evitar duplicacion entre los modulos del paquete.
Extraido de generar_html.py (refactor C2) sin cambios de valores.
"""

from pathlib import Path

# Raiz del proyecto (el paquete dashboard/ vive un nivel adentro)
ROOT = Path(__file__).resolve().parent.parent

BASE      = "https://www.mounts-project.com/static"
TS_DIR    = ROOT / "timeseries"
LATEST    = ROOT / "latest"
DATA_DIR  = ROOT / "data"
OUT       = ROOT / "latest.html"

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

# Ranking ordinal de severidad (para comparar "subio" / "bajo" vs ayer)
SEV_RANK = {"gray": 0, "stale": 0, "green": 1, "yellow": 2, "orange": 3, "red": 4}

# Productos en el status matrix
STATUS_PRODUCTS = ["SWIR", "SO2", "DEF", "COH"]

# Sufijos de imagen -> (etiqueta, orden)
IMG_PRODUCTS = [
    ("_B4B3B2+B12B11B8A", "S2 RGB visible"),   # nuevo: true color
    ("_SO2_PBL",          "SO2 TROPOMI"),
    ("_B12B11B8A_nir",    "S2 SWIR"),
    ("_VV_disp",          "S1 InSAR disp"),
    ("_VV_int_fcnn",      "S1 Intensidad"),
    ("_VV_coh",           "S1 Coherencia"),
]

# Mapa de trazas: nombre -> (yaxis_id, color, mode, dash, symbol, fill)
# Replicando exactamente el layout de mounts-project.com
TRACES_CFG = {
    # Panel 1 (top): SO2 mass [tons] - log
    "so2":       ("y3", "#9467bd", "markers",       None,   None,          None),
    "tbar_so2":  ("y3", "red",     "lines+markers", None,   None,          None),
    # Panel 2: Thermal anomalies [N pix S2Pix] - log
    "swir":      ("y2", "#ff7f0e", "markers",       None,   None,          None),
    "tbar_nir":  ("y2", "red",     "lines+markers", None,   None,          None),
    # Panel 3: Deformation st.dev [m LOS] - linear
    "def_asc":   ("y5", "#ea898a", "lines+markers", None,   "circle-open", None),
    "def_desc":  ("y5", "#c0392b", "lines+markers", None,   "circle",      None),
    "tbar_disp": ("y5", "red",     "lines+markers", None,   None,          None),
    # Panel 4: Coherence (N pix<0.5) - linear
    "coh_asc":   ("y1", "#aed6f1", "lines+markers", None,   "circle-open", None),
    "coh_desc":  ("y1", "#2980b9", "lines+markers", None,   "circle",      None),
    "tbar_coh":  ("y1", "red",     "lines+markers", None,   None,          None),
}

# 4 paneles compactos (saco SAR placeholders int_*: eran y=0 sin valor numerico real)
YAXES_CFG = {
    "y3": {"title": "SO2 [tons]",           "type": "log",    "domain": [0.78, 1.00], "color": "#9467bd"},
    "y2": {"title": "Thermal [S2Pix]",      "type": "log",    "domain": [0.52, 0.76], "color": "#ff7f0e"},
    "y5": {"title": "Deform st.dev [m]",    "type": "linear", "domain": [0.26, 0.50], "color": "#ea898a"},
    "y1": {"title": "Coherence (N<0.5)",    "type": "linear", "domain": [0.00, 0.24], "color": "#2980b9"},
}


def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
