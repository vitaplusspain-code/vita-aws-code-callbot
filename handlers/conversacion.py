"""Lambda de la conversación diaria: code hook de Amazon Lex V2.

Lex solo oye y habla; aquí se decide qué decir. Nunca se relanza una
excepción a Lex: ante cualquier fallo se atiende el riesgo si lo hay y se
cierra la llamada con un texto fijo. En los logs solo van datos de control
(paso, intentos, terminado, tipo de riesgo, nº de observaciones, sessionId):
nunca el turno, la frase ni el nombre.
"""

import copy
import functools
import os
import traceback
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging import utils as logging_utils

from adapters.conversacion_en_memoria import ContextoEnMemoria, RegistroSinPersistencia
from adapters.lex import construir_respuesta, parsear_evento
from core.checkin import Turno, turno_de_riesgo_sin_estado
from core.checkin_guion import TEXTOS, Trato
from core.conversar import ServicioConversacion, turno_de_cierre_error
from core.errores import ErrorConfiguracion
from core.interprete import InterpreteReglas
from handlers.config import aurora_configurada

__all__ = ["handler", "limpiar_cache"]

logger = Logger(service="callbot")
# El core usa `logging` estándar (no importa Powertools): sus registros salen
# por el mismo formato y nivel que los del handler.
logging_utils.copy_config_to_registered_loggers(source_logger=logger, include={"core"})

# Último recurso si ni siquiera se puede construir la respuesta normal.
_CLOSE_FIJO: dict[str, Any] = {
    "sessionState": {
        "dialogAction": {"type": "Close"},
        "intent": {
            "name": "Conversacion",
            "state": "Fulfilled",
            "slots": {"respuesta": None},
        },
        "sessionAttributes": {},
    },
    "messages": [
        {"contentType": "PlainText", "content": TEXTOS[Trato.USTED].cierre_error}
    ],
}


@functools.cache
def _servicio() -> ServicioConversacion:
    """Crea el servicio en la primera petición (no al importar).

    Con las variables `DB_*` usa Aurora; sin ellas, la memoria (demo local).
    """
    if aurora_configurada(os.environ):
        # Import perezoso: sin Aurora (demo local) no se carga el adaptador.
        from adapters.aurora_checkin import AuroraCheckin

        aurora = AuroraCheckin.desde_entorno(os.environ)
        return ServicioConversacion(aurora, aurora, InterpreteReglas())
    return ServicioConversacion(
        contexto=ContextoEnMemoria.desde_entorno(os.environ),
        registro=RegistroSinPersistencia(),
        interprete=InterpreteReglas(),
    )


def limpiar_cache() -> None:
    """Olvida las dependencias creadas (para tests)."""
    _servicio.cache_clear()


def _registrar_turno(turno: Turno, session_id: str) -> None:
    riesgo = turno.senal_riesgo
    logger.info(
        "turno",
        extra={
            "paso": turno.estado.paso.value,
            "intentos": turno.estado.intentos,
            "terminado": turno.terminado,
            "riesgo": riesgo.kind.value if riesgo else None,
            "n_observaciones": len(turno.observaciones),
            "session_id": session_id,
        },
    )


def _origen(error: BaseException) -> str:
    """Fichero:línea donde se lanzó la excepción (sin ruta ni mensaje)."""
    marcos = traceback.extract_tb(error.__traceback__)
    if not marcos:
        return "desconocido"
    return f"{os.path.basename(marcos[-1].filename)}:{marcos[-1].lineno}"


def _servicio_registrado() -> ServicioConversacion:
    try:
        return _servicio()
    except ErrorConfiguracion as error:  # solo el tipo: el mensaje nombra variables
        logger.error("servicio_no_disponible", extra={"tipo": type(error).__name__})
        raise


def _registrar_sin_fallar(turno: Turno, session_id: str) -> None:
    try:
        _registrar_turno(turno, session_id)
    except Exception:  # un log roto no descarta el turno calculado
        pass


def _atender(evento: object) -> dict[str, Any]:
    entrada = parsear_evento(evento)
    servicio = _servicio_registrado()
    try:
        turno = servicio.responder(
            entrada.call_id, entrada.contacto_id, entrada.atributos, entrada.texto
        )
    except Exception as error:
        logger.error("fallo_de_turno", extra={"tipo": type(error).__name__})
        raise
    respuesta = construir_respuesta(turno, entrada.atributos)
    _registrar_sin_fallar(turno, entrada.session_id)
    return respuesta


def _emergencia(evento: object) -> dict[str, Any]:
    """Atiende el riesgo si lo hay; si no, cierra con el texto de error."""
    try:
        entrada = parsear_evento(evento)
        # Límite conocido: aquí no hay contexto, así que el trato es siempre usted
        # (ver `no_subir/proyecto/afinado-post-mvp.md`).
        turno = turno_de_riesgo_sin_estado(entrada.texto, Trato.USTED)
        return construir_respuesta(
            turno or turno_de_cierre_error(Trato.USTED), entrada.atributos
        )
    except Exception:  # último recurso: respuesta fija
        return copy.deepcopy(_CLOSE_FIJO)


@logger.inject_lambda_context(log_event=False)
def handler(event: object, context: object) -> dict[str, Any]:
    """Atiende un evento de Lex V2 y devuelve siempre una respuesta válida."""
    try:
        return _atender(event)
    except Exception as error:  # última barrera: nunca se relanza a Lex
        logger.error(
            "error_inesperado",
            extra={"tipo": type(error).__name__, "origen": _origen(error)},
        )
        return _emergencia(event)
