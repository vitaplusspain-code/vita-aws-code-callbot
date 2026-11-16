"""Adaptador de Aurora del lanzador del check-in diario.

Lee a quién puede tocarle la llamada y reserva la fila de `callbot_call` por la
Data API. Solo usa lo que el usuario `callbot` puede leer y escribir (ver
`propuesta-vistas-y-permisos.sql`): SELECT en perfil, consentimiento y llamadas,
INSERT en llamadas y UPDATE de `connect_contact_id`, `outcome`, `error_code` y
`ended_at`. Todo SQL va parametrizado. En los logs no va nunca un teléfono.
"""

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from adapters.aurora import (
    ESQUEMA,
    SQL_REGISTRAR_CONTACTO,
    SQL_REGISTRAR_FALLO,
    ClienteDataApi,
    ErrorUnicidad,
    param_texto,
    param_uuid,
    validar,
)
from core.errores import ErrorBaseDatos
from core.lanzador import (
    HORA_MAXIMA_CALL_TIME,
    HORA_MINIMA_LLAMADA,
    PERMISO_LLAMADAS,
    TOPE_DIARIO_CHECKIN,
    ZONA_HORARIA,
    Candidato,
    ReservaCheckin,
)
from core.telefono import TelefonoE164
from core.tipos import Uuid

__all__ = [
    "INDICE_CHECKIN_DIA",
    "SQL_BAJO_TOPE",
    "SQL_CANDIDATOS",
    "SQL_EN_FRANJA",
    "SQL_RESERVAR_CHECKIN",
    "AuroraLanzador",
]

_UNA_FILA = 1
_NINGUNA_FILA = 0
_MENSAJE_RESPUESTA = "Respuesta inesperada de la base de datos."
_DIA_MINIMO, _DIA_MAXIMO = 1, 7

# Índice único parcial (persona, día de Madrid) del check-in: ver `0012_callbot_v1`.
INDICE_CHECKIN_DIA = "callbot_call_checkin_dia_uq"

# Último consentimiento `calls` concedido (con dos filas en el mismo instante,
# gana la revocación, como en `SQL_CONSENTIMIENTO`).
_CONSENTIMIENTO_VIGENTE = (
    "(SELECT k.granted "
    f"FROM {ESQUEMA}.callbot_consent k "
    f"WHERE k.person_id = cp.person_id AND k.scope = '{PERMISO_LLAMADAS}' "
    "ORDER BY k.recorded_at DESC, k.granted ASC LIMIT 1) IS TRUE"
)
# Ya hay un check-in hoy (en cualquier estado: en curso, hecho o fallido).
_SIN_CHECKIN_HOY = (
    "NOT EXISTS (SELECT 1 "
    f"FROM {ESQUEMA}.callbot_call c "
    "WHERE c.person_id = cp.person_id AND c.purpose = 'checkin' "
    f"AND CAST(c.requested_at AT TIME ZONE '{ZONA_HORARIA}' AS date) = "
    f"CAST(now() AT TIME ZONE '{ZONA_HORARIA}' AS date))"
)
_PERFIL_LLAMABLE = f"cp.active AND {_CONSENTIMIENTO_VIGENTE} AND {_SIN_CHECKIN_HOY}"
# Franja permitida del `call_time` del perfil (límites incluidos).
SQL_EN_FRANJA = (
    f"(cp.call_time >= TIME '{HORA_MINIMA_LLAMADA:%H:%M}' "
    f"AND cp.call_time <= TIME '{HORA_MAXIMA_CALL_TIME:%H:%M}')"
)
# Tope de check-ins reservados hoy (cualquier estado): freno al coste.
SQL_BAJO_TOPE = (
    "((SELECT count(*) "
    f"FROM {ESQUEMA}.callbot_call t "
    "WHERE t.purpose = 'checkin' "
    f"AND CAST(t.requested_at AT TIME ZONE '{ZONA_HORARIA}' AS date) = "
    f"CAST(now() AT TIME ZONE '{ZONA_HORARIA}' AS date)) < {TOPE_DIARIO_CHECKIN})"
)

