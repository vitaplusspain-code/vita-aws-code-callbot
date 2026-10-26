import pytest
from pydantic import ValidationError

from core.aviso import (
    TAMANO_MAXIMO_CUERPO,
    Aviso,
    Caso,
    parsear_aviso,
    parsear_aviso_json,
)
from core.errores import AvisoInvalido


def test_parsea_un_aviso_valido() -> None:
    aviso = parsear_aviso({"persona_id": "abuela-prueba", "caso": "sin_actividad_hoy"})

    assert aviso == Aviso(persona_id="abuela-prueba", caso=Caso.SIN_ACTIVIDAD_HOY)


def test_caso_tiene_los_tres_valores_del_diseno() -> None:
    assert {c.value for c in Caso} == {
        "medicacion_7_dias",
        "sin_actividad_hoy",
        "sueno_irregular",
    }


def test_caso_desconocido_es_invalido() -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso({"persona_id": "abuela-prueba", "caso": "inventado"})


@pytest.mark.parametrize(
    "persona_id",
    ["Abuela", "abuela prueba", "", "a" * 41, "abuela_1", "ñandú", "abuela\n"],
)
def test_persona_id_fuera_del_patron_es_invalido(persona_id: str) -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso({"persona_id": persona_id, "caso": "sueno_irregular"})


def test_persona_id_de_40_caracteres_es_valido() -> None:
    aviso = parsear_aviso({"persona_id": "a" * 40, "caso": "sueno_irregular"})

    assert len(aviso.persona_id) == 40


def test_campo_extra_es_invalido() -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso(
            {"persona_id": "abuela-prueba", "caso": "sueno_irregular", "x": 1}
        )


@pytest.mark.parametrize(
    "datos",
    [{}, {"persona_id": "abuela-prueba"}, {"caso": "sueno_irregular"}],
)
def test_campos_ausentes_son_invalidos(datos: dict[str, str]) -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso(datos)


@pytest.mark.parametrize("datos", [None, "texto", 42, ["a"], b"{}"])
def test_un_dato_que_no_es_dict_es_invalido(datos: object) -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso(datos)


def test_el_mensaje_de_error_no_refleja_el_input() -> None:
    secreto = "Dato<Sensible>12345"

    with pytest.raises(AvisoInvalido) as info:
        parsear_aviso({"persona_id": secreto, "caso": secreto})

    assert secreto not in str(info.value)
    assert str(info.value)


def test_el_aviso_es_inmutable() -> None:
    aviso = Aviso(persona_id="abuela-prueba", caso=Caso.SUENO_IRREGULAR)

    with pytest.raises(ValidationError):
        aviso.persona_id = "otra"  # type: ignore[misc]


@pytest.mark.parametrize("caso", ["SIN_ACTIVIDAD_HOY", "Sueno_Irregular"])
def test_caso_en_mayusculas_es_invalido(caso: str) -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso({"persona_id": "abuela-prueba", "caso": caso})


def test_persona_id_numerico_es_invalido() -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso({"persona_id": 123, "caso": "sueno_irregular"})


def test_el_mensaje_no_refleja_claves_extra_del_cliente() -> None:
    clave = "+34600123456<x>\n"
    datos = {"persona_id": "abuela-prueba", "caso": "sueno_irregular", clave: 1}

    with pytest.raises(AvisoInvalido) as info:
        parsear_aviso(datos)

    mensaje = str(info.value)
    assert clave not in mensaje
    assert "600123456" not in mensaje
    assert "campos no permitidos" in mensaje


def test_el_mensaje_nombra_solo_campos_conocidos_invalidos() -> None:
    with pytest.raises(AvisoInvalido) as info:
        parsear_aviso({"persona_id": "abuela-prueba", "caso": "inventado"})

    assert "caso" in str(info.value)
    assert "persona_id" not in str(info.value)


