"""Puertos de la conversación diaria: contexto de la llamada y registro."""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from core.checkin import Turno
from core.checkin_guion import Trato

__all__ = ["ContextoConversacion", "DatosConversacion", "RegistroCheckin"]


@dataclass(frozen=True)
class DatosConversacion:
    """Con quién se habla y cómo tratarle; el nombre es dato personal."""

    nombre: str = field(repr=False)
    trato: Trato


@runtime_checkable
class ContextoConversacion(Protocol):
    """Averigua con quién es la llamada a partir de su `call_id`."""

    def datos(self, call_id: str, contacto_id: str) -> DatosConversacion | None:
        """Datos de la llamada, o `None` si no existe o no está activa.

        El `call_id` llega de un sessionAttribute que no es de confianza: solo
        vale si `contacto_id` (el contacto del canal, que no controla quien
        llama) es el de esa llamada. El adaptador de Aurora además comprueba que
        es un check-in sin terminar. Puede lanzar `ErrorBaseDatos`.
        """
        ...


@runtime_checkable
class RegistroCheckin(Protocol):
    """Guarda lo que pasa en cada turno de la conversación."""

    def guardar_turno(self, call_id: str, contacto_id: str, turno: Turno) -> None:
        """Guarda las observaciones y la señal de riesgo del turno.

        Solo escribe si `contacto_id` es el contacto de la llamada `call_id`.
        """
        ...
