"""Patrones del detector de riesgo, sobre texto normalizado (sin tildes).

Los huecos acotados `(\\w+ ){0,3}` toleran palabras intermedias («me duele
mucho aquí el pecho»). El orden de `PATRONES` es la prioridad.
"""

import re
from enum import StrEnum

__all__ = ["PATRONES", "TipoRiesgo"]


class TipoRiesgo(StrEnum):
    """Clases de riesgo que se distinguen (`kind` de la señal)."""

    SELF_HARM = "self_harm"
    CHEST_PAIN = "chest_pain"
    BREATHING = "breathing"
    FALL = "fall"
    OTHER = "other"


_G = r"(?:\w+ ){0,3}"  # hueco de hasta tres palabras
_G2 = r"(?:\w+ ){0,2}"
_PARTES = r"(?:brazos?|piernas?|manos?|pies?|cara|lado|boca)"
_LUGARES = r"(?:suelo|bano|cocina|pasillo|escaleras?|calle)"
_HUESOS = r"(?:cadera|pierna|brazo|muneca|pie|tobillo|rodilla|femur|hueso)"

_SELF_HARM = (
    r"\bquiero morir(?:me)?\b",
    r"\bme quiero (?:morir|matar)\b",
    r"\bquiero matarme\b",
    r"\bno quiero (?:seguir )?(?:vivir|viviendo)\b",
    r"\bquiero acabar con todo\b",
    r"\bsuicid\w+",
    r"\bquitarme la vida\b",
    r"\bme quiero quitar la vida\b",
    r"\bmejor (?:estaria|estar) muert[oa]\b",
    r"\bcansad[oa] de vivir\b",
    r"\bno quiero despertar(?:me)?\b",
)
_CHEST_PAIN = (
    r"\bme duele (?:\w+ ){0,4}pecho\b",
    rf"\bme duele {_G}corazon\b",
    rf"\bdolor {_G}(?:en|de) {_G}pecho\b",
    rf"\bme aprieta {_G2}pecho\b",
    r"\bopresion\b",
    r"\binfarto\b",
    r"\bataque (?:al|de) corazon\b",
    rf"\b(?:dolor|duele) {_G}brazo izquierdo\b",
)
_BREATHING = (
    rf"\bno (?:puedo|consigo|logro) {_G2}respirar\b",
    r"\bno respiro\b",
    rf"\bme cuesta {_G2}respirar\b",
    r"\bme (?:estoy )?ahog(?:o|ando)\b",
    rf"\bme falta {_G2}aire\b",
    r"\bno me entra (?:el )?aire\b",
    r"\bme (?:he )?atragant(?:ado|e)\b",
)
_FALL = (
    r"\bme (?:he )?caid[oa]\b",
    r"\bme (?:cai|caigo)\b",
    r"\bme (?:he )?vuelto a caer\b",
    r"\bme (?:he )?(?:resbalado|tropezado)\b",
    r"\bme (?:resbale|tropece)\b",
    rf"\bme (?:he dado|di) {_G2}golpe\b",
    rf"\bme he (?:roto|fracturado) {_G2}{_HUESOS}\b",
    rf"\bestoy {_G}en el suelo\b",
    rf"\bestoy tirad[oa] (?:en|por) (?:el|la) {_LUGARES}\b",
    r"\buna caida\b",
    r"\bno me (?:puedo|consigo) (?:\w+ )?(?:levantar|mover)\b",
    r"\bno (?:puedo|consigo|logro) (?:\w+ )?(?:levantarme|moverme)\b",
)
_OTHER = (
    rf"\bno (?:me )?siento {_G2}{_PARTES}\b",
    rf"\bno (?:puedo|consigo) mover {_G2}{_PARTES}\b",
    r"\bse me (?:ha |han )?(?:dormido|adormecido) (?:la |el )?(?:cara|boca|lado)\b",
    rf"\bno puedo {_G2}hablar\b",
    rf"\bme cuesta {_G2}hablar\b",
    r"\bhablo (?:raro|rara)\b",
    r"\bveo doble\b",
    r"\b(?:ictus|derrame)\b",
    r"\bme (?:he )?desmayado\b",
    r"\bme desmaye\b",
    r"\bme (?:he )?mareado\b",
    r"\bme mareo\b",
    r"\bperd(?:ido|i) (?:el )?conocimiento\b",
    r"\b(?:sangre|sangro|sangrando|hemorragia)\b",
    r"\bdolor (?:muy |tan )?(?:fuerte|intenso|insoportable|terrible)\b",
    rf"\bme duele {_G2}muchisimo\b",
    r"\bme (?:voy a morir|muero|estoy muriendo)\b",
    r"\bestoy (?:muy )?grave\b",
    r"\b(?:estoy|me encuentro|me siento) fatal\b",
    r"\bme encuentro muy mal\b",
    r"\b(?:socorro|auxilio|ayuda|ayudame|ayudeme|ayudenme|ayudadme)\b",
    r"\bambulancia\b",
    rf"\bnecesito {_G2}(?:medico|medica|doctor|doctora)\b",
    rf"\bllam\w+ (?:a|al) {_G2}(?:medico|medica|doctor|doctora|112)\b",
)

# Orden = prioridad: autolesión > pecho > respiración > caída > otros.
PATRONES: tuple[tuple[TipoRiesgo, re.Pattern[str]], ...] = tuple(
    (tipo, re.compile("|".join(patrones)))
    for tipo, patrones in (
        (TipoRiesgo.SELF_HARM, _SELF_HARM),
        (TipoRiesgo.CHEST_PAIN, _CHEST_PAIN),
        (TipoRiesgo.BREATHING, _BREATHING),
        (TipoRiesgo.FALL, _FALL),
        (TipoRiesgo.OTHER, _OTHER),
    )
)
