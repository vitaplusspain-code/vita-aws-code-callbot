"""Construcción del mensaje en SSML para Polly."""

from xml.sax.saxutils import escape

from core.casos import texto_del_caso
from core.tipos import Caso

VELOCIDAD_VOZ = "90%"


def construir_ssml(texto: str) -> str:
    """Envuelve texto plano en SSML, escapando los caracteres de XML."""
    return f'<speak><prosody rate="{VELOCIDAD_VOZ}">{escape(texto)}</prosody></speak>'


def construir_mensaje(caso: Caso, persona: str, familiar: str) -> str:
    """Devuelve el SSML del caso; los nombres se escapan una sola vez."""
    return construir_ssml(texto_del_caso(caso, persona, familiar))
