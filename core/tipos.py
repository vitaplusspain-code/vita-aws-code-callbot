"""Tipos compartidos del dominio."""

import unicodedata
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, StringConstraints

LONGITUD_MAXIMA_NOMBRE = 100
LONGITUD_MAXIMA_REGLA = 100

PersonaId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,40}$")]

# Categorías Unicode que no se admiten: control, formato, separadores de línea
# y de párrafo, no asignados y sustitutos (invisibles o inválidos en XML).
_CATEGORIAS_PROHIBIDAS = frozenset({"Cc", "Cf", "Zl", "Zp", "Cn", "Cs"})


def _rechazar_caracteres_prohibidos(valor: object) -> object:
    """Falla si el texto lleva caracteres invisibles o de control."""
    if isinstance(valor, str) and any(
        unicodedata.category(c) in _CATEGORIAS_PROHIBIDAS for c in valor
    ):
        raise ValueError("el texto contiene caracteres no permitidos")
    return valor


def _rechazar_digitos(valor: object) -> object:
    """Falla si el nombre lleva dígitos: se lee en voz alta en la llamada."""
    if isinstance(valor, str) and any(c.isdigit() for c in valor):
        raise ValueError("el nombre contiene dígitos")
    return valor


# De 1 a 100 caracteres, sin espacios sobrantes, sin dígitos (que no se pueda
# dictar un número en la llamada) y sin caracteres prohibidos.
NombrePersona = Annotated[
    str,
    BeforeValidator(_rechazar_digitos),
    BeforeValidator(_rechazar_caracteres_prohibidos),
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=LONGITUD_MAXIMA_NOMBRE,
        pattern=r"\S",  # al menos un carácter visible tras limpiar espacios
    ),
]


# UUID en formato canónico (8-4-4-4-12), sin llaves ni prefijos; se guarda en
# minúsculas, como lo devuelve PostgreSQL.
PATRON_UUID = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
Uuid = Annotated[str, StringConstraints(pattern=PATRON_UUID), AfterValidator(str.lower)]

# Identificador de regla de alerta (`alert.rule_id`, texto libre en VitaPlus):
# de 1 a 100 caracteres, sin espacios en los extremos ni caracteres prohibidos.
ReglaId = Annotated[
    str,
    BeforeValidator(_rechazar_caracteres_prohibidos),
    StringConstraints(max_length=LONGITUD_MAXIMA_REGLA, pattern=r"^\S(.*\S)?$"),
]


class Caso(StrEnum):
    """Motivos por los que se avisa a un familiar."""

    MEDICACION_7_DIAS = "medicacion_7_dias"
    SIN_ACTIVIDAD_HOY = "sin_actividad_hoy"
    SUENO_IRREGULAR = "sueno_irregular"
