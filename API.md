# MOUNTS-Chile — API estable

Los archivos JSON/SQLite/CSV servidos por GitHub Pages son **endpoints estables**
consumibles por máquinas. Schema versionado: cualquier cambio breaking se
anuncia en CHANGELOG y se versiona el path.

**Base**: `https://mendozavolcanic.github.io/MOUNTS-Chile/`

---

## `/status.json` — Estado actual

Snapshot del último update. Una entrada por (volcán, producto). Sirve la matriz
del status board.

```json
{
  "generated_at": "2026-05-10T07:35:12+00:00",
  "volcanoes": {
    "lascar": {
      "name": "Lascar",
      "smithsonian_id": 355100,
      "products": {
        "SWIR": {
          "latest_value": 10.0,
          "latest_date": "2026-04-28T14:36:39",
          "zscore_now": 0.17,
          "severity": "green",
          "age_hours": 282.4,
          "stale": false,
          "n_total": 426,
          "sparkline_x": [...],
          "sparkline_y": [...],
          "baseline_med": 9.5,
          "baseline_mad": 3.0
        },
        "SO2": { ... },
        "DEF": { ... },
        "COH": { ... }
      },
      "overall": "green"
    },
    ...
  }
}
```

**Severities**: `green` (z<1.5) · `yellow` (z<3) · `orange` (z<6) · `red` (z≥6) · `stale` (dato atrasado).

---

## `/alerts.json` — Anomalías últimos 30 días

```json
{
  "generated_at": "2026-05-10T07:35:12+00:00",
  "lookback_days": 30,
  "threshold": 3.0,
  "count": 5,
  "alerts": [
    {
      "date": "2026-04-12T14:27:51",
      "value": 11.0,
      "baseline": 0.5,
      "zscore": 20.9,
      "volcano": "Lascar",
      "volcano_key": "lascar",
      "product": "SWIR",
      "unit": "S2Pix"
    },
    ...
  ]
}
```

Ordenado por z-score descendente. Re-genera completo en cada update — para
auditoría histórica usá `mounts.db`.

---

## `/diffs.json` — Índice de imágenes diff SWIR

```json
{
  "lascar": {
    "new":  "latest/lascar/diff/new_lascar_20260427T143739_B12B11B8A_nir.png",
    "old":  "latest/lascar/diff/old_lascar_20260422T143741_B12B11B8A_nir.png",
    "diff": "latest/lascar/diff/diff.png",
    "new_date": "20260427",
    "old_date": "20260422"
  },
  ...
}
```

Paths relativos a la base. Cada diff = `|new - old|` escalado por percentil 95
y compositado en R-amplificado.

---

## `/mounts.db` — Base de datos SQLite (histórico completo)

Disponible para descarga directa. Schema:

| Tabla | Filas (ej.) | Columnas clave |
|---|---|---|
| `volcanoes` | 7 | `key, name, smithsonian_id, lat, lon` |
| `observations` | 22 K | `volcano_key, product, date, value, unit, sensor, image_path` |
| `anomalies` | 5+ | `volcano_key, product, date, value, baseline_median, baseline_mad, zscore, severity, detected_at` |
| `events` | 600+ | `volcano_key, date, track_type, value` — ⚠ marcadores de gráfico `tbar_*` de MOUNTS, **NO** eventos eruptivos: no usar como ground truth |
| `status_history` | * | snapshot por update |
| `metadata` | 1+ | `key, value` (incluye `last_update`) |

**UNIQUE constraints garantizan idempotencia**:
- `observations(volcano_key, product, date)`
- `anomalies(volcano_key, product, date)`
- `events(volcano_key, date, track_type)`

Re-correr `db.py update` no duplica nada.

### Query ejemplos

```python
import sqlite3, urllib.request
urllib.request.urlretrieve(
    "https://mendozavolcanic.github.io/MOUNTS-Chile/mounts.db",
    "mounts.db"
)
conn = sqlite3.connect("mounts.db")

# Últimas 10 anomalías
for row in conn.execute("""
    SELECT a.date, v.name, a.product, a.zscore
    FROM anomalies a JOIN volcanoes v ON v.key = a.volcano_key
    ORDER BY a.detected_at DESC LIMIT 10
"""):
    print(row)

# Serie SO2 Villarrica último año
for row in conn.execute("""
    SELECT date, value FROM observations
    WHERE volcano_key='villarrica' AND product='so2'
      AND date > date('now', '-365 days')
    ORDER BY date
"""):
    print(row)
```

