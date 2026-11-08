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


UUID = TypeAdapter(tipos.Uuid)
UUID_VALIDO = "0f8fad5b-d9cb-469f-a165-70867728950e"


def test_uuid_valido_se_acepta() -> None:
    assert UUID.validate_python(UUID_VALIDO) == UUID_VALIDO


def test_uuid_en_mayusculas_se_normaliza_a_minusculas() -> None:
    assert UUID.validate_python(UUID_VALIDO.upper()) == UUID_VALIDO


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "0f8fad5bd9cb469fa16570867728950e",
        "{0f8fad5b-d9cb-469f-a165-70867728950e}",
        "urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e",
        "0f8fad5b-d9cb-469f-a165-70867728950e\n",
        " 0f8fad5b-d9cb-469f-a165-70867728950e",
        "0f8fad5b-d9cb-469f-a165-70867728950g",
        "' OR 1=1 --",
    ],
)
def test_uuid_fuera_del_formato_canonico_se_rechaza(valor: str) -> None:
    with pytest.raises(ValidationError):
        UUID.validate_python(valor)


def test_uuid_que_no_es_texto_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        UUID.validate_python(12345)


REGLA = TypeAdapter(tipos.ReglaId)


@pytest.mark.parametrize("regla", ["sos", "fall.detected", "no-activity:24h", "R1"])
def test_regla_acepta_identificadores_habituales(regla: str) -> None:
    assert REGLA.validate_python(regla) == regla


@pytest.mark.parametrize(
    "regla", ["", " sos", "sos ", "a" * 101, "sos\n", "s\u200bos", "s\x00os"]
)
def test_regla_rechaza_vacios_espacios_largos_e_invisibles(regla: str) -> None:
    with pytest.raises(ValidationError):
        REGLA.validate_python(regla)


def test_regla_de_100_caracteres_se_acepta() -> None:
    assert REGLA.validate_python("a" * 100) == "a" * 100


@pytest.mark.parametrize("nombre", ["Ana. Llame al 600123456", "Ana 2", "Ana٣"])
def test_nombre_rechaza_digitos(nombre: str) -> None:
    with pytest.raises(ValidationError):
        NOMBRE.validate_python(nombre)
