"""
Tests para anomalies.py — el detector z-score MAD-robusto (corazon cientifico).

Cubre:
  robust_baseline(xs, ys, window_days)  -> (medians, mads) con MAD floor
  detect_anomalies(xs, ys, threshold)   -> lista de anomalias + run/persist
  severity_from_zscore(z)               -> green/yellow/orange/red/gray
  compute_product_status(trace, revisit)-> status actual + staleness
  parse_iso(s)                          -> datetime | None
  overall_severity(product_statuses)    -> peor severidad del volcan

Quirk #4 (snapshot): MAD floor = max(MAD, 0.1*|mediana|, 0.5). Sin el floor,
una serie cuasi-constante con baseline ~0.1 disparara z-scores absurdos. El
test del baseline constante demuestra que el z-score NO explota.
"""

import math
from datetime import datetime, timezone, timedelta

import numpy as np

import anomalies


# --- parse_iso --------------------------------------------------------------

class TestParseIso:
    def test_date_only(self):
        dt = anomalies.parse_iso("2026-01-05")
        assert dt == datetime(2026, 1, 5)

    def test_datetime_with_z(self):
        dt = anomalies.parse_iso("2026-01-05T14:35:21Z")
        assert dt == datetime(2026, 1, 5, 14, 35, 21, tzinfo=timezone.utc)

    def test_invalid_returns_none(self):
        assert anomalies.parse_iso("no-es-fecha") is None

    def test_none_input_returns_none(self):
        assert anomalies.parse_iso(None) is None


# --- robust_baseline (incluye el MAD floor — quirk #4) ----------------------

class TestRobustBaseline:
    def test_empty_input(self):
        med, mad = anomalies.robust_baseline([], [])
        assert med.size == 0 and mad.size == 0

    def test_returns_arrays_same_length_as_input(self, flat_trace):
        xs, ys = flat_trace
        med, mad = anomalies.robust_baseline(xs, ys)
        assert len(med) == len(xs)
        assert len(mad) == len(ys)

    def test_first_points_nan_until_min_samples(self, flat_trace):
        # Los primeros <5 puntos no tienen baseline (NaN); se necesitan >=5
        # muestras en la ventana hacia atras.
        xs, ys = flat_trace
        med, mad = anomalies.robust_baseline(xs, ys)
        assert np.isnan(med[0])
        # con 20 puntos planos, los ultimos si tienen baseline
        assert not np.isnan(med[-1])

    def test_mad_floor_on_constant_series(self, constant_trace):
        """
        CRITICO (quirk #4). Serie ~0.1 constante. MAD crudo ~ 0; el floor lo
        sube a max(0, 0.1*0.1, 0.5) = 0.5. El z-score del punto final (0.3)
        debe quedar acotado, NO explotar.
        """
        xs, ys = constant_trace
        med, mad = anomalies.robust_baseline(xs, ys)
        # Para los puntos con baseline, la mediana es 0.1 y el MAD pisado >= 0.5
        valid = ~np.isnan(mad)
        assert valid.any()
        assert np.all(mad[valid] >= 0.5)
        # z-score del ultimo punto = (0.3 - 0.1) / 0.5 = 0.4  -> NO explota
        z_last = (ys[-1] - med[-1]) / mad[-1]
        assert abs(z_last) < 1.5

    def test_mad_floor_floor_value_dominates_when_median_small(self):
        # Mediana pequena (~2): 0.1*2 = 0.2 < 0.5, gana el piso absoluto 0.5.
        xs = [f"2026-01-{d:02d}" for d in range(1, 13)]
        ys = [2.0] * 12
        med, mad = anomalies.robust_baseline(xs, ys)
        valid = ~np.isnan(mad)
        assert np.all(mad[valid] >= 0.5)

    def test_mad_floor_percent_dominates_when_median_large(self):
        # Mediana grande (1000): 0.1*1000 = 100 > 0.5, gana el 10% relativo.
        xs = [f"2026-01-{d:02d}" for d in range(1, 13)]
        ys = [1000.0] * 12
        med, mad = anomalies.robust_baseline(xs, ys)
        valid = ~np.isnan(mad)
        assert np.all(mad[valid] >= 100.0)

    def test_window_excludes_current_point(self):
        # El baseline se computa con la ventana hacia atras SIN el punto actual,
        # asi un salto en el ultimo punto se detecta contra el historico.
        xs = [f"2026-01-{d:02d}" for d in range(1, 13)]
        ys = [10.0] * 11 + [999.0]
        med, mad = anomalies.robust_baseline(xs, ys)
        # la mediana del ultimo punto debe reflejar el historico (~10), no 999
        assert med[-1] == 10.0


# --- detect_anomalies -------------------------------------------------------

