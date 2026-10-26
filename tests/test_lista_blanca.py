import dataclasses

import pytest

from core.errores import ErrorConfiguracion
from core.lista_blanca import ListaBlanca


def test_permite_los_numeros_de_la_lista() -> None:
    lista = ListaBlanca.desde_texto("+34600000001, +34600000002")

    assert lista.permite("+34600000001")
    assert lista.permite("+34600000002")


def test_no_permite_un_numero_fuera_de_la_lista() -> None:
    lista = ListaBlanca.desde_texto("+34600000001")

    assert not lista.permite("+34600000009")


def test_ignora_espacios_y_entradas_vacias() -> None:
    lista = ListaBlanca.desde_texto(" +34600000001 ,, ,+34600000002, ")

    assert len(lista.telefonos) == 2


@pytest.mark.parametrize("texto", ["", "   ", ",,"])
def test_cadena_vacia_no_permite_nada(texto: str) -> None:
    lista = ListaBlanca.desde_texto(texto)

    assert not lista.telefonos
    assert not lista.permite("+34600000001")


@pytest.mark.parametrize("texto", ["600000001", "+34600000001,abc", "+0123456789"])
def test_numero_mal_formado_en_la_config_lanza_error_de_configuracion(
    texto: str,
) -> None:
    with pytest.raises(ErrorConfiguracion, match="E.164"):
        ListaBlanca.desde_texto(texto)


def test_el_error_indica_la_posicion_y_no_el_valor() -> None:
    with pytest.raises(ErrorConfiguracion) as info:
        ListaBlanca.desde_texto("+34600000001, +34600123456x")

    mensaje = str(info.value)
    assert "entrada nº 2 no tiene formato E.164" in mensaje
    assert "6001" not in mensaje
    assert "+34" not in mensaje


def test_constructor_directo_valida_cada_telefono() -> None:
    with pytest.raises(ErrorConfiguracion):
        ListaBlanca(telefonos=frozenset({"abc"}))


def test_constructor_directo_no_filtra_el_valor_en_el_error() -> None:
    with pytest.raises(ErrorConfiguracion) as info:
        ListaBlanca(telefonos=frozenset({"abc-secreto"}))

    assert "secreto" not in str(info.value)


def test_constructor_directo_convierte_a_frozenset() -> None:
    lista = ListaBlanca(telefonos={"+34600000001"})  # type: ignore[arg-type]

    assert isinstance(lista.telefonos, frozenset)
    assert lista.permite("+34600000001")


@pytest.mark.parametrize(
    "telefono", ["", "no-es-telefono", None, 34600000001, b"+34600000001"]
)
def test_permite_devuelve_false_ante_entradas_raras(telefono: object) -> None:
    lista = ListaBlanca.desde_texto("+34600000001")

    assert lista.permite(telefono) is False  # type: ignore[arg-type]


def test_la_lista_es_inmutable() -> None:
    lista = ListaBlanca.desde_texto("+34600000001")

    with pytest.raises(dataclasses.FrozenInstanceError):
        lista.telefonos = frozenset()  # type: ignore[misc]
