import json
import logging
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

import adapters.aurora_checkin as modulo
from adapters.aurora import param_texto, param_texto_o_nulo, param_uuid
from adapters.aurora_checkin import AuroraCheckin
from core.checkin import EstadoCheckin, Observacion, Turno
from core.checkin_guion import VERSION_GUION_CHECKIN, Paso, Trato
from core.errores import DatosInvalidos, ErrorBaseDatos
from core.puertos_checkin import (
    ContextoConversacion,
    DatosConversacion,
    RegistroCheckin,
)
from core.riesgo import SenalRiesgo, TipoRiesgo

CLUSTER = "arn:aws:rds:eu-west-1:000000000000:cluster:vita-dev-callbot-db"
SECRETO = "arn:aws:secretsmanager:eu-west-1:000000000000:secret:vita-dev-callbot-x"
BASE = "vitaplus"
CALL_ID = "44444444-4444-4444-4444-444444444444"
CONTACTO = "5f0a9c2e-7777-4888-9999-aaaabbbbcccc"
NOMBRE = "Carmen"
FRASE = "me duele la cabeza desde ayer"
FRASE_SENSIBLE = "quiero morirme de verdad"
PARAMS_CALL = [param_uuid("call_id", CALL_ID), param_texto("contacto_id", CONTACTO)]


def _cliente() -> Any:
    return boto3.client(
        "rds-data",
        region_name="eu-west-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _adaptador(cliente: Any) -> AuroraCheckin:
    return AuroraCheckin(cliente, CLUSTER, SECRETO, BASE)


def _esperado(sql: str, parametros: list[dict[str, Any]], lectura: bool) -> Any:
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


def _lectura(stubber: Stubber, sql: str, params: list[Any], filas: Any) -> None:
    stubber.add_response(
        "execute_statement",
        {"formattedRecords": json.dumps(filas)},
        _esperado(sql, params, True),
    )


def _escritura(stubber: Stubber, sql: str, params: list[Any], filas: int) -> None:
    stubber.add_response(
        "execute_statement",
        {"numberOfRecordsUpdated": filas},
        _esperado(sql, params, False),
    )


def _turno(
    paso: Paso = Paso.ANIMO_SEMANA,
    observaciones: tuple[Observacion, ...] = (),
    senal: SenalRiesgo | None = None,
) -> Turno:
    return Turno(
        estado=EstadoCheckin(paso),
        texto_a_decir="texto",
        observaciones=observaciones,
        senal_riesgo=senal,
    )


def _params_observacion(obs: Observacion, verbatim: str | None = None) -> list[Any]:
    return [
        *PARAMS_CALL,
        param_texto("indicator_code", obs.indicator_code),
        param_texto_o_nulo("value_code", obs.value_code),
        param_texto_o_nulo("value_text", obs.value_text),
        param_texto("verbatim", obs.verbatim if verbatim is None else verbatim),
        param_texto("question_version", VERSION_GUION_CHECKIN),
    ]


def _params_riesgo(tipo: str, verbatim: str) -> list[dict[str, Any]]:
    return [
        *PARAMS_CALL,
        param_texto("kind", tipo),
        param_texto("verbatim", verbatim),
        param_texto("action_taken", modulo.ACCION_MENSAJE_112),
    ]


ANIMO = Observacion("animo_hoy", "bien", None, FRASE)
COMIDA = Observacion("que_ha_comido", None, "sopa", "comí sopa")


# --- Puertos y SQL -----------------------------------------------------------


def test_cumple_los_dos_puertos() -> None:
    adaptador = _adaptador(_cliente())

    assert isinstance(adaptador, ContextoConversacion)
    assert isinstance(adaptador, RegistroCheckin)


@pytest.mark.parametrize(
    "sql",
    [
        modulo.SQL_DATOS,
        modulo.SQL_FICHA,
        modulo.SQL_OBSERVACION,
        modulo.SQL_RIESGO,
        modulo.SQL_CONTESTADA,
        modulo.SQL_CERRAR,
    ],
)
def test_todo_sql_va_parametrizado_y_solo_para_checkin_activo(sql: str) -> None:
    assert ":call_id" in sql
    assert "purpose = 'checkin'" in sql
    assert "ended_at IS NULL" in sql
    assert "connect_contact_id = :contacto_id" in sql
    assert "%s" not in sql
    assert "{" not in sql


def test_datos_lee_solo_vistas_y_tablas_con_permiso() -> None:
    assert "callbot_person" in modulo.SQL_DATOS
    assert "public.person " not in modulo.SQL_DATOS


# --- datos -------------------------------------------------------------------


def test_datos_devuelve_nombre_y_trato() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber, modulo.SQL_DATOS, PARAMS_CALL, [{"nombre": NOMBRE, "trato": "tu"}]
        )

        datos = _adaptador(cliente).datos(CALL_ID, CONTACTO)

        stubber.assert_no_pending_responses()
    assert datos == DatosConversacion(nombre=NOMBRE, trato=Trato.TU)


