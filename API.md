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
| `events` | 30+ | `volcano_key, date, track_type, value` (tbar_* GVP) |
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
| `csv/events.csv` | Eventos GVP/USGS |

Columnas: `date, value, unit, product, sensor, image_path, image_url`.

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
