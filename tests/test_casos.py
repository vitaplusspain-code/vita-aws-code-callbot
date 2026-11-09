import re

import pytest

from core.casos import FRASES_CASOS
from core.motivos import texto_detalle
from core.tipos import Caso

PERSONA = "Abuela Prueba"
PROHIBIDAS = r"\b(dosis|mg|tome|tomar|deje de|diagnóstic\w*|ibuprofeno)\b"


def _detalle(caso: Caso, persona: str = PERSONA) -> str:
    return texto_detalle(caso.value, persona, frases=FRASES_CASOS)


def test_hay_frase_para_cada_caso() -> None:
    assert set(FRASES_CASOS) == {c.value for c in Caso}


def test_el_catalogo_es_inmutable() -> None:
    with pytest.raises(TypeError):
        FRASES_CASOS["x"] = "otro"  # type: ignore[index]


@pytest.mark.parametrize("caso", list(Caso))
@pytest.mark.parametrize("fragmento", ["no es una emergencia", "112", "pulse 1"])
def test_cada_detalle_cumple_los_guardarrailes(caso: Caso, fragmento: str) -> None:
    assert fragmento in _detalle(caso)


@pytest.mark.parametrize("caso", list(Caso))
def test_el_nombre_se_sustituye_y_no_quedan_llaves(caso: Caso) -> None:
    detalle = _detalle(caso)

    assert PERSONA in detalle
    assert "{" not in detalle
    assert "}" not in detalle


@pytest.mark.parametrize("caso", list(Caso))
def test_ningun_detalle_da_consejos_medicos(caso: Caso) -> None:
    assert re.search(PROHIBIDAS, _detalle(caso).lower()) is None


@pytest.mark.parametrize("frase", list(FRASES_CASOS.values()))
def test_las_frases_solo_usan_el_marcador_persona(frase: str) -> None:
    assert set(re.findall(r"\{[^}]*\}", frase)) == {"{persona}"}


def test_un_nombre_con_llaves_no_rompe_la_frase() -> None:
    assert "{persona}" in _detalle(Caso.SIN_ACTIVIDAD_HOY, "{persona}")


def test_cada_caso_tiene_un_detalle_distinto() -> None:
    assert len({_detalle(c) for c in Caso}) == len(Caso)
