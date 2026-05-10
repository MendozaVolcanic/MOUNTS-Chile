"""
Detector de anomalias y status board para MOUNTS-Chile.

Para cada (volcan, producto):
  - Calcula baseline rolling 90d (mediana + MAD robusto)
  - Marca anomalias = valores > mediana + 3*MAD
  - Computa z-score actual = (latest - mediana) / MAD
  - Asigna severidad: green / yellow / orange / red
  - Edad del dato mas reciente

Salidas:
  status.json  — estado actual por (volcan, producto), usado por status matrix
  alerts.json  — lista de anomalias recientes (ultimos 30 dias)

Uso:
  python anomalies.py
"""

import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).parent
TS_DIR   = BASE_DIR / "timeseries"
OUT_STATUS = BASE_DIR / "status.json"
OUT_ALERTS = BASE_DIR / "alerts.json"

VOLCANES = [
    ("lascar",             "Lascar",              355100),
    ("planchon-peteroa",   "Planchon-Peteroa",    357040),
    ("laguna-del-maule",   "Laguna del Maule",    357061),
    ("nevados-de-chillan", "Nevados de Chillan",  357070),
    ("copahue",            "Copahue",             357090),
    ("llaima",             "Llaima",              357110),
    ("villarrica",         "Villarrica",          357120),
]

# Productos a analizar: (trace_name, label, unit, expected_revisit_days)
PRODUCTS = [
    ("swir",     "SWIR",  "S2Pix",        5),
    ("so2",      "SO2",   "tons",         1),
    ("def_desc", "DEF",   "m_LOS",        12),
    ("coh_desc", "COH",   "Npix_coh<0.5", 12),
]

ROLLING_WINDOW_DAYS = 90
ANOMALY_THRESHOLD   = 3.0   # desviaciones MAD
ALERTS_LOOKBACK_DAYS = 30


