"""Familiar al que se llama para avisar de una alerta."""

from pydantic import BaseModel, ConfigDict, Field

from core.telefono import TelefonoE164
from core.tipos import NombrePersona, Uuid

__all__ = ["Destinatario"]


class Destinatario(BaseModel):
    """Contacto de aviso (`callbot_alert_contact`) con su nombre visible."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    contacto_id: Uuid
    nombre: NombrePersona = Field(repr=False)
    telefono: TelefonoE164 = Field(repr=False)
