"""Puertos de la conversación diaria: contexto de la llamada y registro."""

from dataclasses import dataclass, field
from typing import Protocol

from core.checkin import Turno
from core.checkin_guion import Trato

__all__ = ["ContextoConversacion", "DatosConversacion", "RegistroCheckin"]


@dataclass(frozen=True)
class DatosConversacion:
    """Con quién se habla y cómo tratarle; el nombre es dato personal."""

    nombre: str = field(repr=False)
    trato: Trato


class ContextoConversacion(Protocol):
    """Averigua con quién es la llamada a partir de su `call_id`."""

    def datos(self, call_id: str) -> DatosConversacion | None:
        """Datos de la llamada, o `None` si no existe.

        Puede lanzar `ErrorBaseDatos`.

        TODO(fase 4): el `call_id` llega de un sessionAttribute que no es de
        confianza (el adaptador solo comprueba que parezca un UUID). Aurora
        debe comprobar que existe y está activo, con consultas parametrizadas.
        """
        ...


class RegistroCheckin(Protocol):
    """Guarda lo que pasa en cada turno de la conversación."""

    def guardar_turno(self, call_id: str, turno: Turno) -> None:
        """Guarda las observaciones y la señal de riesgo del turno."""
        ...
