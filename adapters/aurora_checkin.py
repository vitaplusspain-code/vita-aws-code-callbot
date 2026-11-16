"""Adaptador de Aurora de la conversación diaria (check-in).

Lee con quién es la llamada y guarda cada turno por la Data API. Solo usa lo
que el usuario `callbot` puede leer y escribir (ver
`propuesta-vistas-y-permisos.sql`). Todo SQL va parametrizado y filtra por
`purpose = 'checkin'`, `ended_at IS NULL` y `connect_contact_id`: el `call_id`
llega de un atributo de sesión que no es de confianza, así que solo vale junto
al contacto del canal. En los logs no va nunca ni el turno ni el nombre.
"""

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from adapters.aurora import (
    ESQUEMA,
    ClienteDataApi,
    param_texto,
    param_texto_o_nulo,
    param_uuid,
    validar,
)
from core.checkin import Observacion, Turno
from core.checkin_guion import VERSION_GUION_CHECKIN, Trato
from core.errores import DatosInvalidos, ErrorBaseDatos
from core.puertos_checkin import DatosConversacion
from core.riesgo import SenalRiesgo, TipoRiesgo
from core.tipos import PATRON_UUID, NombrePersona

__all__ = ["ACCION_MENSAJE_112", "AuroraCheckin"]

logger = logging.getLogger(__name__)

# Lo que hizo el callbot ante la señal de riesgo: dio el mensaje del 112.
ACCION_MENSAJE_112 = "emergency_message"

_UUID = re.compile(PATRON_UUID)
_UNA_FILA = 1
# Una escritura idempotente toca 0 filas (ya estaba) o 1 (se guardó).
_NINGUNA_O_UNA = (0, _UNA_FILA)
_MENSAJE_LLAMADA = "La llamada no es una conversación activa."
_MENSAJE_RESPUESTA = "Respuesta inesperada de la base de datos."
_MENSAJE_CALL_ID = "El identificador de llamada no es válido."
_MENSAJE_CONTACTO = "El identificador de contacto no es válido."

# Una llamada de check-in sin terminar y del contacto del canal. Una sola
# definición: sin alias (UPDATE) y con alias `c.` (SELECT e INSERT ... SELECT).
_ACTIVA_PLANTILLA = (
    "{a}purpose = 'checkin' AND {a}ended_at IS NULL "
    "AND {a}connect_contact_id = :contacto_id"
)
_ACTIVA = _ACTIVA_PLANTILLA.format(a="")
_ACTIVA_C = _ACTIVA_PLANTILLA.format(a="c.")

SQL_DATOS = (
    "SELECT p.given_name AS nombre, cp.address_form AS trato "
    f"FROM {ESQUEMA}.callbot_call c "
    f"JOIN {ESQUEMA}.callbot_person p ON p.id = c.person_id "
    f"JOIN {ESQUEMA}.callbot_profile cp ON cp.person_id = p.id "
    f"WHERE c.id = :call_id AND {_ACTIVA_C}"
)
# Crea la ficha o, si ya existe, toca `updated_at`: 1 fila = llamada activa.
SQL_FICHA = (
    f"INSERT INTO {ESQUEMA}.callbot_checkin (call_id, person_id) "
    "SELECT c.id, c.person_id "
    f"FROM {ESQUEMA}.callbot_call c "
    f"WHERE c.id = :call_id AND {_ACTIVA_C} "
    "ON CONFLICT (call_id) DO UPDATE SET updated_at = now()"
)
# Una observación por indicador y llamada: reintentar el turno no duplica.
SQL_OBSERVACION = (
    f"INSERT INTO {ESQUEMA}.callbot_observation (person_id, indicator_code, "
    "observed_at, value_code, value_text, verbatim, source, question_version, "
    "call_id) "
    "SELECT c.person_id, :indicator_code, now(), CAST(:value_code AS text), "
    "CAST(:value_text AS text), :verbatim, 'self_reported', :question_version, "
    "c.id "
    f"FROM {ESQUEMA}.callbot_call c "
    f"WHERE c.id = :call_id AND {_ACTIVA_C} "
    "AND NOT EXISTS (SELECT 1 "
    f"FROM {ESQUEMA}.callbot_observation o "
    "WHERE o.call_id = c.id AND o.indicator_code = :indicator_code)"
)
# Una señal por tipo y llamada.
SQL_RIESGO = (
    f"INSERT INTO {ESQUEMA}.callbot_risk_signal (call_id, person_id, kind, "
    "verbatim, action_taken) "
    "SELECT c.id, c.person_id, :kind, :verbatim, :action_taken "
    f"FROM {ESQUEMA}.callbot_call c "
    f"WHERE c.id = :call_id AND {_ACTIVA_C} "
    "AND NOT EXISTS (SELECT 1 "
    f"FROM {ESQUEMA}.callbot_risk_signal r "
    "WHERE r.call_id = c.id AND r.kind = :kind)"
)
SQL_CONTESTADA = (
    f"UPDATE {ESQUEMA}.callbot_call SET answered_at = COALESCE(answered_at, now()) "
    f"WHERE id = :call_id AND {_ACTIVA}"
)
SQL_CERRAR = (
    f"UPDATE {ESQUEMA}.callbot_call SET answered_at = COALESCE(answered_at, now()), "
    f"ended_at = now(), outcome = 'answered' WHERE id = :call_id AND {_ACTIVA}"
)


