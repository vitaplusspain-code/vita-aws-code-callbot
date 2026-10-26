"""Aviso entrante: validación del cuerpo recibido."""

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from core.errores import AvisoInvalido
from core.tipos import Caso, PersonaId

__all__ = [
    "TAMANO_MAXIMO_CUERPO",
    "Aviso",
    "Caso",
    "PersonaId",
    "parsear_aviso",
    "parsear_aviso_json",
]

TAMANO_MAXIMO_CUERPO = 1024


class Aviso(BaseModel):
    """Petición de aviso: qué persona y qué caso."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    persona_id: PersonaId
    caso: Caso


def parsear_aviso(datos: object) -> Aviso:
    """Valida `datos` y devuelve el aviso; lanza `AvisoInvalido` si no cumple.

    El mensaje solo nombra campos conocidos: nunca refleja lo que envió el
    cliente (valores ni claves). La excepción no arrastra contexto.
    """
    try:
        return Aviso.model_validate(datos)
    except ValidationError as error:
        mensaje = _describir(error)
    raise AvisoInvalido(mensaje)


def parsear_aviso_json(cuerpo: str | bytes | None) -> Aviso:
    """Decodifica un cuerpo JSON y lo valida como aviso.

    Cualquier fallo se traduce a `AvisoInvalido` sin reflejar el contenido.
    """
    datos, problema = _cargar_json(cuerpo)
    if problema:
        raise AvisoInvalido(problema)
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


def _describir(error: ValidationError) -> str:
    """Resume un error de validación usando solo nombres de campo conocidos."""
    conocidos = frozenset(Aviso.model_fields)
    nombrados = {str(e["loc"][0]) for e in error.errors() if e["loc"]}
    partes = []
    erroneos = sorted(nombrados & conocidos)
    if erroneos:
        partes.append(f"campos: {', '.join(erroneos)}")
    if nombrados - conocidos:
        partes.append("campos no permitidos")
    detalle = f" ({'; '.join(partes)})" if partes else ""
    return f"El aviso no es válido{detalle}."
