"""Adaptador de Aurora: lee y escribe el aviso por la Data API de RDS."""

import json
import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping
from typing import Any, NoReturn, Protocol, Self

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from core.alerta import Alerta
from core.destinatario import Destinatario
from core.errores import DatosInvalidos, ErrorBaseDatos, ErrorConfiguracion
from core.puertos import Reserva

__all__ = [
    "CODIGOS_AWS_CONOCIDOS",
    "CONFIG_AURORA",
    "ESPERAS_REANUDACION",
    "ESQUEMA",
    "VARIABLES_AURORA",
    "VAR_BASE",
    "VAR_CLUSTER",
    "VAR_SECRETO",
    "AuroraAdapter",
    "ClienteDataApi",
    "ErrorUnicidad",
    "param_texto",
    "param_texto_o_nulo",
    "param_uuid",
    "validar",
]

logger = logging.getLogger(__name__)

REGION_AURORA = "eu-west-1"
SEGUNDOS_CONEXION = 3
SEGUNDOS_LECTURA = 10
# `total_max_attempts` cuenta el intento inicial: 1 significa sin reintentos.
CONFIG_AURORA = Config(
    region_name=REGION_AURORA,
    connect_timeout=SEGUNDOS_CONEXION,
    read_timeout=SEGUNDOS_LECTURA,
    retries={"total_max_attempts": 1, "mode": "standard"},
)

# Aurora se pausa sola cuando no se usa y la Data API responde
# `DatabaseResumingException` mientras despierta (unos 15 s según AWS). Se
# reintenta solo ese error, esperando cada vez más y sin pasar de un plazo total
# medido con reloj (los intentos también tardan), para que el aviso quepa en los
# 29 s de API Gateway. Tras más de 24 h en pausa AWS habla de 30 s o más: ese
# caso no se cubre (ver `afinado-post-mvp.md`).
CODIGO_REANUDANDO = "DatabaseResumingException"
ESPERAS_REANUDACION = (2.0, 4.0, 6.0, 8.0)
PLAZO_REANUDACION_S = 20.0

# Errores de la Data API (más los genéricos de acceso). Solo estos códigos se
# registran; cualquier otro se anota como `None`.
CODIGOS_AWS_CONOCIDOS = (
    "BadRequestException",
    "ForbiddenException",
    "InternalServerErrorException",
    "ServiceUnavailableError",
    "StatementTimeoutException",
    "DatabaseErrorException",
    "DatabaseNotFoundException",
    "DatabaseUnavailableException",
    "DatabaseResumingException",
    "HttpEndpointNotEnabledException",
    "SecretsErrorException",
    "InvalidSecretException",
    "AccessDeniedException",
    "ThrottlingException",
)

# Único sitio donde se fija el esquema; los SQL de abajo se montan una vez al
# importar el módulo, nunca con datos de entrada (esos van como parámetros).
ESQUEMA = "public"

SQL_REGISTRAR_RECEPCION = (
    f"INSERT INTO {ESQUEMA}.audit_log (action, detail) "
    "VALUES ('callbot.alert_received', jsonb_build_object('alert_id', :alert_id))"
)
SQL_ALERTA_ABIERTA = (
    "SELECT a.id AS alert_id, a.person_id, a.rule_id, a.severity, "
    "floor(extract(epoch from now() - a.opened_at))::int AS antiguedad_segundos, "
    "p.given_name AS persona_nombre "
    f"FROM {ESQUEMA}.callbot_open_alert a "
    f"JOIN {ESQUEMA}.callbot_person p ON p.id = a.person_id "
    "WHERE a.id = :alert_id"
)
SQL_CONSENTIMIENTO = (
    f"SELECT granted FROM {ESQUEMA}.callbot_consent "
    "WHERE person_id = :person_id AND scope = :scope "
    # Con dos filas en el mismo instante (misma transacción), gana la revocación.
    "ORDER BY recorded_at DESC, granted ASC LIMIT 1"
)
SQL_CONTACTO_PRINCIPAL = (
    "SELECT ac.id AS contacto_id, c.display_name AS nombre, "
    "ac.phone_e164 AS telefono "
    f"FROM {ESQUEMA}.callbot_alert_contact ac "
    f"JOIN {ESQUEMA}.callbot_contact c "
    "ON c.account_id = ac.account_id AND c.person_id = ac.person_id "
    "WHERE ac.person_id = :person_id AND ac.priority = 1 AND ac.receives_alerts"
)
SQL_RESERVAR_LLAMADA = (
    f"INSERT INTO {ESQUEMA}.callbot_call (id, purpose, person_id, alert_id, "
    "alert_contact_id, alert_rule_id, alert_severity, phone_e164, phone_kind, "
    "script_version) VALUES (:call_id, 'alert_notice', :person_id, :alert_id, "
    ":contact_id, :rule_id, :severity, :phone, 'contact', :script_version) "
    # Solo el índice del aviso cuenta como «ya avisada»; cualquier otro conflicto
    # (PK, connect_contact_id) es un error y no debe silenciar un SOS.
    "ON CONFLICT (alert_id, alert_contact_id, attempt) "
    "WHERE purpose = 'alert_notice' DO NOTHING"
)
SQL_REGISTRAR_CONTACTO = (
    f"UPDATE {ESQUEMA}.callbot_call SET connect_contact_id = :contact_id "
    "WHERE id = :call_id"
)
SQL_REGISTRAR_FALLO = (
    f"UPDATE {ESQUEMA}.callbot_call SET outcome = 'failed', "
    "error_code = :codigo, ended_at = now() WHERE id = :call_id"
)

