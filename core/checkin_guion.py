"""Guion de la conversación diaria (`checkin-v1`): preguntas y textos."""

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "GUION",
    "TEXTOS",
    "VERSION_GUION_CHECKIN",
    "Paso",
    "Pregunta",
    "TextosTrato",
    "TipoRespuesta",
    "Trato",
]

# Se guarda en `callbot_call.script_version`: cambiarla al cambiar el guion.
VERSION_GUION_CHECKIN = "checkin-v1"


class Trato(StrEnum):
    """Forma de tratamiento (`callbot_profile.address_form`)."""

    USTED = "usted"
    TU = "tu"


class Paso(StrEnum):
    """Pregunta que espera respuesta, o `FIN` si la conversación terminó."""

    ANIMO_HOY = "animo_hoy"
    ANIMO_SEMANA = "animo_semana"
    COMIDA = "comida_tomada"
    QUE_COMIDO = "que_ha_comido"
    FIN = "fin"


class TipoRespuesta(StrEnum):
    """Cómo se interpreta la respuesta a una pregunta."""

    ANIMO = "animo"
    SI_NO = "si_no"
    TEXTO_LIBRE = "texto_libre"


@dataclass(frozen=True)
class Pregunta:
    """Una pregunta del guion.

    `solo_si` es `(indicador, valor)`: la pregunta solo se hace si la pregunta
    recién respondida fue ese indicador con ese valor.
    """

    paso: Paso
    tipo: TipoRespuesta
    texto_usted: str
    texto_tu: str
    solo_si: tuple[str, str] | None = None

    def texto(self, trato: Trato) -> str:
        """Texto de la pregunta con el trato indicado."""
        return self.texto_tu if trato is Trato.TU else self.texto_usted


@dataclass(frozen=True)
class TextosTrato:
    """Textos fijos de un trato; `{nombre}` se rellena al decirlos.

    `urgencia` y `autolesion` son cierres completos (sin despedida normal).
    """

    saludo: str
    no_entendido: str
    despedida: str
    urgencia: str
    autolesion: str


GUION: tuple[Pregunta, ...] = (
    Pregunta(
        Paso.ANIMO_HOY,
        TipoRespuesta.ANIMO,
        "¿Qué tal se encuentra hoy?",
        "¿Qué tal te encuentras hoy?",
    ),
    Pregunta(
        Paso.ANIMO_SEMANA,
        TipoRespuesta.ANIMO,
        "¿Y qué tal ha ido la semana?",
        "¿Y qué tal ha ido la semana?",
    ),
    Pregunta(
        Paso.COMIDA,
        TipoRespuesta.SI_NO,
        "¿Ha comido hoy?",
        "¿Has comido hoy?",
    ),
    Pregunta(
        Paso.QUE_COMIDO,
        TipoRespuesta.TEXTO_LIBRE,
        "¿Qué ha comido?",
        "¿Qué has comido?",
        solo_si=(Paso.COMIDA.value, "si"),
    ),
)

# Pendiente de validar con VitaPlus (criterio clínico)
_URGENCIA_USTED = (
    "Si es una urgencia, cuelgue y llame al 112 ahora mismo. "
    "Repito: llame al 112. Gracias, {nombre}."
)
_URGENCIA_TU = (
    "Si es una urgencia, cuelga y llama al 112 ahora mismo. "
    "Repito: llama al 112. Gracias, {nombre}."
)
_AUTOLESION_USTED = (
    "Siento mucho que se sienta así. Puede llamar ahora al 024, donde le "
    "atenderán a cualquier hora. Si está en peligro, llame al 112. "
    "Gracias por contármelo, {nombre}."
)
_AUTOLESION_TU = (
    "Siento mucho que te sientas así. Puedes llamar ahora al 024, donde te "
    "atenderán a cualquier hora. Si estás en peligro, llama al 112. "
    "Gracias por contármelo, {nombre}."
)

TEXTOS: dict[Trato, TextosTrato] = {
    Trato.USTED: TextosTrato(
        saludo=(
            "Hola, {nombre}. Le llama el asistente automático de VitaPlus "
            "para saber qué tal está."
        ),
        no_entendido="Perdone, no le he entendido.",
        despedida="Muchas gracias, {nombre}. Que tenga un buen día. Hasta mañana.",
        urgencia=_URGENCIA_USTED,
        autolesion=_AUTOLESION_USTED,
    ),
    Trato.TU: TextosTrato(
        saludo=(
            "Hola, {nombre}. Te llama el asistente automático de VitaPlus "
            "para saber qué tal estás."
        ),
        no_entendido="Perdona, no te he entendido.",
        despedida="Muchas gracias, {nombre}. Que tengas un buen día. Hasta mañana.",
        urgencia=_URGENCIA_TU,
        autolesion=_AUTOLESION_TU,
    ),
}
