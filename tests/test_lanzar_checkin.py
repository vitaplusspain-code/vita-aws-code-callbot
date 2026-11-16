import io
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

import handlers.lanzar_checkin as modulo
from adapters.aurora_lanzador import (
    SQL_CANDIDATOS,
    SQL_RESERVAR_CHECKIN,
    AuroraLanzador,
)
from adapters.connect import ConnectAdapter
from core.errores import ErrorBaseDatos, ErrorConfiguracion

RAIZ = Path(__file__).resolve().parent.parent
TELEFONO = "+447700900001"
OTRO_TELEFONO = "+447700900002"
FUERA = "+447700900099"
ORIGEN = "+15550100001"
INSTANCE_ID = "11111111-2222-3333-4444-555555555555"
FLUJO_ID = "66666666-7777-8888-9999-000000000000"
ENTORNO = {
    "LLAMADAS_ACTIVAS": "true",
    "CONNECT_INSTANCE_ID": INSTANCE_ID,
    "CONNECT_CONTACT_FLOW_ID": FLUJO_ID,
    "CONNECT_NUMERO_ORIGEN": ORIGEN,
    "LISTA_BLANCA": f"{TELEFONO},{OTRO_TELEFONO}",
    "DB_CLUSTER_ARN": "arn:cluster",
    "DB_SECRET_ARN": "arn:secreto",
    "DB_NAME": "vitaplus",
}
# 2026-11-16 es lunes; 17:05 UTC son las 18:05 en Madrid.
AHORA = datetime(2026, 11, 16, 17, 5, tzinfo=UTC)