# Variables de entorno de la conexión: único sitio donde se nombran.
VAR_CLUSTER = "DB_CLUSTER_ARN"
VAR_SECRETO = "DB_SECRET_ARN"
VAR_BASE = "DB_NAME"
VARIABLES_AURORA = (VAR_CLUSTER, VAR_SECRETO, VAR_BASE)

_MENSAJE_FALLO = "Fallo al acceder a la base de datos."
_MENSAJE_RESPUESTA = "Respuesta inesperada de la base de datos."
_UNA_FILA = 1
# SQLState de una violación de unicidad y nombre de la restricción en el mensaje.
_SQLSTATE_UNICIDAD = "23505"
_PATRON_RESTRICCION = re.compile(r'unique constraint "([A-Za-z0-9_]+)"')


class _ClienteRdsData(Protocol):
    """Parte del cliente de boto3 que usa el adaptador."""

    def execute_statement(self, **kwargs: Any) -> Mapping[str, Any]:
        """Ejecuta una sentencia SQL por la Data API."""
        ...


class ErrorUnicidad(ErrorBaseDatos):
    """La base rechazó una fila por una restricción de unicidad (SQLState 23505).

    Solo guarda el nombre de la restricción (no es un dato personal); el mensaje
    de la base no se conserva.
    """

    def __init__(self, mensaje: str, restriccion: str) -> None:
        """Guarda el mensaje fijo y la restricción (vacía si no se conoce)."""
        super().__init__(mensaje)
        self.restriccion = restriccion


