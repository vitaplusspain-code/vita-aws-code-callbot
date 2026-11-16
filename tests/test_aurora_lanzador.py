import json
from datetime import time
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

import adapters.aurora_lanzador as modulo
from adapters.aurora import param_texto, param_uuid
from adapters.aurora_lanzador import AuroraLanzador
from core.errores import DatosInvalidos, ErrorBaseDatos
from core.lanzador import (
    TOPE_DIARIO_CHECKIN,
    Candidato,
    RepositorioCheckinDiario,
    ReservaCheckin,
)

CLUSTER = "arn:aws:rds:eu-west-1:000000000000:cluster:vita-dev-callbot-db"
SECRETO = "arn:aws:secretsmanager:eu-west-1:000000000000:secret:vita-dev-callbot-x"
BASE = "vitaplus"
CALL_ID = "44444444-4444-4444-4444-444444444444"
PERSONA = "00000000-0000-0000-0000-0000000000b1"
TELEFONO = "+34611111111"
CANDIDATO = Candidato(PERSONA, TELEFONO, time(18, 0), frozenset({1, 3}))


def _cliente() -> Any:
    return boto3.client(
        "rds-data",
        region_name="eu-west-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _adaptador(cliente: Any) -> AuroraLanzador:
    return AuroraLanzador(cliente, CLUSTER, SECRETO, BASE)


def _esperado(sql: str, parametros: list[Any], lectura: bool) -> dict[str, Any]:
    esperado: dict[str, Any] = {
        "resourceArn": CLUSTER,
        "secretArn": SECRETO,
        "database": BASE,
        "sql": sql,
        "parameters": parametros,
    }
    if lectura:
        esperado["formatRecordsAs"] = "JSON"
    return esperado


def _lectura(stubber: Stubber, filas: Any) -> None:
    stubber.add_response(
        "execute_statement",
        {"formattedRecords": json.dumps(filas)},
        _esperado(modulo.SQL_CANDIDATOS, [], True),
    )


def _escritura(stubber: Stubber, sql: str, params: list[Any], filas: int) -> None:
    stubber.add_response(
        "execute_statement",
        {"numberOfRecordsUpdated": filas},
        _esperado(sql, params, False),
    )


PARAMS_RESERVA = [
    param_uuid("call_id", CALL_ID),
    param_uuid("person_id", PERSONA),
    param_texto("phone", TELEFONO),
    param_texto("script_version", "checkin-v1"),
]
RESERVA = ReservaCheckin(CALL_ID, CANDIDATO, "checkin-v1")


def _fila(**cambios: Any) -> dict[str, Any]:
    fila = {"person_id": PERSONA, "telefono": TELEFONO, "hora": "18:00", "dias": "1,3"}
    return {**fila, **cambios}


def test_cumple_el_puerto() -> None:
    assert isinstance(_adaptador(_cliente()), RepositorioCheckinDiario)


@pytest.mark.parametrize("sql", [modulo.SQL_CANDIDATOS, modulo.SQL_RESERVAR_CHECKIN])
def test_el_sql_exige_perfil_consentimiento_y_sin_checkin_hoy(sql: str) -> None:
    assert "cp.active" in sql
    assert "k.scope = 'calls'" in sql
    assert "ORDER BY k.recorded_at DESC, k.granted ASC LIMIT 1) IS TRUE" in sql
    assert "c.purpose = 'checkin'" in sql
    assert "Europe/Madrid" in sql
    assert "%s" not in sql
    assert "{" not in sql


def test_la_reserva_solo_inserta_con_parametros_y_telefono_del_perfil() -> None:
    sql = modulo.SQL_RESERVAR_CHECKIN

    assert "CAST(:call_id AS uuid)" in sql
    assert "cp.person_id = :person_id AND cp.mobile_e164 = :phone" in sql
    assert sql.startswith("INSERT INTO public.callbot_call")


def test_candidatos_convierte_las_filas() -> None:
    cliente = _cliente()
    filas = [_fila(), _fila(dias=None), _fila(dias=""), _fila(hora="09:30")]
    with Stubber(cliente) as stubber:
        _lectura(stubber, filas)

        resultado = _adaptador(cliente).candidatos()

        stubber.assert_no_pending_responses()
    assert resultado[0] == CANDIDATO
    assert resultado[1].dias is None
    assert resultado[2].dias == frozenset()
    assert resultado[3].hora == time(9, 30)


def test_candidatos_sin_filas_devuelve_lista_vacia() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(stubber, [])

        assert _adaptador(cliente).candidatos() == []


@pytest.mark.parametrize(
    "cambio",
    [
        {"telefono": "no-es-telefono"},
        {"person_id": "x"},
        {"hora": "25:99"},
        {"dias": "8"},
        {"dias": "1,a"},
        {"dias": 5},
        {"extra": 1},
    ],
)
def test_candidatos_con_fila_invalida_lanza_datos_invalidos_sin_reflejar(
    cambio: dict[str, Any],
) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(stubber, [_fila(**cambio)])

        with pytest.raises(DatosInvalidos) as info:
            _adaptador(cliente).candidatos()

    assert TELEFONO not in str(info.value) + repr(info.value)


def test_reservar_devuelve_true_si_inserta() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_RESERVAR_CHECKIN, PARAMS_RESERVA, 1)

        assert _adaptador(cliente).reservar_llamada(RESERVA) is True


