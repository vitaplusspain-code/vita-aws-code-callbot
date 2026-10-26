import pytest
from pydantic import ConfigDict, TypeAdapter, ValidationError

from core import aviso, tipos


def test_aviso_sigue_exponiendo_caso_y_persona_id() -> None:
    assert aviso.Caso is tipos.Caso
    assert aviso.PersonaId == tipos.PersonaId


def test_tipos_define_nombre_persona() -> None:
    assert tipos.NombrePersona is not None


NOMBRE = TypeAdapter(tipos.NombrePersona)


@pytest.mark.parametrize(
    "caracter", ["\u0085", "\u200b", "\u2028", "\u2029", "\u202e", "\uffff", "\ufeff"]
)
def test_nombre_rechaza_caracteres_invisibles_o_no_validos(caracter: str) -> None:
    with pytest.raises(ValidationError):
        NOMBRE.validate_python(f"A{caracter}B")


@pytest.mark.parametrize("caracter", ["\u0085", "\u200b", "\u202e", "\ufeff"])
def test_nombre_rechaza_esos_caracteres_en_los_extremos(caracter: str) -> None:
    with pytest.raises(ValidationError):
        NOMBRE.validate_python(f"{caracter}Ana")


@pytest.mark.parametrize(
    "nombre", ["José Ñandú", "O'Brien", "Ana-María", "Ana María Pérez", "李小龍"]
)
def test_nombre_acepta_letras_acentos_apostrofo_guion_y_espacio(nombre: str) -> None:
    assert NOMBRE.validate_python(nombre) == nombre


def test_el_error_de_nombre_no_incluye_el_valor() -> None:
    adaptador = TypeAdapter(
        tipos.NombrePersona, config=ConfigDict(hide_input_in_errors=True)
    )

    with pytest.raises(ValidationError) as info:
        adaptador.validate_python("Secreto​")

    assert "Secreto" not in str(info.value)
