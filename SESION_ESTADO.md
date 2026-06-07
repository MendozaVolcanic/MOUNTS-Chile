# MOUNTS-Chile — Estado del proyecto para continuación

> Última actualización: 2026-06-07 · Última sesión: implementación V1 + V2 + V8

Este archivo es el **snapshot canónico** del estado del proyecto. Si abrís una
sesión nueva con Claude Code, leé esto primero (la próxima sesión debería
empezar con `cat SESION_ESTADO.md` o equivalente).

---

## Qué es este proyecto

**Mirror + dashboard operacional** de los 7 volcanes chilenos monitoreados por
[mounts-project.com](http://www.mounts-project.com) (Valade et al. 2019,
TU Berlin / GFZ / UNAM).

- **Volcanes**: Láscar (355100), Planchón-Peteroa (357040), Laguna del Maule
  (357061), Nevados de Chillán (357070), Copahue (357090), Llaima (357110),
  Villarrica (357120).
- **Sensores extraídos**: S1 InSAR (def + coh + intensity), S2 SWIR hot-spot
  (S2Pix), S5P TROPOMI SO₂.
- **Dashboard**: https://mendozavolcanic.github.io/MOUNTS-Chile/
- **Repo**: https://github.com/MendozaVolcanic/MOUNTS-Chile

**Usuario**: Nicolás Mendoza, geólogo SERNAGEOMIN (Chile). Comunicación en
español, "por qué" antes que "cómo".

---

## Estado actual del código

### Estructura

```
MOUNTS-Chile/
├── README.md              docs principales + setup Telegram
├── METHODOLOGY.md         procedencia de datos (papers, unidades)
├── API.md                 endpoints estables (JSON/SQLite/CSV)
├── MEJORAS.md             roadmap histórico
├── SESION_ESTADO.md       este archivo
│
├── update.py              orquestador del pipeline (10 pasos)
├── fetch_latest.py        scraper rápido paralelo (cache HTTP, gzip, backoff)
├── scraper.py             archivo histórico completo (NO integrado al pipeline)
├── monitor_upstream.py    detecta cambios en /news /about /targets + schema
├── anomalies.py           detector z-score MAD-robusto + persistence detection
├── sync_latest.py         copia últimas imágenes a latest/<volcan>/
├── image_diff.py          genera diffs antes/después SWIR + retention 30d
├── quality.py             gap analysis + drift detection
├── db.py                  SQLite ingest + multi-product alerts + queries CLI
├── notify_telegram.py     webhook alertas a bot Telegram (opcional)
├── export_csv.py          JSONs → CSVs estilo VRP
├── generar_html.py        ⚠ 1300+ LOC, dios-archivo, refactor pendiente (C2)
├── dashboard.py           dashboard Streamlit interactivo (alternativa local)
│
├── timeseries/            JSONs Plotly por volcán (numérico)
├── csv/                   CSVs por volcán + consolidados + events
├── latest/                imágenes recientes servidas por GH Pages
├── raw/                   HTML upstream versionado (gzip) — reproducibilidad
├── data/                  archivo histórico (gitignored)
├── .cache/                cache HTTP (gitignored)
│
├── mounts.db              SQLite — 22K obs, 738+ anomalías, 38 multi-alerts
├── status.json            estado actual por (volcán, producto)
├── alerts.json            anomalías últimos 30 d
├── multi_alerts en DB     cross-sensor confirmadas
├── upstream_state.json    hashes + citation MOUNTS
├── upstream_changes.json  log de cambios upstream (vacío hasta que MOUNTS cambie)
├── quality.json           gap analysis + drift events
├── diffs.json             índice de imágenes diff
├── anomalies.csv          export del catálogo histórico
├── index.html             dashboard principal (GH Pages)
├── map.html               mapa Folium embebido
└── .github/workflows/update.yml  cron cada 6h
```

### Pipeline

```bash
python update.py            # ~43s con fetch (10 pasos)
python update.py --skip-fetch    # ~25s solo regeneración
```

Pasos: `fetch_latest → monitor_upstream → anomalies → sync_latest → image_diff
→ quality → db → notify_telegram → export_csv → generar_html`.

### Features del dashboard actual

