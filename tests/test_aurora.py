import json
import logging
from typing import Any

import boto3
import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)
from botocore.stub import Stubber

import adapters.aurora as modulo_aurora
from adapters.aurora import CONFIG_AURORA, AuroraAdapter
from core.alerta import Alerta
from core.destinatario import Destinatario
from core.errores import DatosInvalidos, ErrorBaseDatos, ErrorConfiguracion
from core.puertos import RepositorioAvisos, Reserva

CLUSTER = "arn:aws:rds:eu-west-1:000000000000:cluster:vita-dev-callbot-db"
SECRETO = "arn:aws:secretsmanager:eu-west-1:000000000000:secret:vita-dev-callbot-x"
BASE = "vitaplus"
ALERT_ID = "11111111-1111-1111-1111-111111111111"
PERSON_ID = "22222222-2222-2222-2222-222222222222"
CONTACTO_ID = "33333333-3333-3333-3333-333333333333"
CALL_ID = "44444444-4444-4444-4444-444444444444"
TELEFONO = "+34600000001"
NOMBRE_PERSONA = "Carmen"
NOMBRE_FAMILIAR = "Lucía Gómez"
MENSAJE_LECTURA = "Fallo al acceder a la base de datos."
MENSAJE_RESPUESTA = "Respuesta inesperada de la base de datos."

ALERTA = Alerta(
    alert_id=ALERT_ID,
    person_id=PERSON_ID,
    rule_id="sos_button",
    severity="critical",
    antiguedad_segundos=12,
    persona_nombre=NOMBRE_PERSONA,
)
DESTINATARIO = Destinatario(
    contacto_id=CONTACTO_ID, nombre=NOMBRE_FAMILIAR, telefono=TELEFONO
)
RESERVA = Reserva(
    call_id=CALL_ID, alerta=ALERTA, destinatario=DESTINATARIO, version_guion="v1"
)