def parse_iso(s):
    """Parse ISO string to datetime. None if invalid."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def load_traces(key):
    f = TS_DIR / f"{key}.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    return {t["name"]: t for t in data.get("traces", []) if t.get("name")}


def robust_baseline(xs, ys, window_days=ROLLING_WINDOW_DAYS):
    """
    Rolling robust baseline. Para cada punto i, calcula mediana y MAD de
    los valores en [t_i - window, t_i]. Devuelve (median_arr, mad_arr).
    """
    if not xs or not ys:
        return np.array([]), np.array([])

    times = [parse_iso(x) for x in xs]
    vals  = np.array([y if y is not None else np.nan for y in ys], dtype=float)

    medians = np.full(len(vals), np.nan)
    mads    = np.full(len(vals), np.nan)

    for i, t in enumerate(times):
        if t is None:
            continue
        # ventana hacia atras (no incluye el punto actual para que la deteccion
        # de anomalia compare con baseline historico)
        lower = t - timedelta(days=window_days)
        idxs = [j for j, tj in enumerate(times[:i]) if tj is not None and lower <= tj < t]
        if len(idxs) < 5:    # minimo de muestras para baseline
            continue
        window = vals[idxs]
        window = window[~np.isnan(window)]
        if len(window) < 5:
            continue
        med = np.median(window)
        mad = np.median(np.abs(window - med))
        # MAD floor robusto: al menos 10% del valor mediano O un piso absoluto
        # (evita z-scores enormes cuando MAD ~ 0 con valores cuasi-constantes)
        mad = max(mad, 0.1 * max(abs(med), 0.0), 0.5)
        medians[i] = med
        mads[i]    = mad

    return medians, mads


def detect_anomalies(xs, ys, threshold=ANOMALY_THRESHOLD):
    """
    Devuelve lista de dicts {date, value, zscore, baseline} para puntos
    que exceden mediana + threshold*MAD del baseline rolling.
    """
    medians, mads = robust_baseline(xs, ys)
    anomalies = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        if y is None or np.isnan(medians[i]) or np.isnan(mads[i]):
            continue
        if y <= medians[i]:
            continue
        z = (y - medians[i]) / mads[i]
        if z >= threshold:
            anomalies.append({
                "date":     x,
                "value":    float(y),
                "baseline": float(medians[i]),
                "zscore":   float(z),
            })
    return anomalies


def severity_from_zscore(z):
    """green / yellow / orange / red."""
    if z is None or math.isnan(z):
        return "gray"
    if z < 1.5:
        return "green"
    if z < 3.0:
        return "yellow"
    if z < 6.0:
        return "orange"
    return "red"


def compute_product_status(trace, expected_revisit_days):
    """
    Para una traza, calcula el status actual:
      latest_value, latest_date, zscore_now, severity, age_hours, sparkline_data
    """
    if not trace or not trace.get("y"):
        return None

    xs = trace.get("x") or []
    ys = trace.get("y") or []

    # Limpiar None/NaN
    pairs = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if not pairs:
        return None

    # Ordenar por fecha ascendente (los traces de MOUNTS no siempre vienen ordenados)
    pairs_sorted = []
    for x, y in pairs:
        t = parse_iso(x)
        pairs_sorted.append((t or datetime.min.replace(tzinfo=timezone.utc), x, y))
    pairs_sorted.sort(key=lambda p: p[0])
    xs_clean = [p[1] for p in pairs_sorted]
    ys_clean = [p[2] for p in pairs_sorted]

    # Baseline + z-score del ultimo punto
    medians, mads = robust_baseline(xs_clean, ys_clean)

    # ultimo z-score valido
    z_now = None
    if len(medians) > 0 and not np.isnan(medians[-1]) and not np.isnan(mads[-1]):
        z_now = (ys_clean[-1] - medians[-1]) / mads[-1]

    # Edad
    last_dt = parse_iso(xs_clean[-1])
    now = datetime.now(timezone.utc)
    age_hours = None
    if last_dt:
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        age_hours = (now - last_dt).total_seconds() / 3600

    # ¿Datos atrasados? threshold = max(7d, 3*revisit) para evitar marcar todo como stale
    stale_threshold_h = max(7 * 24, expected_revisit_days * 24 * 3)
    stale = age_hours is not None and age_hours > stale_threshold_h

    # Sparkline: ultimos 90 dias
    sparkline_x, sparkline_y = [], []
    if last_dt:
        cutoff = last_dt - timedelta(days=90)
        for x, y in pairs:
            t = parse_iso(x)
            if t:
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t >= cutoff:
                    sparkline_x.append(x)
                    sparkline_y.append(y)

    severity = severity_from_zscore(z_now)
    if stale:
        severity = "stale"   # gris/atrasado pisa todo

    return {
        "latest_value":  float(ys_clean[-1]),
        "latest_date":   xs_clean[-1],
        "zscore_now":    None if z_now is None or math.isnan(z_now) else float(z_now),
        "severity":      severity,
        "age_hours":     None if age_hours is None else round(age_hours, 1),
        "stale":         stale,
        "n_total":       len(ys_clean),
        "sparkline_x":   sparkline_x,
        "sparkline_y":   [float(y) for y in sparkline_y],
        "baseline_med":  None if np.isnan(medians[-1]) else float(medians[-1]),
        "baseline_mad":  None if np.isnan(mads[-1])    else float(mads[-1]),
    }


def overall_severity(product_statuses):
    """Severidad global del volcan = peor de sus productos."""
    order = {"red": 4, "orange": 3, "yellow": 2, "green": 1, "stale": 0, "gray": 0}
    worst = "gray"
    worst_score = -1
    for ps in product_statuses.values():
        if ps is None:
            continue
        s = ps.get("severity", "gray")
        if order.get(s, 0) > worst_score:
            worst_score = order.get(s, 0)
            worst = s
    return worst


def main():
    status = {"generated_at": datetime.now(timezone.utc).isoformat(), "volcanoes": {}}
    all_alerts = []

    print(f"{'Volcan':22} {'Producto':6} {'Latest':>10}  {'Z':>6}  Sev")
    print("-" * 60)

    for key, name, sid in VOLCANES:
        traces = load_traces(key)
        prod_status = {}

        for tname, label, unit, revisit in PRODUCTS:
            trace = traces.get(tname)
            ps = compute_product_status(trace, revisit) if trace else None
            prod_status[label] = ps

            # detectar anomalias recientes
            if trace and trace.get("y"):
                anoms = detect_anomalies(trace["x"], trace["y"])
                # filtrar a ultimos N dias
                cutoff = datetime.now(timezone.utc) - timedelta(days=ALERTS_LOOKBACK_DAYS)
                for a in anoms:
                    t = parse_iso(a["date"])
                    if t:
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=timezone.utc)
                        if t >= cutoff:
                            a["volcano"] = name
                            a["volcano_key"] = key
                            a["product"] = label
                            a["unit"] = unit
                            all_alerts.append(a)

            # log
            if ps:
                z = ps["zscore_now"]
                z_str = f"{z:>6.2f}" if z is not None else "   -- "
                print(f"{name:22} {label:6} {ps['latest_value']:>10.3g}  {z_str}  {ps['severity']}")
            else:
                print(f"{name:22} {label:6} {'(sin datos)':>10}    --   gray")

        status["volcanoes"][key] = {
            "name":     name,
            "smithsonian_id": sid,
            "products": prod_status,
            "overall":  overall_severity(prod_status),
        }

    # Ordenar alerts por z-score desc
    all_alerts.sort(key=lambda a: a["zscore"], reverse=True)
    alerts_obj = {
        "generated_at": status["generated_at"],
        "lookback_days": ALERTS_LOOKBACK_DAYS,
        "threshold": ANOMALY_THRESHOLD,
        "count": len(all_alerts),
        "alerts": all_alerts,
    }

    OUT_STATUS.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_ALERTS.write_text(json.dumps(alerts_obj, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"status.json:  {OUT_STATUS.name}  ({len(status['volcanoes'])} volcanes)")
    print(f"alerts.json:  {OUT_ALERTS.name}  ({len(all_alerts)} anomalias en ultimos {ALERTS_LOOKBACK_DAYS}d)")


if __name__ == "__main__":
    main()
