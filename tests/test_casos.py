import re

import pytest

from core.aviso import Caso
from core.casos import PLANTILLAS, texto_del_caso

PERSONA = "Abuela Prueba"
FAMILIAR = "Familiar Prueba"


def test_hay_plantilla_para_cada_caso() -> None:
    assert set(PLANTILLAS) == set(Caso)


def test_el_catalogo_es_inmutable() -> None:
    with pytest.raises(TypeError):
        PLANTILLAS[Caso.SUENO_IRREGULAR] = "otro"  # type: ignore[index]


@pytest.mark.parametrize("caso", list(Caso))
@pytest.mark.parametrize(
    "fragmento",
    ["asistente automático", "VitaPlus", "112", "no es una emergencia", "pulse 1"],
)
def test_cada_texto_cumple_los_guardarrailes(caso: Caso, fragmento: str) -> None:
    texto = texto_del_caso(caso, PERSONA, FAMILIAR)

    assert fragmento in texto


@pytest.mark.parametrize("caso", list(Caso))
def test_los_nombres_se_sustituyen_y_no_quedan_llaves(caso: Caso) -> None:
    texto = texto_del_caso(caso, PERSONA, FAMILIAR)

    assert PERSONA in texto
    assert FAMILIAR in texto
    assert "{" not in texto
    assert "}" not in texto


@pytest.mark.parametrize("caso", list(Caso))
def test_ningun_texto_da_consejos_medicos(caso: Caso) -> None:
    texto = texto_del_caso(caso, PERSONA, FAMILIAR).lower()

    prohibidas = r"\b(dosis|mg|tome|tomar|deje de|diagnóstic\w*|ibuprofeno)\b"
    assert re.search(prohibidas, texto) is None


def test_un_nombre_con_llaves_no_rompe_la_plantilla() -> None:
    texto = texto_del_caso(Caso.SIN_ACTIVIDAD_HOY, "{persona}", "{0}")

    assert "{persona}" in texto
    assert "{0}" in texto


def test_cada_caso_tiene_un_texto_distinto() -> None:
    textos = {texto_del_caso(c, PERSONA, FAMILIAR) for c in Caso}

    assert len(textos) == len(Caso)