def _cliente() -> Any:
    return boto3.client(
        "rds-data",
        region_name="eu-west-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _adaptador(cliente: Any) -> AuroraAdapter:
    return AuroraAdapter(cliente, CLUSTER, SECRETO, BASE)


def _uuid(nombre: str, valor: str) -> dict[str, Any]:
    return {"name": nombre, "typeHint": "UUID", "value": {"stringValue": valor}}


def _texto(nombre: str, valor: str) -> dict[str, Any]:
    return {"name": nombre, "value": {"stringValue": valor}}


def _esperado(
    sql: str, parametros: list[dict[str, Any]], *, lectura: bool
) -> dict[str, Any]:
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


def _lectura(
    stubber: Stubber, sql: str, parametros: list[dict[str, Any]], filas: Any
) -> None:
    stubber.add_response(
        "execute_statement",
        {"formattedRecords": json.dumps(filas)},
        _esperado(sql, parametros, lectura=True),
    )


def _escritura(
    stubber: Stubber, sql: str, parametros: list[dict[str, Any]], filas: int
) -> None:
    stubber.add_response(
        "execute_statement",
        {"numberOfRecordsUpdated": filas},
        _esperado(sql, parametros, lectura=False),
    )


FILA_ALERTA = {
    "alert_id": ALERT_ID,
    "person_id": PERSON_ID,
    "rule_id": "sos_button",
    "severity": "critical",
    "antiguedad_segundos": 12,
    "persona_nombre": NOMBRE_PERSONA,
}
FILA_CONTACTO = {
    "contacto_id": CONTACTO_ID,
    "nombre": NOMBRE_FAMILIAR,
    "telefono": TELEFONO,
}
PARAMS_ALERTA = [_uuid("alert_id", ALERT_ID)]
PARAMS_CONSENTIMIENTO = [_uuid("person_id", PERSON_ID), _texto("scope", "calls")]
PARAMS_CONTACTO = [_uuid("person_id", PERSON_ID)]
PARAMS_RESERVA = [
    _uuid("call_id", CALL_ID),
    _uuid("person_id", PERSON_ID),
    _uuid("alert_id", ALERT_ID),
    _uuid("contact_id", CONTACTO_ID),
    _texto("rule_id", "sos_button"),
    _texto("severity", "critical"),
    _texto("phone", TELEFONO),
    _texto("script_version", "v1"),
]


class _ClienteQueFalla:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def execute_statement(self, **_: object) -> dict[str, Any]:
        raise self._error


class _ClienteQueDevuelve:
    def __init__(self, respuesta: dict[str, Any]) -> None:
        self._respuesta = respuesta

    def execute_statement(self, **_: object) -> dict[str, Any]:
        return self._respuesta


# --- Puerto y configuración -------------------------------------------------


def test_cumple_el_puerto_repositorio_avisos() -> None:
    assert isinstance(_adaptador(_cliente()), RepositorioAvisos)


def test_config_sin_reintentos_y_timeouts_cortos() -> None:
    assert CONFIG_AURORA.region_name == "eu-west-1"
    assert CONFIG_AURORA.retries == {"total_max_attempts": 1, "mode": "standard"}
    assert CONFIG_AURORA.connect_timeout <= 5
    assert CONFIG_AURORA.read_timeout <= 15


@pytest.mark.parametrize(
    ("argumentos", "faltante"),
    [
        (("", SECRETO, BASE), "cluster_arn"),
        ((CLUSTER, "", BASE), "secret_arn"),
        ((CLUSTER, SECRETO, ""), "database"),
    ],
)
def test_init_valida_la_configuracion(
    argumentos: tuple[str, str, str], faltante: str
) -> None:
    with pytest.raises(ErrorConfiguracion, match=faltante):
        AuroraAdapter(_cliente(), *argumentos)


def test_crear_usa_un_cliente_rds_data_real_con_la_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    cliente = _cliente()

    def falso(*args: Any, **kwargs: Any) -> Any:
        llamadas.append((args, kwargs))
        return cliente

    monkeypatch.setattr(modulo_aurora.boto3, "client", falso)

    adaptador = AuroraAdapter.crear(CLUSTER, SECRETO, BASE)

    assert llamadas == [(("rds-data",), {"config": CONFIG_AURORA})]
    assert isinstance(adaptador, AuroraAdapter)


def test_desde_entorno_crea_el_adaptador(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    entorno = {"DB_CLUSTER_ARN": CLUSTER, "DB_SECRET_ARN": SECRETO, "DB_NAME": BASE}

    assert isinstance(AuroraAdapter.desde_entorno(entorno), AuroraAdapter)


@pytest.mark.parametrize("variable", ["DB_CLUSTER_ARN", "DB_SECRET_ARN", "DB_NAME"])
@pytest.mark.parametrize("vacia", [False, True])
def test_desde_entorno_nombra_la_variable_que_falta(variable: str, vacia: bool) -> None:
    entorno = {"DB_CLUSTER_ARN": CLUSTER, "DB_SECRET_ARN": SECRETO, "DB_NAME": BASE}
    if vacia:
        entorno[variable] = ""
    else:
        del entorno[variable]

    with pytest.raises(ErrorConfiguracion) as info:
        AuroraAdapter.desde_entorno(entorno)

    assert str(info.value) == f"Falta la variable {variable}."
    for valor in (CLUSTER, SECRETO, BASE):
        assert valor not in str(info.value)


# --- registrar_recepcion ----------------------------------------------------


def test_registrar_recepcion_inserta_en_audit_log() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo_aurora.SQL_REGISTRAR_RECEPCION, PARAMS_ALERTA, 1)

        assert _adaptador(cliente).registrar_recepcion(ALERT_ID) is None

        stubber.assert_no_pending_responses()
    assert "callbot.alert_received" in modulo_aurora.SQL_REGISTRAR_RECEPCION
    assert "audit_log" in modulo_aurora.SQL_REGISTRAR_RECEPCION


def test_registrar_recepcion_traduce_el_fallo() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_client_error("execute_statement", "ForbiddenException")

        with pytest.raises(ErrorBaseDatos) as info:
            _adaptador(cliente).registrar_recepcion(ALERT_ID)

    assert str(info.value) == MENSAJE_LECTURA


# --- alerta_abierta ---------------------------------------------------------


def test_alerta_abierta_devuelve_la_alerta() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber, modulo_aurora.SQL_ALERTA_ABIERTA, PARAMS_ALERTA, [FILA_ALERTA]
        )

        alerta = _adaptador(cliente).alerta_abierta(ALERT_ID)

        stubber.assert_no_pending_responses()
    assert alerta == ALERTA


