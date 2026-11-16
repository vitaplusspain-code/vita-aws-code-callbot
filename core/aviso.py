"""Aviso entrante: validación del cuerpo recibido."""

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from core.errores import AvisoInvalido
from core.tipos import Caso, PersonaId, Uuid

__all__ = [
    "TAMANO_MAXIMO_CUERPO",
    "Aviso",
    "AvisoAlerta",
    "Caso",
    "PersonaId",
    "parsear_aviso",
    "parsear_aviso_alerta",
    "parsear_aviso_json",
    "parsear_cuerpo_json",
]

TAMANO_MAXIMO_CUERPO = 1024


class Aviso(BaseModel):
    """Petición de aviso: qué persona y qué caso."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    persona_id: PersonaId
    caso: Caso


class AvisoAlerta(BaseModel):
    """Aviso del backend de VitaPlus: solo el identificador de la alerta."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    alert_id: Uuid


def _validar[T: BaseModel](modelo: type[T], datos: object) -> T:
    """Valida `datos` con `modelo`; lanza `AvisoInvalido` sin reflejar nada.

    El mensaje solo nombra campos conocidos: nunca refleja lo que envió el
    cliente (valores ni claves). La excepción no arrastra contexto.
    """
    try:
        return modelo.model_validate(datos)
    except ValidationError as error:
        mensaje = _describir(modelo, error)
    raise AvisoInvalido(mensaje)


def parsear_aviso(datos: object) -> Aviso:
    """Valida `datos` y devuelve el aviso; lanza `AvisoInvalido` si no cumple."""
    return _validar(Aviso, datos)


def parsear_aviso_alerta(datos: object) -> AvisoAlerta:
    """Valida `datos` como `{"alert_id": <uuid>}`; si no, lanza `AvisoInvalido`."""
    return _validar(AvisoAlerta, datos)


def parsear_aviso_json(cuerpo: str | bytes | None) -> Aviso:
    """Decodifica un cuerpo JSON y lo valida como aviso.

    Cualquier fallo se traduce a `AvisoInvalido` sin reflejar el contenido.
    """
    datos, problema = _cargar_json(cuerpo)
    if problema:
        raise AvisoInvalido(problema)
    return parsear_aviso(datos)


def parsear_cuerpo_json(cuerpo: str | bytes | None) -> Aviso | AvisoAlerta:
    """Decodifica el cuerpo y lo valida según su forma.

    Un objeto cuya única clave es `alert_id` es un `AvisoAlerta`; cualquier
    otra cosa se valida como aviso de demo (así, mezclas y campos extra
    fallan). Nunca refleja el contenido en el error.
    """
    datos, problema = _cargar_json(cuerpo)
    if problema:
        raise AvisoInvalido(problema)
    if isinstance(datos, dict) and datos.keys() == {"alert_id"}:
        return parsear_aviso_alerta(datos)
    return parsear_aviso(datos)


def _cargar_json(cuerpo: object) -> tuple[object, str | None]:
    """Devuelve `(datos, None)` o `(None, mensaje fijo del problema)`."""
    if not isinstance(cuerpo, str | bytes):
        return None, "El aviso no es válido: falta el cuerpo."
    if len(cuerpo) > TAMANO_MAXIMO_CUERPO:
        return None, "El aviso no es válido: el cuerpo es demasiado grande."
    try:
        return json.loads(cuerpo, object_pairs_hook=_sin_claves_duplicadas), None
    except _ClaveDuplicadaError:
        return None, "El aviso no es válido: el cuerpo tiene claves duplicadas."
    except (ValueError, RecursionError):
        # ValueError cubre JSONDecodeError y UnicodeDecodeError.
        return None, "El aviso no es válido: el cuerpo no es JSON."


class _ClaveDuplicadaError(ValueError):
    """Un objeto JSON repite una clave."""


def _sin_claves_duplicadas(pares: list[tuple[str, object]]) -> dict[str, object]:
    """Construye el objeto JSON rechazando claves repetidas."""
    objeto = dict(pares)
    if len(objeto) != len(pares):
        raise _ClaveDuplicadaError
    return objeto


def _describir(modelo: type[BaseModel], error: ValidationError) -> str:
    """Resume un error de validación usando solo nombres de campo conocidos."""
    conocidos = frozenset(modelo.model_fields)
    nombrados = {str(e["loc"][0]) for e in error.errors() if e["loc"]}
    partes = []
    erroneos = sorted(nombrados & conocidos)
    if erroneos:
        partes.append(f"campos: {', '.join(erroneos)}")
    if nombrados - conocidos:
        partes.append("campos no permitidos")
    detalle = f" ({'; '.join(partes)})" if partes else ""
    return f"El aviso no es válido{detalle}."
