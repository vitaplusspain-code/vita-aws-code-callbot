import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import handlers.conversacion as modulo
from core.checkin_guion import TEXTOS, Trato


@dataclass
class ContextoFalso:
    function_name: str = "vita-dev-callbot-conversacion"
    memory_limit_in_mb: int = 128
    invoked_function_arn: str = "arn:aws:lambda:eu-central-1:000000000000:function:f"
    aws_request_id: str = "req-1"


RAIZ = Path(__file__).resolve().parent.parent
NOMBRE = "Marisol"
CENTINELA = "zanahoria hervida"
CONTEXTO = ContextoFalso()
URGENCIA = TEXTOS[Trato.USTED].urgencia.replace(", {nombre}", "")


@pytest.fixture(autouse=True)
def _entorno(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DEMO_PERSONA_NOMBRE", NOMBRE)
    monkeypatch.setenv("DEMO_TRATO", "usted")
    modulo.limpiar_cache()
    yield


def _evento(nombre: str) -> dict[str, Any]:
    return json.loads((RAIZ / "events" / nombre).read_text(encoding="utf-8"))


def _con_texto(evento: dict[str, Any], texto: str) -> dict[str, Any]:
    return {**evento, "inputTranscript": texto}


def _mensaje(respuesta: dict[str, Any]) -> str:
    return respuesta["messages"][0]["content"]


def _atributos(respuesta: dict[str, Any]) -> dict[str, str]:
    return respuesta["sessionState"]["sessionAttributes"]


def test_el_primer_turno_saluda_y_pregunta() -> None:
    respuesta = modulo.handler(_evento("lex-inicio.json"), CONTEXTO)

    assert respuesta["sessionState"]["dialogAction"]["type"] == "ElicitSlot"
    assert f"Hola, {NOMBRE}" in _mensaje(respuesta)
    assert _atributos(respuesta)["checkin_paso"] == "animo_hoy"
    assert _atributos(respuesta)["call_id"].startswith("0b6c1f0e")


def test_un_turno_normal_avanza_a_la_siguiente_pregunta() -> None:
    respuesta = modulo.handler(_evento("lex-turno.json"), CONTEXTO)

    assert _atributos(respuesta)["checkin_paso"] == "animo_semana"
    assert "semana" in _mensaje(respuesta)


def test_una_urgencia_cierra_la_llamada_con_el_112() -> None:
    evento = _con_texto(_evento("lex-turno.json"), "me he caído y no me levanto")

    respuesta = modulo.handler(evento, CONTEXTO)

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert respuesta["sessionState"]["intent"]["state"] == "Fulfilled"
    assert "112" in _mensaje(respuesta)


def test_el_riesgo_se_atiende_aunque_falle_la_configuracion_del_contexto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEMO_PERSONA_NOMBRE")
    evento = _con_texto(_evento("lex-turno.json"), "me duele el pecho")

    respuesta = modulo.handler(evento, CONTEXTO)

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert _mensaje(respuesta) == URGENCIA


def test_sin_contexto_y_sin_riesgo_cierra_con_el_texto_de_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEMO_PERSONA_NOMBRE")

    respuesta = modulo.handler(_evento("lex-turno.json"), CONTEXTO)

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert _mensaje(respuesta) == TEXTOS[Trato.USTED].cierre_error
    assert _atributos(respuesta)["call_id"].startswith("0b6c1f0e")


def test_un_evento_basura_no_rompe_el_handler() -> None:
    respuesta = modulo.handler(None, CONTEXTO)

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert _mensaje(respuesta) == TEXTOS[Trato.USTED].cierre_error


def test_una_excepcion_inesperada_devuelve_un_close_valido(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError(f"fallo con {CENTINELA}")

    monkeypatch.setattr(modulo, "_servicio", _rompe)

    respuesta = modulo.handler(_evento("lex-turno.json"), CONTEXTO)

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert respuesta["sessionState"]["intent"]["state"] == "Fulfilled"
    assert _mensaje(respuesta) == TEXTOS[Trato.USTED].cierre_error
    assert CENTINELA not in caplog.text


def test_una_excepcion_inesperada_no_oculta_el_riesgo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError("fallo")

    monkeypatch.setattr(modulo, "_servicio", _rompe)
    evento = _con_texto(_evento("lex-turno.json"), "no puedo respirar")

    respuesta = modulo.handler(evento, CONTEXTO)

    assert _mensaje(respuesta) == URGENCIA


def test_si_hasta_la_emergencia_falla_devuelve_el_close_fijo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError("fallo")

    monkeypatch.setattr(modulo, "_servicio", _rompe)
    monkeypatch.setattr(modulo, "construir_respuesta", _rompe)

    respuesta = modulo.handler(_evento("lex-turno.json"), CONTEXTO)

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert respuesta["sessionState"]["intent"]["state"] == "Fulfilled"
    assert _mensaje(respuesta) == TEXTOS[Trato.USTED].cierre_error


def test_la_respuesta_fija_no_se_comparte_entre_llamadas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError("fallo")

    monkeypatch.setattr(modulo, "_servicio", _rompe)
    monkeypatch.setattr(modulo, "construir_respuesta", _rompe)

    primera = modulo.handler(None, CONTEXTO)
    primera["messages"].clear()

    assert modulo.handler(None, CONTEXTO)["messages"]


def test_los_logs_no_contienen_la_frase_ni_el_nombre(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    turno = _con_texto(_evento("lex-turno.json"), f"bien, como {CENTINELA}")
    urgencia = _con_texto(_evento("lex-turno.json"), f"me he caído con {CENTINELA}")

    for evento in (_evento("lex-inicio.json"), turno, urgencia):
        modulo.handler(evento, CONTEXTO)

    salida = capsys.readouterr()
    registros = " ".join(str(r.__dict__) for r in caplog.records)
    todo = salida.out + salida.err + caplog.text + registros
    assert CENTINELA not in todo
    assert NOMBRE not in todo
    assert "caído" not in todo
    assert "turno" in caplog.text


def test_el_log_del_turno_trae_solo_los_campos_permitidos(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    evento = _con_texto(_evento("lex-turno.json"), "me siento solo, no quiero vivir")

    modulo.handler(evento, CONTEXTO)

    registro = next(r for r in caplog.records if r.getMessage() == "turno")
    assert registro.riesgo == "self_harm"
    assert registro.terminado is True
    assert registro.n_observaciones == 0
    assert registro.session_id == "00000000-ejemplo-sesion-lex"
    assert registro.paso == "fin"
    assert registro.intentos == 0
    assert "vivir" not in str(registro.__dict__)


def test_limpiar_cache_recrea_las_dependencias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modulo.handler(_evento("lex-inicio.json"), CONTEXTO)
    monkeypatch.setenv("DEMO_PERSONA_NOMBRE", "Lucía")

    modulo.limpiar_cache()
    respuesta = modulo.handler(_evento("lex-inicio.json"), CONTEXTO)

    assert "Hola, Lucía" in _mensaje(respuesta)


def test_el_origen_de_una_excepcion_sin_traza_es_desconocido() -> None:
    assert modulo._origen(RuntimeError("x")) == "desconocido"


def test_un_fallo_de_configuracion_se_distingue_en_el_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DEMO_PERSONA_NOMBRE", f"{CENTINELA}1")
    caplog.set_level(logging.INFO)

    respuesta = modulo.handler(_evento("lex-turno.json"), CONTEXTO)

    mensajes = [r.getMessage() for r in caplog.records]
    assert "servicio_no_disponible" in mensajes
    assert "fallo_de_turno" not in mensajes
    registro = next(r for r in caplog.records if r.getMessage() == mensajes[0])
    assert registro.tipo == "ErrorConfiguracion"
    assert CENTINELA not in caplog.text
    assert _mensaje(respuesta) == TEXTOS[Trato.USTED].cierre_error


def test_un_fallo_del_turno_se_distingue_en_el_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError(f"fallo con {CENTINELA}")

    monkeypatch.setattr(modulo.ServicioConversacion, "responder", _rompe)
    caplog.set_level(logging.INFO)

    modulo.handler(_evento("lex-turno.json"), CONTEXTO)

    mensajes = [r.getMessage() for r in caplog.records]
    assert "fallo_de_turno" in mensajes
    assert "servicio_no_disponible" not in mensajes
    assert "error_inesperado" in mensajes
    assert CENTINELA not in caplog.text


def test_un_fallo_del_log_del_turno_no_descarta_la_respuesta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError("log roto")

    monkeypatch.setattr(modulo, "_registrar_turno", _rompe)

    respuesta = modulo.handler(_evento("lex-turno.json"), CONTEXTO)

    assert _atributos(respuesta)["checkin_paso"] == "animo_semana"
    assert "semana" in _mensaje(respuesta)


def test_los_logs_del_core_salen_por_el_logger_del_handler() -> None:
    nucleo = logging.getLogger("core")

    assert modulo.logger.registered_handler in nucleo.handlers
