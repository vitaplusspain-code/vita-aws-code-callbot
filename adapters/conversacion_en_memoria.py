"""Contexto y registro de la conversación en memoria (hasta la fase 4).

El nombre y el trato salen de variables de entorno; Aurora los dará después.
"""

from collections.abc import Mapping
from typing import Self

from pydantic import TypeAdapter, ValidationError

from core.checkin import Turno
from core.checkin_guion import Trato
from core.errores import ErrorConfiguracion
from core.puertos_checkin import DatosConversacion
from core.tipos import NombrePersona

__all__ = ["ContextoEnMemoria", "RegistroSinPersistencia"]

_VAR_NOMBRE = "DEMO_PERSONA_NOMBRE"
_VAR_TRATO = "DEMO_TRATO"
_NOMBRE = TypeAdapter(NombrePersona)


def _invalida(variable: str) -> ErrorConfiguracion:
    return ErrorConfiguracion(f"La variable {variable} no es válida.")


class ContextoEnMemoria:
    """Implementa `ContextoConversacion` con una única persona fija."""

    def __init__(self, datos: DatosConversacion) -> None:
        """Guarda los datos que se devuelven para cualquier `call_id`."""
        self._datos = datos

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> Self:
        """Lee `DEMO_PERSONA_NOMBRE` y `DEMO_TRATO` (por defecto, usted).

        Lanza `ErrorConfiguracion` nombrando la variable, nunca su valor.
        """
        if _VAR_NOMBRE not in entorno:
            raise ErrorConfiguracion(f"Falta la variable {_VAR_NOMBRE}.")
        try:
            nombre = _NOMBRE.validate_python(entorno[_VAR_NOMBRE])
        except ValidationError:
            raise _invalida(_VAR_NOMBRE) from None
        try:
            trato = Trato(entorno.get(_VAR_TRATO, Trato.USTED.value))
        except ValueError:
            raise _invalida(_VAR_TRATO) from None
        return cls(DatosConversacion(nombre=nombre, trato=trato))

    def datos(self, call_id: str) -> DatosConversacion | None:
        """Los datos fijos, salvo que no haya `call_id`."""
        return self._datos if call_id.strip() else None


class RegistroSinPersistencia:
    """Implementa `RegistroCheckin` sin guardar nada (Aurora, en la fase 4)."""

    def guardar_turno(self, call_id: str, turno: Turno) -> None:
        """Descarta el turno."""
        ...
