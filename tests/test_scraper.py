"""
Tests para los parsers de scraper.py (entrada strings -> datos).

Cubre:
  classify_product(path)   -> (product_type, sensor)
  parse_timestamp(path)    -> fecha ISO desde el filename
  extract_image_paths(html)-> lista de paths data_mounts/...png
  extract_timeseries_json(html, name, sid) -> dict con trazas Plotly

Los formatos de path se derivaron de catalog.csv (datos reales), p.ej.:
  data_mounts/copahue/2026/copahue_20260312T095629_20260324T095630_VV_coh.png
"""

from unittest.mock import Mock

import pytest
import requests

import scraper


# --- capa de red: fetch_page / download_image -------------------------------
#
# Estas son las "canerias" del pipeline: red y disco. Se testean con dobles
# (unittest.mock) en vez de pegarle al servidor real de MOUNTS, porque un test
# debe ser rapido, determinista y capaz de simular fallas que no podemos
# provocar de verdad (un 500, una conexion cortada a mitad de imagen).
# time.sleep se parchea para que el backoff no haga esperar al test.

@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda *_: None)


class TestFetchPage:
    def test_devuelve_texto_en_exito(self, no_sleep):
        r = Mock(); r.text = "<html>ok</html>"; r.raise_for_status = Mock()
        sess = Mock(); sess.get.return_value = r
        assert scraper.fetch_page(sess, "http://x/p") == "<html>ok</html>"
        assert sess.get.call_count == 1

    def test_reintenta_y_devuelve_none_si_todo_falla(self, no_sleep):
        sess = Mock()
        sess.get.side_effect = requests.RequestException("boom")
        assert scraper.fetch_page(sess, "http://x/p", retries=3) is None
        assert sess.get.call_count == 3, "debe agotar los 3 intentos"

    def test_se_recupera_en_el_segundo_intento(self, no_sleep):
        ok = Mock(); ok.text = "recuperado"; ok.raise_for_status = Mock()
        sess = Mock()
        sess.get.side_effect = [requests.RequestException("timeout"), ok]
        assert scraper.fetch_page(sess, "http://x/p") == "recuperado"
        assert sess.get.call_count == 2

    def test_http_500_cuenta_como_falla(self, no_sleep):
        r = Mock()
        r.raise_for_status.side_effect = requests.HTTPError("500")
        sess = Mock(); sess.get.return_value = r
        assert scraper.fetch_page(sess, "http://x/p", retries=2) is None

    def test_respeta_el_numero_de_reintentos(self, no_sleep):
        sess = Mock()
        sess.get.side_effect = requests.RequestException("x")
        scraper.fetch_page(sess, "http://x/p", retries=1)
        assert sess.get.call_count == 1


def _img_response(chunks):
    r = Mock()
    r.raise_for_status = Mock()
    r.iter_content = Mock(return_value=iter(chunks))
    return r


