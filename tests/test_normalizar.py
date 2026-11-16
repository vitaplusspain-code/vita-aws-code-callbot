import pytest

from core.normalizar import limpiar_texto, normalizar, normalizar_con_posiciones


def test_normalizar() -> None:
    assert normalizar("  ¡Sí, Mamá!  Más   o menos... ") == "si mama mas o menos"
    assert normalizar("Ñandú") == "nandu"


def test_normalizar_quita_ancho_cero_y_control() -> None:
    assert normalizar("me he ca\u200bído") == "me he caido"
    assert normalizar("a\x00b") == "ab"


def test_normalizar_los_saltos_de_linea_separan_palabras() -> None:
    assert normalizar("hola\nmundo\t!") == "hola mundo"


def test_normalizar_usa_nfkd_para_compatibilidad() -> None:
    assert normalizar("ﬁn ①") == "fin 1"


def test_posiciones_apuntan_al_texto_original() -> None:
    normalizado, posiciones = normalizar_con_posiciones("¡Sí!  Ya")

    assert normalizado == "si ya"
    assert posiciones == (1, 2, 3, 6, 7)


def test_posiciones_de_texto_vacio() -> None:
    assert normalizar_con_posiciones("...") == ("", ())


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("  sopa \n y\t fruta ", "sopa y fruta"),
        ("a\x00b\u200bc", "abc"),
        ("\x00\n", ""),
        ("", ""),
        ("Sí, él", "Sí, él"),
    ],
)
def test_limpiar_texto(texto: str, esperado: str) -> None:
    assert limpiar_texto(texto) == esperado
