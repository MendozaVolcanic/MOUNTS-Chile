# MOUNTS-Chile

Mirror y dashboard unificado de los **7 volcanes chilenos** monitoreados por
[MOUNTS](https://www.mounts-project.com) (Valade et al. 2019, TU Berlin / GFZ /
UNAM): térmico Sentinel-2 SWIR, SO₂ Sentinel-5P TROPOMI, deformación InSAR
Sentinel-1.

## 🌐 Dashboard en vivo

**👉 [https://mendozavolcanic.github.io/MOUNTS-Chile/](https://mendozavolcanic.github.io/MOUNTS-Chile/)**

Vista única con las 5 series temporales + últimas imágenes por volcán, sin
saltar entre páginas. Replica el layout de mounts-project.com pero todo
visible de un solo scroll.

## Volcanes monitoreados

| Volcán | Smithsonian ID | Región |
|---|---|---|
| Láscar | 355100 | Antofagasta |
| Planchón-Peteroa | 357040 | Maule (frontera AR) |
| Laguna del Maule | 357061 | Maule |
| Nevados de Chillán | 357070 | Ñuble |
| Copahue | 357090 | Bío-Bío (frontera AR) |
| Llaima | 357110 | Araucanía |
| Villarrica | 357120 | Araucanía / Los Ríos |

## ¿Qué hace este repo?

1. **Scraper** (`scraper.py`, `fetch_latest.py`): extrae las series Plotly
   embebidas en el HTML de mounts-project.com (no hay API oficial), descarga
   las imágenes PNG (S2 SWIR, S5P SO₂, S1 InSAR/coherencia) y guarda los
   datos numéricos en `timeseries/<volcan>.json`.

2. **Exportador CSV** (`export_csv.py`): convierte los JSONs a CSVs estilo
   VRP-MIROVA (`csv/<volcan>_<producto>.csv` + consolidados `all_*.csv`).
   14 590 filas SO₂, 3 966 filas térmicas, 90 eventos.

3. **Dashboard estático** (`generar_html.py`): genera `index.html` con las
   5 gráficas Plotly y las imágenes recientes de los 7 volcanes. Se sirve
   vía GitHub Pages.

4. **Dashboard interactivo** (`dashboard.py`): app Streamlit local con vista
   por volcán, filtros, comparación entre series.

## Uso rápido

```bash
# Instalar deps
pip install -r requirements.txt

# Pipeline completo (fetch + anomalies + diffs + csv + html), ~1 min
python update.py

# O paso por paso:
python fetch_latest.py    # bajar timeseries + imágenes (~1 min)
python anomalies.py       # status board + alertas
python image_diff.py      # diffs antes/después SWIR
python export_csv.py      # CSVs estilo VRP
python generar_html.py    # dashboard HTML (index.html + map.html)

# Si ya bajaste antes y solo querés regenerar:
python update.py --skip-fetch

# Dashboard interactivo Streamlit (alternativa local)
streamlit run dashboard.py
```

## Qué muestra el dashboard

1. **Status board**: matriz 7×4 (volcanes × productos SWIR/SO₂/DEF/COH) con z-score MAD-robusto vs baseline 90 d, sparklines SVG y código de color.
2. **Filtro temporal global** (header): 30 d / 90 d / 1 a / todo — ajusta el rango X de todos los charts simultáneamente.
3. **Alertas recientes** (últimos 30 d): tabla ordenada por severidad. Distingue **anomalías persistentes** (≥3 detecciones consecutivas, alta confianza) de **transientes** (1 punto aislado, podría ser nube/incendio).
4. **Multi-product alerts (cross-sensor)**: tabla con eventos donde ≥2 productos del mismo volcán muestran anomalía dentro de 14 d. Filtra falsos positivos drásticamente — un evento SO₂ + SWIR simultáneo es casi siempre real.
5. **Histórico de anomalías**: catálogo completo persistido en `mounts.db` con stats globales y validación detector-vs-eventos-GVP.
6. **Streamgraph SO₂ y SWIR multi-volcán**: serie regional apilada (suma mensual por volcán). Detecta eventos sincrónicos o transferencias entre volcanes vecinos.
7. **Mapa de Chile**: los 7 volcanes geolocalizados (Folium dark theme), coloreados por severidad agregada, popup con detalle de productos.
8. **Vista por volcán**: 4 paneles Plotly (SO₂, SWIR, Deformación, Coherencia) con bandas baseline ±3σ sombreadas y estrellas rojas en anomalías; columna lateral con últimas imágenes.
9. **Comparación temporal SWIR** (antes/después/diff): por volcán, las 2 imágenes S2 SWIR más recientes + su diferencia absoluta — resalta puntos calientes nuevos.

## Auto-update

GitHub Actions corre el pipeline cada 6 h ([`.github/workflows/update.yml`](.github/workflows/update.yml)):
- cron: `17 */6 * * *` (UTC)
- workflow_dispatch para trigger manual
- commitea solo si hay cambios (con `[skip ci]` para no triggerear builds)

## Notificaciones Telegram (opcional)

Cuando se detectan anomalías nuevas, manda mensaje al bot. Setup:

1. **Crear bot**: en Telegram, chat con `@BotFather`:
   ```
   /newbot
   nombre: MOUNTS Chile Bot
   username: mounts_chile_bot
   ```
   Anota el TOKEN.

2. **Obtener chat ID**: agregá el bot a un grupo (o chateá directo). Luego visitá:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → copiar `result[0].message.chat.id`.

3. **Configurar secrets en GitHub** (Settings → Secrets and variables → Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

4. **Test local**:
   ```bash
   export TELEGRAM_BOT_TOKEN=...
   export TELEGRAM_CHAT_ID=...
   python notify_telegram.py --test           # mensaje de prueba
   python notify_telegram.py --dry-run         # ve qué enviaría
   ```

Si los secrets no están configurados, el step es no-op (no falla el pipeline).

## Endpoints estables

Ver [API.md](API.md) — JSON/SQLite/CSV consumibles por máquinas:
- `status.json` — estado actual (status board)
- `alerts.json` — anomalías últimos 30 d
- `multi_alerts` (en `mounts.db`) — eventos cross-sensor
- `mounts.db` — base de datos completa
- `csv/*.csv` — series temporales VRP-style

## Base de datos histórica

`mounts.db` (SQLite) se actualiza en cada `update.py`. Esquema:

| Tabla | Propósito |
|---|---|
| `volcanoes` | 7 volcanes con coordenadas + Smithsonian ID |
| `observations` | todas las muestras numéricas (22 K filas, idempotente por `(volcano, product, date)`) |
| `anomalies` | anomalías detectadas por z-score MAD-robusto, con `detected_at` para auditoría |
| `events` | flags `tbar_*` ingestados de GVP/USGS — usados como ground truth |
| `status_history` | snapshot del status board en cada update |
| `metadata` | timestamp del último update |

Queries directas:

```bash
python db.py summary              # estadísticas globales
python db.py recent --n 20        # últimas 20 anomalías detectadas
python db.py top --n 30           # top 30 históricas por z-score
python db.py validate --days 7    # TPR del detector vs GVP (ventana ±N días)
python db.py export               # anomalies.csv
```

Disponible para descarga vía GitHub Pages: [`mounts.db`](https://mendozavolcanic.github.io/MOUNTS-Chile/mounts.db).

## Estructura

```
MOUNTS-Chile/
├── README.md              ← este archivo
├── METHODOLOGY.md         ← procedencia de los datos (papers, algoritmos, unidades)
├── MEJORAS.md             ← roadmap de 14 mejoras priorizadas
│
├── update.py              ← orquestador pipeline completo
├── scraper.py             ← scraper completo (archivo histórico)
├── fetch_latest.py        ← scraper rápido (últimas N imágenes)
├── anomalies.py           ← detector z-score robusto + status board
├── image_diff.py          ← genera diffs antes/después SWIR
├── db.py                  ← base de datos SQLite (histórico)
├── export_csv.py          ← JSONs → CSVs estilo VRP
├── generar_html.py        ← genera index.html + map.html (dashboard)
├── dashboard.py           ← dashboard Streamlit interactivo
│
├── timeseries/            ← JSONs Plotly por volcán (numérico)
├── csv/                   ← CSVs exportados (per-volcán + consolidados)
├── latest/                ← imágenes más recientes + diffs (GitHub Pages)
├── data/                  ← archivo histórico de imágenes (gitignored)
│
├── status.json            ← estado actual por volcán/producto
├── alerts.json            ← anomalías últimos 30 d
├── diffs.json             ← índice de imágenes diff
├── mounts.db              ← base de datos SQLite (histórico completo)
├── anomalies.csv          ← export del catálogo histórico
├── index.html             ← dashboard estático (GitHub Pages)
├── map.html               ← mapa Folium embebido en dashboard
└── catalog.csv            ← índice de imágenes descargadas
```

## Datos disponibles

Cada `timeseries/<volcan>.json` tiene 13 trazas Plotly. Resumen de unidades
(detalle completo en [METHODOLOGY.md](METHODOLOGY.md)):

| Traza | Producto | Unidad | Sensor |
|---|---|---|---|
| `swir` | Hot-spot térmico | **N° píxeles (S2Pix)** ⚠️ no es VRP en watts | Sentinel-2 (B12+B11+B8A) |
| `so2` | Masa SO₂ | **toneladas** | Sentinel-5P TROPOMI |
| `def_asc` / `def_desc` | Deformación InSAR | **metros LOS** | Sentinel-1 (asc + desc) |
| `coh_asc` / `coh_desc` | Coherencia | **N° píxeles coh<0.5** | Sentinel-1 |
| `int_asc` / `int_desc` | Intensidad backscatter | placeholder | Sentinel-1 VV |
| `tbar_*` | Eventos | banderas verticales | GVP + USGS (curado manual) |

## Limitaciones conocidas

- **MOUNTS no tiene API oficial** — todo viene de scrapear HTML+Plotly.
- **`swir` ≠ VRP MIROVA**: son métricas distintas (N° píxeles vs watts radiantes).
  Para VRP en watts, usar el repo hermano [VRP-chile](https://github.com/MendozaVolcanic/VRP-chile).
- **mounts-project.com solo sirve HTTP** (puerto 443 cerrado) — por eso las
  imágenes en el dashboard se sirven desde `latest/` del repo, no externamente.
- **AOI fijo por volcán**: si la pluma o deformación se sale del bbox de MOUNTS,
  no se ve.
- **C-band InSAR**: decorrelación severa en Villarrica/Llaima (vegetación, nieve).

Detalle completo en [METHODOLOGY.md](METHODOLOGY.md).

## Roadmap

Ver [MEJORAS.md](MEJORAS.md) — 14 mejoras priorizadas (auto-update GitHub
Actions, detector de anomalías z-score, fusion cross-sensor S2Pix ↔ VRP MIROVA,
georef de PNGs, SQLite, reportes PDF, webhooks).

## Referencias

- **Valade et al. 2019** — *Towards Global Volcano Monitoring Using Multisensor
  Sentinel Missions and Artificial Intelligence: The MOUNTS Monitoring System.*
  Remote Sensing 11(13), 1528. [doi:10.3390/rs11131528](https://doi.org/10.3390/rs11131528)
- **Massimetti et al. 2020** — *Volcanic Hot-Spot Detection Using Sentinel-2: A
  Comparison with MODIS–MIROVA Thermal Data Series.* Remote Sensing 12(5), 820.
  [doi:10.3390/rs12050820](https://doi.org/10.3390/rs12050820)
- [mounts-project.com](https://www.mounts-project.com)
- [Smithsonian GVP](https://volcano.si.edu/) (IDs de los volcanes)

## Contexto

Parte del ecosistema [Volcanología SERNAGEOMIN](../) — monitoreo satelital
integrado para OVDAS:

| Repo | Sensor | Unidad |
|---|---|---|
| **MOUNTS-Chile** (este) | S1/S2/S5P | S2Pix, tons SO₂, m LOS |
| [VRP-chile](https://github.com/MendozaVolcanic/VRP-chile) | MODIS/VIIRS térmico | VRP (watts) |
| OpenVIS | Infrasonido OVDAS | dB |

Objetivo: dashboard unificado térmico + gases + deformación + infrasonido,
independiente de mirovaweb.it.

## Licencia / Atribución

Datos: © Copernicus / ESA (Sentinel-1/2/5P) vía MOUNTS (Valade et al.).
Código: MIT. Mantenido por **Nicolás Mendoza** (geólogo, SERNAGEOMIN).