---

## `/anomalies.csv` — Catálogo histórico de anomalías

CSV con todas las anomalías detectadas, ordenadas por z-score desc:

```csv
date,volcano,product,value,baseline,zscore,severity,detected_at
2026-04-12T14:27:51,Lascar,swir,11.0,0.5,20.9,red,2026-05-10T07:35:12+00:00
...
```

Generado por `db.py export`. Súbset de `mounts.db.anomalies`.

---

## `/csv/*.csv` — Series temporales VRP-style

| Path | Contenido |
|---|---|
| `csv/<volcán>_thermal_swir.csv` | SWIR S2Pix por volcán |
| `csv/<volcán>_so2_mass.csv` | SO₂ toneladas por volcán |
| `csv/<volcán>_def_{asc,desc}.csv` | Deformación InSAR |
| `csv/all_thermal.csv` | SWIR consolidado todos los volcanes |
| `csv/all_so2.csv` | SO₂ consolidado |
| `csv/events.csv` | Marcadores `tbar_*` de MOUNTS — ⚠ **no** son eventos eruptivos |

Columnas: `date, value, detection, unit, product, sensor, image_path, image_url`
(los consolidados agregan `volcano` y `track`).

### ⚠ La columna `detection` — leer antes de promediar

En **SWIR** y **SO₂**, MOUNTS publica un valor placeholder (~`0.1`) cuando no
hay señal sobre el umbral. **No es una medición.** Se conserva el valor crudo
(integridad de datos) y se marca con `detection`:

- `detection=true` → medición real
- `detection=false` → no-detección (valor ≤ 0.5)

Esto importa más de lo que parece: **la serie de SO₂ es casi toda
no-detección**. Nevados de Chillán tiene 1 detección real en 2.699 puntos;
Láscar, 152 en 2.410. Promediar sin filtrar da un resultado sin sentido.

```python
import pandas as pd
df = pd.read_csv("csv/all_thermal.csv")
reales = df[df.detection]           # solo mediciones
```

No aplica a `def_*` / `coh_*`: ahí un valor chico (8e-05 m) **sí** es una
medición real de desplazamiento.

---

## `/actividad_termica_so2.json` — Térmico + SO₂ consolidado

Un solo JSON con las dos series de actividad de los 7 volcanes, pensado para
consumir los datos sin tener que juntar 14 CSVs. Incluye los caveats
científicos en el propio archivo (campo `notes`).

```jsonc
{
  "generated_at": "...",
  "source": "mounts-project.com (Valade et al. 2019, TU Berlin / GFZ)",
  "notes": { "swir": "...", "so2": "...", "detection": "..." },
  "volcanoes": {
    "lascar": {
      "name": "Lascar", "smithsonian_id": 355100,
      "series": {
        "swir": {
          "product": "thermal_swir", "unit": "S2Pix", "sensor": "Sentinel-2",
          "n_points": 450, "n_detections": 220,
          "first_date": "2020-01-04T14:37:21", "last_date": "...",
          "data": [{"date": "...", "value": 7.0, "detection": true,
                    "image_path": "data_mounts/..."}]
        },
        "so2": { }
      }
    }
  }
}
```

Cobertura: **19.478 puntos**, desde 2018-08 (Nevados de Chillán) hasta hoy.
Laguna del Maule figura con `n_points: 0` — MOUNTS no publica series para ese
volcán.

---

## Versioning policy

- **Cambios aditivos** (nuevos campos en JSON, nuevas columnas en SQLite): sin
  bump de versión, retrocompatibles.
- **Cambios breaking** (rename, remove, type change): se anuncia en
  CHANGELOG.md y se sube `?v=2` al path o se mantiene el endpoint legacy
  por 90 días.

## Integraciones esperadas

- **OpenVIS / VRP-chile**: pueden consumir `mounts.db` o los CSVs para
  comparación cross-sensor.
- **Streamlit dashboards**: leer `status.json` + `mounts.db` para render
  rápido.
- **Webhook de alertas**: consumir `alerts.json` cada N min y comparar con
  cache local para detectar anomalías nuevas.