def test_datos_con_uuid_en_mayusculas_consulta_igual() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo.SQL_DATOS,
            [
                param_uuid("call_id", CALL_ID.upper()),
                param_texto("contacto_id", CONTACTO),
            ],
            [{"nombre": NOMBRE, "trato": "usted"}],
        )

        datos = _adaptador(cliente).datos(CALL_ID.upper(), CONTACTO)

    assert datos is not None
    assert datos.trato is Trato.USTED


def test_datos_de_llamada_inexistente_o_de_otro_proposito_es_none() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(stubber, modulo.SQL_DATOS, PARAMS_CALL, [])

        assert _adaptador(cliente).datos(CALL_ID, CONTACTO) is None

        stubber.assert_no_pending_responses()


@pytest.mark.parametrize("call_id", ["", "  ", "no-es-uuid", f"{CALL_ID}' OR 1=1"])
def test_datos_con_call_id_que_no_es_uuid_ni_consulta(call_id: str) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        assert _adaptador(cliente).datos(call_id, CONTACTO) is None

        stubber.assert_no_pending_responses()


@pytest.mark.parametrize(
    "filas",
    [
        [{"nombre": NOMBRE, "trato": "tu"}, {"nombre": "Luis", "trato": "tu"}],
        [{"nombre": "", "trato": "tu"}],
        [{"nombre": "Ana2", "trato": "tu"}],
        [{"nombre": NOMBRE, "trato": "colega"}],
        [{"nombre": NOMBRE}],
        [{"nombre": NOMBRE, "trato": "tu", "extra": 1}],
    ],
)
def test_datos_mal_formados_lanzan_datos_invalidos(filas: Any) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(stubber, modulo.SQL_DATOS, PARAMS_CALL, filas)

        with pytest.raises(DatosInvalidos) as info:
            _adaptador(cliente).datos(CALL_ID, CONTACTO)

    assert NOMBRE not in str(info.value)


def test_datos_traduce_el_fallo_de_la_data_api() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_client_error("execute_statement", "ForbiddenException")

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).datos(CALL_ID, CONTACTO)


# --- guardar_turno -----------------------------------------------------------


def test_turno_sin_datos_solo_toca_la_ficha_y_marca_contestada() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_CONTESTADA, PARAMS_CALL, 1)

        assert _adaptador(cliente).guardar_turno(CALL_ID, CONTACTO, _turno()) is None

        stubber.assert_no_pending_responses()


