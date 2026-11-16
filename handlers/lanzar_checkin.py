"""Lambda del check-in diario: la invoca EventBridge Scheduler y llama a quien toca.

El evento (`{"origen": "horario-checkin"}`) no se usa: la hora la fija el reloj.
Sin reintentos (ni Scheduler ni Lambda): cada persona se reserva en Aurora
antes de llamarla, así que una invocación repetida no duplica llamadas. En los
logs solo van contadores, nunca nombres ni teléfonos.

El interruptor `LLAMADAS_ACTIVAS` se lee una vez por invocación y no se relee
entre llamadas del lote: es una variable de entorno y en Lambda solo cambia con
un despliegue, así que releerla no aportaría nada.
"""

import functools
import os
from datetime import UTC, datetime
from typing import Any

from aws_lambda_powertools import Logger

from adapters.aurora_lanzador import AuroraLanzador
from adapters.connect import ConnectAdapter
from core.errores import ErrorCallbot
from core.lanzador import ServicioCheckin
from handlers.config import lista_blanca_desde_entorno, llamadas_activas

__all__ = ["MARGEN_MS", "handler", "limpiar_cache"]

logger = Logger(service="callbot")

# Con menos de esto de tiempo restante no se empieza otra llamada: cada una son
# tres accesos (reservar, Connect, guardar contacto) de hasta 10 s cada uno.
MARGEN_MS = 35_000


@functools.cache
def _servicio() -> ServicioCheckin:
    """Crea el servicio en la primera invocación (no al importar)."""
    lista_blanca = lista_blanca_desde_entorno(os.environ)
    return ServicioCheckin(
        repositorio=AuroraLanzador.desde_entorno(os.environ),
        canal=ConnectAdapter.desde_entorno(os.environ, lista_blanca),
        lista_blanca=lista_blanca,
    )


def limpiar_cache() -> None:
    """Olvida el servicio creado (para tests)."""
    _servicio.cache_clear()


def _ahora() -> datetime:
    return datetime.now(UTC)


def _queda_tiempo(context: object) -> bool:
    """Hay margen para otra llamada; sin contexto de Lambda, siempre."""
    restante = getattr(context, "get_remaining_time_in_millis", None)
    return restante is None or restante() > MARGEN_MS


@logger.inject_lambda_context(log_event=False)
def handler(event: object, context: object) -> dict[str, Any]:
    """Lanza las llamadas del check-in que tocan ahora."""
    if not llamadas_activas(os.environ):
        logger.warning("checkin_desactivado")
        return {"estado": "desactivado"}
    try:
        resumen = _servicio().lanzar(_ahora(), lambda: _queda_tiempo(context))
    except ErrorCallbot as error:
        logger.error("checkin_fallido", extra={"codigo": error.codigo})
        raise
    except Exception as error:
        logger.error("checkin_error_inesperado", extra={"tipo": type(error).__name__})
        raise
    logger.info("checkin_procesado", extra=resumen.como_dict())
    return {"estado": "ok", **resumen.como_dict()}
