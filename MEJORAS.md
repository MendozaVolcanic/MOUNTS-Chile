# Mejoras para el scraper MOUNTS-Chile

Lista priorizada (alto impacto / bajo esfuerzo arriba). Cada una con justificación
técnica y archivo donde implementarla.

---

## 🟢 Quick wins (1–2 h cada uno)

### 1. Auto-update con GitHub Actions
**Por qué**: hoy hay que correr `fetch_latest.py` + `generar_html.py` + `git push` a mano.
Con un workflow programado, el sitio se actualiza solo cada 6 h sin intervención.
**Cómo**: `.github/workflows/update.yml` con cron `0 */6 * * *` que corra
fetch → export_csv → generar_html → commit. Imágenes en `latest/` y CSVs se
versionan en cada update; los JSONs son chicos (~30 MB total).

### 2. Cache HTTP con `If-Modified-Since` / ETag
**Por qué**: `fetch_latest.py` baja 7 HTML completos (~2 MB c/u) cada vez,
incluso si no cambiaron. Con cache condicional bajamos a ~7 HEAD requests
cuando no hay update.
**Cómo**: guardar `Last-Modified` por volcán en `cache/<volcan>.headers.json`,
mandarlo en próximo request, hacer 304-aware.

### 3. Detección de gaps + backfill automático
**Por qué**: si el cron falla o un volcán pierde una semana, hoy no hay manera
de saberlo sin abrir el JSON.
**Cómo**: en `fetch_latest.py`, después de bajar, comparar fecha máxima vs
expected (S5P: ahora-1d, S2: ahora-5d, S1: ahora-12d). Si hay gap, log warning
con el delta. Sumar `--backfill` flag que fuerza re-descarga del archive completo
para llenar.

### 4. Logging estructurado (JSON lines)
**Por qué**: hoy `log.info(...)` va a stdout. Para diagnosticar fallos en CI/cron
necesitamos timestamps + nivel + contexto parseable.
**Cómo**: `logging` con `python-json-logger`, archivo `logs/scraper.log` rotado
por día.

### 5. Validación con `pydantic` / `dataclass` de los JSONs
**Por qué**: hoy si MOUNTS cambia el formato Plotly, fallamos en runtime con
KeyError críptico. Un schema explícito da error temprano.
**Cómo**: `models.py` con `TimeseriesData(BaseModel)` y validar después del
parse.

---

## 🟡 Valor científico (medio esfuerzo)

### 6. Detección de anomalías (z-score + change-point)
**Por qué**: las trazas tienen ruido de fondo (fumarolas residuales, falsos
positivos por nubes). Para alertar OVDAS necesitamos un detector que ignore
ese baseline.
**Cómo**: módulo `anomalies.py` que para cada serie:
  - Computa rolling median ± 3*MAD (robust z-score)
  - Marca puntos que excedan
  - Compara con `tbar_*` (eventos GVP) — TPR/FPR del detector
  - Salida: `anomalies/<volcan>.csv` con timestamps de anomalías propias

### 7. Cross-sensor fusion: S2Pix ↔ VRP MIROVA
**Por qué**: tu repo VRP-chile tiene VRP en watts (MODIS/VIIRS).
MOUNTS tiene S2Pix (Sentinel-2). Massimetti+ 2020 mostró que correlacionan
pero a distinta resolución temporal/espectral. Ploteándolos juntos por
volcán, validamos ambos y detectamos divergencias (= cobertura nubosa
en uno, evento real en otro).
**Cómo**: `cross_sensor.py` que carga `csv/<vol>_thermal_swir.csv` +
`../VRP-chile/data/<vol>_vrp.csv`, alinea por fecha (interp/nearest), genera
plot + Pearson r + MAE. Ideal para tu paper de SERNAGEOMIN.

### 8. Georeferenciación de PNGs
**Por qué**: las imágenes `_B12B11B8A_nir.png` son rasters sin georreferencia
explícita en el archivo. Pero MOUNTS las genera siempre con el **mismo bbox por
volcán**, así que se puede inferir.
**Cómo**: para cada volcán, hacer una vez `inspect_aoi.py` que descarga 3
imágenes de distintas fechas, las compara visualmente, y deduce el bbox
geográfico (lat/lon corners). Guardar en `aoi.json`. Luego cualquier imagen
se puede convertir a GeoTIFF con `rasterio` y overlay en QGIS / Folium.

