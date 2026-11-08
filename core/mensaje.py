"""Construcción del mensaje en SSML para Polly."""

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from core.casos import texto_del_caso
from core.motivos import texto_detalle, texto_saludo
from core.tipos import Caso

VELOCIDAD_VOZ = "90%"


@dataclass(frozen=True)
class MensajeAviso:
    """Las dos partes de la llamada de aviso, ya en SSML.

    Llevan nombres y el motivo (dato de salud): no salen en la representación.
    """

    saludo: str = field(repr=False)
    detalle: str = field(repr=False)


def construir_mensaje_aviso(rule_id: str, persona: str, familiar: str) -> MensajeAviso:
    """Devuelve saludo y detalle en SSML; los nombres se escapan una sola vez."""
    return MensajeAviso(
        saludo=construir_ssml(texto_saludo(familiar)),
        detalle=construir_ssml(texto_detalle(rule_id, persona)),
    )


def construir_ssml(texto: str) -> str:
    """Envuelve texto plano en SSML, escapando los caracteres de XML."""
    return f'<speak><prosody rate="{VELOCIDAD_VOZ}">{escape(texto)}</prosody></speak>'


def construir_mensaje(caso: Caso, persona: str, familiar: str) -> str:
    """Devuelve el SSML del caso; los nombres se escapan una sola vez."""
    return construir_ssml(texto_del_caso(caso, persona, familiar))