1. **Bulletin operacional** (V1) — una línea por volcán, color-coded
2. **Status board 7×4** con sparklines, severidad, edad
3. **Diff vs ayer** (V2) — badges de cambio en cada celda
4. **Filtro temporal** 30d/90d/1a/todo (Plotly relayout)
5. **Estado upstream MOUNTS** — citation, hashes, métricas calidad
6. **Alertas recientes** (últimos 30d)
7. **Multi-producto cross-sensor** (37+ eventos históricos)
8. **Catálogo histórico** (top 20 por z-score, expandible)
9. **Streamgraph SO₂ + SWIR multi-volcán** (suma mensual)
10. **Mapa Chile** Folium con markers por severidad
11. **Vista por volcán**: 4 paneles Plotly con baseline ±3σ + anomaly stars
12. **Image-diff SWIR**: antes/después/diff por volcán

---

## Quirks importantes (memorizar)

1. **mounts-project.com solo acepta HTTP** (port 443 cerrado). `BASE_URL =
   "http://www.mounts-project.com"`. GH Pages es HTTPS → las imágenes se
   sirven locales desde `latest/` (paths relativos) para evitar mixed-content.
2. **S2Pix ≠ VRP MIROVA**: la traza `swir` es N° píxeles térmicos
   (Massimetti+ 2020 sobre Sentinel-2 L1C TOA), NO watts radiantes.
3. **Sentinel-2 L1C, no L2A**: confirmado en Massimetti+ 2020 (Sen2Cor
   enmascara hot-spots saturados).
4. **MAD floor crítico**: `max(MAD, 0.1·|mediana|, 0.5)` para evitar z-scores
   absurdos cuando baseline ≈ 0.1.
5. **TROPOMI SO₂ con perfil PBL** está mal para Andes altos (Láscar 5592m,
   Llaima 3125m). Subestima 2-4× la masa real. Caveat documentado en
   METHODOLOGY.md.
6. **GitHub Actions cron 17 */6 * * *** corre cada 6h y commitea con
   `[skip ci]`. Si tu commit y el del bot se cruzan, hay que `git pull --rebase`.
7. **Encoding Windows**: `notify_telegram.py` fuerza UTF-8 stdout (console
   cp1252 rompe emojis).

---

## Tareas pendientes (priorizadas)

### 🔴 Alta prioridad — lo siguiente que vale la pena

1. **C1 Tests pytest** (3-5 días)
   - 0 tests hoy, 4500+ LOC. Cada cambio puede romper algo silenciosamente.
   - Cobertura objetivo: parsers (`extract_image_paths`, `parse_timestamp`,
     `classify_product`, `robust_baseline`, `detect_anomalies`,
     `detect_multi_product_alerts`).
   - Estructura: `tests/test_anomalies.py`, `tests/test_scraper.py`, etc.
     con fixtures de HTML mockeado en `tests/fixtures/`.
   - Integrar en GH Actions `test.yml` workflow separado del cron de update.

2. **C2 Refactor `generar_html.py`** (2 días)
   - Ya pasa los 1300 LOC, sigue creciendo. Antes de seguir agregando
     features, separar en módulos:
     - `dashboard/status.py` — status matrix + bulletin + diff badges
     - `dashboard/charts.py` — Plotly per-volcano + streamgraph + baselines
     - `dashboard/map.py` — Folium
     - `dashboard/sections.py` — alerts, multi, history, upstream
     - `dashboard/template.py` — base HTML + CSS
   - Considerar templates Jinja2 en lugar de f-strings gigantes.

3. **E2 Archivo histórico completo + resumability** (1 día)
   - `scraper.py` existe pero `update.py` solo invoca `fetch_latest.py`.
   - Agregar flag `python scraper.py --archive` que baje TODO el catálogo
     histórico (~30K imágenes en lugar de 2356).
   - `scraper_state.json` para retomar si falla mid-way.
   - Backup independiente de TU Berlin (si MOUNTS cae mañana, mantenemos
     historia completa).

### 🟡 Media prioridad — valor científico

4. **V3 Bayesian Online Changepoint** (2 días)
   - Detector más robusto que z-score MAD. Adams & MacKay 2007.
   - Da probabilidad posterior de "ha habido un cambio aquí" — resiste mejor
     drift de baseline.
   - Trabaja como overlay del detector actual, no reemplazo.
   - Librería: `bayesian-changepoint-detection` o implementar el algoritmo
     online (es corto, ~50 LOC).

5. **V4 Forecast EWMA/Holt-Winters** (1 día)
   - Para cada serie, predecir próximo valor con banda de confianza.
   - Si la próxima medición cae fuera de la banda → **alerta predictiva**
     (no reactiva).
   - `statsmodels.tsa.holtwinters.ExponentialSmoothing`.