def test_alerta_abierta_calcula_la_antiguedad_en_sql() -> None:
    sql = modulo_aurora.SQL_ALERTA_ABIERTA
    assert "extract(epoch from now() - a.opened_at)" in sql
    assert "callbot_open_alert" in sql
    assert "callbot_person" in sql


def test_alerta_abierta_sin_filas_devuelve_none() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(stubber, modulo_aurora.SQL_ALERTA_ABIERTA, PARAMS_ALERTA, [])

        assert _adaptador(cliente).alerta_abierta(ALERT_ID) is None


def test_alerta_abierta_con_varias_filas_es_error() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo_aurora.SQL_ALERTA_ABIERTA,
            PARAMS_ALERTA,
            [FILA_ALERTA, FILA_ALERTA],
        )

        with pytest.raises(DatosInvalidos) as info:
            _adaptador(cliente).alerta_abierta(ALERT_ID)

    assert str(info.value) == MENSAJE_RESPUESTA


@pytest.mark.parametrize(
    "cambio",
    [
        {"persona_nombre": "Carmen 2"},
        {"severity": "gravisima"},
        {"person_id": "no-es-uuid"},
        {"antiguedad_segundos": "doce"},
        {"campo_extra": "x"},
    ],
)
def test_alerta_abierta_con_fila_invalida_no_filtra_datos(
    cambio: dict[str, Any],
) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo_aurora.SQL_ALERTA_ABIERTA,
            PARAMS_ALERTA,
            [{**FILA_ALERTA, **cambio}],
        )

        with pytest.raises(DatosInvalidos) as info:
            _adaptador(cliente).alerta_abierta(ALERT_ID)

    assert str(info.value) == MENSAJE_RESPUESTA
    assert NOMBRE_PERSONA not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


# --- tiene_consentimiento ---------------------------------------------------


@pytest.mark.parametrize(
    ("filas", "esperado"),
    [
        ([{"granted": True}], True),
        ([{"granted": False}], False),  # el último registro es una revocación
        ([], False),  # nunca se concedió
    ],
)
def test_tiene_consentimiento(filas: list[dict[str, Any]], esperado: bool) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber, modulo_aurora.SQL_CONSENTIMIENTO, PARAMS_CONSENTIMIENTO, filas
        )

        resultado = _adaptador(cliente).tiene_consentimiento(PERSON_ID, "calls")

        stubber.assert_no_pending_responses()
    assert resultado is esperado


def test_consentimiento_toma_el_ultimo_y_ante_empate_la_revocacion() -> None:
    # Test del texto del SQL: Stubber no ejecuta SQL (se valida en Postgres local).
    sql = modulo_aurora.SQL_CONSENTIMIENTO
    assert "ORDER BY recorded_at DESC, granted ASC LIMIT 1" in sql


@pytest.mark.parametrize("granted", ["true", 1, None])
def test_consentimiento_con_valor_no_booleano_es_error(granted: Any) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo_aurora.SQL_CONSENTIMIENTO,
            PARAMS_CONSENTIMIENTO,
            [{"granted": granted}],
        )

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).tiene_consentimiento(PERSON_ID, "calls")


# --- contacto_principal -----------------------------------------------------


def test_contacto_principal_devuelve_el_destinatario() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo_aurora.SQL_CONTACTO_PRINCIPAL,
            PARAMS_CONTACTO,
            [FILA_CONTACTO],
        )

        destinatario = _adaptador(cliente).contacto_principal(PERSON_ID)

        stubber.assert_no_pending_responses()
    assert destinatario == DESTINATARIO