def test_reservar_devuelve_false_si_ya_no_procede() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_RESERVAR_CHECKIN, PARAMS_RESERVA, 0)

        assert _adaptador(cliente).reservar_llamada(RESERVA) is False


def test_reservar_con_respuesta_rara_lanza_error() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_RESERVAR_CHECKIN, PARAMS_RESERVA, 2)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).reservar_llamada(RESERVA)


def test_registrar_contacto_actualiza_una_fila() -> None:
    cliente = _cliente()
    params = [param_texto("contact_id", "abc"), param_uuid("call_id", CALL_ID)]
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_REGISTRAR_CONTACTO, params, 1)

        _adaptador(cliente).registrar_contacto(CALL_ID, "abc")

        stubber.assert_no_pending_responses()


def test_registrar_fallo_actualiza_una_fila() -> None:
    cliente = _cliente()
    params = [param_texto("codigo", "error_connect"), param_uuid("call_id", CALL_ID)]
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_REGISTRAR_FALLO, params, 1)

        _adaptador(cliente).registrar_fallo(CALL_ID, "error_connect")

        stubber.assert_no_pending_responses()


def test_una_actualizacion_que_no_toca_una_fila_lanza_error() -> None:
    cliente = _cliente()
    params = [param_texto("contact_id", "abc"), param_uuid("call_id", CALL_ID)]
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_REGISTRAR_CONTACTO, params, 0)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).registrar_contacto(CALL_ID, "abc")


def test_un_fallo_de_aws_se_traduce_a_error_base_datos() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_client_error("execute_statement", "ForbiddenException")

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).candidatos()


def test_la_reserva_exige_el_call_time_dentro_de_la_franja() -> None:
    assert modulo.SQL_EN_FRANJA in modulo.SQL_RESERVAR_CHECKIN
    assert "cp.call_time >= TIME '09:00'" in modulo.SQL_EN_FRANJA
    assert "cp.call_time <= TIME '20:45'" in modulo.SQL_EN_FRANJA


def test_la_reserva_aplica_el_tope_diario_de_checkins() -> None:
    assert modulo.SQL_BAJO_TOPE in modulo.SQL_RESERVAR_CHECKIN
    assert f"< {TOPE_DIARIO_CHECKIN})" in modulo.SQL_BAJO_TOPE
    assert "purpose = 'checkin'" in modulo.SQL_BAJO_TOPE


def _error_unicidad(restriccion: str) -> str:
    return (
        "ERROR: duplicate key value violates unique constraint "
        f'"{restriccion}"\n'
        "  Detail: Key already exists.; SQLState: 23505"
    )


def _reservar_con_error(codigo: str, mensaje: str) -> bool:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_client_error(
            "execute_statement",
            codigo,
            mensaje,
            expected_params=_esperado(
                modulo.SQL_RESERVAR_CHECKIN, PARAMS_RESERVA, False
            ),
        )

        return _adaptador(cliente).reservar_llamada(RESERVA)


def test_una_violacion_del_indice_diario_es_ya_reservada() -> None:
    mensaje = _error_unicidad(modulo.INDICE_CHECKIN_DIA)

    assert _reservar_con_error("BadRequestException", mensaje) is False


@pytest.mark.parametrize(
    "mensaje",
    [
        _error_unicidad("callbot_call_pkey"),
        "ERROR: duplicate key; SQLState: 23505",
        "ERROR: otra cosa; SQLState: 23503",
        "",
    ],
)
def test_otro_error_de_la_base_en_la_reserva_sigue_siendo_error(mensaje: str) -> None:
    with pytest.raises(ErrorBaseDatos):
        _reservar_con_error("BadRequestException", mensaje)


def test_el_error_no_refleja_el_mensaje_de_la_base() -> None:
    mensaje = _error_unicidad("callbot_call_pkey") + " " + TELEFONO

    with pytest.raises(ErrorBaseDatos) as info:
        _reservar_con_error("BadRequestException", mensaje)

    assert TELEFONO not in str(info.value) + repr(info.value)
