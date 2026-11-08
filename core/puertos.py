"""Puertos del aviso: lo que el dominio necesita de Aurora y del canal de llamada."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.alerta import Alerta
from core.destinatario import Destinatario
from core.mensaje import MensajeAviso

__all__ = ["CanalAviso", "RepositorioAvisos", "Reserva"]


@dataclass(frozen=True)
class Reserva:
    """Fila de `callbot_call` que se reserva antes de llamar."""

    call_id: str
    alerta: Alerta
    destinatario: Destinatario
    version_guion: str


@runtime_checkable
class RepositorioAvisos(Protocol):
    """Lecturas y escrituras del aviso en Aurora; lo implementa un adaptador.

    Todos los métodos lanzan `ErrorBaseDatos` si Aurora falla.
    """

    def registrar_recepcion(self, alert_id: str) -> None:
        """Apunta en `audit_log` que ha llegado un aviso de esa alerta."""
        ...

    def alerta_abierta(self, alert_id: str) -> Alerta | None:
        """Devuelve la alerta si está abierta y su persona está en el callbot."""
        ...

    def tiene_consentimiento(self, person_id: str, permiso: str) -> bool:
        """Indica si el último consentimiento de ese permiso está concedido."""
        ...

    def contacto_principal(self, person_id: str) -> Destinatario | None:
        """Devuelve el contacto de aviso de prioridad 1, si recibe avisos."""
        ...

    def reservar_llamada(self, reserva: Reserva) -> bool:
        """Crea la fila de la llamada; `False` si ya existía.

        Debe ser atómico (`INSERT … ON CONFLICT DO NOTHING`). La clave única es
        `(alert_id, alert_contact_id, attempt)`; el MVP siempre usa el intento 1
        y un solo contacto (prioridad 1), así que equivale a una por alerta.
        """
        ...

    def registrar_contacto(self, call_id: str, contact_id: str) -> None:
        """Guarda el identificador del contacto que devolvió el canal."""
        ...

    def registrar_fallo(self, call_id: str, codigo: str) -> None:
        """Marca la llamada como fallida con el código del error."""
        ...


@runtime_checkable
class CanalAviso(Protocol):
    """Canal que hace llegar el aviso al familiar (hoy, Amazon Connect)."""

    def iniciar_llamada(self, destino: str, mensaje: MensajeAviso) -> str:
        """Inicia la llamada y devuelve su identificador; lanza `ErrorCanal`."""
        ...
