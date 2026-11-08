"""Servicio del hito 1: de un `alert_id` a una llamada al familiar.

Orden (decisiones 28-30, 35-37): registrar la recepción, leer la alerta
abierta, filtrar por antigüedad y gravedad, exigir consentimiento, buscar el
contacto principal, aplicar la lista blanca, reservar la fila de la llamada y,
solo entonces, llamar. Sin reintentos: si el canal falla, la reserva queda
marcada como fallida y esa alerta no vuelve a llamar.

Riesgos aceptados para el MVP: entre leer la alerta y llamar pasan segundos en
los que la alerta podría cerrarse o el consentimiento retirarse; y si el
proceso muere entre reservar y llamar, la fila queda reservada sin
`connect_contact_id` ni resultado (hay que vigilarlas con una consulta o alarma).
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from core.alerta import Alerta, ReglasAviso, es_grave, es_reciente
from core.destinatario import Destinatario
from core.errores import AvisoInvalido, ErrorBaseDatos, ErrorCanal
from core.lista_blanca import ListaBlanca
from core.mensaje import construir_mensaje_aviso
from core.motivos import VERSION_GUION
from core.puertos import CanalAviso, RepositorioAvisos, Reserva
from core.tipos import Uuid

__all__ = [
    "CODIGO_FALLO_INTERNO",
    "PERMISO_AVISOS",
    "Desenlace",
    "Resultado",
    "ServicioAviso",
]

# Permiso de la persona mayor para avisar a su familia por llamada (decisión 36).
PERMISO_AVISOS = "alert_calls"

# Código que se guarda en `callbot_call.error_code` ante un fallo no previsto.
CODIGO_FALLO_INTERNO = "error_interno"

_UUID = TypeAdapter(Uuid)


class Resultado(StrEnum):
    """Qué pasó con el aviso; va a los logs, nunca a la respuesta."""

    LLAMADA = "llamada"
    LLAMADA_SIN_REGISTRO = "llamada_sin_registro"
    NO_ABIERTA = "no_abierta"
    ANTIGUA = "antigua"
    NO_GRAVE = "no_grave"
    SIN_CONSENTIMIENTO = "sin_consentimiento"
    SIN_CONTACTO = "sin_contacto"
    FUERA_LISTA_BLANCA = "fuera_lista_blanca"
    YA_AVISADA = "ya_avisada"
    FALLO_CANAL = "fallo_canal"
    FALLO_CANAL_SIN_REGISTRO = "fallo_canal_sin_registro"


@dataclass(frozen=True)
class Desenlace:
    """Resultado del aviso con el contacto o el código de error, si los hay."""

    resultado: Resultado
    contact_id: str | None = None
    codigo_error: str | None = None


def _uuid_nuevo() -> str:
    return str(uuid4())


def _validar_alert_id(valor: object) -> str:
    """Devuelve el UUID en minúsculas o lanza `AvisoInvalido` sin reflejarlo."""
    try:
        return _UUID.validate_python(valor)
    except ValidationError:
        mensaje = "El aviso no es válido (campos: alert_id)."
    raise AvisoInvalido(mensaje)


@dataclass(frozen=True)
class ServicioAviso:
    """Orquesta el aviso contra los puertos; no sabe nada de AWS."""

    repositorio: RepositorioAvisos
    canal: CanalAviso
    lista_blanca: ListaBlanca
    reglas: ReglasAviso
    nuevo_id: Callable[[], str] = _uuid_nuevo

    def avisar(self, alert_id: str) -> Desenlace:
        """Decide si se llama por la alerta y, si toca, llama una sola vez.

        Lanza `AvisoInvalido` si `alert_id` no es un UUID, sin tocar la base de
        datos. Los `ErrorBaseDatos` anteriores a la llamada se propagan, también
        el de la auditoría: sin registro de recepción no se llama.
        """
        alert_id = _validar_alert_id(alert_id)
        self.repositorio.registrar_recepcion(alert_id)
        alerta = self.repositorio.alerta_abierta(alert_id)
        if alerta is None:
            return Desenlace(Resultado.NO_ABIERTA)
        descarte = self._descarte(alerta)
        if descarte is not None:
            return Desenlace(descarte)
        destinatario = self.repositorio.contacto_principal(alerta.person_id)
        if destinatario is None:
            return Desenlace(Resultado.SIN_CONTACTO)
        if not self.lista_blanca.permite(destinatario.telefono):
            return Desenlace(Resultado.FUERA_LISTA_BLANCA)
        return self._llamar(alerta, destinatario)

    def _descarte(self, alerta: Alerta) -> Resultado | None:
        """Motivo para no avisar de la alerta, o `None` si hay que avisar."""
        if not es_reciente(alerta, self.reglas):
            return Resultado.ANTIGUA
        if not es_grave(alerta, self.reglas):
            return Resultado.NO_GRAVE
        if not self.repositorio.tiene_consentimiento(alerta.person_id, PERMISO_AVISOS):
            return Resultado.SIN_CONSENTIMIENTO
        return None

    def _llamar(self, alerta: Alerta, destinatario: Destinatario) -> Desenlace:
        """Reserva la fila y llama; cualquier fallo del canal queda registrado.

        El mensaje se construye antes de reservar: si falla, no se gasta la
        reserva. Un error no previsto marca la fila y se propaga.
        """
        mensaje = construir_mensaje_aviso(
            alerta.rule_id, alerta.persona_nombre, destinatario.nombre
        )
        reserva = Reserva(self.nuevo_id(), alerta, destinatario, VERSION_GUION)
        if not self.repositorio.reservar_llamada(reserva):
            return Desenlace(Resultado.YA_AVISADA)
        try:
            contact_id = self.canal.iniciar_llamada(destinatario.telefono, mensaje)
        except ErrorCanal as error:
            registrado = self._marcar_fallo(reserva.call_id, error.codigo)
            resultado = (
                Resultado.FALLO_CANAL
                if registrado
                else Resultado.FALLO_CANAL_SIN_REGISTRO
            )
            return Desenlace(resultado, codigo_error=error.codigo)
        except Exception:
            self._marcar_fallo(reserva.call_id, CODIGO_FALLO_INTERNO)
            raise
        return self._registrar_contacto(reserva.call_id, contact_id)

    def _marcar_fallo(self, call_id: str, codigo: str) -> bool:
        """Marca la reserva como fallida; `False` si Aurora no lo guardó."""
        try:
            self.repositorio.registrar_fallo(call_id, codigo)
        except ErrorBaseDatos:
            return False
        return True

    def _registrar_contacto(self, call_id: str, contact_id: str) -> Desenlace:
        """Guarda el contacto; si Aurora falla, la llamada ya está en marcha."""
        try:
            self.repositorio.registrar_contacto(call_id, contact_id)
        except ErrorBaseDatos:
            return Desenlace(Resultado.LLAMADA_SIN_REGISTRO, contact_id=contact_id)
        return Desenlace(Resultado.LLAMADA, contact_id=contact_id)
