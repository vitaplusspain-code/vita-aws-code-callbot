"""Frases de los casos de la demo de la fase 1, con los guardarraíles de la decisión 9.

Cada frase es el principio del detalle de la llamada; el cierre (contactar,
112, repetir) lo añade `core.motivos.texto_detalle`. Son avisos que no son
urgentes, así que cada frase lo dice. Desaparece con el aviso de alerta.
"""

from collections.abc import Mapping
from types import MappingProxyType

from core.tipos import Caso

__all__ = ["FRASES_CASOS"]

_NO_EMERGENCIA = "Este aviso no es una emergencia. "

FRASES_CASOS: Mapping[str, str] = MappingProxyType(
    {
        Caso.MEDICACION_7_DIAS.value: (
            _NO_EMERGENCIA + "El dispensador indica que {persona} lleva siete días "
            "sin registrar la toma de su medicación."
        ),
        Caso.SIN_ACTIVIDAD_HOY.value: (
            _NO_EMERGENCIA + "Hoy no se ha detectado actividad en casa de {persona}."
        ),
        Caso.SUENO_IRREGULAR.value: (
            _NO_EMERGENCIA + "Hemos observado un patrón de sueño irregular en "
            "{persona} durante las últimas noches."
        ),
    }
)
