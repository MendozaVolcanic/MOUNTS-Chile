"""
Tests para export_csv.py — JSONs Plotly -> CSVs estilo VRP.

Por que importa: los CSVs son el endpoint estable que consume cualquiera de
afuera (colegas, scripts, otro dashboard). Un bug aca no rompe nada visible
en el sitio, pero entrega datos corruptos aguas abajo sin que nadie lo note.

Punto critico: un `y = None` en la traza es una NO-observacion (el satelite
no paso o no hubo dato), no un cero. Si se exportara como fila, aguas abajo
se leeria como una medicion de valor nulo.
"""

import csv
import json

import pytest

import export_csv


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    ts, out = tmp_path / "timeseries", tmp_path / "csv"
    ts.mkdir(); out.mkdir()
    monkeypatch.setattr(export_csv, "TS_DIR", ts)
    monkeypatch.setattr(export_csv, "CSV_DIR", out)
    # Un solo volcan para que los asserts sean claros
    monkeypatch.setattr(export_csv, "VOLCANES", [("lascar", "Lascar", 355100)])
    return ts, out


def write_ts(ts_dir, key, traces):
    (ts_dir / f"{key}.json").write_text(
        json.dumps({"volcano": key, "traces": traces}), encoding="utf-8")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestLoadTs:
    def test_carga_json_existente(self, dirs):
        ts, _ = dirs
        write_ts(ts, "lascar", [{"name": "swir", "x": ["2026-01-01"], "y": [1.0]}])
        assert export_csv.load_ts("lascar")["volcano"] == "lascar"

    def test_devuelve_none_si_no_existe(self, dirs):
        assert export_csv.load_ts("no-existe") is None


class TestExportPerVolcano:
    def test_escribe_csv_con_columnas_correctas(self, dirs):
        ts, out = dirs
        write_ts(ts, "lascar", [{"name": "swir", "x": ["2026-01-01T00:00:00"],
                                 "y": [7.0], "text": ["data_mounts/a.png"]}])
        export_csv.export_per_volcano()
        rows = read_csv(out / "lascar_thermal_swir.csv")
        assert list(rows[0].keys()) == export_csv.COLS
        assert rows[0]["value"] == "7.0"
        assert rows[0]["unit"] == "S2Pix"
        assert rows[0]["sensor"] == "Sentinel-2"

    def test_descarta_observaciones_nulas(self, dirs):
        # y=None es no-observacion: NO debe generar fila.
        ts, out = dirs
        write_ts(ts, "lascar", [{"name": "swir",
                                 "x": ["2026-01-01", "2026-01-02", "2026-01-03"],
                                 "y": [1.0, None, 3.0]}])
        export_csv.export_per_volcano()
        rows = read_csv(out / "lascar_thermal_swir.csv")
        assert len(rows) == 2
        assert [r["value"] for r in rows] == ["1.0", "3.0"]

    def test_construye_url_absoluta_de_imagen(self, dirs):
        ts, out = dirs
        write_ts(ts, "lascar", [{"name": "swir", "x": ["2026-01-01"], "y": [1.0],
                                 "text": ["data_mounts/lascar/2026/x.png"]}])
        export_csv.export_per_volcano()
        r = read_csv(out / "lascar_thermal_swir.csv")[0]
        assert r["image_url"] == f"{export_csv.MOUNTS_BASE}/data_mounts/lascar/2026/x.png"
        assert r["image_path"] == "data_mounts/lascar/2026/x.png"

    def test_sin_texto_deja_url_vacia(self, dirs):
        ts, out = dirs
        write_ts(ts, "lascar", [{"name": "swir", "x": ["2026-01-01"], "y": [1.0]}])
        export_csv.export_per_volcano()
        r = read_csv(out / "lascar_thermal_swir.csv")[0]
        assert r["image_url"] == ""

    def test_alinea_longitudes_desparejas(self, dirs):
        # Si MOUNTS manda x e y de distinto largo, se toma el minimo comun:
        # inventar filas seria fabricar observaciones.
        ts, out = dirs
        write_ts(ts, "lascar", [{"name": "swir",
                                 "x": ["2026-01-01", "2026-01-02", "2026-01-03"],
                                 "y": [1.0, 2.0]}])
        export_csv.export_per_volcano()
        assert len(read_csv(out / "lascar_thermal_swir.csv")) == 2

    def test_traza_vacia_no_genera_csv(self, dirs):
        ts, out = dirs
        write_ts(ts, "lascar", [{"name": "swir", "x": [], "y": []}])
        export_csv.export_per_volcano()
        assert not (out / "lascar_thermal_swir.csv").exists()

    def test_volcan_sin_json_no_rompe(self, dirs):
        # Laguna del Maule no tiene series en MOUNTS: debe saltarse limpio.
        export_csv.export_per_volcano()
        _, out = dirs
        assert list(out.iterdir()) == []

    def test_exporta_ambas_orbitas_insar(self, dirs):
        # Planchon es ASC y los demas DESC: el export no debe asumir una sola.
        ts, out = dirs
        write_ts(ts, "lascar", [
            {"name": "def_asc",  "x": ["2026-01-01"], "y": [1e-4]},
            {"name": "def_desc", "x": ["2026-01-02"], "y": [2e-4]},
        ])
        export_csv.export_per_volcano()
        assert (out / "lascar_def_asc.csv").exists()
        assert (out / "lascar_def_desc.csv").exists()

    def test_mapea_unidad_por_producto(self, dirs):
        ts, out = dirs
        write_ts(ts, "lascar", [
            {"name": "so2",      "x": ["2026-01-01"], "y": [100.0]},
            {"name": "coh_desc", "x": ["2026-01-01"], "y": [500.0]},
        ])
        export_csv.export_per_volcano()
        assert read_csv(out / "lascar_so2_mass.csv")[0]["unit"] == "tons"
        assert read_csv(out / "lascar_coh_desc.csv")[0]["unit"] == "Npix_coh<0.5"
