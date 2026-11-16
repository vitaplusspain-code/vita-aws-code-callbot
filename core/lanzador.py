"""Lanzador del check-in diario: a quién toca llamar ahora y cómo se llama.

Orden: leer las personas con perfil activo, consentimiento `calls` vigente y
sin check-in hoy; quedarse con las que les toca por hora y día (zona de
Madrid); descartar las que no están en la lista blanca; y, por cada una,
reservar la fila de la llamada ANTES de llamar. La reserva es atómica en el
repositorio: una segunda invocación, o un relanzamiento a mitad de lote, no
duplica llamadas. Sin reintentos: si Connect falla, la fila queda marcada como
fallida y esa persona no vuelve a llamarse hoy. Una excepción no prevista corta
el lote: las personas que quedaban se quedan sin llamada ese día (a propósito).
"""

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, time, timedelta
from typing import Protocol, runtime_checkable
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.checkin_guion import VERSION_GUION_CHECKIN
from core.errores import ErrorBaseDatos, ErrorCanal
from core.lista_blanca import ListaBlanca

__all__ = [
    "CODIGO_FALLO_INTERNO",
    "HORA_MAXIMA_CALL_TIME",
    "HORA_MINIMA_LLAMADA",
    "LIMITE_POR_INVOCACION",
    "PERMISO_LLAMADAS",
    "TOPE_DIARIO_CHECKIN",
    "VENTANA_TOLERANCIA",
    "VERSION_GUION_LLAMADA",
    "ZONA_HORARIA",
    "CanalCheckin",
    "Candidato",
    "RepositorioCheckinDiario",
    "ReservaCheckin",
    "ResumenLanzamiento",
    "ServicioCheckin",
    "toca_llamar",
]

logger = logging.getLogger(__name__)

ZONA_HORARIA = "Europe/Madrid"
_MADRID = ZoneInfo(ZONA_HORARIA)
# Desde la hora de la persona hasta este margen se la sigue considerando «ahora»
# (cubre un horario que se lanza cada pocos minutos o un retraso de la Lambda).
VENTANA_TOLERANCIA = timedelta(minutes=30)
# Franja del `call_time` del perfil (hora de Madrid), ambos límites incluidos: el
# horario de infra dispara cada 15 min de 09:00 a 20:45, así que 20:45 es el
# último disparo y con la ventana de 30 min la última llamada empieza antes de
# las 21:15. Un `call_time` fuera de la franja nunca se llama.
HORA_MINIMA_LLAMADA = time(9, 0)
HORA_MAXIMA_CALL_TIME = time(20, 45)
# Tope de check-ins reservados en un día de Madrid (freno al coste por un error).
TOPE_DIARIO_CHECKIN = 50
# Tope de llamadas por invocación (timeout de 120 s; cada una son 3 accesos).
LIMITE_POR_INVOCACION = 20
# Permiso de la persona mayor para recibir la llamada diaria.
PERMISO_LLAMADAS = "calls"
VERSION_GUION_LLAMADA = VERSION_GUION_CHECKIN
CODIGO_FALLO_INTERNO = "error_interno"


@dataclass(frozen=True)
class Candidato:
    """Persona que podría recibir la llamada; el teléfono es dato personal.

    `dias` usa la numeración ISO (1 = lunes ... 7 = domingo); `None` es todos.
    """

    person_id: str
    telefono: str = field(repr=False)
    hora: time
    dias: frozenset[int] | None = None


@dataclass(frozen=True)
class ReservaCheckin:
    """Fila de `callbot_call` que se reserva antes de llamar."""

    call_id: str
    candidato: Candidato
    version_guion: str


@dataclass(frozen=True)
class ResumenLanzamiento:
    """Qué pasó en la invocación; solo contadores, sin datos personales."""

    llamadas: int = 0
    llamadas_sin_registro: int = 0
    fallos: int = 0
    fallos_sin_registro: int = 0
    ya_reservadas: int = 0
    fuera_lista_blanca: int = 0
    pendientes: int = 0

    def como_dict(self) -> dict[str, int]:
        """Los contadores, para los logs."""
        return asdict(self)


@runtime_checkable
class RepositorioCheckinDiario(Protocol):
    """Lecturas y escrituras del lanzador en Aurora.

    Todos los métodos lanzan `ErrorBaseDatos` si Aurora falla.
    """

    def candidatos(self) -> list[Candidato]:
        """Personas con perfil activo, consentimiento `calls` y sin check-in hoy."""
        ...

    def reservar_llamada(self, reserva: ReservaCheckin) -> bool:
        """Crea la fila de la llamada; `False` si ya no procede (ya hay una hoy).

        Debe ser atómico: es lo que impide llamar dos veces el mismo día.
        """
        ...

    def registrar_contacto(self, call_id: str, contact_id: str) -> None:
        """Guarda el identificador del contacto que devolvió el canal."""
        ...

    def registrar_fallo(self, call_id: str, codigo: str) -> None:
        """Marca la llamada como fallida con el código del error."""
        ...