class TestDownloadImage:
    def test_descarga_y_escribe_el_archivo(self, tmp_path, no_sleep):
        dest = tmp_path / "sub" / "img.png"
        sess = Mock(); sess.get.return_value = _img_response([b"PNG", b"data"])
        assert scraper.download_image(sess, "http://x/i.png", dest) is True
        assert dest.read_bytes() == b"PNGdata"

    def test_crea_directorios_padre(self, tmp_path, no_sleep):
        dest = tmp_path / "a" / "b" / "c" / "img.png"
        sess = Mock(); sess.get.return_value = _img_response([b"x"])
        scraper.download_image(sess, "http://x/i.png", dest)
        assert dest.exists()

    def test_no_re_descarga_si_ya_existe(self, tmp_path, no_sleep):
        # Idempotencia: el scraper corre cada 6h y no debe re-bajar todo.
        dest = tmp_path / "img.png"
        dest.write_bytes(b"ya-estaba")
        sess = Mock()
        assert scraper.download_image(sess, "http://x/i.png", dest) is True
        sess.get.assert_not_called()
        assert dest.read_bytes() == b"ya-estaba"

    def test_devuelve_false_si_agota_reintentos(self, tmp_path, no_sleep):
        dest = tmp_path / "img.png"
        sess = Mock()
        sess.get.side_effect = requests.RequestException("sin red")
        assert scraper.download_image(sess, "http://x/i.png", dest, retries=3) is False
        assert sess.get.call_count == 3

    def test_se_recupera_en_el_segundo_intento(self, tmp_path, no_sleep):
        dest = tmp_path / "img.png"
        sess = Mock()
        sess.get.side_effect = [requests.RequestException("cae"),
                                _img_response([b"bien"])]
        assert scraper.download_image(sess, "http://x/i.png", dest) is True
        assert dest.read_bytes() == b"bien"

    def test_corte_a_mitad_no_deja_imagen_truncada(self, tmp_path, no_sleep):
        """
        Si la conexion se corta a mitad de la descarga y se agotan los
        reintentos, en disco queda un PNG parcial. Como download_image solo
        mira dest.exists() al entrar, la corrida SIGUIENTE lo da por bueno y
        no lo vuelve a bajar: la imagen queda corrupta para siempre.

        El comportamiento correcto es no dejar rastro de una descarga
        incompleta (escribir a temporal y renombrar al final, que ademas es
        atomico).
        """
        dest = tmp_path / "img.png"

        def corta_a_mitad(*a, **k):
            r = Mock()
            r.raise_for_status = Mock()

            def gen(**kw):
                yield b"mitad-de-"
                raise requests.RequestException("conexion cortada")
            r.iter_content = gen
            return r

        sess = Mock(); sess.get.side_effect = corta_a_mitad
        assert scraper.download_image(sess, "http://x/i.png", dest, retries=2) is False
        assert not dest.exists(), (
            "una descarga fallida no debe dejar un archivo parcial: la proxima "
            "corrida lo saltearia por dest.exists() y nunca se repararia"
        )

class TestClassifyProduct:
    def test_s2_hotspot(self):
        path = "data_mounts/lascar/2026/lascar_20260105T143521_B12B11B8A_nir.png"
        assert scraper.classify_product(path) == ("S2_hotspot", "Sentinel-2")

    def test_s5p_so2(self):
        path = "data_mounts/lascar/2026/lascar_20260105_SO2_PBL.png"
        assert scraper.classify_product(path) == ("S5P_SO2", "Sentinel-5P")

    def test_s1_coherence(self):
        path = ("data_mounts/copahue/2026/"
                "copahue_20260312T095629_20260324T095630_VV_coh.png")
        assert scraper.classify_product(path) == ("S1_coherence", "Sentinel-1")

    def test_s1_interferogram(self):
        path = "data_mounts/villarrica/2025/villarrica_20250101T101010_VV_ifg.png"
        assert scraper.classify_product(path) == ("S1_ifg", "Sentinel-1")

    def test_s1_intensity_fcnn(self):
        path = "data_mounts/llaima/2025/llaima_20250101T101010_VV_int_fcnn.png"
        assert scraper.classify_product(path) == ("S1_intensity", "Sentinel-1")

    def test_s1_disp(self):
        path = ("data_mounts/copahue/2026/"
                "copahue_20260312T095629_20260324T095630_VV_disp.png")
        assert scraper.classify_product(path) == ("S1_disp", "Sentinel-1")

    def test_unknown_product(self):
        path = "data_mounts/lascar/2026/lascar_something_unmapped.png"
        assert scraper.classify_product(path) == ("unknown", "unknown")


# --- parse_timestamp --------------------------------------------------------

