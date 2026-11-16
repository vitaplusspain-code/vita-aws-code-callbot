import pytest

from core.errores import ErrorConfiguracion
from handlers.config import (
    VAR_ANTIGUEDAD_MAXIMA,
    VAR_DEMO_ACTIVA,
    VAR_LISTA_BLANCA,
    VAR_LLAMADAS_ACTIVAS,
    VAR_REGLAS_SIEMPRE,
    demo_activa,
    lista_blanca_desde_entorno,
    llamadas_activas,
    reglas_desde_entorno,
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


@pytest.mark.parametrize("valor", ["true", "TRUE", " True ", "\ttRuE\n"])
def test_demo_activa_acepta_solo_true(valor: str) -> None:
    assert demo_activa({VAR_DEMO_ACTIVA: valor}) is True


@pytest.mark.parametrize("valor", ["", "false", "1", "yes", "si", "truee", " "])
def test_demo_activa_cualquier_otro_valor_es_apagada(valor: str) -> None:
    assert demo_activa({VAR_DEMO_ACTIVA: valor}) is False


def test_demo_activa_ausente_es_apagada() -> None:
    assert demo_activa({}) is False


def test_demo_activa_no_depende_de_llamadas_activas() -> None:
    assert demo_activa({VAR_LLAMADAS_ACTIVAS: "true"}) is False


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


def test_antiguedad_por_defecto_son_900_segundos() -> None:
    assert reglas_desde_entorno({}).antiguedad_maxima_segundos == 900


def test_antiguedad_se_lee_del_entorno() -> None:
    entorno = {VAR_ANTIGUEDAD_MAXIMA: " 60 "}

    assert reglas_desde_entorno(entorno).antiguedad_maxima_segundos == 60


@pytest.mark.parametrize(
    "valor",
    ["-5", "abc", "1.5", "1e3", "٣", "86401", "100000", "9" * 5000],
)
def test_antiguedad_invalida_nombra_la_variable_y_no_el_valor(valor: str) -> None:
    with pytest.raises(ErrorConfiguracion) as info:
        reglas_desde_entorno({VAR_ANTIGUEDAD_MAXIMA: valor})

    assert VAR_ANTIGUEDAD_MAXIMA in str(info.value)
    assert valor not in str(info.value)


@pytest.mark.parametrize("valor", ["0", "", "  "])
def test_antiguedad_cero_o_vacia_nombra_la_variable(valor: str) -> None:
    with pytest.raises(ErrorConfiguracion, match=VAR_ANTIGUEDAD_MAXIMA):
        reglas_desde_entorno({VAR_ANTIGUEDAD_MAXIMA: valor})


@pytest.mark.parametrize("valor", ["86400", "1", "000060"])
def test_antiguedad_dentro_del_tope_se_acepta(valor: str) -> None:
    reglas = reglas_desde_entorno({VAR_ANTIGUEDAD_MAXIMA: valor})

    assert reglas.antiguedad_maxima_segundos == int(valor)


def test_reglas_siempre_por_defecto_vacia() -> None:
    assert reglas_desde_entorno({}).reglas_siempre == frozenset()


def test_reglas_siempre_separa_por_comas_e_ignora_vacios() -> None:
    entorno = {VAR_REGLAS_SIEMPRE: " sos_pulsado, caida ,,"}

    reglas = reglas_desde_entorno(entorno)

    assert reglas.reglas_siempre == {"sos_pulsado", "caida"}


def test_reglas_siempre_invalida_es_error_de_configuracion() -> None:
    with pytest.raises(ErrorConfiguracion):
        reglas_desde_entorno({VAR_REGLAS_SIEMPRE: "a b\x00"})