def test_turno_con_observaciones_las_inserta_una_a_una() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(ANIMO), 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(COMIDA), 1)
        _escritura(stubber, modulo.SQL_CONTESTADA, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(
            CALL_ID, CONTACTO, _turno(observaciones=(ANIMO, COMIDA))
        )

        stubber.assert_no_pending_responses()


def test_turno_terminado_cierra_la_llamada_como_contestada() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_CERRAR, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(CALL_ID, CONTACTO, _turno(Paso.FIN))

        stubber.assert_no_pending_responses()
    assert "outcome = 'answered'" in modulo.SQL_CERRAR
    assert "ended_at = now()" in modulo.SQL_CERRAR


def test_reintento_no_duplica_observaciones() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(ANIMO), 0)
        _escritura(stubber, modulo.SQL_CONTESTADA, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(
            CALL_ID, CONTACTO, _turno(observaciones=(ANIMO,))
        )

        stubber.assert_no_pending_responses()
    assert "NOT EXISTS" in modulo.SQL_OBSERVACION
    assert "NOT EXISTS" in modulo.SQL_RIESGO
    assert "ON CONFLICT (call_id)" in modulo.SQL_FICHA


def test_riesgo_guarda_el_tipo_y_la_frase() -> None:
    senal = SenalRiesgo(TipoRiesgo.FALL, "me he caído")
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_RIESGO, _params_riesgo("fall", "me he caído"), 1)
        _escritura(stubber, modulo.SQL_CERRAR, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(
            CALL_ID, CONTACTO, _turno(Paso.FIN, senal=senal)
        )

        stubber.assert_no_pending_responses()


def test_autolesion_se_guarda_solo_por_tipo_sin_la_frase() -> None:
    senal = SenalRiesgo(TipoRiesgo.SELF_HARM, FRASE_SENSIBLE)
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_RIESGO, _params_riesgo("self_harm", ""), 1)
        _escritura(stubber, modulo.SQL_CERRAR, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(
            CALL_ID, CONTACTO, _turno(Paso.FIN, senal=senal)
        )

        stubber.assert_no_pending_responses()


def test_llamada_inexistente_inactiva_o_de_otro_proposito_no_guarda_nada() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 0)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(
                CALL_ID, CONTACTO, _turno(observaciones=(ANIMO,))
            )

        stubber.assert_no_pending_responses()


def test_actualizar_la_llamada_sin_tocar_una_fila_es_error() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_CONTESTADA, PARAMS_CALL, 0)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(CALL_ID, CONTACTO, _turno())


@pytest.mark.parametrize("filas", [-1, 2])
def test_la_ficha_con_un_numero_raro_de_filas_es_error(filas: int) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, filas)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(CALL_ID, CONTACTO, _turno())


def test_observacion_con_filas_raras_es_error() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(ANIMO), 2)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(
                CALL_ID, CONTACTO, _turno(observaciones=(ANIMO,))
            )


def test_riesgo_con_filas_raras_es_error() -> None:
    senal = SenalRiesgo(TipoRiesgo.OTHER, "ayuda")
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_RIESGO, _params_riesgo("other", "ayuda"), 3)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(
                CALL_ID, CONTACTO, _turno(Paso.FIN, senal=senal)
            )


def test_fallo_de_la_data_api_se_traduce_y_no_filtra_datos(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        stubber.add_client_error("execute_statement", "StatementTimeoutException")

        with pytest.raises(ErrorBaseDatos) as info:
            _adaptador(cliente).guardar_turno(
                CALL_ID, CONTACTO, _turno(observaciones=(ANIMO,))
            )

    registro = caplog.text + str(info.value) + repr(info.value.__cause__)
    for secreto in (FRASE, CALL_ID, CLUSTER, SECRETO):
        assert secreto not in registro


@pytest.mark.parametrize("call_id", ["", "no-es-uuid"])
def test_guardar_con_call_id_invalido_no_consulta(call_id: str) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        with pytest.raises(DatosInvalidos):
            _adaptador(cliente).guardar_turno(call_id, CONTACTO, _turno())

        stubber.assert_no_pending_responses()


def test_llamada_no_activa_se_registra_sin_datos_personales(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 0)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(
                CALL_ID, CONTACTO, _turno(observaciones=(ANIMO,))
            )

    assert "checkin_llamada_no_activa" in caplog.text
    assert FRASE not in caplog.text
    assert CALL_ID not in caplog.text


# --- contacto, orden y autolesión --------------------------------------------


@pytest.mark.parametrize(
    "contacto", ["", "  ", "no-es-uuid", f"{CONTACTO}' OR 1=1", CONTACTO + "x"]
)
def test_datos_con_contacto_que_no_es_valido_ni_consulta(contacto: str) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        assert _adaptador(cliente).datos(CALL_ID, contacto) is None

        stubber.assert_no_pending_responses()


@pytest.mark.parametrize("contacto", ["", "no-es-uuid"])
def test_guardar_con_contacto_invalido_no_escribe(contacto: str) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        with pytest.raises(DatosInvalidos):
            _adaptador(cliente).guardar_turno(CALL_ID, contacto, _turno())

        stubber.assert_no_pending_responses()


def test_datos_de_un_contacto_ajeno_no_devuelve_nada() -> None:
    otro = "11111111-2222-4333-8444-555555555555"
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo.SQL_DATOS,
            [param_uuid("call_id", CALL_ID), param_texto("contacto_id", otro)],
            [],
        )

        assert _adaptador(cliente).datos(CALL_ID, otro) is None

        stubber.assert_no_pending_responses()


