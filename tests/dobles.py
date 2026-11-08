"""Dobles en memoria de los puertos del aviso (sin AWS)."""

from dataclasses import dataclass, field

from core.alerta import Alerta
from core.destinatario import Destinatario
from core.errores import ErrorCallbot
from core.mensaje import MensajeAviso
from core.puertos import Reserva


@dataclass
class RepositorioFalso:
    """Implementa `RepositorioAvisos` con datos fijos y apunta lo que recibe."""

    alertas: dict[str, Alerta] = field(default_factory=dict)
    consentimientos: set[tuple[str, str]] = field(default_factory=set)
    contactos: dict[str, Destinatario] = field(default_factory=dict)
    recibidas: list[str] = field(default_factory=list)
    reservas: list[Reserva] = field(default_factory=list)
    contactos_registrados: list[tuple[str, str]] = field(default_factory=list)
    fallos: list[tuple[str, str]] = field(default_factory=list)
    fallar_al_registrar_contacto: ErrorCallbot | None = None
    fallar_al_registrar_fallo: ErrorCallbot | None = None

    def registrar_recepcion(self, alert_id: str) -> None:
        self.recibidas.append(alert_id)

    def alerta_abierta(self, alert_id: str) -> Alerta | None:
        return self.alertas.get(alert_id)

    def tiene_consentimiento(self, person_id: str, permiso: str) -> bool:
        return (person_id, permiso) in self.consentimientos

    def contacto_principal(self, person_id: str) -> Destinatario | None:
        return self.contactos.get(person_id)

    def reservar_llamada(self, reserva: Reserva) -> bool:
        clave = (reserva.alerta.alert_id, reserva.destinatario.contacto_id)
        ya = any(
            (r.alerta.alert_id, r.destinatario.contacto_id) == clave
            for r in self.reservas
        )
        if ya:
            return False
        self.reservas.append(reserva)
        return True

    def registrar_contacto(self, call_id: str, contact_id: str) -> None:
        if self.fallar_al_registrar_contacto is not None:
            raise self.fallar_al_registrar_contacto
        self.contactos_registrados.append((call_id, contact_id))

    def registrar_fallo(self, call_id: str, codigo: str) -> None:
        self.fallos.append((call_id, codigo))
        if self.fallar_al_registrar_fallo is not None:
            raise self.fallar_al_registrar_fallo


@dataclass
class CanalFalso:
    """Implementa `CanalAviso`: devuelve un id fijo o lanza el error indicado."""

    contact_id: str = "contacto-1"
    error: Exception | None = None
    llamadas: list[tuple[str, MensajeAviso]] = field(default_factory=list)

    def iniciar_llamada(self, destino: str, mensaje: MensajeAviso) -> str:
        self.llamadas.append((destino, mensaje))
        if self.error is not None:
            raise self.error
        return self.contact_id
