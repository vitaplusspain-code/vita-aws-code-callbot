"""Lambda de `POST /avisos`: valida el aviso y pide la llamada a Connect."""

import base64
import binascii
import functools
import json
import os
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aws_lambda_powertools import Logger

from adapters.connect import ConnectAdapter
from adapters.persona_en_memoria import PersonaEnMemoria
from core.aviso import TAMANO_MAXIMO_CUERPO, parsear_aviso_json
from core.errores import (
    AvisoInvalido,
    ErrorCallbot,
    LlamadasDesactivadas,
    TelefonoNoPermitido,
)
from core.lista_blanca import ListaBlanca
from core.mensaje import construir_mensaje
from core.telefono import enmascarar_telefono
from handlers.config import (
    lista_blanca_desde_entorno,
    llamadas_activas,
)

__all__ = ["handler", "limpiar_cache"]

logger = Logger(service="callbot")

CODIGO_INTERNO = "error_interno"
# Un cuerpo en base64 de más de esta longitud decodifica a más de
# TAMANO_MAXIMO_CUERPO bytes: no se decodifica, lo rechaza el parser tal cual.
_MAXIMO_BASE64 = (TAMANO_MAXIMO_CUERPO // 3 + 1) * 4

# código -> (estado HTTP, texto fijo). Nunca se devuelve `str(e)`.
_RESPUESTAS_ERROR: Mapping[str, tuple[int, str]] = {
    LlamadasDesactivadas.codigo: (503, "El servicio de llamadas no está activo."),
    "aviso_invalido": (400, "El aviso no es válido."),
    "persona_no_encontrada": (400, "La persona indicada no existe."),
    "telefono_no_permitido": (403, "No se permite llamar a ese teléfono."),
    "error_connect": (500, "No se pudo iniciar la llamada."),
    "error_configuracion": (500, "El servicio no está bien configurado."),
    CODIGO_INTERNO: (500, "Error interno."),
}


@dataclass(frozen=True)
class _Dependencias:
    connect: ConnectAdapter
    personas: PersonaEnMemoria
    lista_blanca: ListaBlanca


@functools.cache
def _dependencias() -> _Dependencias:
    """Crea las dependencias en la primera petición (no al importar).

    `functools.cache` no guarda las excepciones: si falla, se reintenta.
    """
    return _Dependencias(
        connect=ConnectAdapter.desde_entorno(os.environ),
        personas=PersonaEnMemoria.desde_entorno(os.environ),
        lista_blanca=lista_blanca_desde_entorno(os.environ),
    )


def limpiar_cache() -> None:
    """Olvida las dependencias creadas (para tests)."""
    _dependencias.cache_clear()


def _respuesta(estado: int, datos: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": estado,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(datos),
    }


def _respuesta_error(codigo: str) -> dict[str, Any]:
    """Respuesta de error con el texto fijo del código (ya normalizado)."""
    estado, mensaje = _RESPUESTAS_ERROR[codigo]
    return _respuesta(estado, {"error": {"codigo": codigo, "mensaje": mensaje}})


def _cuerpo(evento: object) -> str | bytes | None:
    """Extrae el cuerpo; decodifica base64 si el evento lo indica.

    Con `isBase64Encoded` se decodifica de forma estricta; si no es base64
    válido se rechaza con `AvisoInvalido`. Un cuerpo demasiado largo no se
    decodifica: pasa tal cual y el parser lo rechaza por tamaño.
    """
    if not isinstance(evento, Mapping):
        return None
    cuerpo = evento.get("body")
    if evento.get("isBase64Encoded") is not True or not isinstance(cuerpo, str):
        return cuerpo
    if len(cuerpo) > _MAXIMO_BASE64:
        return cuerpo
    try:
        return base64.b64decode(cuerpo, validate=True)
    except (binascii.Error, ValueError):
        problema = "El aviso no es válido: el cuerpo no es base64."
    raise AvisoInvalido(problema)


def _lanzar(evento: object) -> dict[str, Any]:
    """Flujo principal; las excepciones las traduce `handler`."""
    if not llamadas_activas(os.environ):
        raise LlamadasDesactivadas("Llamadas desactivadas por configuración.")
    aviso = parsear_aviso_json(_cuerpo(evento))
    dependencias = _dependencias()
    persona = dependencias.personas.obtener(aviso.persona_id)
    telefono = persona.familiar.telefono
    if not dependencias.lista_blanca.permite(telefono):
        raise TelefonoNoPermitido("Teléfono fuera de la lista blanca.")
    mensaje = construir_mensaje(aviso.caso, persona.nombre, persona.familiar.nombre)
    contact_id = dependencias.connect.iniciar_llamada(telefono, mensaje)
    logger.info(
        "llamada_iniciada",
        extra={"telefono": enmascarar_telefono(telefono), "contact_id": contact_id},
    )
    return _respuesta(200, {"contact_id": contact_id})


def _origen(error: BaseException) -> str:
    """Fichero:línea donde se lanzó la excepción (sin ruta ni mensaje)."""
    marcos = traceback.extract_tb(error.__traceback__)
    if not marcos:
        return "desconocido"
    return f"{os.path.basename(marcos[-1].filename)}:{marcos[-1].lineno}"


def _registrar_rechazo(error: ErrorCallbot, codigo: str, estado: int) -> None:
    """Registra un error del dominio: `error` si es 5xx, `warning` si no.

    El 503 de llamadas desactivadas es un estado deliberado (interruptor de
    configuración), no un fallo: se registra como `warning`.
    """
    campos = {"codigo": codigo, "tipo": type(error).__name__}
    if estado >= 500 and codigo != LlamadasDesactivadas.codigo:
        logger.error("aviso_fallido", extra=campos)
    else:
        logger.warning("aviso_rechazado", extra=campos)


@logger.inject_lambda_context(log_event=False)
def handler(event: object, context: object) -> dict[str, Any]:
    """Atiende un evento proxy de API Gateway REST para `POST /avisos`."""
    try:
        return _lanzar(event)
    except ErrorCallbot as error:
        codigo = error.codigo if error.codigo in _RESPUESTAS_ERROR else CODIGO_INTERNO
        _registrar_rechazo(error, codigo, _RESPUESTAS_ERROR[codigo][0])
    except Exception as error:  # última barrera: nunca se filtra nada al cliente
        codigo = CODIGO_INTERNO
        logger.error(
            "error_inesperado",
            extra={
                "codigo": codigo,
                "tipo": type(error).__name__,
                "origen": _origen(error),
            },
        )
    return _respuesta_error(codigo)