def test_guardar_en_la_llamada_de_otro_contacto_no_escribe_nada() -> None:
    otro = "11111111-2222-4333-8444-555555555555"
    parametros = [param_uuid("call_id", CALL_ID), param_texto("contacto_id", otro)]
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, parametros, 0)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(CALL_ID, otro, _turno(Paso.FIN))

        stubber.assert_no_pending_responses()


def test_la_condicion_de_llamada_activa_es_la_misma_en_todo_el_sql() -> None:
    condicion = "purpose = 'checkin' AND ended_at IS NULL AND connect_contact_id"
    con_alias = (
        condicion.replace("purpose", "c.purpose")
        .replace("AND ended_at", "AND c.ended_at")
        .replace("AND connect", "AND c.connect")
    )
    for sql in (modulo.SQL_CONTESTADA, modulo.SQL_CERRAR):
        assert condicion in sql
    for sql in (modulo.SQL_DATOS, modulo.SQL_FICHA, modulo.SQL_OBSERVACION):
        assert con_alias in sql
    assert con_alias in modulo.SQL_RIESGO


def test_el_riesgo_se_guarda_justo_tras_la_ficha_y_antes_de_las_observaciones() -> None:
    senal = SenalRiesgo(TipoRiesgo.FALL, "me he caído")
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_RIESGO, _params_riesgo("fall", "me he caído"), 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(ANIMO), 1)
        _escritura(stubber, modulo.SQL_CERRAR, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(
            CALL_ID, CONTACTO, _turno(Paso.FIN, (ANIMO,), senal)
        )

        stubber.assert_no_pending_responses()


def test_si_falla_una_observacion_el_riesgo_ya_estaba_guardado() -> None:
    senal = SenalRiesgo(TipoRiesgo.FALL, "me he caído")
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_RIESGO, _params_riesgo("fall", "me he caído"), 1)
        stubber.add_client_error("execute_statement", "StatementTimeoutException")

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).guardar_turno(
                CALL_ID, CONTACTO, _turno(Paso.FIN, (ANIMO,), senal)
            )

        stubber.assert_no_pending_responses()


def test_con_autolesion_todas_las_observaciones_del_turno_van_sin_frase() -> None:
    senal = SenalRiesgo(TipoRiesgo.SELF_HARM, FRASE_SENSIBLE)
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_RIESGO, _params_riesgo("self_harm", ""), 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(ANIMO, ""), 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(COMIDA, ""), 1)
        _escritura(stubber, modulo.SQL_CERRAR, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(
            CALL_ID, CONTACTO, _turno(Paso.FIN, (ANIMO, COMIDA), senal)
        )

        stubber.assert_no_pending_responses()


def test_otro_riesgo_conserva_la_frase_en_las_observaciones() -> None:
    senal = SenalRiesgo(TipoRiesgo.FALL, "me he caído")
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo.SQL_FICHA, PARAMS_CALL, 1)
        _escritura(stubber, modulo.SQL_RIESGO, _params_riesgo("fall", "me he caído"), 1)
        _escritura(stubber, modulo.SQL_OBSERVACION, _params_observacion(ANIMO), 1)
        _escritura(stubber, modulo.SQL_CERRAR, PARAMS_CALL, 1)

        _adaptador(cliente).guardar_turno(
            CALL_ID, CONTACTO, _turno(Paso.FIN, (ANIMO,), senal)
        )

        stubber.assert_no_pending_responses()
