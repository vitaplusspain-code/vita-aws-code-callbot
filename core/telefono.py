"""Validación E.164 y enmascarado de teléfonos."""

import re
from typing import Annotated

from pydantic import StringConstraints

PATRON_E164 = r"^\+[1-9][0-9]{7,14}$"
PREFIJO_VISIBLE = 3
FINAL_VISIBLE = 4
_MINIMO_ENMASCARABLE = 11

TelefonoE164 = Annotated[str, StringConstraints(pattern=PATRON_E164)]


def es_telefono_e164(valor: str) -> bool:
    """Indica si `valor` es un teléfono en formato E.164."""
    return re.fullmatch(PATRON_E164, valor) is not None


def enmascarar_telefono(telefono: str) -> str:
    """Oculta el centro del teléfono para los logs: `+34*****3456`."""
    if len(telefono) < _MINIMO_ENMASCARABLE:
        return "*" * len(telefono)
    oculto = "*" * (len(telefono) - PREFIJO_VISIBLE - FINAL_VISIBLE)
    return telefono[:PREFIJO_VISIBLE] + oculto + telefono[-FINAL_VISIBLE:]