class TestParseTimestamp:
    def test_full_timestamp_with_time(self):
        # YYYYMMDDTHHMMSS -> ISO datetime
        path = "data_mounts/lascar/2026/lascar_20260105T143521_B12B11B8A_nir.png"
        assert scraper.parse_timestamp(path) == "2026-01-05T14:35:21"

    def test_date_only_so2(self):
        # Sin componente T -> cae al patron \d{8} -> ISO date
        path = "data_mounts/lascar/2026/lascar_20260105_SO2_PBL.png"
        assert scraper.parse_timestamp(path) == "2026-01-05"

    def test_takes_first_timestamp_when_two_present(self):
        # El filename de coherencia tiene DOS timestamps (par interferometrico).
        # re.search devuelve el PRIMERO (fecha de adquisicion base).
        path = ("data_mounts/copahue/2026/"
                "copahue_20260312T095629_20260324T095630_VV_coh.png")
        assert scraper.parse_timestamp(path) == "2026-03-12T09:56:29"

    def test_no_timestamp_returns_empty(self):
        path = "data_mounts/lascar/2026/lascar_nodate.png"
        assert scraper.parse_timestamp(path) == ""

    def test_operates_on_basename_only(self):
        # Aunque el directorio contiene "2026", el parse usa solo el filename.
        path = "data_mounts/lascar/2026/lascar_20251231T000000_VV_ifg.png"
        assert scraper.parse_timestamp(path) == "2025-12-31T00:00:00"


# --- extract_image_paths ----------------------------------------------------

class TestExtractImagePaths:
    def test_extracts_all_unique_paths(self, sample_html):
        paths = scraper.extract_image_paths(sample_html)
        # El fixture tiene 6 paths (3 swir + 2 so2 + 1 coh), todos distintos.
        assert len(paths) == 6
        assert all(p.startswith("data_mounts/") for p in paths)
        assert all(p.endswith(".png") for p in paths)

    def test_includes_expected_paths(self, sample_html):
        paths = scraper.extract_image_paths(sample_html)
        assert ("data_mounts/lascar/2026/"
                "lascar_20260105T143521_B12B11B8A_nir.png") in paths
        assert "data_mounts/lascar/2026/lascar_20260105_SO2_PBL.png" in paths

    def test_deduplicates_preserving_order(self):
        html = (
            'x = "data_mounts/a/2026/a_VV_ifg.png" '
            'y = "data_mounts/a/2026/a_VV_ifg.png" '
            'z = "data_mounts/b/2026/b_VV_coh.png"'
        )
        paths = scraper.extract_image_paths(html)
        assert paths == [
            "data_mounts/a/2026/a_VV_ifg.png",
            "data_mounts/b/2026/b_VV_coh.png",
        ]

    def test_no_matches_returns_empty(self):
        assert scraper.extract_image_paths("<html>nada aqui</html>") == []

    def test_ignores_non_png(self):
        html = 'data_mounts/a/2026/a.jpg data_mounts/a/2026/a_VV_ifg.png'
        paths = scraper.extract_image_paths(html)
        assert paths == ["data_mounts/a/2026/a_VV_ifg.png"]


# --- extract_timeseries_json ------------------------------------------------

class TestExtractTimeseriesJson:
    def test_parses_var_graph_block(self, sample_html):
        data = scraper.extract_timeseries_json(sample_html, "lascar", 355100)
        assert data["volcano"] == "lascar"
        assert data["id"] == 355100
        assert "fetched_at" in data
        names = {t["name"] for t in data["traces"]}
        assert names == {"swir", "so2", "coh_desc"}

    def test_trace_xy_preserved(self, sample_html):
        data = scraper.extract_timeseries_json(sample_html, "lascar", 355100)
        swir = next(t for t in data["traces"] if t["name"] == "swir")
        assert swir["x"] == ["2026-01-05", "2026-01-10", "2026-01-15"]
        assert swir["y"] == [3, 4, 12]

    def test_no_graph_block_returns_empty_dict(self):
        assert scraper.extract_timeseries_json("<html></html>", "x", 1) == {}