SQL_CANDIDATOS = (
    "SELECT cp.person_id AS person_id, cp.mobile_e164 AS telefono, "
    "to_char(cp.call_time, 'HH24:MI') AS hora, "
    "array_to_string(cp.call_days, ',') AS dias "
    f"FROM {ESQUEMA}.callbot_profile cp "
    f"WHERE cp.call_time IS NOT NULL AND {_PERFIL_LLAMABLE} "
    "ORDER BY cp.call_time, cp.person_id"
)
# Una sola sentencia: comprueba otra vez franja, tope diario, perfil,
# consentimiento y «sin check-in hoy» y crea la fila. 0 filas = ya no procede.
# Dos reservas simultáneas las frena el índice único (`INDICE_CHECKIN_DIA`).
# El teléfono de la lectura debe seguir siendo el del perfil.
SQL_RESERVAR_CHECKIN = (
    f"INSERT INTO {ESQUEMA}.callbot_call (id, purpose, person_id, phone_e164, "
    "phone_kind, script_version) "
    "SELECT CAST(:call_id AS uuid), 'checkin', cp.person_id, cp.mobile_e164, "
    "'mobile', :script_version "
    f"FROM {ESQUEMA}.callbot_profile cp "
    "WHERE cp.person_id = :person_id AND cp.mobile_e164 = :phone "
    f"AND {SQL_EN_FRANJA} AND {SQL_BAJO_TOPE} AND {_PERFIL_LLAMABLE}"
)


class _FilaCandidato(BaseModel):
    """Fila de `SQL_CANDIDATOS`; el teléfono no se refleja en los errores."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    person_id: Uuid
    telefono: TelefonoE164 = Field(repr=False)
    hora: time
    dias: StrictStr | None = None

    @field_validator("dias")
    @classmethod
    def _dias_validos(cls, valor: str | None) -> str | None:
        """Lista de días ISO separados por comas (puede ser vacía)."""
        if valor is None or valor == "":
            return valor
        partes = valor.split(",")
        if not all(
            p.isdigit() and _DIA_MINIMO <= int(p) <= _DIA_MAXIMO for p in partes
        ):
            raise ValueError("días no válidos")
        return valor

    def a_candidato(self) -> Candidato:
        """Convierte la fila en el candidato del dominio."""
        dias = None
        if self.dias is not None:
            dias = frozenset(int(d) for d in self.dias.split(",") if d)
        return Candidato(self.person_id, self.telefono, self.hora, dias)


class AuroraLanzador(ClienteDataApi):
    """Lee candidatos y reserva llamadas (implementa `RepositorioCheckinDiario`)."""

    def candidatos(self) -> list[Candidato]:
        """Personas con perfil activo, consentimiento `calls` y sin check-in hoy."""
        filas = self._leer(SQL_CANDIDATOS, [])
        return [validar(_FilaCandidato, f).a_candidato() for f in filas]

    def reservar_llamada(self, reserva: ReservaCheckin) -> bool:
        """Crea la fila de la llamada; `False` si ya hay una hoy o ya no procede."""
        candidato = reserva.candidato
        parametros = [
            param_uuid("call_id", reserva.call_id),
            param_uuid("person_id", candidato.person_id),
            param_texto("phone", candidato.telefono),
            param_texto("script_version", reserva.version_guion),
        ]
        try:
            escritas = self._escribir(SQL_RESERVAR_CHECKIN, parametros)
        except ErrorUnicidad as error:
            if error.restriccion == INDICE_CHECKIN_DIA:
                return False  # otra invocación reservó a la vez
            raise
        if escritas not in (_NINGUNA_FILA, _UNA_FILA):
            raise ErrorBaseDatos(_MENSAJE_RESPUESTA)
        return escritas == _UNA_FILA

    def registrar_contacto(self, call_id: str, contact_id: str) -> None:
        """Guarda el `ContactId` que devolvió Connect (lo usa la conversación)."""
        parametros = [
            param_texto("contact_id", contact_id),
            param_uuid("call_id", call_id),
        ]
        self._exigir_una_fila(SQL_REGISTRAR_CONTACTO, parametros)

    def registrar_fallo(self, call_id: str, codigo: str) -> None:
        """Marca la llamada como fallida con el código del error."""
        parametros = [param_texto("codigo", codigo), param_uuid("call_id", call_id)]
        self._exigir_una_fila(SQL_REGISTRAR_FALLO, parametros)
