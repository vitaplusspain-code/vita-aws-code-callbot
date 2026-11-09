"""Construcción del mensaje en SSML para Polly."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from core.casos import FRASES_CASOS
from core.motivos import FRASES_POR_REGLA, texto_detalle, texto_saludo
from core.tipos import Caso

__all__ = [
    "VELOCIDAD_VOZ",
    "MensajeAviso",
    "construir_mensaje_aviso",
    "construir_mensaje_caso",
    "construir_ssml",
]

VELOCIDAD_VOZ = "90%"


@dataclass(frozen=True)
class MensajeAviso:
    """Las dos partes de la llamada de aviso, ya en SSML.

    Llevan nombres y el motivo (dato de salud): no salen en la representación.
    """

    saludo: str = field(repr=False)
    detalle: str = field(repr=False)


def construir_ssml(texto: str) -> str:
    """Envuelve texto plano en SSML, escapando los caracteres de XML."""
    return f'<speak><prosody rate="{VELOCIDAD_VOZ}">{escape(texto)}</prosody></speak>'


def construir_mensaje_aviso(
    rule_id: str,
    persona: str,
    familiar: str,
    *,
    frases: Mapping[str, str] = FRASES_POR_REGLA,
) -> MensajeAviso:
    """Devuelve saludo y detalle en SSML; los nombres se escapan una sola vez."""
    return MensajeAviso(
        saludo=construir_ssml(texto_saludo(familiar)),
        detalle=construir_ssml(texto_detalle(rule_id, persona, frases)),
    )


def construir_mensaje_caso(caso: Caso, persona: str, familiar: str) -> MensajeAviso:
    """Mensaje de un caso de la demo de la fase 1, con el mismo guion de dos partes."""
    return construir_mensaje_aviso(caso.value, persona, familiar, frases=FRASES_CASOS)
