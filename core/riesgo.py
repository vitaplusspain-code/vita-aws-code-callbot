"""Detector de riesgo por palabras clave (guardarraíl de la decisión 9).

Criterio conservador: ante la duda es mejor avisar que callar. Limitaciones
conocidas, fijadas con tests:

- No entiende negaciones: «no me he caído» dispara la señal de caída.
- «ayuda» suelto dispara: «me ayuda mi hija» cuenta como petición de ayuda.
- «sangre», «me muero» o «derrame» disparan aunque sean figurados.
- «me encuentro mal» a secas NO es riesgo (es ánimo); «estoy fatal» sí.
- Con varias coincidencias manda la prioridad: autolesión, dolor de pecho,
  respiración, caída y otros.
"""

from dataclasses import dataclass, field

from core.normalizar import limpiar_texto, normalizar_con_posiciones
from core.riesgo_patrones import PATRONES, TipoRiesgo

__all__ = ["LONGITUD_MAXIMA_VERBATIM", "SenalRiesgo", "TipoRiesgo", "detectar_riesgo"]

LONGITUD_MAXIMA_VERBATIM = 1000
_MARGEN_PREVIO = 100  # caracteres antes del acierto al recortar un texto largo


@dataclass(frozen=True)
class SenalRiesgo:
    """Riesgo detectado; la frase de la persona es un dato de salud."""

    kind: TipoRiesgo
    verbatim: str = field(repr=False)


def _recortar(limpio: str, inicio: int) -> str:
    """Recorta a la longitud máxima dejando el acierto dentro."""
    if len(limpio) <= LONGITUD_MAXIMA_VERBATIM:
        return limpio
    desde = max(0, inicio - _MARGEN_PREVIO)
    return limpio[desde : desde + LONGITUD_MAXIMA_VERBATIM].strip()


def detectar_riesgo(texto: str) -> SenalRiesgo | None:
    """Devuelve la señal de riesgo si la frase contiene algún disparador."""
    limpio = limpiar_texto(texto)
    normalizado, posiciones = normalizar_con_posiciones(limpio)
    for tipo, patron in PATRONES:
        acierto = patron.search(normalizado)
        if acierto is not None:
            return SenalRiesgo(tipo, _recortar(limpio, posiciones[acierto.start()]))
    return None