6. **V7 TPR/FPR del detector** (4h)
   - Más allá del 100% precisión actual, calcular curva ROC contra eventos
     GVP (`events` table en mounts.db).
   - Por umbral de z (1.5, 3, 6), qué TPR vs FPR.
   - Dirá si z≥3 es óptimo o debería ser z≥5.

### 🟢 Quick wins (<1 día)

7. **E7 Status badge README** (1h) — GitHub Actions badge + Shields.io custom
   "0 anomalías activas". Confianza visual instantánea.
8. **E10 DOI Zenodo** (1h) — Integración Zenodo-GitHub. Cada `git tag v1.x`
   → DOI citable. Crítico para paper.
9. **E6 Healthchecks.io heartbeat** (2h) — ping al final de update.py. Si
   cron deja de correr, email automático.
10. **V11 Permalinks URL params** (3h) — `?vol=villarrica&range=90d`. Link
    compartible por chat/email.

### 🔵 Operacional / sostenibilidad

11. **C3 Type hints + mypy** (2 días) — bajo cobertura actual.
12. **C4 Logging estructurado JSON** (4h) — diagnóstico cron Actions.
13. **C5 Pydantic schemas** (4h) — validación temprana JSONs MOUNTS.
14. **V8 Telegram setup pendiente del usuario** — el código está, faltan
    los GitHub Secrets:
    - `TELEGRAM_BOT_TOKEN` (de @BotFather)
    - `TELEGRAM_CHAT_ID` (de getUpdates)
    Ver README sección "Notificaciones Telegram (opcional)".

---

## Decisiones de diseño que NO cambiar

1. **HTML estático + JSON endpoints**, no servidor. GH Pages free tier.
2. **SQLite commiteado al repo** (6.5 MB). Disponible para download vía Pages.
3. **Imágenes en `latest/` con paths relativos**, no URLs HTTP externas
   (mixed-content kill).
4. **Anomalías detectadas se mantienen en DB para siempre** (idempotente).
   `alerts.json` es solo snapshot reciente para UI rápida.
5. **Pipeline secuencial en `update.py`** — no paralelizar pasos
   (race conditions con DB / archivos generados).
6. **Cache HTTP en `.cache/` gitignored** — rebuildeable.
7. **HTML raw versionado en `raw/` SÍ commiteado** — reproducibilidad
   científica (cada update guarda un snapshot de ~80KB gzip por volcán).

---

## Comandos útiles para próxima sesión

```bash
# Diagnóstico estado
python db.py summary
python db.py recent --n 20
python db.py validate --days 7
python anomalies.py        # regenera status.json + alerts.json
python quality.py          # gap analysis
python monitor_upstream.py # check MOUNTS upstream

# Pipeline
python update.py           # todo
python update.py --skip-fetch  # solo regeneración
python generar_html.py     # solo dashboard

# Telegram
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python notify_telegram.py --test
python notify_telegram.py --dry-run --lookback-min 99999
```

---

## Métricas actuales (último update)

```
DB: 6.5 MB
  volcanoes        7
  observations    22,792
  anomalies          738
  events              30
  multi_alerts        37
  status_history     132
  data_changes         0 (ningún drift detectado upstream)

Pipeline: ~43s end-to-end con fetch
Dashboard HTML: 1.8 MB
```

**Anomalías top por z-score** (válidas, GVP-correlated):
- Láscar SWIR 2026-04-12, z=20.9, PERSIST (run=3) — la más fuerte detectada
- Villarrica 2021-04-19, 4 productos correlacionados (multi-alert HIGH)
- Láscar 2025-03-06, 3 productos correlacionados (multi-alert HIGH)

---

## Cosas que el usuario NO ha hecho aún (gates externos)

- [ ] Crear bot Telegram en @BotFather + agregar Secrets en GitHub
- [ ] Conectar Zenodo al repo para DOI
- [ ] Configurar Healthchecks.io (opcional, gratis)
- [ ] Pedir DOAS SO₂ ground truth a OVDAS (para validación cuantitativa)

---

## Commits recientes

```
d0c05e8  feat: 3 mejoras operacionales — bulletin, diff vs ayer, Telegram
563558a  regen: HTML con panel upstream MOUNTS
20176bb  feat: 5 fases de mejoras al scraper (monitor + quality + sync_latest)
03355d3  fix: anomalies.csv auto-export
613b760  feat: 9 mejoras dashboard (filtro temporal, streamgraph, multi-alerts)
a5801b1  feat: base de datos SQLite con histórico
f4729d5  feat: rediseño completo del dashboard — 5 capas
```
