"""Adaptador de Amazon Connect: pide la llamada saliente con el mensaje."""

import logging
from collections.abc import Mapping
from typing import Any, Protocol, Self

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    NoRegionError,
    PartialCredentialsError,
)

from core.errores import ErrorConfiguracion, ErrorConnect
from core.telefono import es_telefono_e164

__all__ = [
    "ATRIBUTO_MENSAJE",
    "CODIGOS_AWS_CONOCIDOS",
    "CONFIG_CONNECT",
    "LONGITUD_MAXIMA_ATRIBUTO",
    "REGION_CONNECT",
    "ConnectAdapter",
]

logger = logging.getLogger(__name__)

REGION_CONNECT = "eu-central-1"
SEGUNDOS_CONEXION = 3
SEGUNDOS_LECTURA = 10
# `total_max_attempts` cuenta el intento inicial: 1 significa sin reintentos
# (`max_attempts=1` daría 2 intentos). Cada POST es una llamada.
CONFIG_CONNECT = Config(
    region_name=REGION_CONNECT,
    connect_timeout=SEGUNDOS_CONEXION,
    read_timeout=SEGUNDOS_LECTURA,
    retries={"total_max_attempts": 1, "mode": "standard"},
)

# Atributo de contacto con el SSML; el flujo lo lee como `$.Attributes.mensaje`.
ATRIBUTO_MENSAJE = "mensaje"

# Límite de los valores de `Attributes` en el modelo de botocore (32767),
# aplicado aquí en bytes UTF-8 por prudencia.
LONGITUD_MAXIMA_ATRIBUTO = 32767

# Errores del modelo de botocore de StartOutboundVoiceContact, más los
# genéricos de acceso y limitación. Solo estos códigos se reflejan.
CODIGOS_AWS_CONOCIDOS = (
    "InvalidRequestException",
    "InvalidParameterException",
    "ResourceNotFoundException",
    "InternalServiceException",
    "LimitExceededException",
    "DestinationNotAllowedException",
    "OutboundContactNotPermittedException",
    "ThrottlingException",
    "AccessDeniedException",
)

_VAR_INSTANCE = "CONNECT_INSTANCE_ID"
_VAR_FLUJO = "CONNECT_CONTACT_FLOW_ID"
_VAR_ORIGEN = "CONNECT_NUMERO_ORIGEN"


class _ClienteConnect(Protocol):
    """Parte del cliente de boto3 que usa el adaptador."""

    def start_outbound_voice_contact(self, **kwargs: Any) -> Mapping[str, Any]:
        """Pide una llamada saliente de voz."""
        ...


class ConnectAdapter:
    """Pide a Amazon Connect una llamada saliente de voz."""

    def __init__(
        self,
        cliente: _ClienteConnect,
        instance_id: str,
        contact_flow_id: str,
        numero_origen: str,
    ) -> None:
        """Recibe el cliente de boto3 ya creado y la configuración de Connect."""
        if not instance_id:
            raise ErrorConfiguracion("Falta instance_id de Connect.")
        if not contact_flow_id:
            raise ErrorConfiguracion("Falta contact_flow_id de Connect.")
        if not es_telefono_e164(numero_origen):
            raise ErrorConfiguracion("El número de origen no está en formato E.164.")
        self._cliente = cliente
        self._instance_id = instance_id
        self._contact_flow_id = contact_flow_id
        self._numero_origen = numero_origen

    @classmethod
    def crear(cls, instance_id: str, contact_flow_id: str, numero_origen: str) -> Self:
        """Crea el adaptador con un cliente real de Connect (`CONFIG_CONNECT`)."""
        cliente = boto3.client("connect", config=CONFIG_CONNECT)
        return cls(cliente, instance_id, contact_flow_id, numero_origen)

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> Self:
        """Crea el adaptador con las variables `CONNECT_*` de `entorno`.

        Lanza `ErrorConfiguracion` nombrando la variable, nunca su valor.
        """
        for variable in (_VAR_INSTANCE, _VAR_FLUJO, _VAR_ORIGEN):
            if not entorno.get(variable):
                raise ErrorConfiguracion(f"Falta la variable {variable}.")
        if not es_telefono_e164(entorno[_VAR_ORIGEN]):
            raise ErrorConfiguracion(f"La variable {_VAR_ORIGEN} no es válida.")
        return cls.crear(
            entorno[_VAR_INSTANCE], entorno[_VAR_FLUJO], entorno[_VAR_ORIGEN]
        )

    def iniciar_llamada(self, destino: str, mensaje_ssml: str) -> str:
        """Inicia la llamada y devuelve el `ContactId`.

        El llamador DEBE aplicar `ListaBlanca` antes: el adaptador solo valida
        que `destino` sea E.164. Lanza `ErrorConnect` con un mensaje fijo (sin
        teléfono, SSML ni texto de AWS). Un `ErrorConnect` por timeout o fallo
        de red es un resultado desconocido: la llamada puede haberse hecho.
        """
        if not es_telefono_e164(destino):
            raise ErrorConnect("El teléfono de destino no es válido.")
        if not 0 < len(mensaje_ssml.encode("utf-8")) <= LONGITUD_MAXIMA_ATRIBUTO:
            raise ErrorConnect("El mensaje está vacío o supera el límite de Connect.")
        try:
            respuesta = self._cliente.start_outbound_voice_contact(
                DestinationPhoneNumber=destino,
                ContactFlowId=self._contact_flow_id,
                InstanceId=self._instance_id,
                SourcePhoneNumber=self._numero_origen,
                Attributes={ATRIBUTO_MENSAJE: mensaje_ssml},
            )
        except (ClientError, BotoCoreError) as error:
            mensaje = _traducir(error)
        else:
            contacto = respuesta.get("ContactId")
            if isinstance(contacto, str) and contacto:
                return contacto
            mensaje = "Connect no devolvió el identificador del contacto."
        raise ErrorConnect(mensaje)


def _codigo_conocido(error: ClientError | BotoCoreError) -> str | None:
    """Código de AWS del error si pertenece a la lista cerrada."""
    if not isinstance(error, ClientError):
        return None
    codigo = error.response.get("Error", {}).get("Code")
    return codigo if codigo in CODIGOS_AWS_CONOCIDOS else None


def _traducir(error: ClientError | BotoCoreError) -> str:
    """Registra el fallo (solo tipo y código) y devuelve el mensaje fijo."""
    codigo = _codigo_conocido(error)
    logger.warning(
        "connect_fallo", extra={"tipo": type(error).__name__, "codigo": codigo}
    )
    if isinstance(error, ClientError):
        if codigo:
            return f"Connect rechazó la llamada (código: {codigo})."
        return "Connect rechazó la llamada."
    if isinstance(error, NoCredentialsError | PartialCredentialsError | NoRegionError):
        return "Configuración de AWS incompleta para llamar a Connect."
    return "Fallo al comunicarse con Connect."
