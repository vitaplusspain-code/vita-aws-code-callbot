"""Traducción entre los eventos de Amazon Lex V2 y la conversación.

Solo manipula diccionarios: no llama a AWS. El parseo es tolerante (AWS puede
añadir campos sin cambiar la versión) y nunca registra lo que dijo la persona.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.checkin import Turno
from core.checkin_guion import TEXTOS, Trato

__all__ = [
    "CLAVE_CALL_ID",
    "TIEMPOS_VOZ",
    "EntradaLex",
    "construir_respuesta",
    "parsear_evento",
]

CLAVE_CALL_ID = "call_id"
_INTENT = "Conversacion"
_SLOT = "respuesta"
_MAX_SESSION_ID = 100
# `call_id` es un UUID; cualquier otra cosa se trata como ausente.
_UUID = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")

# TODO-verificar: nombres exactos de los atributos de voz de Lex V2 (la forma
# por intent y slot, `...:<intent>:<slot>`, no está comprobada). Único sitio.
TIEMPOS_VOZ: Mapping[str, str] = {
    "x-amz-lex:audio:start-timeout-ms": "6000",  # silencio inicial
    "x-amz-lex:audio:end-timeout-ms": "1200",  # fin de frase
}


@dataclass(frozen=True)
class EntradaLex:
    """Lo que interesa de un evento de Lex; la frase es dato de salud."""

    call_id: str
    texto: str = field(repr=False)
    atributos: Mapping[str, str]
    session_id: str = ""


def _mapa(valor: object) -> Mapping[str, Any]:
    return valor if isinstance(valor, Mapping) else {}


def _texto(valor: object) -> str:
    return valor if isinstance(valor, str) else ""


def _call_id_valido(valor: object) -> str:
    """El `call_id` si tiene forma de UUID; si no, cadena vacía."""
    if isinstance(valor, str) and _UUID.fullmatch(valor):
        return valor
    return ""


def parsear_evento(evento: object) -> EntradaLex:
    """Extrae la entrada de un evento de Lex ignorando lo que no conoce."""
    estado = _mapa(_mapa(evento).get("sessionState"))
    atributos = {
        clave: valor
        for clave, valor in _mapa(estado.get("sessionAttributes")).items()
        if isinstance(clave, str) and isinstance(valor, str)
    }
    return EntradaLex(
        call_id=_call_id_valido(atributos.get(CLAVE_CALL_ID)),
        texto=_texto(_mapa(evento).get("inputTranscript")),
        atributos=atributos,
        session_id=_texto(_mapa(evento).get("sessionId"))[:_MAX_SESSION_ID],
    )


def _atributos_de_salida(
    turno: Turno, atributos_entrada: Mapping[str, str]
) -> dict[str, str]:
    """Solo `call_id`, el estado propio y los tiempos de voz; sin eco del resto.

    Con lista blanca el tamaño queda acotado muy por debajo del límite de
    12 KB de Lex para los `sessionAttributes`.
    """
    atributos: dict[str, str] = {}
    call_id = _call_id_valido(atributos_entrada.get(CLAVE_CALL_ID))
    if call_id:
        atributos[CLAVE_CALL_ID] = call_id
    return {**atributos, **turno.estado.a_atributos(), **TIEMPOS_VOZ}


def construir_respuesta(
    turno: Turno, atributos_entrada: Mapping[str, str]
) -> dict[str, Any]:
    """Respuesta de Lex: `Close` si terminó; si no, pide el slot `respuesta`."""
    if turno.terminado:
        accion: dict[str, str] = {"type": "Close"}
        estado_intent = "Fulfilled"
    else:
        accion = {"type": "ElicitSlot", "slotToElicit": _SLOT}
        estado_intent = "InProgress"
    respuesta: dict[str, Any] = {
        "sessionState": {
            "dialogAction": accion,
            "intent": {
                "name": _INTENT,
                "state": estado_intent,
                "slots": {_SLOT: None},
            },
            "sessionAttributes": _atributos_de_salida(turno, atributos_entrada),
        }
    }
    texto = turno.texto_a_decir
    if not texto and turno.terminado:
        texto = TEXTOS[Trato.USTED].cierre_error  # un cierre nunca va mudo
    if texto:
        respuesta["messages"] = [{"contentType": "PlainText", "content": texto}]
    return respuesta
