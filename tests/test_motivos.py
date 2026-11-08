import re
from types import MappingProxyType

import pytest

from core.motivos import (
    FRASE_GENERICA,
    FRASES_POR_REGLA,
    VERSION_GUION,
    texto_detalle,
    texto_saludo,
)

PERSONA = "Carmen"
FAMILIAR = "Francisco"
FRASES_PRUEBA = MappingProxyType({"sos": "{persona} ha pulsado el botón de ayuda."})
PROHIBIDAS = r"\b(dosis|mg|tome|tomar|deje de|diagnóstic\w*|ibuprofeno)\b"


def _detalles() -> list[str]:
    """Detalle de cada frase del catálogo y de la genérica."""
    reglas = [*FRASES_POR_REGLA, "regla-desconocida"]
    return [texto_detalle(regla, PERSONA) for regla in reglas]


def _todos() -> list[str]:
    return [texto_saludo(FAMILIAR), *_detalles()]


def test_el_catalogo_es_inmutable() -> None:
    with pytest.raises(TypeError):
        FRASES_POR_REGLA["x"] = "otra"  # type: ignore[index]


def test_hay_version_del_guion() -> None:
    assert VERSION_GUION


@pytest.mark.parametrize("fragmento", ["asistente automático", "VitaPlus", "pulse 1"])
def test_el_saludo_se_identifica_y_pide_confirmar_la_identidad(fragmento: str) -> None:
    assert fragmento in texto_saludo(FAMILIAR)


def test_el_saludo_nombra_al_familiar() -> None:
    assert FAMILIAR in texto_saludo(FAMILIAR)


@pytest.mark.parametrize("fragmento", ["112", "pulse 1"])
def test_cada_detalle_deriva_al_112_y_ofrece_repetir(fragmento: str) -> None:
    for detalle in _detalles():
        assert fragmento in detalle


def test_cada_detalle_nombra_a_la_persona() -> None:
    for detalle in _detalles():
        assert PERSONA in detalle


def test_ningun_texto_dice_que_no_es_una_emergencia() -> None:
    for texto in _todos():
        assert "emergencia" not in texto.lower()


def test_ningun_texto_da_consejos_medicos() -> None:
    for texto in _todos():
        assert re.search(PROHIBIDAS, texto.lower()) is None


def test_una_regla_desconocida_usa_la_frase_generica() -> None:
    detalle = texto_detalle("regla-desconocida", PERSONA)

    assert detalle.startswith(FRASE_GENERICA.format(persona=PERSONA))


def test_una_regla_del_catalogo_usa_su_frase() -> None:
    detalle = texto_detalle("sos", PERSONA, frases=FRASES_PRUEBA)

    assert detalle.startswith("Carmen ha pulsado el botón de ayuda.")


def test_el_saludo_no_revela_nada_de_la_persona_ni_del_motivo() -> None:
    saludo = texto_saludo(FAMILIAR)

    assert PERSONA not in saludo
    assert "alerta" not in saludo.lower()


def test_nombres_con_llaves_no_rompen_las_plantillas() -> None:
    assert "{0}" in texto_saludo("{0}")
    assert "{persona}" in texto_detalle("x", "{persona}")
    assert "{familiar}" in texto_detalle("sos", "{familiar}", frases=FRASES_PRUEBA)


def test_no_quedan_marcadores_sin_sustituir() -> None:
    for texto in _todos():
        assert "{" not in texto
        assert "}" not in texto


def test_una_frase_con_marcadores_desconocidos_no_rompe_el_detalle() -> None:
    frases = MappingProxyType({"r": "Aviso {x} de {persona}."})

    assert texto_detalle("r", PERSONA, frases=frases).startswith("Aviso {x} de Carmen.")


def test_las_frases_del_catalogo_solo_usan_el_marcador_persona() -> None:
    for frase in [*FRASES_POR_REGLA.values(), FRASE_GENERICA]:
        assert set(re.findall(r"\{[^}]*\}", frase)) <= {"{persona}"}
