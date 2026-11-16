"""Interpretación de las respuestas del mayor: puerto y versión por reglas.

El MVP interpreta con palabras clave. Más adelante entrará un intérprete con
Bedrock detrás del mismo puerto, sin tocar el resto.
"""

import re
from typing import Protocol

from core.checkin_guion import Pregunta, TipoRespuesta, Trato
from core.normalizar import limpiar_texto, normalizar

__all__ = ["LONGITUD_MAXIMA_TEXTO", "Interprete", "InterpreteReglas"]

LONGITUD_MAXIMA_TEXTO = 200


class Interprete(Protocol):
    """Convierte lo que dijo la persona en un valor del guion."""

    def interpretar(self, pregunta: Pregunta, texto: str, trato: Trato) -> str | None:
        """Devuelve el valor (`bien`, `si`, un texto...) o `None` si no entiende.

        No debe lanzar excepciones (si lanza, se trata como no entendido) y
        nunca devuelve texto que se vaya a hablar: solo valores del guion o
        texto libre para guardar.
        """
        ...


# ---- Ánimo -----------------------------------------------------------------

_AUX = r"(?:(?:estoy|me|encuentro|siento|muy|tan|del|todo|demasiado|nada) ){0,3}"
_SIN_QUEJA = re.compile(
    r"\b(?:no me puedo quejar|no me quejo|no puedo quejarme|no hay quejas)\b"
)
_NEGACION_MAL = re.compile(rf"\bno {_AUX}mal\b")
_NEGACION_BIEN = re.compile(rf"\bno {_AUX}bien\b")
_REGULAR = re.compile(
    r"\b(?:regular|mas o menos|asi asi|normal|tirando|ni bien ni mal)\b"
)
_MAL = re.compile(r"\b(?:mal|muy mal|fatal|fatales|horrible|pesimo)\b")
_BIEN = re.compile(
    r"\b(?:bien|estupendo|estupenda|estupendamente|genial|fenomenal|perfecto|"
    r"perfectamente|de maravilla)\b"
)
# En este orden: las negaciones antes que las palabras sueltas.
_REGLAS_ANIMO = (
    ("bien", _SIN_QUEJA),
    ("regular", _NEGACION_MAL),
    ("mal", _NEGACION_BIEN),
    ("regular", _REGULAR),
    ("mal", _MAL),
    ("bien", _BIEN),
)
_CLAUSULAS = re.compile(r"[,;.]+")


def _animo_de_clausula(clausula: str) -> str | None:
    return next((v for v, patron in _REGLAS_ANIMO if patron.search(clausula)), None)


def _interpretar_animo(texto: str) -> str | None:
    """Evalúa por cláusulas (`,;.`): la primera con valor decide."""
    clausulas = (normalizar(c) for c in _CLAUSULAS.split(texto))
    return next((v for c in clausulas if (v := _animo_de_clausula(c))), None)


# ---- Sí / no ---------------------------------------------------------------

_AMBIGUO = re.compile(
    r"\b(?:no se(?! preocup)|no lo se|no me acuerdo|no estoy segur[oa]|"
    r"no sabria decir)\b"
)
_SI_NO = re.compile(
    r"\b(?:(?P<neutro>no (?:se|te) preocup\w*)"
    r"|(?P<no>claro que no|por supuesto que no|que va|ya no|no he comido"
    r"|no ha comido|no comi|no)"
    r"|(?P<si>claro que si|por supuesto|ya he comido|he comido|ha comido"
    r"|comi|si))\b"
)


def _interpretar_si_no(texto: str) -> str | None:
    normalizado = normalizar(texto)
    if _AMBIGUO.search(normalizado):
        return None
    grupos = {m.lastgroup for m in _SI_NO.finditer(normalizado)} - {"neutro"}
    return grupos.pop() if len(grupos) == 1 else None


# ---- Texto libre -----------------------------------------------------------


def _interpretar_texto(texto: str) -> str | None:
    """Texto libre: lo no vacío, sin caracteres de control y recortado."""
    return limpiar_texto(texto)[:LONGITUD_MAXIMA_TEXTO].rstrip() or None


class InterpreteReglas:
    """Interpreta con reglas y palabras clave, sin red ni modelos."""

    def interpretar(self, pregunta: Pregunta, texto: str, trato: Trato) -> str | None:
        """Devuelve el valor de la respuesta o `None` si no se entiende."""
        if pregunta.tipo == TipoRespuesta.ANIMO:
            return _interpretar_animo(texto)
        if pregunta.tipo == TipoRespuesta.SI_NO:
            return _interpretar_si_no(texto)
        if pregunta.tipo == TipoRespuesta.TEXTO_LIBRE:
            return _interpretar_texto(texto)
        raise ValueError("tipo de respuesta desconocido")