def test_contacto_principal_filtra_prioridad_1_y_recibe_avisos() -> None:
    sql = modulo_aurora.SQL_CONTACTO_PRINCIPAL
    assert "ac.priority = 1" in sql
    assert "ac.receives_alerts" in sql
    assert "c.account_id = ac.account_id AND c.person_id = ac.person_id" in sql


def test_contacto_principal_sin_filas_devuelve_none() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(stubber, modulo_aurora.SQL_CONTACTO_PRINCIPAL, PARAMS_CONTACTO, [])

        assert _adaptador(cliente).contacto_principal(PERSON_ID) is None


def test_contacto_principal_con_varias_filas_es_error() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo_aurora.SQL_CONTACTO_PRINCIPAL,
            PARAMS_CONTACTO,
            [FILA_CONTACTO, FILA_CONTACTO],
        )

        with pytest.raises(DatosInvalidos) as info:
            _adaptador(cliente).contacto_principal(PERSON_ID)

    assert str(info.value) == MENSAJE_RESPUESTA


@pytest.mark.parametrize(
    "cambio",
    [
        {"telefono": "600000001"},  # no es E.164
        {"nombre": "Lucía 2"},  # lleva dígitos
        {"contacto_id": "abc"},
        {"nombre": None},
    ],
)
def test_contacto_principal_con_fila_invalida_no_filtra_datos(
    cambio: dict[str, Any],
) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _lectura(
            stubber,
            modulo_aurora.SQL_CONTACTO_PRINCIPAL,
            PARAMS_CONTACTO,
            [{**FILA_CONTACTO, **cambio}],
        )

        with pytest.raises(DatosInvalidos) as info:
            _adaptador(cliente).contacto_principal(PERSON_ID)

    assert str(info.value) == MENSAJE_RESPUESTA
    assert "600000001" not in str(info.value)
    assert NOMBRE_FAMILIAR not in str(info.value)


# --- reservar_llamada -------------------------------------------------------


@pytest.mark.parametrize(("filas", "esperado"), [(1, True), (0, False)])
def test_reservar_llamada(filas: int, esperado: bool) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo_aurora.SQL_RESERVAR_LLAMADA, PARAMS_RESERVA, filas)

        resultado = _adaptador(cliente).reservar_llamada(RESERVA)

        stubber.assert_no_pending_responses()
    assert resultado is esperado


def test_reservar_llamada_es_atomica_y_de_tipo_contacto() -> None:
    # Test del texto del SQL: Stubber no ejecuta SQL (se valida en Postgres local).
    sql = modulo_aurora.SQL_RESERVAR_LLAMADA
    # Solo el índice del aviso cuenta como duplicado; otro conflicto es un error.
    assert sql.endswith(
        "ON CONFLICT (alert_id, alert_contact_id, attempt) "
        "WHERE purpose = 'alert_notice' DO NOTHING"
    )
    assert "'alert_notice'" in sql
    assert "'contact'" in sql


def test_reservar_llamada_con_numero_raro_es_error() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo_aurora.SQL_RESERVAR_LLAMADA, PARAMS_RESERVA, 2)

        with pytest.raises(ErrorBaseDatos) as info:
            _adaptador(cliente).reservar_llamada(RESERVA)

    assert str(info.value) == MENSAJE_RESPUESTA


def test_reservar_llamada_sin_contador_es_error() -> None:
    adaptador = _adaptador(_ClienteQueDevuelve({}))

    with pytest.raises(ErrorBaseDatos):
        adaptador.reservar_llamada(RESERVA)


def test_reservar_llamada_con_contador_booleano_es_error() -> None:
    adaptador = _adaptador(_ClienteQueDevuelve({"numberOfRecordsUpdated": True}))

    with pytest.raises(ErrorBaseDatos):
        adaptador.reservar_llamada(RESERVA)


# --- registrar_contacto y registrar_fallo -----------------------------------


