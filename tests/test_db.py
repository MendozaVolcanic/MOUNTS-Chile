"""
Tests para db.py — foco en detect_multi_product_alerts.

Usa SQLite in-memory (fixture memory_db en conftest.py). NUNCA toca mounts.db.

Logica bajo prueba (detect_multi_product_alerts):
  - Agrupa anomalias por volcan, ordenadas por fecha.
  - Clusteriza por proximidad temporal: una anomalia entra al cluster si su
    fecha esta a <= window_days del ULTIMO miembro del cluster.
  - Registra una multi_alert solo si el cluster tiene >= 2 PRODUCTOS distintos.
  - confidence = 'high' si n_products >= 3, si no 'medium'.
"""

import json

import db


# --- helpers de lectura -----------------------------------------------------

def _multi_rows(conn):
    cur = conn.execute(
        "SELECT volcano_key, date_center, products, n_products, "
        "zscore_max, zscore_sum, confidence FROM multi_alerts "
        "ORDER BY volcano_key, date_center"
    )
    return cur.fetchall()


# --- schema / fixture sanity ------------------------------------------------

class TestSchema:
    def test_volcanoes_seeded(self, memory_db):
        n = memory_db.execute("SELECT COUNT(*) FROM volcanoes").fetchone()[0]
        assert n == 7

    def test_starts_with_no_multi_alerts(self, memory_db):
        n = memory_db.execute("SELECT COUNT(*) FROM multi_alerts").fetchone()[0]
        assert n == 0


# --- detect_multi_product_alerts: casos que NO disparan ---------------------

class TestNoMultiAlert:
    def test_no_anomalies_at_all(self, memory_db):
        assert db.detect_multi_product_alerts(memory_db) == 0
        assert _multi_rows(memory_db) == []

    def test_single_product_does_not_trigger(self, memory_db, insert_anomaly):
        # Dos anomalias mismo volcan, misma ventana, pero MISMO producto.
        insert_anomaly("lascar", "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "swir", "2026-03-05", zscore=5.0)
        assert db.detect_multi_product_alerts(memory_db) == 0
        assert _multi_rows(memory_db) == []

    def test_two_products_far_apart_no_alert(self, memory_db, insert_anomaly):
        # Dos productos distintos pero separados > window_days (14) -> clusters
        # distintos, cada uno con 1 solo producto -> sin multi-alert.
        insert_anomaly("lascar", "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "so2",  "2026-04-01", zscore=4.0)
        assert db.detect_multi_product_alerts(memory_db) == 0
        assert _multi_rows(memory_db) == []

    def test_cross_volcano_does_not_combine(self, memory_db, insert_anomaly):
        # Productos distintos pero en VOLCANES distintos: nunca se combinan.
        insert_anomaly("lascar",    "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("villarrica", "so2", "2026-03-02", zscore=4.0)
        assert db.detect_multi_product_alerts(memory_db) == 0


# --- detect_multi_product_alerts: casos que SI disparan ---------------------

class TestMultiAlertTriggers:
    def test_two_products_same_window_medium(self, memory_db, insert_anomaly):
        # SWIR + SO2 en la misma semana -> multi-alert 'medium' (n=2).
        insert_anomaly("lascar", "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "so2",  "2026-03-05", zscore=6.0)
        n = db.detect_multi_product_alerts(memory_db)
        assert n == 1
        rows = _multi_rows(memory_db)
        assert len(rows) == 1
        vol, _, products, n_prod, zmax, zsum, conf = rows[0]
        assert vol == "lascar"
        assert sorted(json.loads(products)) == ["so2", "swir"]
        assert n_prod == 2
        assert conf == "medium"
        assert zmax == 6.0
        assert zsum == 10.0

    def test_three_products_high_confidence(self, memory_db, insert_anomaly):
        # 3 productos distintos en ventana -> confidence 'high'.
        insert_anomaly("lascar", "swir",     "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "so2",      "2026-03-04", zscore=5.0)
        insert_anomaly("lascar", "def_desc", "2026-03-07", zscore=3.5)
        n = db.detect_multi_product_alerts(memory_db)
        assert n == 1
        rows = _multi_rows(memory_db)
        vol, _, products, n_prod, zmax, zsum, conf = rows[0]
        assert n_prod == 3
        assert conf == "high"
        assert sorted(json.loads(products)) == ["def_desc", "so2", "swir"]

    def test_duplicate_products_count_once(self, memory_db, insert_anomaly):
        # 3 anomalias pero solo 2 productos distintos -> n_products = 2, medium.
        insert_anomaly("lascar", "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "swir", "2026-03-03", zscore=4.5)
        insert_anomaly("lascar", "so2",  "2026-03-05", zscore=6.0)
        db.detect_multi_product_alerts(memory_db)
        rows = _multi_rows(memory_db)
        assert len(rows) == 1
        _, _, products, n_prod, _, _, conf = rows[0]
        assert n_prod == 2
        assert conf == "medium"

    def test_idempotent_rerun(self, memory_db, insert_anomaly):
        # Re-correr no debe duplicar (UNIQUE(volcano_key, date_center)).
        insert_anomaly("lascar", "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "so2",  "2026-03-05", zscore=6.0)
        first = db.detect_multi_product_alerts(memory_db)
        second = db.detect_multi_product_alerts(memory_db)
        assert first == 1
        assert second == 0
        assert len(_multi_rows(memory_db)) == 1

    def test_separate_clusters_two_alerts(self, memory_db, insert_anomaly):
        # Dos episodios separados (>14d entre ellos), cada uno con 2 productos.
        insert_anomaly("lascar", "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "so2",  "2026-03-03", zscore=5.0)
        insert_anomaly("lascar", "swir", "2026-05-01", zscore=4.0)
        insert_anomaly("lascar", "so2",  "2026-05-03", zscore=5.0)
        n = db.detect_multi_product_alerts(memory_db)
        assert n == 2
        assert len(_multi_rows(memory_db)) == 2

    def test_window_days_param_respected(self, memory_db, insert_anomaly):
        # Con window_days chico, dos productos a 10d caen en clusters distintos.
        insert_anomaly("lascar", "swir", "2026-03-01", zscore=4.0)
        insert_anomaly("lascar", "so2",  "2026-03-11", zscore=5.0)
        # window=5: 10 dias de separacion -> NO se agrupan -> sin alerta
        assert db.detect_multi_product_alerts(memory_db, window_days=5) == 0
        # window=20: si se agrupan -> 1 alerta
        assert db.detect_multi_product_alerts(memory_db, window_days=20) == 1


# --- _julian helper ---------------------------------------------------------

class TestJulian:
    def test_ordinal_diff_in_days(self):
        a = db._julian("2026-03-01")
        b = db._julian("2026-03-11")
        assert abs(b - a) == 10

    def test_invalid_returns_zero(self):
        assert db._julian("no-date") == 0