def _persona(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _fila(n: int, telefono: str) -> dict[str, Any]:
    return {
        "person_id": _persona(n),
        "telefono": telefono,
        "hora": "18:00",
        "dias": None,
    }


class AuroraFalsa:
    """Cliente `rds-data` falso con memoria: una reserva por persona."""

    def __init__(self, filas: list[dict[str, Any]]) -> None:
        self.filas = filas
        self.reservadas: dict[str, str] = {}
        self.contactos: dict[str, str] = {}
        self.fallos: dict[str, str] = {}
        self.sentencias: list[str] = []
        self.error: Exception | None = None
        # Con True, la lectura devuelve también a quien ya está reservado.
        self.lectura_atrasada = False

    def execute_statement(self, **kwargs: Any) -> Mapping[str, Any]:
        sql = kwargs["sql"]
        self.sentencias.append(sql)
        if self.error is not None:
            raise self.error
        valores = {
            p["name"]: p["value"].get("stringValue") for p in kwargs["parameters"]
        }
        if sql == SQL_CANDIDATOS:
            return {"formattedRecords": json.dumps(self._visibles())}
        if sql == SQL_RESERVAR_CHECKIN:
            if valores["person_id"] in self.reservadas:
                return {"numberOfRecordsUpdated": 0}
            self.reservadas[valores["person_id"]] = valores["call_id"]
        elif "connect_contact_id" in sql:
            self.contactos[valores["call_id"]] = valores["contact_id"]
        else:
            self.fallos[valores["call_id"]] = valores["codigo"]
        return {"numberOfRecordsUpdated": 1}

    def _visibles(self) -> list[dict[str, Any]]:
        if self.lectura_atrasada:
            return self.filas
        return [f for f in self.filas if f["person_id"] not in self.reservadas]


class ConnectFalso:
    def __init__(self) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def start_outbound_voice_contact(self, **kwargs: Any) -> Mapping[str, Any]:
        self.llamadas.append(kwargs)
        if self.error:
            raise self.error
        return {"ContactId": f"contacto-{len(self.llamadas)}"}


class ContextoFalso:
    function_name = "vita-dev-callbot-lanzar-checkin"
    memory_limit_in_mb = 256
    invoked_function_arn = "arn:aws:lambda:eu-west-1:000000000000:function:f"
    aws_request_id = "req-1"

    def __init__(self, restante_ms: int = 120_000) -> None:
        self.restante_ms = restante_ms

    def get_remaining_time_in_millis(self) -> int:
        return self.restante_ms


class ContextoSinTiempo:
    """Contexto sin `get_remaining_time_in_millis` (p. ej. un invocador local)."""

    function_name = "f"
    memory_limit_in_mb = 256
    invoked_function_arn = "arn"
    aws_request_id = "r"


@pytest.fixture
def mundo(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[AuroraFalsa, ConnectFalso]]:
    """Entorno válido, Aurora y Connect falsos, y reloj fijo."""
    for nombre, valor in ENTORNO.items():
        monkeypatch.setenv(nombre, valor)
    aurora = AuroraFalsa([_fila(1, TELEFONO), _fila(2, OTRO_TELEFONO)])
    connect = ConnectFalso()
    monkeypatch.setattr(
        AuroraLanzador, "crear", classmethod(lambda cls, *a: cls(aurora, *a))
    )
    monkeypatch.setattr(
        ConnectAdapter, "crear", classmethod(lambda cls, *a: cls(connect, *a))
    )
    monkeypatch.setattr(modulo, "_ahora", lambda: AHORA)
    modulo.limpiar_cache()
    yield aurora, connect
    modulo.limpiar_cache()


@pytest.fixture
def salida_logs() -> Iterator[io.StringIO]:
    manejador = modulo.logger.registered_handler
    buffer = io.StringIO()
    anterior = manejador.setStream(buffer)
    yield buffer
    manejador.setStream(anterior)


def _lanzar(contexto: object | None = None) -> dict[str, Any]:
    return modulo.handler({"origen": "horario-checkin"}, contexto or ContextoFalso())


def test_llama_a_quien_toca_con_el_flujo_del_checkin_y_el_call_id(
    mundo: tuple[AuroraFalsa, ConnectFalso],
) -> None:
    aurora, connect = mundo

    respuesta = _lanzar()

    assert respuesta["estado"] == "ok"
    assert respuesta["llamadas"] == 2
    for llamada in connect.llamadas:
        assert llamada["ContactFlowId"] == FLUJO_ID
        assert llamada["InstanceId"] == INSTANCE_ID
        assert llamada["SourcePhoneNumber"] == ORIGEN
        assert set(llamada["Attributes"]) == {"call_id"}
    llamados = {c["DestinationPhoneNumber"] for c in connect.llamadas}
    assert llamados == {TELEFONO, OTRO_TELEFONO}
    call_ids = {c["Attributes"]["call_id"] for c in connect.llamadas}
    assert call_ids == set(aurora.reservadas.values()) == set(aurora.contactos)
    assert set(aurora.contactos.values()) == {"contacto-1", "contacto-2"}


def test_una_segunda_invocacion_no_vuelve_a_llamar(
    mundo: tuple[AuroraFalsa, ConnectFalso],
) -> None:
    _, connect = mundo

    _lanzar()
    segunda = _lanzar()

    assert segunda["llamadas"] == 0
    assert len(connect.llamadas) == 2


def test_una_lectura_atrasada_no_duplica_llamadas_gracias_a_la_reserva(
    mundo: tuple[AuroraFalsa, ConnectFalso],
) -> None:
    aurora, connect = mundo
    aurora.lectura_atrasada = True

    _lanzar()
    segunda = _lanzar()

    assert segunda["ya_reservadas"] == 2
    assert segunda["llamadas"] == 0
    assert len(connect.llamadas) == 2


def test_relanzar_tras_morir_a_mitad_de_lote_solo_llama_a_los_pendientes(
    mundo: tuple[AuroraFalsa, ConnectFalso],
) -> None:
    aurora, connect = mundo
    aurora.reservadas[_persona(1)] = "reservada-por-la-invocacion-muerta"

    respuesta = _lanzar()

    assert respuesta["llamadas"] == 1
    assert [c["DestinationPhoneNumber"] for c in connect.llamadas] == [OTRO_TELEFONO]


def test_respeta_la_lista_blanca(mundo: tuple[AuroraFalsa, ConnectFalso]) -> None:
    aurora, connect = mundo
    aurora.filas.append(_fila(3, FUERA))

    respuesta = _lanzar()

    assert respuesta["fuera_lista_blanca"] == 1
    assert FUERA not in {c["DestinationPhoneNumber"] for c in connect.llamadas}
    assert _persona(3) not in aurora.reservadas


@pytest.mark.parametrize("valor", ["false", "", "si", "0"])
def test_con_las_llamadas_desactivadas_no_toca_nada(
    mundo: tuple[AuroraFalsa, ConnectFalso],
    monkeypatch: pytest.MonkeyPatch,
    valor: str,
) -> None:
    aurora, connect = mundo
    monkeypatch.setenv("LLAMADAS_ACTIVAS", valor)

    respuesta = _lanzar()

    assert respuesta == {"estado": "desactivado"}
    assert aurora.sentencias == []
    assert connect.llamadas == []


def test_sin_la_variable_de_llamadas_tambien_falla_cerrado(
    mundo: tuple[AuroraFalsa, ConnectFalso], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LLAMADAS_ACTIVAS")

    assert _lanzar() == {"estado": "desactivado"}


def test_un_fallo_de_connect_se_registra_y_no_aborta(
    mundo: tuple[AuroraFalsa, ConnectFalso],
) -> None:
    aurora, connect = mundo
    connect.error = ClientError(
        {"Error": {"Code": "LimitExceededException"}}, "StartOutboundVoiceContact"
    )

    respuesta = _lanzar()

    assert respuesta["fallos"] == 2
    assert set(aurora.fallos.values()) == {"error_connect"}
    assert aurora.contactos == {}


def test_para_cuando_no_queda_tiempo(
    mundo: tuple[AuroraFalsa, ConnectFalso],
) -> None:
    _, connect = mundo

    respuesta = _lanzar(ContextoFalso(restante_ms=modulo.MARGEN_MS))

    assert respuesta["llamadas"] == 0
    assert respuesta["pendientes"] == 2
    assert connect.llamadas == []


def test_sin_contexto_de_lambda_no_limita_por_tiempo(
    mundo: tuple[AuroraFalsa, ConnectFalso],
) -> None:
    _, connect = mundo

    respuesta = _lanzar(ContextoSinTiempo())

    assert respuesta["llamadas"] == 2
    assert len(connect.llamadas) == 2


def test_los_logs_no_llevan_telefonos(
    mundo: tuple[AuroraFalsa, ConnectFalso], salida_logs: io.StringIO
) -> None:
    _lanzar()

    texto = salida_logs.getvalue()
    assert "checkin_procesado" in texto
    for dato in (TELEFONO, OTRO_TELEFONO, "7700900001", ORIGEN):
        assert dato not in texto


def test_un_error_del_dominio_se_registra_y_se_propaga(
    mundo: tuple[AuroraFalsa, ConnectFalso], salida_logs: io.StringIO
) -> None:
    aurora, _ = mundo
    aurora.error = ClientError({"Error": {"Code": "ForbiddenException"}}, "x")

    with pytest.raises(ErrorBaseDatos):
        _lanzar()

    registro = json.loads(salida_logs.getvalue().splitlines()[-1])
    assert registro["message"] == "checkin_fallido"
    assert registro["codigo"] == "error_base_datos"


def test_un_error_inesperado_se_registra_sin_mensaje_y_se_propaga(
    mundo: tuple[AuroraFalsa, ConnectFalso], salida_logs: io.StringIO
) -> None:
    _, connect = mundo
    connect.error = ValueError(f"secreto {TELEFONO}")

    with pytest.raises(ValueError, match="secreto"):
        _lanzar()

    texto = salida_logs.getvalue()
    assert "checkin_error_inesperado" in texto
    assert TELEFONO not in texto


def test_falta_configuracion_lanza_error_de_configuracion(
    mundo: tuple[AuroraFalsa, ConnectFalso], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DB_NAME")

    with pytest.raises(ErrorConfiguracion, match="DB_NAME"):
        _lanzar()


def test_el_evento_de_ejemplo_es_el_del_horario() -> None:
    ruta = RAIZ / "events" / "lanzar-checkin.json"

    assert json.loads(ruta.read_text("utf-8")) == {"origen": "horario-checkin"}


def test_el_reloj_real_devuelve_la_hora_actual_con_zona() -> None:
    ahora = modulo._ahora()  # noqa: SLF001

    assert ahora.tzinfo is not None
    assert abs((datetime.now(UTC) - ahora).total_seconds()) < 5