class _FilaConsentimiento(BaseModel):
    """Fila de `callbot_consent` que interesa: si se concedió."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    granted: StrictBool


def param_uuid(nombre: str, valor: str) -> dict[str, Any]:
    """Parámetro UUID con nombre."""
    return {"name": nombre, "typeHint": "UUID", "value": {"stringValue": valor}}


def param_texto(nombre: str, valor: str) -> dict[str, Any]:
    """Parámetro de texto con nombre."""
    return {"name": nombre, "value": {"stringValue": valor}}


def param_texto_o_nulo(nombre: str, valor: str | None) -> dict[str, Any]:
    """Parámetro de texto que puede ser NULL."""
    if valor is None:
        return {"name": nombre, "value": {"isNull": True}}
    return param_texto(nombre, valor)


class ClienteDataApi:
    """Base de los adaptadores de Aurora: conexión y ejecución por la Data API."""

    def __init__(
        self,
        cliente: _ClienteRdsData,
        cluster_arn: str,
        secret_arn: str,
        database: str,
        *,
        esperar: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        """Recibe el cliente de boto3 ya creado y la configuración de Aurora.

        `esperar` y `reloj` se sustituyen en los tests para no dormir de verdad.
        """
        if not cluster_arn:
            raise ErrorConfiguracion("Falta cluster_arn de Aurora.")
        if not secret_arn:
            raise ErrorConfiguracion("Falta secret_arn de Aurora.")
        if not database:
            raise ErrorConfiguracion("Falta database de Aurora.")
        self._cliente = cliente
        self._cluster_arn = cluster_arn
        self._secret_arn = secret_arn
        self._database = database
        self._esperar = esperar
        self._reloj = reloj

    @classmethod
    def crear(cls, cluster_arn: str, secret_arn: str, database: str) -> Self:
        """Crea el adaptador con un cliente real de `rds-data`."""
        cliente = boto3.client("rds-data", config=CONFIG_AURORA)
        return cls(cliente, cluster_arn, secret_arn, database)

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> Self:
        """Crea el adaptador con las variables `DB_*` de `entorno`.

        Lanza `ErrorConfiguracion` nombrando la variable, nunca su valor.
        """
        for variable in VARIABLES_AURORA:
            if not entorno.get(variable):
                raise ErrorConfiguracion(f"Falta la variable {variable}.")
        return cls.crear(entorno[VAR_CLUSTER], entorno[VAR_SECRETO], entorno[VAR_BASE])

    def _ejecutar(
        self, sql: str, parametros: list[dict[str, Any]], **extra: Any
    ) -> Mapping[str, Any]:
        """Llama a `execute_statement`; traduce los fallos de AWS.

        Si Aurora está despertando, reintenta (ver `_espera_para_reintentar`).
        """
        inicio = self._reloj()
        esperas = iter(ESPERAS_REANUDACION)
        while True:
            try:
                return self._cliente.execute_statement(
                    resourceArn=self._cluster_arn,
                    secretArn=self._secret_arn,
                    database=self._database,
                    sql=sql,
                    parameters=parametros,
                    **extra,
                )
            except (ClientError, BotoCoreError) as error:
                espera = self._espera_para_reintentar(error, esperas, inicio)
                if espera is None:
                    _traducir(error)
                logger.warning("aurora_reanudando", extra={"espera_s": espera})
                self._esperar(espera)

    def _espera_para_reintentar(
        self,
        error: ClientError | BotoCoreError,
        esperas: Iterator[float],
        inicio: float,
    ) -> float | None:
        """Segundos que esperar antes de repetir, o `None` si no se repite.

        Solo se repite `DatabaseResumingException`: la sentencia no llegó a
        ejecutarse, así que repetirla no duplica escrituras. No añadir otros
        códigos (timeouts, `StatementTimeoutException`) ni usarlo dentro de una
        transacción sin pensar antes en la idempotencia.
        """
        if _codigo(error) != CODIGO_REANUDANDO:
            return None
        espera = next(esperas, None)
        if espera is None:
            return None
        if self._reloj() - inicio + espera > PLAZO_REANUDACION_S:
            return None
        return espera

    def _escribir(self, sql: str, parametros: list[dict[str, Any]]) -> int:
        """Ejecuta una escritura y devuelve las filas afectadas."""
        respuesta = self._ejecutar(sql, parametros)
        filas = respuesta.get("numberOfRecordsUpdated")
        if isinstance(filas, int) and not isinstance(filas, bool):
            return filas
        raise ErrorBaseDatos(_MENSAJE_RESPUESTA)

    def _exigir_una_fila(self, sql: str, parametros: list[dict[str, Any]]) -> None:
        """Ejecuta un UPDATE y exige que toque exactamente una fila."""
        if self._escribir(sql, parametros) != _UNA_FILA:
            raise ErrorBaseDatos(_MENSAJE_RESPUESTA)

    def _leer(self, sql: str, parametros: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ejecuta una consulta y devuelve sus filas como diccionarios."""
        respuesta = self._ejecutar(sql, parametros, formatRecordsAs="JSON")
        crudo = respuesta.get("formattedRecords")
        try:
            filas = json.loads(crudo) if isinstance(crudo, str) else None
        except ValueError:
            filas = None
        if not isinstance(filas, list) or not all(isinstance(f, dict) for f in filas):
            raise ErrorBaseDatos(_MENSAJE_RESPUESTA)
        return filas


