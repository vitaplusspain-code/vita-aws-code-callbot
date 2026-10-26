"""Persona cuidada, su familiar de contacto y el puerto de acceso a ellos."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from core.telefono import TelefonoE164
from core.tipos import NombrePersona, PersonaId


class Familiar(BaseModel):
    """Familiar al que se llama."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    nombre: NombrePersona = Field(repr=False)
    telefono: TelefonoE164 = Field(repr=False)


class Persona(BaseModel):
    """Persona cuidada y su familiar de contacto."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    persona_id: PersonaId
    nombre: NombrePersona = Field(repr=False)
    familiar: Familiar


@runtime_checkable
class PersonaRepository(Protocol):
    """Puerto de acceso a personas; lo implementa un adaptador."""

    def obtener(self, persona_id: str) -> Persona:
        """Devuelve la persona o lanza `PersonaNoEncontrada`."""
        ...
