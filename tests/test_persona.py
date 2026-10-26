import pytest
from pydantic import ValidationError

from core.errores import PersonaNoEncontrada
from core.persona import Familiar, Persona, PersonaRepository


def _familiar() -> Familiar:
    return Familiar(nombre="Familiar Prueba", telefono="+34600000001")


def test_familiar_valido() -> None:
    assert _familiar().telefono == "+34600000001"


@pytest.mark.parametrize("telefono", ["", "600000001", "+34 600000001", "+0600000001"])
def test_familiar_con_telefono_invalido(telefono: str) -> None:
    with pytest.raises(ValidationError):
        Familiar(nombre="Familiar Prueba", telefono=telefono)


def test_familiar_con_nombre_vacio_es_invalido() -> None:
    with pytest.raises(ValidationError):
        Familiar(nombre="", telefono="+34600000001")


def test_persona_valida() -> None:
    persona = Persona(
        persona_id="abuela-prueba", nombre="Abuela Prueba", familiar=_familiar()
    )

    assert persona.familiar.nombre == "Familiar Prueba"


def test_persona_con_id_invalido() -> None:
    with pytest.raises(ValidationError):
        Persona(persona_id="Abuela Prueba", nombre="Abuela", familiar=_familiar())


def test_persona_rechaza_campos_extra() -> None:
    with pytest.raises(ValidationError):
        Persona(
            persona_id="abuela-prueba",
            nombre="Abuela",
            familiar=_familiar(),
            edad=90,  # type: ignore[call-arg]
        )


def test_los_modelos_son_inmutables() -> None:
    familiar = _familiar()

    with pytest.raises(ValidationError):
        familiar.nombre = "Otro"  # type: ignore[misc]


class RepositorioFalso:
    def obtener(self, persona_id: str) -> Persona:
        raise PersonaNoEncontrada(persona_id)


def test_un_objeto_con_obtener_es_un_persona_repository() -> None:
    assert isinstance(RepositorioFalso(), PersonaRepository)


def test_un_objeto_sin_obtener_no_es_un_persona_repository() -> None:
    assert not isinstance(object(), PersonaRepository)


@pytest.mark.parametrize(
    "nombre", ["   ", "\x0b", "A\nB", "A\x00B", "A\x7fB", "A\tB", "a" * 101]
)
@pytest.mark.parametrize("modelo", ["familiar", "persona"])
def test_nombre_invalido_se_rechaza(modelo: str, nombre: str) -> None:
    with pytest.raises(ValidationError):
        if modelo == "familiar":
            Familiar(nombre=nombre, telefono="+34600000001")
        else:
            Persona(persona_id="abuela-prueba", nombre=nombre, familiar=_familiar())


def test_nombre_se_limpia_de_espacios_y_admite_100_caracteres() -> None:
    assert Familiar(nombre="  Ana  ", telefono="+34600000001").nombre == "Ana"
    assert len(Familiar(nombre="a" * 100, telefono="+34600000001").nombre) == 100


def test_nombre_admite_acentos_y_simbolos() -> None:
    nombre = "María José O'Brien & Co"

    assert Familiar(nombre=nombre, telefono="+34600000001").nombre == nombre


def test_repr_y_str_no_contienen_telefono_ni_nombres() -> None:
    persona = Persona(
        persona_id="abuela-prueba",
        nombre="Abuela Secreta",
        familiar=Familiar(nombre="Familiar Secreto", telefono="+34600000001"),
    )

    for texto in (repr(persona), str(persona), repr(persona.familiar)):
        assert "+346" not in texto
        assert "Secreta" not in texto
        assert "Secreto" not in texto


def test_el_error_de_validacion_no_incluye_el_telefono_recibido() -> None:
    with pytest.raises(ValidationError) as info:
        Familiar(nombre="Familiar Prueba", telefono="+34-600-secreto")

    assert "secreto" not in str(info.value)
    assert "+34-600" not in str(info.value)


def test_el_error_de_validacion_no_incluye_el_nombre_recibido() -> None:
    with pytest.raises(ValidationError) as info:
        Familiar(nombre="Nombre\nSecreto", telefono="+34600000001")

    assert "Secreto" not in str(info.value)
