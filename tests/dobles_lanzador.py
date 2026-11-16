"""Dobles en memoria de los puertos del lanzador del check-in (sin AWS)."""

from dataclasses import dataclass, field

from core.lanzador import Candidato, ReservaCheckin


@dataclass
class RepositorioDiarioFalso:
    """Implementa `RepositorioCheckinDiario`; reservar es idempotente por persona."""

    candidatos_hoy: list[Candidato] = field(default_factory=list)
    reservas: list[ReservaCheckin] = field(default_factory=list)
    contactos: list[tuple[str, str]] = field(default_factory=list)
    fallos: list[tuple[str, str]] = field(default_factory=list)
    # Simula que otra invocación reservó entre la lectura y la reserva.
    ignorar_reservas_al_leer: bool = False
    error_al_leer: Exception | None = None
    error_al_reservar: Exception | None = None
    error_al_registrar_contacto: Exception | None = None
    error_al_registrar_fallo: Exception | None = None

    def candidatos(self) -> list[Candidato]:
        if self.error_al_leer is not None:
            raise self.error_al_leer
        if self.ignorar_reservas_al_leer:
            return list(self.candidatos_hoy)
        return [c for c in self.candidatos_hoy if not self._reservada(c.person_id)]

    def reservar_llamada(self, reserva: ReservaCheckin) -> bool:
        if self.error_al_reservar is not None:
            raise self.error_al_reservar
        if self._reservada(reserva.candidato.person_id):
            return False
        self.reservas.append(reserva)
        return True

    def registrar_contacto(self, call_id: str, contact_id: str) -> None:
        if self.error_al_registrar_contacto is not None:
            raise self.error_al_registrar_contacto
        self.contactos.append((call_id, contact_id))

    def registrar_fallo(self, call_id: str, codigo: str) -> None:
        self.fallos.append((call_id, codigo))
        if self.error_al_registrar_fallo is not None:
            raise self.error_al_registrar_fallo

    def _reservada(self, person_id: str) -> bool:
        return any(r.candidato.person_id == person_id for r in self.reservas)


@dataclass
class CanalCheckinFalso:
    """Implementa `CanalCheckin`: ids correlativos o el error indicado.

    Con `fallar_la_primera`, solo la primera llamada lanza el error.
    """

    error: Exception | None = None
    fallar_la_primera: bool = False
    llamadas: list[tuple[str, str]] = field(default_factory=list)

    def iniciar_llamada_checkin(self, destino: str, call_id: str) -> str:
        self.llamadas.append((destino, call_id))
        if self.error is not None and (
            not self.fallar_la_primera or len(self.llamadas) == 1
        ):
            raise self.error
        return f"contacto-{len(self.llamadas)}"