def test_registrar_contacto_actualiza_una_fila() -> None:
    cliente = _cliente()
    parametros = [_texto("contact_id", "contacto-abc"), _uuid("call_id", CALL_ID)]
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo_aurora.SQL_REGISTRAR_CONTACTO, parametros, 1)

        assert _adaptador(cliente).registrar_contacto(CALL_ID, "contacto-abc") is None

        stubber.assert_no_pending_responses()


@pytest.mark.parametrize("filas", [0, 2])
def test_registrar_contacto_sin_una_fila_es_error(filas: int) -> None:
    cliente = _cliente()
    parametros = [_texto("contact_id", "contacto-abc"), _uuid("call_id", CALL_ID)]
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo_aurora.SQL_REGISTRAR_CONTACTO, parametros, filas)

        with pytest.raises(ErrorBaseDatos) as info:
            _adaptador(cliente).registrar_contacto(CALL_ID, "contacto-abc")

    assert str(info.value) == MENSAJE_RESPUESTA


def test_registrar_fallo_actualiza_una_fila() -> None:
    cliente = _cliente()
    parametros = [_texto("codigo", "error_connect"), _uuid("call_id", CALL_ID)]
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo_aurora.SQL_REGISTRAR_FALLO, parametros, 1)

        assert _adaptador(cliente).registrar_fallo(CALL_ID, "error_connect") is None

        stubber.assert_no_pending_responses()
    assert "outcome = 'failed'" in modulo_aurora.SQL_REGISTRAR_FALLO
    assert "ended_at = now()" in modulo_aurora.SQL_REGISTRAR_FALLO


@pytest.mark.parametrize("filas", [0, 2])
def test_registrar_fallo_sin_una_fila_es_error(filas: int) -> None:
    cliente = _cliente()
    parametros = [_texto("codigo", "error_connect"), _uuid("call_id", CALL_ID)]
    with Stubber(cliente) as stubber:
        _escritura(stubber, modulo_aurora.SQL_REGISTRAR_FALLO, parametros, filas)

        with pytest.raises(ErrorBaseDatos):
            _adaptador(cliente).registrar_fallo(CALL_ID, "error_connect")


# --- Respuestas rotas y errores de AWS --------------------------------------


@pytest.mark.parametrize(
    "respuesta",
    [
        {},  # sin formattedRecords
        {"formattedRecords": "{no es json"},
        {"formattedRecords": '{"no": "una lista"}'},
        {"formattedRecords": "[1, 2]"},  # filas que no son objetos
        {"formattedRecords": None},
    ],
)
def test_lectura_con_respuesta_rota_es_error(respuesta: dict[str, Any]) -> None:
    adaptador = _adaptador(_ClienteQueDevuelve(respuesta))

    with pytest.raises(ErrorBaseDatos) as info:
        adaptador.alerta_abierta(ALERT_ID)

    assert not isinstance(info.value, DatosInvalidos)
    assert str(info.value) == MENSAJE_RESPUESTA


