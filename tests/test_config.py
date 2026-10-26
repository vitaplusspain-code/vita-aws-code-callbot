import pytest

from core.errores import ErrorConfiguracion
from handlers.config import (
    VAR_LISTA_BLANCA,
    VAR_LLAMADAS_ACTIVAS,
    lista_blanca_desde_entorno,
    llamadas_activas,
)


@pytest.mark.parametrize("valor", ["true", "TRUE", "True", "  true  ", "\ttRuE\n"])
def test_llamadas_activas_acepta_solo_true(valor: str) -> None:
    assert llamadas_activas({VAR_LLAMADAS_ACTIVAS: valor}) is True


@pytest.mark.parametrize(
    "valor", ["", "false", "1", "yes", "si", "on", "tru e", "truee", "true;", " "]
)
def test_llamadas_activas_cualquier_otro_valor_es_desactivado(valor: str) -> None:
    assert llamadas_activas({VAR_LLAMADAS_ACTIVAS: valor}) is False


def test_llamadas_activas_ausente_es_desactivado() -> None:
    assert llamadas_activas({}) is False


def test_llamadas_activas_no_lee_otras_variables() -> None:
    assert llamadas_activas({"OTRA": "true"}) is False


def test_lista_blanca_desde_entorno_separa_por_comas() -> None:
    entorno = {VAR_LISTA_BLANCA: "+447700900001, +447700900002"}

    lista = lista_blanca_desde_entorno(entorno)

    assert lista.telefonos == {"+447700900001", "+447700900002"}


def test_lista_blanca_vacia_no_permite_nada() -> None:
    lista = lista_blanca_desde_entorno({VAR_LISTA_BLANCA: ""})

    assert not lista.permite("+447700900001")


def test_lista_blanca_ausente_es_error_de_configuracion() -> None:
    with pytest.raises(ErrorConfiguracion, match=VAR_LISTA_BLANCA):
        lista_blanca_desde_entorno({})


def test_lista_blanca_rechaza_entradas_raras_sin_limpiarlas() -> None:
    entorno = {VAR_LISTA_BLANCA: "+447700900001,SENTINELA-LISTA"}

    with pytest.raises(ErrorConfiguracion) as info:
        lista_blanca_desde_entorno(entorno)

    assert "SENTINELA-LISTA" not in str(info.value)


@pytest.mark.parametrize(
    "texto",
    [
        "+447700900001,+447700900002,",
        "+447700900001,,+447700900002",
        " +447700900001 , +447700900002 ",
    ],
)
def test_lista_blanca_ignora_separadores_vacios_y_espacios(texto: str) -> None:
    lista = lista_blanca_desde_entorno({VAR_LISTA_BLANCA: texto})

    assert lista.telefonos == {"+447700900001", "+447700900002"}


def test_lista_blanca_solo_con_espacios_no_permite_nada() -> None:
    lista = lista_blanca_desde_entorno({VAR_LISTA_BLANCA: "   "})

    assert lista.telefonos == frozenset()