def test_json_valido_se_parsea() -> None:
    cuerpo = '{"persona_id": "abuela-prueba", "caso": "sin_actividad_hoy"}'

    assert parsear_aviso_json(cuerpo).caso is Caso.SIN_ACTIVIDAD_HOY


def test_json_en_bytes_se_parsea() -> None:
    cuerpo = b'{"persona_id": "abuela-prueba", "caso": "sin_actividad_hoy"}'

    assert parsear_aviso_json(cuerpo).persona_id == "abuela-prueba"


@pytest.mark.parametrize(
    "cuerpo",
    [
        None,
        "",
        "{no es json",
        b"\xff\xfe",
        "[1, 2]",
        "42",
        "null",
        '"texto"',
        pytest.param("[" * 1000, id="anidado-profundo"),
    ],
)
def test_json_defectuoso_es_aviso_invalido(cuerpo: str | bytes | None) -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso_json(cuerpo)


def test_json_defectuoso_no_refleja_el_contenido() -> None:
    cuerpo = "{secreto-12345 <x>"

    with pytest.raises(AvisoInvalido) as info:
        parsear_aviso_json(cuerpo)

    assert "secreto" not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_json_de_tipo_inesperado_es_aviso_invalido() -> None:
    with pytest.raises(AvisoInvalido):
        parsear_aviso_json(123)  # type: ignore[arg-type]


CUERPO_VALIDO = '{"persona_id": "abuela-prueba", "caso": "sin_actividad_hoy"}'


def test_el_limite_de_tamano_es_1024() -> None:
    assert TAMANO_MAXIMO_CUERPO == 1024


@pytest.mark.parametrize("tipo", [str, bytes])
def test_cuerpo_de_exactamente_el_limite_se_acepta(tipo: type) -> None:
    cuerpo = CUERPO_VALIDO + " " * (TAMANO_MAXIMO_CUERPO - len(CUERPO_VALIDO))
    assert len(cuerpo) == TAMANO_MAXIMO_CUERPO

    entrada = cuerpo if tipo is str else cuerpo.encode()
    assert parsear_aviso_json(entrada).persona_id == "abuela-prueba"


@pytest.mark.parametrize("tipo", [str, bytes])
def test_cuerpo_por_encima_del_limite_se_rechaza_sin_parsear(tipo: type) -> None:
    cuerpo = CUERPO_VALIDO + " " * (TAMANO_MAXIMO_CUERPO + 1 - len(CUERPO_VALIDO))
    assert len(cuerpo) == TAMANO_MAXIMO_CUERPO + 1

    entrada = cuerpo if tipo is str else cuerpo.encode()
    with pytest.raises(AvisoInvalido, match="demasiado grande"):
        parsear_aviso_json(entrada)


@pytest.mark.parametrize("clave", ["persona_id", "k<x>+34600123456"])
def test_claves_duplicadas_se_rechazan_sin_reflejar_la_clave(clave: str) -> None:
    cuerpo = f'{{"{clave}": "a", "{clave}": "b", "caso": "sueno_irregular"}}'

    with pytest.raises(AvisoInvalido) as info:
        parsear_aviso_json(cuerpo)

    assert clave not in str(info.value)
    assert "duplicadas" in str(info.value)


def test_parsear_aviso_no_encadena_la_excepcion_original() -> None:
    with pytest.raises(AvisoInvalido) as info:
        parsear_aviso({"persona_id": "MAYUS", "caso": "x"})

    assert info.value.__cause__ is None
    assert info.value.__context__ is None


@pytest.mark.parametrize(
    "cuerpo",
    [None, "{roto", b"\xff", '{"a": 1, "a": 2}', "[1]", '{"persona_id": "A"}'],
)
def test_parsear_aviso_json_no_encadena_la_excepcion_original(
    cuerpo: str | bytes | None,
) -> None:
    with pytest.raises(AvisoInvalido) as info:
        parsear_aviso_json(cuerpo)

    assert info.value.__cause__ is None
    assert info.value.__context__ is None
