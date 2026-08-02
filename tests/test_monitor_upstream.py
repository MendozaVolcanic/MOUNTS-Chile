"""
Tests para monitor_upstream.py — el tripwire que avisa si MOUNTS cambia.

Este modulo es el que grita cuando el proveedor upstream (TU Berlin / GFZ)
cambia el markup, la calibracion o la lista de volcanes. Si falla en
silencio, seguimos scrapeando basura sin enterarnos; si grita de mas, nadie
le cree. Las dos cosas se testean aca.

Contexto historico: el dashboard llego a mostrar "4 cambios upstream
detectados" con severidad high que eran TODOS falsos — el mismo set de 6
volcanes reportado como "nuevo" cuatro veces. La causa fue que un parseo
vacio de /targets sobreescribia el baseline con [], y la corrida siguiente
veia los 6 como nuevos. `diff_target_volcanoes` encapsula esa decision para
que quede cubierta.
"""

from unittest.mock import Mock

import monitor_upstream as mu


# Los 6 volcanes chilenos que MOUNTS ya publicaba (baseline real del proyecto)
BASELINE = [
    [357070, "Chillán, Nevados de", "cl"],
    [355100, "Láscar", "cl"],
    [357110, "Llaima", "cl"],
    [357061, "Maule, Laguna del", "cl"],
    [357040, "Planchón-Peteroa", "cl"],
    [357120, "Villarrica", "cl"],
]


def _vols(chilean, n_global=None):
    """Arma la lista global de /targets con los chilenos dados + relleno."""
    others = [[900000 + i, f"Volcan{i}", "it"] for i in range(3)]
    return list(chilean) + others


class TestDiffTargetVolcanoes:
    """La decision: que guardar y si avisar de un volcan nuevo."""

    def test_sin_cambios_no_reporta(self):
        res = mu.diff_target_volcanoes(_vols(BASELINE), BASELINE)
        assert res.change is None
        assert res.chilean_state == BASELINE

    def test_parseo_vacio_conserva_baseline_y_no_reporta(self):
        # LA REGRESION: /targets devuelve 0 volcanes (fetch parcial o cambio
        # de markup). NO debe sobreescribir el estado ni reportar nada.
        res = mu.diff_target_volcanoes([], BASELINE)
        assert res.change is None, "un parseo vacio no es un cambio upstream"
        assert res.chilean_state == BASELINE, "no se debe perder el baseline"
        assert res.parse_failed is True

    def test_parseo_vacio_luego_normal_no_dispara_falsa_alarma(self):
        # Secuencia completa que producia las falsas alarmas historicas.
        paso1 = mu.diff_target_volcanoes([], BASELINE)
        assert paso1.change is None
        # La corrida siguiente parsea bien: como el baseline se conservo,
        # los 6 NO aparecen como nuevos.
        paso2 = mu.diff_target_volcanoes(_vols(BASELINE), paso1.chilean_state)
        assert paso2.change is None, "los 6 de siempre no son volcanes nuevos"

    def test_volcan_chileno_nuevo_si_reporta(self):
        nuevo = BASELINE + [[357100, "Antuco", "cl"]]
        res = mu.diff_target_volcanoes(_vols(nuevo), BASELINE)
        assert res.change is not None
        assert res.change["page"] == "/targets"
        assert res.change["new_chilean_volcanoes"] == [357100]
        assert res.change["severity"] == "high"

    def test_primera_corrida_es_inicializacion_no_cambio(self):
        # Sin baseline previo, los volcanes encontrados son inicializacion.
        res = mu.diff_target_volcanoes(_vols(BASELINE), [])
        assert res.change is None, "la primera corrida no es un cambio upstream"
        assert res.chilean_state == BASELINE

    def test_volcan_que_desaparece_no_se_reporta_como_nuevo(self):
        menos = BASELINE[:-1]
        res = mu.diff_target_volcanoes(_vols(menos), BASELINE)
        assert res.change is None
        assert res.chilean_state == menos

    def test_ignora_volcanes_no_chilenos(self):
        con_extranjero = _vols(BASELINE) + [[211060, "Etna", "it"]]
        res = mu.diff_target_volcanoes(con_extranjero, BASELINE)
        assert res.change is None

    def test_reporta_varios_nuevos_ordenados(self):
        nuevos = BASELINE + [[357100, "Antuco", "cl"], [357020, "Tupungatito", "cl"]]
        res = mu.diff_target_volcanoes(_vols(nuevos), BASELINE)
        assert res.change["new_chilean_volcanoes"] == [357020, 357100]


class TestFetchEncoding:
    """
    MOUNTS no declara charset en el Content-Type. Por spec HTTP, requests
    asume entonces ISO-8859-1 para text/*, y los acentos se rompen:
    "Chillán" -> "Chill?n". Eso corrompio upstream_state.json.
    """

    def _resp(self, content_type, apparent="utf-8"):
        r = Mock()
        r.headers = {"content-type": content_type}
        r.apparent_encoding = apparent
        r.text = "ok"
        r.raise_for_status = Mock()
        return r

    def test_fija_encoding_cuando_no_hay_charset(self):
        r = self._resp("text/html")
        sess = Mock(); sess.get.return_value = r
        mu.fetch(sess, "http://x/targets")
        assert r.encoding == "utf-8", "debe usar el encoding detectado del contenido"

    def test_respeta_charset_declarado_por_el_server(self):
        r = self._resp("text/html; charset=iso-8859-1")
        sess = Mock(); sess.get.return_value = r
        mu.fetch(sess, "http://x/targets")
        # Si el server lo declara, requests ya lo resolvio: no lo pisamos.
        assert not isinstance(r.encoding, str) or r.encoding != "utf-8"

    def test_cae_a_utf8_si_no_hay_apparent_encoding(self):
        r = self._resp("text/html", apparent=None)
        sess = Mock(); sess.get.return_value = r
        mu.fetch(sess, "http://x/targets")
        assert r.encoding == "utf-8"

    def test_propaga_error_http(self):
        import pytest
        r = self._resp("text/html")
        r.raise_for_status.side_effect = RuntimeError("500")
        sess = Mock(); sess.get.return_value = r
        with pytest.raises(RuntimeError):
            mu.fetch(sess, "http://x/targets")