### 9. Series sismológicas/GNSS desde fuentes oficiales
**Por qué**: MOUNTS no incluye sismicidad ni GNSS. SERNAGEOMIN tiene RNVV
(Red Nacional de Vigilancia Volcánica). Sumar datos de OVDAS al dashboard
hace que sea utilizable para guardia 24×7.
**Cómo**: módulo `sismo_ovdas.py` que pega de la web pública de OVDAS
(o pide API a Diego/Rodrigo) número de eventos VT/LP/TR diarios, los une al
CSV consolidado por fecha+volcán.

---

## 🔴 Estructural (mayor esfuerzo, alto retorno)

### 10. Migración a base de datos (SQLite)
**Por qué**: 36 CSVs + 7 JSONs + 2190 PNGs no escala. Una DB con índices
permite queries rápidas: "todas las anomalías SWIR > 50 px en últimos 30 días"
es trivial vs parsear 7 CSVs.
**Cómo**: SQLite local (`mounts.db`). Tablas: `volcanoes`, `observations`
(date, volcano_id, product, value, unit, image_path), `events` (tbar), `aoi`.
Migrar los CSVs como bootstrap. Dashboard Streamlit/HTML lee de DB.

### 11. Pipeline de imágenes: thumbnails + diff entre fechas
**Por qué**: el dashboard hoy muestra una imagen reciente por producto. Más
útil sería: thumbnail + comparación con la anterior (diff) para ver el
cambio (ej. nuevo punto caliente, nuevo lóbulo de lava).
**Cómo**: `imgproc.py` con `Pillow` + `numpy`. Para SWIR: diff |new - prev|
luego threshold → genera `latest/<vol>/<product>_diff.png`. Lo incluís en
el HTML.

### 12. Reportes PDF semanales por volcán
**Por qué**: para circulación interna OVDAS, un PDF con plots + tabla de
eventos + interpretación es más útil que la web. Si volvés del terreno y
hubo actividad, querés un PDF que repase la semana.
**Cómo**: `report.py` con `matplotlib` + `reportlab` o `weasyprint`. Cron
semanal genera `reports/<volcan>_<YYYY-WW>.pdf`. Sumás al repo o mandás
por email.

### 13. Webhook a Telegram/Slack en eventos
**Por qué**: monitoreo 24×7 sin notificación es ineficaz. Si Villarrica
SWIR pasa de 5 → 80 px en 24 h, querés saberlo en el celular.
**Cómo**: `notifier.py` que después de cada update revisa los outputs del
detector de anomalías (#6) y manda a Telegram bot con el plot adjunto.

### 14. Tests unitarios + CI
**Por qué**: hoy si refactorizás `extract_image_paths()` y rompés algo, te
enterás cuando el dashboard se ve raro. Tests previenen regresiones.
**Cómo**: `pytest` con fixtures de HTML mockeado en `tests/fixtures/`.
Coverage objetivo: parsers (extract_*, classify, parse_timestamp) ~90 %.
Workflow CI corre tests en cada PR.

---

## ❄️ Wishlist (proyectos)

- **Comparación MOUNTS vs reportes oficiales SERNAGEOMIN**: scrapear los
  REAV (Reportes Especiales de Actividad Volcánica) y cruzarlos con eventos
  tbar de MOUNTS. ¿Cuántos REAV emitidos coinciden con anomalía MOUNTS?
  ¿Hay anomalías MOUNTS sin REAV? → estudio de falsos negativos OVDAS.
- **InSAR multi-temporal con MintPy**: bajar los SLCs originales de Copernicus
  y procesar con MintPy time-series para cada volcán, en lugar de depender
  de los DEF scores agregados de MOUNTS. Mucha más resolución espacial.
- **Hot-spot detection propio con S2 L2A**: bajar L2A de Copernicus,
  reimplementar Massimetti+ 2020 con tu AOI personalizado (no el bbox de
  MOUNTS). Útil si necesitás cubrir cráteres secundarios fuera del AOI MOUNTS.

---

## Dependencias técnicas

Si bajás el orden de la lista, cosas que faltan en `requirements.txt`:

```
# Core actual
requests
beautifulsoup4
streamlit
plotly
pandas

# Mejoras propuestas
pydantic         # #5 validación
python-json-logger # #4
numpy            # #6 z-score
scipy            # #6 change-point
rasterio         # #8 GeoTIFF
folium           # visualización mapa
matplotlib       # #12 reportes
reportlab        # #12 PDF
python-telegram-bot # #13
pytest           # #14
```
