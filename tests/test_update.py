"""
Tests para update.py — el orquestador de los 10 pasos del pipeline.

Por que importa: si un paso falla y los siguientes corren igual, se publica
un dashboard construido sobre datos a medias — y se ve perfectamente normal.
Ese es el modo de falla peligroso en monitoreo: no el error visible, sino el
tablero que parece sano y no lo esta. El contrato es fail-fast.

Tambien se fija el ORDEN, que es una decision de diseno explicita del
proyecto: el pipeline es secuencial a proposito (no paralelizar: hay race
conditions sobre la DB y los archivos generados).
"""

from unittest.mock import Mock, patch

import pytest

import update


class TestRunStep:
    def test_exito_devuelve_true(self):
        with patch.object(update.subprocess, "run",
                          return_value=Mock(returncode=0)) as run:
            assert update.run_step("x.py", "desc") is True
            run.assert_called_once()

    def test_returncode_distinto_de_cero_devuelve_false(self):
        with patch.object(update.subprocess, "run",
                          return_value=Mock(returncode=1)):
            assert update.run_step("x.py", "desc") is False

    def test_skip_no_ejecuta_el_script(self):
        with patch.object(update.subprocess, "run") as run:
            assert update.run_step("x.py", "desc", skip=True) is True
            run.assert_not_called()

    def test_corre_con_el_interprete_actual(self):
        # Debe usar sys.executable, no un "python" del PATH que podria ser otro.
        with patch.object(update.subprocess, "run",
                          return_value=Mock(returncode=0)) as run:
            update.run_step("x.py", "desc")
            assert run.call_args[0][0][0] == update.sys.executable


class TestPipelineOrder:
    """El orden no es cosmetico: cada paso consume lo que produjo el anterior."""

    def _names(self):
        return [s[0] for s in update.STEPS]

    def test_fetch_es_el_primero(self):
        assert self._names()[0] == "fetch_latest.py"

    def test_html_es_el_ultimo(self):
        # El dashboard se arma con TODO ya calculado.
        assert self._names()[-1] == "generar_html.py"

    def test_anomalies_antes_que_db_y_html(self):
        n = self._names()
        assert n.index("anomalies.py") < n.index("db.py")
        assert n.index("anomalies.py") < n.index("generar_html.py")

    def test_sync_latest_antes_de_image_diff(self):
        # image_diff compara lo que sync_latest dejo en latest/.
        n = self._names()
        assert n.index("sync_latest.py") < n.index("image_diff.py")

    def test_export_csv_despues_de_anomalies(self):
        n = self._names()
        assert n.index("export_csv.py") > n.index("anomalies.py")

    def test_solo_fetch_es_salteable(self):
        # El flag --skip-fetch debe afectar unicamente a la descarga.
        salteables = [s[0] for s in update.STEPS if s[2]]
        assert salteables == ["fetch_latest.py"]

    def test_no_hay_pasos_duplicados(self):
        n = self._names()
        assert len(n) == len(set(n))


class TestMainFailFast:
    def _run_main(self, argv, side_effect):
        with patch.object(update.sys, "argv", argv), \
             patch.object(update, "run_step", side_effect=side_effect) as rs:
            with pytest.raises(SystemExit) as exc:
                update.main()
            return rs, exc.value.code

    def test_aborta_en_el_primer_fallo(self):
        # Falla el 3er paso: los 7 restantes NO deben correr.
        calls = []

        def fake(script, desc, skip=False):
            calls.append(script)
            return len(calls) < 3

        rs, code = self._run_main(["update.py"], fake)
        assert code == 1, "debe salir con codigo de error"
        assert len(calls) == 3, "no debe seguir despues del fallo"
        assert calls[-1] == update.STEPS[2][0]

    def test_pipeline_completo_no_aborta(self):
        with patch.object(update.sys, "argv", ["update.py"]), \
             patch.object(update, "run_step", return_value=True) as rs:
            update.main()   # no debe levantar SystemExit
            assert rs.call_count == len(update.STEPS)

    def test_skip_fetch_marca_solo_el_fetch(self):
        vistos = {}

        def fake(script, desc, skip=False):
            vistos[script] = skip
            return True

        with patch.object(update.sys, "argv", ["update.py", "--skip-fetch"]), \
             patch.object(update, "run_step", side_effect=fake):
            update.main()

        assert vistos["fetch_latest.py"] is True
        assert all(v is False for k, v in vistos.items() if k != "fetch_latest.py")
