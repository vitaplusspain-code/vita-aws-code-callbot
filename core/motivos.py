"""Textos de la llamada de aviso, con los guardarraíles de la decisión 9.

La llamada tiene dos partes (decisión 37): un saludo que solo nombra al
familiar y le pide confirmar su identidad, y el detalle con el motivo, que el
flujo de Connect solo reproduce si pulsa 1.
"""

from collections.abc import Mapping
from types import MappingProxyType

__all__ = [
    "FRASES_POR_REGLA",
    "FRASE_GENERICA",
    "VERSION_GUION",
    "texto_detalle",
    "texto_saludo",
]

# Se guarda en `callbot_call.script_version`: cambiarla al cambiar los textos.
VERSION_GUION = "aviso-v1"

_SALUDO = (
    "Hola. Le llama el asistente automático de VitaPlus con un aviso para "
    "{familiar}. Si es usted, pulse 1."
)
_CIERRE = (
    " Le sugerimos que contacte con {persona} lo antes posible. "
    "Si cree que hay una urgencia, llame al 112. "
    "Para repetir el mensaje, pulse 1."
)

FRASE_GENERICA = "VitaPlus ha registrado una alerta importante de {persona}."

# Frase por `alert.rule_id`. Se rellena cuando Jaime pase la lista de reglas
# (duda 2 de la solicitud de la BD v1); hasta entonces todas usan la genérica.
# El único marcador admitido es `{persona}`; cualquier otro se lee tal cual.
FRASES_POR_REGLA: Mapping[str, str] = MappingProxyType({})


def texto_saludo(familiar: str) -> str:
    """Saludo con el nombre del familiar; no dice nada de la persona ni del motivo."""
    return _SALUDO.replace("{familiar}", familiar)


def texto_detalle(
    rule_id: str, persona: str, frases: Mapping[str, str] = FRASES_POR_REGLA
) -> str:
    """Motivo del aviso (frase de la regla o la genérica) y cierre con el 112.

    Se sustituye con `replace` en una sola pasada: una frase mal escrita no
    lanza excepción y un nombre con llaves no se vuelve a interpretar.
    """
    frase = frases.get(rule_id, FRASE_GENERICA)
    return (frase + _CIERRE).replace("{persona}", persona)
