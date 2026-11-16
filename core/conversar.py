"""Servicio de la conversación diaria: un turno de Lex de principio a fin.

El detector de riesgo corre siempre primero, también cuando falla el contexto
o el estado viene roto: una urgencia nunca se queda sin atender.
"""

import logging
from collections.abc import Mapping

from core.checkin import (
    EstadoCheckin,
    Turno,
    avanzar,
    hay_estado,
    iniciar,
    trato_o_usted,
    turno_de_riesgo_sin_estado,
)
from core.checkin_guion import TEXTOS, Paso, Trato
from core.interprete import Interprete
from core.puertos_checkin import (
    ContextoConversacion,
    DatosConversacion,
    RegistroCheckin,
)

__all__ = [
    "EVENTO_RIESGO_NO_REGISTRADO",
    "ServicioConversacion",
    "turno_de_cierre_error",
]

logger = logging.getLogger(__name__)

# Evento fijo para la alarma: hubo una señal de riesgo y no se pudo guardar.
EVENTO_RIESGO_NO_REGISTRADO = "riesgo_no_registrado"


def turno_de_cierre_error(trato: Trato = Trato.USTED) -> Turno:
    """Turno que cierra con el texto fijo de error, sin nombre."""
    return Turno(
        estado=EstadoCheckin(Paso.FIN), texto_a_decir=TEXTOS[trato].cierre_error
    )


def _riesgo_o_cierre(texto: str, trato: Trato = Trato.USTED) -> Turno:
    """Urgencia sin nombre si el texto la tiene; si no, cierre de error."""
    return turno_de_riesgo_sin_estado(texto, trato) or turno_de_cierre_error(trato)


class ServicioConversacion:
    """Decide qué decir en cada turno y lo registra."""

    def __init__(
        self,
        contexto: ContextoConversacion,
        registro: RegistroCheckin,
        interprete: Interprete,
    ) -> None:
        """Guarda los puertos y el intérprete."""
        self._contexto = contexto
        self._registro = registro
        self._interprete = interprete

    def responder(
        self,
        call_id: str,
        contacto_id: str,
        atributos: Mapping[str, str],
        texto: str,
    ) -> Turno:
        """Procesa lo que dijo la persona y devuelve el turno a hablar.

        `contacto_id` ata el `call_id` (no fiable) al contacto del canal.
        Nunca lanza por fallos de contexto, estado o registro.
        """
        turno = self._decidir(call_id, contacto_id, atributos, texto)
        self._guardar(call_id, contacto_id, turno)
        return turno

    def _datos(self, call_id: str, contacto_id: str) -> DatosConversacion | None:
        try:
            return self._contexto.datos(call_id, contacto_id)
        except Exception as error:  # sin contexto se atiende solo el riesgo
            logger.warning("contexto_no_disponible: %s", type(error).__name__)
            return None

    def _decidir(
        self,
        call_id: str,
        contacto_id: str,
        atributos: Mapping[str, str],
        texto: str,
    ) -> Turno:
        datos = self._datos(call_id, contacto_id)
        if datos is None:
            return _riesgo_o_cierre(texto)
        trato = trato_o_usted(datos.trato)
        try:
            if not hay_estado(atributos):
                return self._primer_turno(datos, texto, trato)
            estado = EstadoCheckin.desde_atributos(atributos)
            return avanzar(estado, texto, self._interprete, datos.nombre, trato)
        except Exception as error:  # nunca se pierde la urgencia ni el trato
            logger.warning("turno_fallido: %s", type(error).__name__)
            return _riesgo_o_cierre(texto, trato)

    def _primer_turno(
        self, datos: DatosConversacion, texto: str, trato: Trato
    ) -> Turno:
        riesgo = turno_de_riesgo_sin_estado(texto, trato)
        return riesgo or iniciar(datos.nombre, trato)

    def _guardar(self, call_id: str, contacto_id: str, turno: Turno) -> None:
        try:
            self._registro.guardar_turno(call_id, contacto_id, turno)
        except Exception as error:  # guardar no debe tumbar la llamada
            logger.error("registro_fallido: %s", type(error).__name__)
            self._alarma_de_riesgo(turno)

    def _alarma_de_riesgo(self, turno: Turno) -> None:
        """Evento fijo para una alarma si la señal de riesgo pudo perderse.

        Solo el tipo: nunca la frase ni el nombre.
        """
        if turno.senal_riesgo is not None:
            logger.error(
                EVENTO_RIESGO_NO_REGISTRADO,
                extra={"tipo_riesgo": turno.senal_riesgo.kind.value},
            )
