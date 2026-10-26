"""Tipos compartidos del dominio."""

import unicodedata
from enum import StrEnum
from typing import Annotated

from pydantic import BeforeValidator, StringConstraints

LONGITUD_MAXIMA_NOMBRE = 100

PersonaId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,40}$")]

# Categorías Unicode que no se admiten: control, formato, separadores de línea
# y de párrafo, no asignados y sustitutos (invisibles o inválidos en XML).
_CATEGORIAS_PROHIBIDAS = frozenset({"Cc", "Cf", "Zl", "Zp", "Cn", "Cs"})


def _rechazar_caracteres_prohibidos(valor: object) -> object:
    """Falla si el texto lleva caracteres invisibles o de control."""
    if isinstance(valor, str) and any(
        unicodedata.category(c) in _CATEGORIAS_PROHIBIDAS for c in valor
    ):
        raise ValueError("el nombre contiene caracteres no permitidos")
    return valor


# De 1 a 100 caracteres, sin espacios sobrantes y sin caracteres prohibidos.
NombrePersona = Annotated[
    str,
    BeforeValidator(_rechazar_caracteres_prohibidos),
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=LONGITUD_MAXIMA_NOMBRE,
        pattern=r"\S",  # al menos un carácter visible tras limpiar espacios
    ),
]


class Caso(StrEnum):
    """Motivos por los que se avisa a un familiar."""

    MEDICACION_7_DIAS = "medicacion_7_dias"
    SIN_ACTIVIDAD_HOY = "sin_actividad_hoy"
    SUENO_IRREGULAR = "sueno_irregular"