@runtime_checkable
class CanalCheckin(Protocol):
    """Canal que llama a la persona mayor (hoy, Amazon Connect)."""

    def iniciar_llamada_checkin(self, destino: str, call_id: str) -> str:
        """Inicia la llamada y devuelve su identificador; lanza `ErrorCanal`."""
        ...


def toca_llamar(candidato: Candidato, ahora: datetime) -> bool:
    """Indica si `ahora` cae en la ventana de llamada de la persona.

    Solo se llama a quien tiene `call_time` entre `HORA_MINIMA_LLAMADA` y
    `HORA_MAXIMA_CALL_TIME`. La ventana empieza a su hora (hora de Madrid) y
    dura `VENTANA_TOLERANCIA`, sin pasar de la medianoche. El día se mira en
    hora de Madrid.
    """
    if ahora.tzinfo is None:
        raise ValueError("`ahora` necesita zona horaria.")
    if not HORA_MINIMA_LLAMADA <= candidato.hora <= HORA_MAXIMA_CALL_TIME:
        return False
    local = ahora.astimezone(_MADRID)
    if candidato.dias is not None and local.isoweekday() not in candidato.dias:
        return False
    inicio = datetime.combine(local.date(), candidato.hora, tzinfo=_MADRID)
    return inicio <= local < inicio + VENTANA_TOLERANCIA


def _uuid_nuevo() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class ServicioCheckin:
    """Orquesta el lanzamiento contra los puertos; no sabe nada de AWS."""

    repositorio: RepositorioCheckinDiario
    canal: CanalCheckin
    lista_blanca: ListaBlanca
    nuevo_id: Callable[[], str] = _uuid_nuevo

    def lanzar(
        self, ahora: datetime, queda_tiempo: Callable[[], bool] = lambda: True
    ) -> ResumenLanzamiento:
        """Llama a quienes toca ahora, hasta el límite o hasta agotar el tiempo.

        Los `ErrorBaseDatos` de la lectura y de la reserva se propagan (sin
        Aurora no se llama a nadie). Un fallo del canal se registra y se sigue
        con la siguiente persona; un error no previsto marca la fila y se
        propaga.
        """
        debidos = sorted(
            (c for c in self.repositorio.candidatos() if toca_llamar(c, ahora)),
            key=lambda c: (c.hora, c.person_id),
        )
        permitidos = [c for c in debidos if self.lista_blanca.permite(c.telefono)]
        resumen = ResumenLanzamiento(fuera_lista_blanca=len(debidos) - len(permitidos))
        for indice, candidato in enumerate(permitidos):
            if indice >= LIMITE_POR_INVOCACION or not queda_tiempo():
                return replace(resumen, pendientes=len(permitidos) - indice)
            resumen = self._llamar(candidato, resumen)
        return resumen

    def _llamar(
        self, candidato: Candidato, resumen: ResumenLanzamiento
    ) -> ResumenLanzamiento:
        """Reserva la fila y llama; devuelve el resumen actualizado."""
        reserva = ReservaCheckin(self.nuevo_id(), candidato, VERSION_GUION_LLAMADA)
        if not self.repositorio.reservar_llamada(reserva):
            return replace(resumen, ya_reservadas=resumen.ya_reservadas + 1)
        try:
            contact_id = self.canal.iniciar_llamada_checkin(
                candidato.telefono, reserva.call_id
            )
        except ErrorCanal as error:
            registrado = self._marcar_fallo(reserva.call_id, error.codigo)
            if registrado:
                return replace(resumen, fallos=resumen.fallos + 1)
            return replace(resumen, fallos_sin_registro=resumen.fallos_sin_registro + 1)
        except Exception:
            self._marcar_fallo(reserva.call_id, CODIGO_FALLO_INTERNO)
            raise
        try:
            self.repositorio.registrar_contacto(reserva.call_id, contact_id)
        except ErrorBaseDatos:
            sin = resumen.llamadas_sin_registro + 1
            return replace(resumen, llamadas_sin_registro=sin)
        return replace(resumen, llamadas=resumen.llamadas + 1)

    def _marcar_fallo(self, call_id: str, codigo: str) -> bool:
        """Marca la reserva como fallida; `False` si Aurora no lo guardó."""
        try:
            self.repositorio.registrar_fallo(call_id, codigo)
        except ErrorBaseDatos:
            logger.warning("checkin_fallo_sin_registrar")
            return False
        return True
