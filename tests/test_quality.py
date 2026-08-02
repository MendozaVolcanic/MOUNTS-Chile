"""
Tests para quality.py — gap analysis de las series.

Por que importa: este modulo decide si FALTA dato. Un bug aca no tira un
error, produce falsa tranquilidad ("cobertura ok") mientras media serie no
llego. Para monitoreo volcanico, un hueco no detectado es peor que un dato
ruidoso: el hueco se lee como "sin actividad".

Regla del detector: hay gap cuando el intervalo entre observaciones
consecutivas supera 3x el revisit nominal del sensor. El factor 3 tolera
que un pasaje se pierda por nubes u orbita sin gritar.
"""

import json

import pytest

import quality


@pytest.fixture
def ts_dir(tmp_path, monkeypatch):
    """Redirige TS_DIR a un directorio temporal (no toca timeseries/ real)."""
    d = tmp_path / "timeseries"
    d.mkdir()
    monkeypatch.setattr(quality, "TS_DIR", d)
    return d


def write_trace(ts_dir, volcano, name, xs, ys=None):
    ys = [1.0] * len(xs) if ys is None else ys
    payload = {"volcano": volcano, "traces": [{"name": name, "x": xs, "y": ys}]}
    (ts_dir / f"{volcano}.json").write_text(
        json.dumps(payload), encoding="utf-8")


def days(n):
    """Fechas diarias consecutivas, n dias desde 2026-01-01."""
    from datetime import datetime, timedelta
    base = datetime(2026, 1, 1)
    return [(base + timedelta(days=i)).isoformat() for i in range(n)]


class TestLoadTrace:
    def test_devuelve_pares_x_y(self, ts_dir):
        write_trace(ts_dir, "lascar", "swir", days(3), [1.0, 2.0, 3.0])
        pairs = quality.load_trace("lascar", "swir")
        assert len(pairs) == 3
        assert pairs[0][1] == 1.0

    def test_descarta_y_nulos(self, ts_dir):
        # Un y=None es una no-observacion, no un cero: no debe contar.
        write_trace(ts_dir, "lascar", "swir", days(4), [1.0, None, 3.0, None])
        assert len(quality.load_trace("lascar", "swir")) == 2

    def test_volcan_inexistente_devuelve_vacio(self, ts_dir):
        assert quality.load_trace("no-existe", "swir") == []

    def test_traza_inexistente_devuelve_vacio(self, ts_dir):
        write_trace(ts_dir, "lascar", "swir", days(3))
        assert quality.load_trace("lascar", "so2") == []


class TestAnalyzeGaps:
    def test_serie_regular_sin_gaps(self, ts_dir):
        # 20 observaciones diarias, revisit 5 -> umbral 15 d: ningun hueco.
        write_trace(ts_dir, "lascar", "swir", days(20))
        r = quality.analyze_gaps("lascar", "swir", 5)
        assert r["n_gaps"] == 0
        assert r["largest_gap_days"] == 0
        assert r["n_observations"] == 20

    def test_detecta_gap_mayor_a_3x_revisit(self, ts_dir):
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1)
        xs = [base.isoformat(),
              (base + timedelta(days=1)).isoformat(),
              (base + timedelta(days=100)).isoformat()]  # hueco de 99 d
        write_trace(ts_dir, "lascar", "swir", xs)
        r = quality.analyze_gaps("lascar", "swir", 5)
        assert r["n_gaps"] == 1
        assert r["largest_gap_days"] == 99

    def test_no_marca_gap_justo_bajo_el_umbral(self, ts_dir):
        # revisit 5 -> umbral 15 d. Un salto de 15 d NO es gap (usa >).
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1)
        xs = [base.isoformat(), (base + timedelta(days=15)).isoformat()]
        write_trace(ts_dir, "lascar", "swir", xs)
        assert quality.analyze_gaps("lascar", "swir", 5)["n_gaps"] == 0

    def test_marca_gap_apenas_supera_el_umbral(self, ts_dir):
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1)
        xs = [base.isoformat(), (base + timedelta(days=16)).isoformat()]
        write_trace(ts_dir, "lascar", "swir", xs)
        assert quality.analyze_gaps("lascar", "swir", 5)["n_gaps"] == 1

    def test_menos_de_dos_puntos_devuelve_none(self, ts_dir):
        write_trace(ts_dir, "lascar", "swir", days(1))
        assert quality.analyze_gaps("lascar", "swir", 5) is None

    def test_serie_vacia_devuelve_none(self, ts_dir):
        write_trace(ts_dir, "lascar", "swir", [], [])
        assert quality.analyze_gaps("lascar", "swir", 5) is None

    def test_deduplica_fechas_repetidas(self, ts_dir):
        # Dos observaciones con la misma fecha cuentan una sola vez.
        xs = days(3)
        write_trace(ts_dir, "lascar", "swir", xs + [xs[0]], [1.0, 2.0, 3.0, 4.0])
        assert quality.analyze_gaps("lascar", "swir", 5)["n_observations"] == 3

    def test_ordena_fechas_desordenadas(self, ts_dir):
        xs = days(5)
        write_trace(ts_dir, "lascar", "swir", list(reversed(xs)))
        r = quality.analyze_gaps("lascar", "swir", 5)
        assert r["first_date"] < r["last_date"]
        assert r["n_gaps"] == 0

    def test_gaps_top5_ordenados_por_tamano(self, ts_dir):
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1)
        offsets = [0, 30, 100, 400, 900]  # huecos crecientes
        xs = [(base + timedelta(days=o)).isoformat() for o in offsets]
        write_trace(ts_dir, "lascar", "swir", xs)
        r = quality.analyze_gaps("lascar", "swir", 5)
        sizes = [g["days"] for g in r["gaps_top5"]]
        assert sizes == sorted(sizes, reverse=True)
        assert len(r["gaps_top5"]) <= 5

    def test_cobertura_puede_superar_100_pct(self, ts_dir):
        """
        Caso real: Lascar def_asc reporta coverage_pct 266.7.

        Con 4 observaciones en 18 dias y revisit 12, el modelo espera
        18/12 = 1.5 observaciones, y 4/1.5 = 267%. Ocurre en series cortas
        o con pasadas superpuestas.

        El numero NO es un porcentaje de cobertura en sentido estricto: es
        la razon observado/esperado. Se testea para dejarlo documentado, no
        porque este bien presentarlo como "%" en el dashboard (ver nota en
        SESION_ESTADO). El chequeo de <50% que usa el panel sigue siendo
        valido; lo enganoso es solo el extremo superior.
        """
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1)
        xs = [(base + timedelta(days=o)).isoformat() for o in (0, 6, 12, 18)]
        write_trace(ts_dir, "lascar", "def_asc", xs)
        r = quality.analyze_gaps("lascar", "def_asc", 12)
        assert r["coverage_pct"] > 100
        assert r["total_span_days"] == 18
        assert r["n_observations"] == 4
