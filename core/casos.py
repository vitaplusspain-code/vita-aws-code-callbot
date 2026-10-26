"""Catálogo de textos por caso, con los guardarraíles de la decisión 9."""

from types import MappingProxyType

from core.tipos import Caso

_INTRODUCCION = (
    "Hola {familiar}. Le llama el asistente automático de VitaPlus. "
    "Este aviso no es una emergencia. "
)
_CIERRE = (
    " Le sugerimos que contacte con {persona}. "
    "Si cree que hay una urgencia, llame al 112. "
    "Para repetir el mensaje, pulse 1."
)

PLANTILLAS = MappingProxyType(
    {
        Caso.MEDICACION_7_DIAS: (
            _INTRODUCCION + "El dispensador indica que {persona} lleva siete días sin "
            "registrar la toma de su medicación." + _CIERRE
        ),
        Caso.SIN_ACTIVIDAD_HOY: (
            _INTRODUCCION
            + "Hoy no se ha detectado actividad en casa de {persona}."
            + _CIERRE
        ),
        Caso.SUENO_IRREGULAR: (
            _INTRODUCCION + "Hemos observado un patrón de sueño irregular en {persona} "
            "durante las últimas noches." + _CIERRE
        ),
    }
)


def texto_del_caso(caso: Caso, persona: str, familiar: str) -> str:
    """Devuelve el texto del caso con los nombres sustituidos."""
    return PLANTILLAS[caso].format(persona=persona, familiar=familiar)