class AuroraAdapter(ClienteDataApi):
    """Guarda y lee los avisos en Aurora (implementa `RepositorioAvisos`)."""

    def registrar_recepcion(self, alert_id: str) -> None:
        """Apunta en `audit_log` que ha llegado un aviso de esa alerta."""
        self._ejecutar(SQL_REGISTRAR_RECEPCION, [param_uuid("alert_id", alert_id)])

    def alerta_abierta(self, alert_id: str) -> Alerta | None:
        """Devuelve la alerta si está abierta y su persona está en el callbot."""
        filas = self._leer(SQL_ALERTA_ABIERTA, [param_uuid("alert_id", alert_id)])
        if not filas:
            return None
        if len(filas) > 1:
            raise DatosInvalidos(_MENSAJE_RESPUESTA)
        return validar(Alerta, filas[0])

    def tiene_consentimiento(self, person_id: str, permiso: str) -> bool:
        """Indica si el último consentimiento de ese permiso está concedido."""
        filas = self._leer(
            SQL_CONSENTIMIENTO,
            [param_uuid("person_id", person_id), param_texto("scope", permiso)],
        )
        if not filas:
            return False
        return validar(_FilaConsentimiento, filas[0]).granted

    def contacto_principal(self, person_id: str) -> Destinatario | None:
        """Devuelve el contacto de aviso de prioridad 1, si recibe avisos."""
        filas = self._leer(SQL_CONTACTO_PRINCIPAL, [param_uuid("person_id", person_id)])
        if not filas:
            return None
        if len(filas) > 1:
            raise DatosInvalidos(_MENSAJE_RESPUESTA)
        return validar(Destinatario, filas[0])

    def reservar_llamada(self, reserva: Reserva) -> bool:
        """Crea la fila de la llamada; `False` si ya existía."""
        alerta = reserva.alerta
        parametros = [
            param_uuid("call_id", reserva.call_id),
            param_uuid("person_id", alerta.person_id),
            param_uuid("alert_id", alerta.alert_id),
            param_uuid("contact_id", reserva.destinatario.contacto_id),
            param_texto("rule_id", alerta.rule_id),
            param_texto("severity", alerta.severity),
            param_texto("phone", reserva.destinatario.telefono),
            param_texto("script_version", reserva.version_guion),
        ]
        escritas = self._escribir(SQL_RESERVAR_LLAMADA, parametros)
        if escritas not in (0, _UNA_FILA):
            raise ErrorBaseDatos(_MENSAJE_RESPUESTA)
        return escritas == _UNA_FILA

    def registrar_contacto(self, call_id: str, contact_id: str) -> None:
        """Guarda el identificador del contacto que devolvió el canal."""
        parametros = [
            param_texto("contact_id", contact_id),
            param_uuid("call_id", call_id),
        ]
        self._exigir_una_fila(SQL_REGISTRAR_CONTACTO, parametros)

    def registrar_fallo(self, call_id: str, codigo: str) -> None:
        """Marca la llamada como fallida con el código del error."""
        parametros = [param_texto("codigo", codigo), param_uuid("call_id", call_id)]
        self._exigir_una_fila(SQL_REGISTRAR_FALLO, parametros)


def validar[T: BaseModel](modelo: type[T], fila: dict[str, Any]) -> T:
    """Valida la fila con pydantic sin filtrar su contenido al error."""
    try:
        return modelo.model_validate(fila)
    except ValidationError:
        raise DatosInvalidos(_MENSAJE_RESPUESTA) from None


def _codigo(error: ClientError | BotoCoreError) -> str | None:
    """Código de error de AWS, o `None` si no es un `ClientError`."""
    if not isinstance(error, ClientError):
        return None
    return error.response.get("Error", {}).get("Code")


def _traducir(error: ClientError | BotoCoreError) -> NoReturn:
    """Registra el fallo y lo convierte en un error del dominio."""
    _registrar_fallo_aws(error)
    restriccion = _restriccion_violada(error)
    if restriccion is not None:
        raise ErrorUnicidad(_MENSAJE_FALLO, restriccion) from None
    # `from None`: el contexto llevaría el ARN y el SQL de la petición.
    raise ErrorBaseDatos(_MENSAJE_FALLO) from None


def _registrar_fallo_aws(error: ClientError | BotoCoreError) -> None:
    """Registra el fallo (solo tipo y código conocido, sin SQL ni datos)."""
    candidato = _codigo(error)
    codigo = candidato if candidato in CODIGOS_AWS_CONOCIDOS else None
    logger.warning(
        "aurora_fallo", extra={"tipo": type(error).__name__, "codigo": codigo}
    )


def _restriccion_violada(error: ClientError | BotoCoreError) -> str | None:
    """Nombre de la restricción si el error es una violación de unicidad.

    Devuelve `None` si no lo es y `""` si lo es pero no se lee el nombre.
    """
    if not isinstance(error, ClientError):
        return None
    mensaje = error.response.get("Error", {}).get("Message")
    if not isinstance(mensaje, str) or _SQLSTATE_UNICIDAD not in mensaje:
        return None
    encontrada = _PATRON_RESTRICCION.search(mensaje)
    return encontrada.group(1) if encontrada else ""