class _FilaContexto(BaseModel):
    """Fila de `SQL_DATOS`: el nombre es dato personal, no se refleja en errores."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    nombre: NombrePersona
    trato: Trato


def _parametros(call_id: str, contacto_id: str) -> list[dict[str, Any]]:
    """Parámetros que identifican la llamada y su contacto."""
    return [param_uuid("call_id", call_id), param_texto("contacto_id", contacto_id)]


class AuroraCheckin(ClienteDataApi):
    """Contexto y registro de la conversación en Aurora.

    Implementa `ContextoConversacion` y `RegistroCheckin`. Toda sentencia exige
    que `contacto_id` sea el `connect_contact_id` de la llamada: un `call_id`
    ajeno no sirve sin el contacto, que no controla quien habla.
    """

    def datos(self, call_id: str, contacto_id: str) -> DatosConversacion | None:
        """Nombre y trato si `call_id` es un check-in activo de ese contacto."""
        if not (_UUID.fullmatch(call_id) and _UUID.fullmatch(contacto_id)):
            return None
        filas = self._leer(SQL_DATOS, _parametros(call_id, contacto_id))
        if not filas:
            return None
        if len(filas) > 1:
            raise DatosInvalidos(_MENSAJE_RESPUESTA)
        fila = validar(_FilaContexto, filas[0])
        return DatosConversacion(nombre=fila.nombre, trato=fila.trato)

    def guardar_turno(self, call_id: str, contacto_id: str, turno: Turno) -> None:
        """Guarda ficha, riesgo, observaciones y cierre, en ese orden.

        El riesgo va justo tras la ficha: si algo falla después, ya está
        guardado. Cada sentencia se puede repetir sin duplicar nada; no hay
        transacción. Si la llamada no es un check-in activo de ese contacto no
        se guarda nada y se lanza `ErrorBaseDatos`.
        """
        if not _UUID.fullmatch(call_id):
            raise DatosInvalidos(_MENSAJE_CALL_ID)
        if not _UUID.fullmatch(contacto_id):
            raise DatosInvalidos(_MENSAJE_CONTACTO)
        parametros = _parametros(call_id, contacto_id)
        self._asegurar_ficha(parametros)
        senal = turno.senal_riesgo
        if senal is not None:
            self._guardar_riesgo(parametros, senal)
        sin_frase = senal is not None and senal.kind is TipoRiesgo.SELF_HARM
        for observacion in turno.observaciones:
            self._guardar_observacion(parametros, observacion, sin_frase)
        sql = SQL_CERRAR if turno.terminado else SQL_CONTESTADA
        self._exigir_filas(sql, parametros, _UNA_FILA)

    def _asegurar_ficha(self, parametros: list[dict[str, Any]]) -> None:
        """Crea o toca la ficha; 0 filas es que la llamada no está activa."""
        filas = self._escribir(SQL_FICHA, parametros)
        if filas == 0:
            logger.warning("checkin_llamada_no_activa")
            raise ErrorBaseDatos(_MENSAJE_LLAMADA)
        if filas != _UNA_FILA:
            raise ErrorBaseDatos(_MENSAJE_RESPUESTA)

    def _guardar_observacion(
        self, llamada: list[dict[str, Any]], obs: Observacion, sin_frase: bool
    ) -> None:
        """Inserta una observación; sin la frase si el turno tiene autolesión."""
        parametros = [
            *llamada,
            param_texto("indicator_code", obs.indicator_code),
            param_texto_o_nulo("value_code", obs.value_code),
            param_texto_o_nulo("value_text", obs.value_text),
            param_texto("verbatim", "" if sin_frase else obs.verbatim),
            param_texto("question_version", VERSION_GUION_CHECKIN),
        ]
        self._exigir_filas(SQL_OBSERVACION, parametros, *_NINGUNA_O_UNA)

    def _guardar_riesgo(
        self, llamada: list[dict[str, Any]], senal: SenalRiesgo
    ) -> None:
        """Inserta la señal de riesgo; la autolesión, solo por tipo."""
        frase = "" if senal.kind is TipoRiesgo.SELF_HARM else senal.verbatim
        parametros = [
            *llamada,
            param_texto("kind", senal.kind.value),
            param_texto("verbatim", frase),
            param_texto("action_taken", ACCION_MENSAJE_112),
        ]
        self._exigir_filas(SQL_RIESGO, parametros, *_NINGUNA_O_UNA)

    def _exigir_filas(
        self, sql: str, parametros: list[dict[str, Any]], *admitidas: int
    ) -> None:
        """Ejecuta la escritura y exige que toque un número admitido de filas."""
        if self._escribir(sql, parametros) not in admitidas:
            raise ErrorBaseDatos(_MENSAJE_RESPUESTA)
