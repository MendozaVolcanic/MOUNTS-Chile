"""
Tests para image_diff.py — comparacion visual antes/despues de SWIR.

Por que importa: el diff es lo que un geologo mira para decidir si un
hot-spot crecio entre dos pasadas. Si empareja mal las imagenes (compara la
de hoy contra una de hace un ano) o si la retencion borra de mas, la lectura
visual miente.

El diff es |nueva - vieja| pixel a pixel, escalado por el percentil 95 para
que un pixel ruidoso no sature toda la imagen, y compuesto en rojo.
"""

import time

import numpy as np
import pytest
from PIL import Image

import image_diff


def png(path, color=(0, 0, 0), size=(8, 8)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "PNG")
    return path


SUF = image_diff.PRODUCT_SUFFIX  # "_B12B11B8A_nir"


class TestGetLatestTwo:
    def test_devuelve_las_dos_mas_recientes(self, tmp_path):
        d = tmp_path / "lascar" / "2026"
        for ts in ["20260101T100000", "20260615T100000", "20260731T100000"]:
            png(d / f"lascar_{ts}{SUF}.png")
        got = image_diff.get_latest_two(tmp_path / "lascar", SUF)
        assert len(got) == 2
        assert "20260731" in got[0].name, "la primera debe ser la mas nueva"
        assert "20260615" in got[1].name

    def test_ordena_correctamente_entre_anios(self, tmp_path):
        # El orden es por ruta, y los directorios son por anio: 2026 > 2025.
        png(tmp_path / "lascar" / "2025" / f"lascar_20251231T100000{SUF}.png")
        png(tmp_path / "lascar" / "2026" / f"lascar_20260101T100000{SUF}.png")
        got = image_diff.get_latest_two(tmp_path / "lascar", SUF)
        assert "20260101" in got[0].name

    def test_menos_de_dos_imagenes(self, tmp_path):
        png(tmp_path / "lascar" / "2026" / f"lascar_20260101T100000{SUF}.png")
        assert len(image_diff.get_latest_two(tmp_path / "lascar", SUF)) == 1

    def test_directorio_inexistente(self, tmp_path):
        assert image_diff.get_latest_two(tmp_path / "no-existe", SUF) == []

    def test_ignora_otros_productos(self, tmp_path):
        # Solo SWIR entra al diff; SO2 e InSAR no deben colarse.
        d = tmp_path / "lascar" / "2026"
        png(d / f"lascar_20260731T100000{SUF}.png")
        png(d / "lascar_20260731_SO2_PBL.png")
        png(d / "lascar_20260731T100000_VV_coh.png")
        got = image_diff.get_latest_two(tmp_path / "lascar", SUF)
        assert len(got) == 1
        assert SUF in got[0].name


class TestComputeDiff:
    def test_imagenes_identicas_dan_diff_negro(self, tmp_path):
        a = png(tmp_path / "a.png", (120, 120, 120))
        b = png(tmp_path / "b.png", (120, 120, 120))
        out = tmp_path / "d" / "diff.png"
        image_diff.compute_diff(a, b, out)
        arr = np.array(Image.open(out))
        assert arr.max() == 0, "sin cambios reales el diff debe ser negro"

    def test_imagenes_distintas_dan_senal(self, tmp_path):
        a = png(tmp_path / "a.png", (255, 255, 255))
        b = png(tmp_path / "b.png", (0, 0, 0))
        out = tmp_path / "diff.png"
        image_diff.compute_diff(a, b, out)
        arr = np.array(Image.open(out))
        assert arr.max() > 0

    def test_resalta_en_rojo(self, tmp_path):
        # El compuesto amplifica R sobre G y B para que el cambio salte.
        a = png(tmp_path / "a.png", (255, 255, 255))
        b = png(tmp_path / "b.png", (0, 0, 0))
        out = tmp_path / "diff.png"
        image_diff.compute_diff(a, b, out)
        arr = np.array(Image.open(out))
        assert arr[..., 0].max() > arr[..., 1].max() >= arr[..., 2].max()

    def test_redimensiona_si_los_tamanos_diferen(self, tmp_path):
        # MOUNTS puede cambiar el tamano del render entre pasadas.
        a = png(tmp_path / "a.png", (200, 200, 200), size=(16, 12))
        b = png(tmp_path / "b.png", (0, 0, 0), size=(8, 6))
        out = tmp_path / "diff.png"
        image_diff.compute_diff(a, b, out)
        assert Image.open(out).size == (16, 12), "el diff sigue el tamano de la nueva"

    def test_crea_el_directorio_de_salida(self, tmp_path):
        a = png(tmp_path / "a.png")
        b = png(tmp_path / "b.png")
        out = tmp_path / "x" / "y" / "diff.png"
        image_diff.compute_diff(a, b, out)
        assert out.exists()


class TestCleanupOld:
    @pytest.fixture
    def latest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_diff, "LATEST", tmp_path)
        monkeypatch.setattr(image_diff, "VOLCANES", ["lascar"])
        d = tmp_path / "lascar" / "diff"
        d.mkdir(parents=True)
        return d

    def _aged(self, path, days):
        path.write_bytes(b"x")
        old = time.time() - days * 86400
        import os
        os.utime(path, (old, old))
        return path

    def test_borra_los_viejos_y_conserva_los_recientes(self, latest):
        self._aged(latest / "viejo.png", 45)
        self._aged(latest / "nuevo.png", 3)
        n = image_diff.cleanup_old(retention_days=30)
        assert n == 1
        assert not (latest / "viejo.png").exists()
        assert (latest / "nuevo.png").exists()

    def test_no_borra_nada_si_todo_es_reciente(self, latest):
        self._aged(latest / "a.png", 1)
        assert image_diff.cleanup_old(retention_days=30) == 0

    def test_respeta_la_ventana_de_retencion(self, latest):
        self._aged(latest / "a.png", 10)
        assert image_diff.cleanup_old(retention_days=5) == 1

    def test_directorio_inexistente_no_falla(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_diff, "LATEST", tmp_path / "vacio")
        monkeypatch.setattr(image_diff, "VOLCANES", ["lascar"])
        assert image_diff.cleanup_old() == 0
