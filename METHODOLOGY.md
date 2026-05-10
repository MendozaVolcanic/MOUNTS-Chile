# MOUNTS — Procedencia de los datos

Documento técnico para SERNAGEOMIN/OVDAS. ¿De dónde sale cada número que muestra
mounts-project.com? Esto es lo que extrae nuestro `scraper.py` / `fetch_latest.py`
y guarda en `timeseries/<volcan>.json`.

---

## Papers de referencia

| Cita | DOI | Qué define |
|---|---|---|
| **Valade et al. 2019** — *Towards Global Volcano Monitoring Using Multisensor Sentinel Missions and Artificial Intelligence: The MOUNTS Monitoring System.* **Remote Sensing 11(13), 1528** (MDPI, open access) | [10.3390/rs11131528](https://doi.org/10.3390/rs11131528) | Arquitectura general MOUNTS, definiciones de DEF/COH scores, CNN de filtrado de fase |
| **Massimetti et al. 2020** — *Volcanic Hot-Spot Detection Using Sentinel-2: A Comparison with MODIS–MIROVA Thermal Data Series.* **Remote Sensing 12(5), 820** | [10.3390/rs12050820](https://doi.org/10.3390/rs12050820) | Algoritmo SWIR S2 (S2Pix) y comparación con VRP MIROVA |
| **Ley** (companion code) | [github.com/Andreas-Ley/SAR-InterfPhaseFilter](https://github.com/Andreas-Ley/SAR-InterfPhaseFilter) | CNN U-Net para filtrar fase envuelta de interferogramas |

> **Aclaración importante**: la "U-Net" mencionada en algunos resúmenes NO es para
> hot-spots térmicos — es para filtrado de fase InSAR (Ley). El sufijo `_VV_int_fcnn`
> en imágenes Sentinel-1 sí corresponde a una FCNN aplicada a intensidad VV para
> apoyo de inspección visual (Valade 2019).

---

## Productos y unidades (las trazas en el JSON)

Cada `timeseries/<volcan>.json` tiene 13 trazas Plotly. Su mapeo físico:

| Traza JSON | Producto satelital | Unidad eje Y | Algoritmo |
|---|---|---|---|
| `swir` | Sentinel-2 MSI bands **B12 (2190 nm) + B11 (1610 nm) + B8A (865 nm)**, 20 m TOA reflectance | **N° de píxeles térmicamente anómalos (S2Pix)** — *no es VRP en watts* | Massimetti+ 2020: índices espectrales SWIR + umbral estadístico contextual sobre clusters alertados (omisión ~1 %, comisión ~6 %) |
| `so2` | Sentinel-5P TROPOMI L2 `__SO2___` (ESA/DLR operational, **DOAS**) | **toneladas SO₂** integradas sobre AOI | Asume perfil de caja en **PBL (1 km sobre suelo)** — TROPOMI provee 3 perfiles a-priori (PBL/7km/15km); MOUNTS usa PBL. Falla en plumas a gran altitud. |
| `def_asc`, `def_desc` | Sentinel-1 IW SLC, procesado con **ESA SNAP** + CNN de filtrado de fase (Ley) | **metros LOS (std/max de fase desenrollada)** sobre AOI, separado por órbitas ascendente/descendente | Interferograma envuelto → CNN filtra → desenrollado → std/max convertido a desplazamiento LOS |
| `coh_asc`, `coh_desc` | Sentinel-1 coherencia | **N° de píxeles con coherencia < 0.5** en AOI | Proxy de cambio de reflectividad superficial: pérdida de vegetación, depósito de cenizas/lavas, daños piroclásticos, lahares. Picos durante/post erupción. |
| `int_asc`, `int_desc` | Sentinel-1 GRD VV-pol | (sin uso numérico claro — placeholder) | Backscatter intensity sobre AOI; el `_VV_int_fcnn` aplica una FCNN para localizar anomalías |
| `tbar_*` (so2, nir, int, disp, coh) | — | banderas verticales rojas | **Eventos de erupción/actividad** ingestados de catálogos Smithsonian GVP semanales + USGS/GEOFON sismológicos. **Curados manual/semi-automáticamente, no derivados de las trazas satelitales.** |

### `swir` no es VRP MIROVA

Esta es la confusión más común y por qué importa: **MIROVA reporta VRP en
watts** (radiative power, MODIS/VIIRS, banda M14 ~3.9 µm), mientras **MOUNTS
reporta S2Pix en N° de píxeles** (Sentinel-2, SWIR ~1.6/2.2 µm). Correlacionan
(Massimetti 2020 lo demuestra para Stromboli, Etna, etc.) pero son escalas
distintas. Si querés VRP-equivalente para Chile, seguís necesitando VRP-chile
(MODIS/VIIRS).

---

## Selección de volcanes y AOI

- ~30 volcanes monitoreados globalmente (2026), seleccionados manualmente por
  Valade (`valade@igeofisica.unam.mx`, ahora en UNAM).
- IDs son **Smithsonian VOTW** (Global Volcanism Program). Los 7 chilenos:
  - 355100 Láscar · 357040 Planchón-Peteroa · 357061 Laguna del Maule
  - 357070 Nevados de Chillán · 357090 Copahue · 357110 Llaima · 357120 Villarrica
- Cada volcán tiene un **AOI bbox de pocos km** alrededor del cráter activo,
  definido manualmente. Esta es la principal limitación: si la pluma o
  deformación se sale del bbox, no se ve.

---

## Cadencia y latencia

| Sensor | Revisita | Latencia post-adquisición |
|---|---|---|
| Sentinel-1 | 6 d (single-sat post-S1B) → 12 d efectivo desde dic-2021 | 6–24 h |
| Sentinel-2 | 5 d en ecuador (A+B) | 6–24 h |
| Sentinel-5P | ~diario global | 6–24 h |

Origen de los datos: **Copernicus Data Space Ecosystem** (ex Open Access Hub),
auto-polled. Procesamiento con **ESA SNAP** vía Python API + base local PostgreSQL.

---

## Limitaciones explícitas (Valade 2019 + observaciones propias)

- **SWIR térmico**:
  - Falsos negativos bajo nubes (Sentinel-2 es óptico).
  - Falsos positivos: incendios forestales, quemas agrícolas, industria cercana al AOI.
  - Para Chile: Villarrica (vegetación densa) tiene más decorrelación que Láscar (desierto).
- **SO₂**: sensible a fracción de nubes y SZA. Plumas débiles (<0.5 DU) bajo
  detección. Asumir perfil PBL falla para columnas eruptivas altas (>5 km).
- **InSAR C-band**:
  - Decorrelación severa en vegetación/nieve. Crítico para Villarrica, Llaima,
    Nevados de Chillán.
  - Sin cobertura L-band (no NISAR/ALOS-2 en pipeline).
  - Revisita 6–12 d pierde transientes rápidos.
- **CNNs**: entrenadas con catálogo limitado de erupciones; generalización con asterisco.

---

## Acceso a datos

- **No hay API JSON/CSV oficial.**
- La web sirve figuras Plotly embebidas en HTML en
  `mounts-project.com/timeseries/<GVP_ID>` y `/volcano/<GVP_ID>`.
- El scraper extrae el JSON Plotly del bloque `<script>var graph = {...};
  Plotly.newPlot(...);</script>` con regex (no hace falta JS).
- **No existe `github.com/mounts-project`**. Solo el repo auxiliar de Ley
  (filtrado fase) es público.
- Alertas por email opt-in vía email a Valade.

---

## Cómo usar nuestros JSONs

```python
import json
from pathlib import Path

data = json.loads(Path("timeseries/villarrica.json").read_text())
# data["traces"] = lista de 13 dicts con {name, x (fechas ISO), y (valores), text (paths imagen)}

# Ejemplo: serie SWIR (S2Pix)
swir = next(t for t in data["traces"] if t["name"] == "swir")
print(f"{len(swir['y'])} muestras desde {swir['x'][0]} hasta {swir['x'][-1]}")
```

O usá `export_csv.py` para volcar todo a CSVs estilo VRP.
