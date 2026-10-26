import pytest

from adapters.persona_en_memoria import PERSONA_DEMO_ID, PersonaEnMemoria
from core.errores import ErrorConfiguracion, PersonaNoEncontrada
from core.persona import Persona, PersonaRepository

ENTORNO = {
    "DEMO_PERSONA_NOMBRE": "Abuela Prueba",
    "DEMO_FAMILIAR_NOMBRE": "Familiar Prueba",
    "DEMO_FAMILIAR_TELEFONO": "+34600000001",
}


def test_cumple_el_protocolo_del_repositorio() -> None:
    assert isinstance(PersonaEnMemoria.desde_entorno(ENTORNO), PersonaRepository)


def test_encuentra_a_demo_01() -> None:
    persona = PersonaEnMemoria.desde_entorno(ENTORNO).obtener("demo-01")

    assert isinstance(persona, Persona)
    assert PERSONA_DEMO_ID == "demo-01"
    assert persona.persona_id == "demo-01"
    assert persona.nombre == "Abuela Prueba"
    assert persona.familiar.nombre == "Familiar Prueba"
    assert persona.familiar.telefono == "+34600000001"


@pytest.mark.parametrize("otro", ["demo-02", "", "DEMO-01", "otra-persona"])
def test_otro_id_lanza_persona_no_encontrada(otro: str) -> None:
    repo = PersonaEnMemoria.desde_entorno(ENTORNO)

    with pytest.raises(PersonaNoEncontrada) as info:
        repo.obtener(otro)

    assert "otra-persona" not in str(info.value)
    assert "demo-02" not in str(info.value)


@pytest.mark.parametrize("variable", sorted(ENTORNO))
def test_variable_que_falta_da_su_error(variable: str) -> None:
    entorno = {k: v for k, v in ENTORNO.items() if k != variable}

    with pytest.raises(ErrorConfiguracion) as info:
        PersonaEnMemoria.desde_entorno(entorno)

    assert variable in str(info.value)
    assert info.value.__context__ is None


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("DEMO_FAMILIAR_TELEFONO", "600-secreto"),
        ("DEMO_PERSONA_NOMBRE", "   "),
        ("DEMO_FAMILIAR_NOMBRE", "secreto\x00"),
    ],
)
def test_valor_invalido_nombra_la_variable_pero_no_el_valor(
    variable: str, valor: str
) -> None:
    entorno = {**ENTORNO, variable: valor}

    with pytest.raises(ErrorConfiguracion) as info:
        PersonaEnMemoria.desde_entorno(entorno)

    assert variable in str(info.value)
    assert "secreto" not in str(info.value)
    assert info.value.__context__ is None


def test_nombre_con_espacios_sobrantes_se_normaliza() -> None:
    entorno = {**ENTORNO, "DEMO_PERSONA_NOMBRE": "  Abuela Prueba  "}

    persona = PersonaEnMemoria.desde_entorno(entorno).obtener("demo-01")

    assert persona.nombre == "Abuela Prueba"


def test_telefono_con_espacios_da_error_nombrando_la_variable() -> None:
    entorno = {**ENTORNO, "DEMO_FAMILIAR_TELEFONO": " +34600000001 "}

    with pytest.raises(ErrorConfiguracion) as info:
        PersonaEnMemoria.desde_entorno(entorno)

    assert "DEMO_FAMILIAR_TELEFONO" in str(info.value)
    assert "34600000001" not in str(info.value)