class TestDetectAnomalies:
    def test_flat_series_no_anomalies(self, flat_trace):
        xs, ys = flat_trace
        assert anomalies.detect_anomalies(xs, ys) == []

    def test_constant_low_series_no_false_positive(self, constant_trace):
        # El MAD floor evita que el saltito 0.1 -> 0.3 dispare anomalia.
        xs, ys = constant_trace
        assert anomalies.detect_anomalies(xs, ys) == []

    def test_isolated_outlier_detected(self, outlier_trace):
        xs, ys = outlier_trace
        anoms = anomalies.detect_anomalies(xs, ys)
        assert len(anoms) == 1
        a = anoms[0]
        assert a["date"] == xs[-1]
        assert a["value"] == 200.0
        assert a["zscore"] >= 3.0
        assert a["run_length"] == 1
        assert a["persistent"] is False

    def test_persistent_anomaly_run_and_flag(self, persistent_trace):
        xs, ys = persistent_trace
        anoms = anomalies.detect_anomalies(xs, ys)
        assert len(anoms) == 3
        # run_length crece 1,2,3 en anomalias consecutivas
        assert [a["run_length"] for a in anoms] == [1, 2, 3]
        # persistent True solo cuando run_length >= 3
        assert [a["persistent"] for a in anoms] == [False, False, True]

    def test_only_positive_excursions_flagged(self):
        # Una caida por debajo de la mediana NO es anomalia (y <= median -> skip)
        xs = [f"2026-01-{d:02d}" for d in range(1, 13)]
        ys = [100.0] * 11 + [1.0]
        assert anomalies.detect_anomalies(xs, ys) == []

    def test_threshold_respected(self, outlier_trace):
        xs, ys = outlier_trace
        # Con threshold absurdamente alto no debe detectar nada.
        assert anomalies.detect_anomalies(xs, ys, threshold=1e9) == []

    def test_anomaly_dict_keys(self, outlier_trace):
        xs, ys = outlier_trace
        a = anomalies.detect_anomalies(xs, ys)[0]
        assert set(a) == {"date", "value", "baseline", "zscore",
                          "run_length", "persistent"}


# --- severity_from_zscore ---------------------------------------------------

class TestSeverityFromZscore:
    def test_thresholds(self):
        assert anomalies.severity_from_zscore(0.0) == "green"
        assert anomalies.severity_from_zscore(1.49) == "green"
        assert anomalies.severity_from_zscore(1.5) == "yellow"
        assert anomalies.severity_from_zscore(2.99) == "yellow"
        assert anomalies.severity_from_zscore(3.0) == "orange"
        assert anomalies.severity_from_zscore(5.99) == "orange"
        assert anomalies.severity_from_zscore(6.0) == "red"
        assert anomalies.severity_from_zscore(20.0) == "red"

    def test_none_and_nan_are_gray(self):
        assert anomalies.severity_from_zscore(None) == "gray"
        assert anomalies.severity_from_zscore(float("nan")) == "gray"


# --- compute_product_status -------------------------------------------------

class TestComputeProductStatus:
    def test_none_trace(self):
        assert anomalies.compute_product_status(None, 5) is None

    def test_empty_y(self):
        assert anomalies.compute_product_status({"x": [], "y": []}, 5) is None

    def test_all_none_values(self):
        trace = {"x": ["2026-01-01", "2026-01-02"], "y": [None, None]}
        assert anomalies.compute_product_status(trace, 5) is None

    def test_recent_data_not_stale(self):
        # Datos hasta "hoy": no debe marcarse stale.
        now = datetime.now(timezone.utc)
        xs, ys = [], []
        for i in range(15, 0, -1):
            xs.append((now - timedelta(days=i)).date().isoformat())
            ys.append(10.0)
        ps = anomalies.compute_product_status({"x": xs, "y": ys}, expected_revisit_days=5)
        assert ps is not None
        assert ps["stale"] is False
        assert ps["latest_value"] == 10.0
        assert ps["n_total"] == 15

    def test_old_data_is_stale(self):
        # Ultimo dato hace 400 dias: supera max(7d, 3*revisit) -> stale.
        old = datetime.now(timezone.utc) - timedelta(days=400)
        xs = [(old + timedelta(days=i)).date().isoformat() for i in range(10)]
        ys = [10.0] * 10
        ps = anomalies.compute_product_status({"x": xs, "y": ys}, expected_revisit_days=5)
        assert ps["stale"] is True
        assert ps["severity"] == "stale"

    def test_sorts_unordered_input(self):
        # MOUNTS no siempre entrega ordenado; latest_date debe ser el mayor.
        now = datetime.now(timezone.utc)
        d1 = (now - timedelta(days=2)).date().isoformat()
        d2 = (now - timedelta(days=1)).date().isoformat()
        trace = {"x": [d2, d1], "y": [20.0, 10.0]}
        ps = anomalies.compute_product_status(trace, 5)
        assert ps["latest_date"] == d2

    def test_status_dict_keys(self):
        now = datetime.now(timezone.utc)
        xs = [(now - timedelta(days=i)).date().isoformat() for i in range(10, 0, -1)]
        ys = [10.0] * 10
        ps = anomalies.compute_product_status({"x": xs, "y": ys}, 5)
        expected = {"latest_value", "latest_date", "zscore_now", "severity",
                    "age_hours", "stale", "n_total", "sparkline_x",
                    "sparkline_y", "baseline_med", "baseline_mad"}
        assert set(ps) == expected


# --- overall_severity -------------------------------------------------------

class TestOverallSeverity:
    def test_picks_worst(self):
        statuses = {
            "SWIR": {"severity": "green"},
            "SO2":  {"severity": "red"},
            "DEF":  {"severity": "yellow"},
        }
        assert anomalies.overall_severity(statuses) == "red"

    def test_ignores_none_products(self):
        statuses = {"SWIR": None, "SO2": {"severity": "orange"}}
        assert anomalies.overall_severity(statuses) == "orange"

    def test_all_none_returns_gray(self):
        assert anomalies.overall_severity({"SWIR": None}) == "gray"

    def test_empty_returns_gray(self):
        assert anomalies.overall_severity({}) == "gray"

    def test_stale_ranks_below_green(self):
        statuses = {"SWIR": {"severity": "stale"}, "SO2": {"severity": "green"}}
        assert anomalies.overall_severity(statuses) == "green"
