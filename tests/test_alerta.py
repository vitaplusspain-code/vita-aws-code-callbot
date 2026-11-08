import pytest
from pydantic import ValidationError

from core.alerta import Alerta, ReglasAviso, es_grave, es_reciente
from core.errores import ErrorConfiguracion

ALERTA_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"
PERSONA_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


def _alerta(**cambios: object) -> Alerta:
    datos: dict[str, object] = {
        "alert_id": ALERTA_ID,
        "person_id": PERSONA_ID,
        "rule_id": "fall.detected",
        "severity": "critical",
        "antiguedad_segundos": 60,
        "persona_nombre": "Carmen",
    }
    return Alerta.model_validate(datos | cambios)


REGLAS = ReglasAviso(reglas_siempre=frozenset({"sos"}), antiguedad_maxima_segundos=3600)


def test_alerta_valida_se_construye() -> None:
    alerta = _alerta()

    assert alerta.alert_id == ALERTA_ID
    assert alerta.severity == "critical"


@pytest.mark.parametrize("severidad", ["info", "low", "medium", "high", "critical"])
def test_alerta_acepta_las_severidades_de_la_tabla_de_llamadas(severidad: str) -> None:
    assert _alerta(severity=severidad).severity == severidad


@pytest.mark.parametrize("severidad", ["CRITICAL", "urgent", ""])
def test_alerta_con_severidad_desconocida_es_invalida(severidad: str) -> None:
    with pytest.raises(ValidationError):
        _alerta(severity=severidad)


def test_alerta_con_campo_extra_es_invalida() -> None:
    with pytest.raises(ValidationError):
        _alerta(notes="secreto")


def test_el_error_de_la_alerta_no_incluye_el_nombre() -> None:
    with pytest.raises(ValidationError) as info:
        _alerta(persona_nombre="Secreto​")

    assert "Secreto" not in str(info.value)


def test_el_nombre_no_sale_en_la_representacion() -> None:
    assert "Carmen" not in repr(_alerta())


def test_alerta_critica_es_grave() -> None:
    assert es_grave(_alerta(severity="critical", rule_id="otra"), REGLAS)


def test_alerta_no_critica_de_una_regla_que_siempre_avisa_es_grave() -> None:
    assert es_grave(_alerta(severity="high", rule_id="sos"), REGLAS)


def test_alerta_no_critica_de_otra_regla_no_es_grave() -> None:
    assert not es_grave(_alerta(severity="high", rule_id="otra"), REGLAS)


@pytest.mark.parametrize("segundos", [-5, 0, 3599, 3600])
def test_alerta_dentro_del_limite_es_reciente(segundos: int) -> None:
    assert es_reciente(_alerta(antiguedad_segundos=segundos), REGLAS)


def test_alerta_por_encima_del_limite_no_es_reciente() -> None:
    assert not es_reciente(_alerta(antiguedad_segundos=3601), REGLAS)


@pytest.mark.parametrize("segundos", [0, -1])
def test_reglas_con_limite_no_positivo_son_un_error_de_configuracion(
    segundos: int,
) -> None:
    with pytest.raises(ErrorConfiguracion):
        ReglasAviso(reglas_siempre=frozenset(), antiguedad_maxima_segundos=segundos)


def test_reglas_normalizan_a_frozenset() -> None:
    reglas = ReglasAviso(
        reglas_siempre={"sos"},  # type: ignore[arg-type]
        antiguedad_maxima_segundos=60,
    )

    assert reglas.reglas_siempre == frozenset({"sos"})
    assert isinstance(reglas.reglas_siempre, frozenset)


@pytest.mark.parametrize("regla", ["", " sos", "s​os"])
def test_reglas_con_una_regla_invalida_son_un_error_de_configuracion(
    regla: str,
) -> None:
    with pytest.raises(ErrorConfiguracion) as info:
        ReglasAviso(reglas_siempre=frozenset({regla}), antiguedad_maxima_segundos=60)

    assert info.value.__context__ is None