def test_client_error_se_traduce_sin_datos_y_se_registra(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_client_error(
            "execute_statement",
            service_error_code="StatementTimeoutException",
            service_message=f"detalle {TELEFONO} {NOMBRE_PERSONA} SELECT",
        )
        with (
            caplog.at_level(logging.WARNING, logger="adapters.aurora"),
            pytest.raises(ErrorBaseDatos) as info,
        ):
            _adaptador(cliente).alerta_abierta(ALERT_ID)

    assert str(info.value) == MENSAJE_LECTURA
    assert info.value.__cause__ is None
    (registro,) = caplog.records
    assert registro.getMessage() == "aurora_fallo"
    assert registro.tipo == "StatementTimeoutException"
    assert registro.codigo == "StatementTimeoutException"
    texto = caplog.text + repr(registro.__dict__)
    for dato in (TELEFONO, "600000001", NOMBRE_PERSONA, "SELECT", "detalle", ALERT_ID):
        assert dato not in texto


def test_codigo_desconocido_no_se_registra(caplog: pytest.LogCaptureFixture) -> None:
    error = ClientError({"Error": {"Code": f"Raro{TELEFONO}"}}, "ExecuteStatement")
    with (
        caplog.at_level(logging.WARNING, logger="adapters.aurora"),
        pytest.raises(ErrorBaseDatos),
    ):
        _adaptador(_ClienteQueFalla(error)).registrar_recepcion(ALERT_ID)

    assert caplog.records[0].codigo is None
    assert TELEFONO not in caplog.text + repr(caplog.records[0].__dict__)


def test_client_error_sin_codigo_se_traduce() -> None:
    error = ClientError({}, "ExecuteStatement")

    with pytest.raises(ErrorBaseDatos) as info:
        _adaptador(_ClienteQueFalla(error)).registrar_recepcion(ALERT_ID)

    assert str(info.value) == MENSAJE_LECTURA


@pytest.mark.parametrize(
    "error",
    [
        EndpointConnectionError(endpoint_url=f"https://{TELEFONO}.example"),
        NoCredentialsError(),
    ],
)
def test_botocore_error_se_traduce_sin_datos(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="adapters.aurora"),
        pytest.raises(ErrorBaseDatos) as info,
    ):
        _adaptador(_ClienteQueFalla(error)).reservar_llamada(RESERVA)

    assert str(info.value) == MENSAJE_LECTURA
    assert info.value.__cause__ is None
    assert caplog.records[0].tipo == type(error).__name__
    assert caplog.records[0].codigo is None
    assert TELEFONO not in caplog.text


def test_error_no_de_aws_no_se_traga() -> None:
    adaptador = _adaptador(_ClienteQueFalla(RuntimeError("bug")))

    with pytest.raises(RuntimeError):
        adaptador.registrar_recepcion(ALERT_ID)


# --- SQL --------------------------------------------------------------------


def _constantes_sql() -> dict[str, str]:
    return {
        nombre: valor
        for nombre, valor in vars(modulo_aurora).items()
        if nombre.startswith("SQL_") and isinstance(valor, str)
    }


def test_hay_siete_sentencias_sql() -> None:
    assert len(_constantes_sql()) == 7


@pytest.mark.parametrize("nombre", sorted(_constantes_sql()))
def test_el_sql_no_lleva_llaves_ni_datos_formateados(nombre: str) -> None:
    sql = _constantes_sql()[nombre]
    assert "{" not in sql
    assert "}" not in sql
    assert "%s" not in sql
    for dato in (ALERT_ID, PERSON_ID, TELEFONO):
        assert dato not in sql


def test_todas_las_tablas_llevan_el_esquema() -> None:
    esquema = modulo_aurora.ESQUEMA
    for sql in _constantes_sql().values():
        for tabla in ("audit_log", "callbot_", "callbot_call"):
            for parte in sql.split(tabla)[:-1]:
                assert parte.endswith(f"{esquema}.") or parte.endswith("_")


def test_los_parametros_del_sql_estan_todos_declarados() -> None:
    esperados = {
        "SQL_REGISTRAR_RECEPCION": PARAMS_ALERTA,
        "SQL_ALERTA_ABIERTA": PARAMS_ALERTA,
        "SQL_CONSENTIMIENTO": PARAMS_CONSENTIMIENTO,
        "SQL_CONTACTO_PRINCIPAL": PARAMS_CONTACTO,
        "SQL_RESERVAR_LLAMADA": PARAMS_RESERVA,
    }
    for nombre, parametros in esperados.items():
        sql = _constantes_sql()[nombre]
        for parametro in parametros:
            assert f":{parametro['name']}" in sql


def test_fallo_de_infraestructura_no_es_datos_invalidos() -> None:
    error = ClientError({}, "ExecuteStatement")

    with pytest.raises(ErrorBaseDatos) as info:
        _adaptador(_ClienteQueFalla(error)).alerta_abierta(ALERT_ID)

    assert not isinstance(info.value, DatosInvalidos)
