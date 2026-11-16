"""Conversación diaria con la persona mayor: función pura turno a turno.

Lex solo oye y habla; aquí se decide qué decir y qué guardar. El estado viaja
entre turnos en los `sessionAttributes` de Lex (`dict[str, str]`).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from pydantic import TypeAdapter, ValidationError

from core.checkin_guion import (
    GUION,
    TEXTOS,
    VERSION_GUION_CHECKIN,
    Paso,
    Pregunta,
    TipoRespuesta,
    Trato,
)
from core.errores import EstadoInvalido, NombreInvalido, TratoInvalido
from core.interprete import LONGITUD_MAXIMA_TEXTO, Interprete
from core.normalizar import limpiar_texto
from core.riesgo import (
    LONGITUD_MAXIMA_VERBATIM,
    SenalRiesgo,
    TipoRiesgo,
    detectar_riesgo,
)
from core.tipos import NombrePersona

__all__ = [
    "EstadoCheckin",
    "Observacion",
    "Turno",
    "avanzar",
    "hay_estado",
    "iniciar",
    "trato_o_usted",
    "turno_de_riesgo_sin_estado",
]

_NOMBRE = TypeAdapter(NombrePersona)
_CLAVE_VERSION = "checkin_version"
_CLAVE_PASO = "checkin_paso"
_CLAVE_INTENTOS = "checkin_intentos"
_MAX_FALLOS = 1  # fallos de una pregunta antes de pasar a la siguiente
_INTENTOS_VALIDOS = {str(n): n for n in range(_MAX_FALLOS + 1)}
_LONGITUD_MAXIMA_ENTRADA = 5000  # solo para interpretar y guardar, no para el riesgo
_PREFIJO_CLAVES = "checkin_"

_VALORES_ENUM: dict[TipoRespuesta, frozenset[str]] = {
    TipoRespuesta.ANIMO: frozenset({"bien", "regular", "mal"}),
    TipoRespuesta.SI_NO: frozenset({"si", "no"}),
}
_PREGUNTAS = {p.paso: p for p in GUION}


@dataclass(frozen=True)
class EstadoCheckin:
    """Dónde va la conversación: pregunta pendiente e intentos fallidos.

    No guarda respuestas: cada observación sale en el turno en que se da.
    """

    paso: Paso
    intentos: int = 0

    @property
    def terminado(self) -> bool:
        """Indica si la conversación ya acabó."""
        return self.paso is Paso.FIN

    def a_atributos(self) -> dict[str, str]:
        """Serializa a `sessionAttributes` de Lex.

        El handler debe FUSIONAR este diccionario con el resto de los
        `sessionAttributes`, no reemplazarlos. Esos atributos no son de
        confianza: el paso puede manipularse desde fuera. El impacto es de
        integridad de datos (preguntas saltadas o repetidas), no clínico,
        porque el detector de riesgo corre en todos los turnos.
        """
        return {
            _CLAVE_VERSION: VERSION_GUION_CHECKIN,
            _CLAVE_PASO: self.paso.value,
            _CLAVE_INTENTOS: str(self.intentos),
        }

    @classmethod
    def desde_atributos(cls, atributos: Mapping[str, str]) -> "EstadoCheckin":
        """Reconstruye validando; `EstadoInvalido` (sin reflejar nada) si falla."""
        if not isinstance(atributos, Mapping):
            raise EstadoInvalido("Estado de la conversación no válido.")
        version = atributos.get(_CLAVE_VERSION)
        paso = atributos.get(_CLAVE_PASO)
        intentos = atributos.get(_CLAVE_INTENTOS)
        if (
            version != VERSION_GUION_CHECKIN
            or not isinstance(paso, str)
            or paso not in {p.value for p in Paso}
            or not isinstance(intentos, str)
            or intentos not in _INTENTOS_VALIDOS
        ):
            raise EstadoInvalido("Estado de la conversación no válido.")
        return cls(Paso(paso), _INTENTOS_VALIDOS[intentos])


def hay_estado(atributos: Mapping[str, str]) -> bool:
    """Indica si los atributos traen alguna clave `checkin_*`.

    Si no trae ninguna, es una sesión nueva. Si trae alguna pero falta el paso,
    `desde_atributos` lo rechaza como `EstadoInvalido`.
    """
    return any(clave.startswith(_PREFIJO_CLAVES) for clave in atributos)


@dataclass(frozen=True)
class Observacion:
    """Dato a guardar; lleva lo que dijo la persona, que es dato de salud."""

    indicator_code: str
    value_code: str | None = field(repr=False)
    value_text: str | None = field(repr=False)
    verbatim: str = field(repr=False)


@dataclass(frozen=True)
class Turno:
    """Resultado de un turno: qué decir, nuevo estado y qué guardar."""

    estado: EstadoCheckin
    texto_a_decir: str = field(repr=False)
    observaciones: tuple[Observacion, ...] = ()
    senal_riesgo: SenalRiesgo | None = None

    @property
    def terminado(self) -> bool:
        """Indica si la conversación acabó con este turno."""
        return self.estado.terminado


def _nombre_valido(nombre: str) -> str:
    try:
        return _NOMBRE.validate_python(nombre)
    except ValidationError:
        raise NombreInvalido("El nombre no es válido.") from None


def _trato_valido(trato: Trato | str) -> Trato:
    try:
        return Trato(trato)
    except ValueError:
        raise TratoInvalido("El trato no es válido.") from None


def trato_o_usted(trato: Trato | str) -> Trato:
    """Trato válido o, si no lo es, usted."""
    try:
        return _trato_valido(trato)
    except TratoInvalido:
        return Trato.USTED


def _nombre_o_nada(nombre: str) -> str | None:
    try:
        return _nombre_valido(nombre)
    except NombreInvalido:
        return None


def _como_texto(texto: object) -> str:
    """Texto recibido completo: lo que no es `str` cuenta como vacío.

    El detector de riesgo recibe el texto entero: una urgencia dicha al final
    de una transcripción larga no debe perderse.
    """
    return texto if isinstance(texto, str) else ""


def iniciar(nombre: str, trato: Trato) -> Turno:
    """Primer turno: saludo y primera pregunta."""
    trato = _trato_valido(trato)
    saludo = TEXTOS[trato].saludo.format(nombre=_nombre_valido(nombre))
    return Turno(
        estado=EstadoCheckin(GUION[0].paso),
        texto_a_decir=f"{saludo} {GUION[0].texto(trato)}",
    )


def _siguiente(actual: Pregunta, valor: str | None) -> Paso:
    """Siguiente pregunta que aplica tras responder (o saltarse) la actual."""
    pendientes = GUION[GUION.index(actual) + 1 :]
    for pregunta in pendientes:
        if pregunta.solo_si is None or pregunta.solo_si == (actual.paso.value, valor):
            return pregunta.paso
    return Paso.FIN


def _valor_valido(pregunta: Pregunta, valor: str | None) -> str | None:
    """Descarta lo que el intérprete devuelva fuera de lo que admite el guion."""
    if valor is None:
        return None
    if pregunta.tipo is TipoRespuesta.TEXTO_LIBRE:
        return limpiar_texto(valor)[:LONGITUD_MAXIMA_TEXTO].rstrip() or None
    return valor if valor in _VALORES_ENUM[pregunta.tipo] else None


def _observacion(pregunta: Pregunta, valor: str, texto: str) -> Observacion:
    es_texto = pregunta.tipo is TipoRespuesta.TEXTO_LIBRE
    return Observacion(
        indicator_code=pregunta.paso.value,
        value_code=None if es_texto else valor,
        value_text=valor if es_texto else None,
        verbatim=limpiar_texto(texto)[:LONGITUD_MAXIMA_VERBATIM],
    )


def _turno_riesgo(senal: SenalRiesgo, nombre: str | None, trato: Trato) -> Turno:
    textos = TEXTOS[trato]
    es_autolesion = senal.kind is TipoRiesgo.SELF_HARM
    plantilla = textos.autolesion if es_autolesion else textos.urgencia
    if nombre is None:
        texto = plantilla.replace(", {nombre}", "")
    else:
        texto = plantilla.format(nombre=nombre)
    return Turno(
        estado=EstadoCheckin(Paso.FIN), texto_a_decir=texto, senal_riesgo=senal
    )


def turno_de_riesgo_sin_estado(texto: str, trato: Trato) -> Turno | None:
    """Turno de riesgo (sin nombre) si el texto lo tiene; `None` si no.

    Para el handler de Lex cuando `desde_atributos` lanza `EstadoInvalido`:
    el riesgo se atiende igual.
    """
    senal = detectar_riesgo(_como_texto(texto))
    if senal is None:
        return None
    return _turno_riesgo(senal, None, trato_o_usted(trato))


def _decir(paso: Paso, trato: Trato, nombre: str, prefijo: str = "") -> str:
    if paso is Paso.FIN:
        return TEXTOS[trato].despedida.format(nombre=nombre)
    return f"{prefijo}{_PREGUNTAS[paso].texto(trato)}"


def _interpretar(
    interprete: Interprete, pregunta: Pregunta, texto: str, trato: Trato
) -> str | None:
    """Valor válido del intérprete; si lanza o no entiende, `None`."""
    if not texto:
        return None
    try:
        return _valor_valido(pregunta, interprete.interpretar(pregunta, texto, trato))
    except Exception:  # un intérprete roto cuenta como no entendido
        return None


def avanzar(
    estado: EstadoCheckin,
    texto: str,
    interprete: Interprete,
    nombre: str,
    trato: Trato,
) -> Turno:
    """Procesa lo que dijo la persona y devuelve el siguiente turno.

    El detector de riesgo corre lo primero y siempre, también con la
    conversación terminada o con un nombre inválido.
    """
    completo = _como_texto(texto)
    senal = detectar_riesgo(completo)
    if senal is not None:
        return _turno_riesgo(senal, _nombre_o_nada(nombre), trato_o_usted(trato))
    nombre = _nombre_valido(nombre)
    trato = _trato_valido(trato)
    if estado.terminado:
        return Turno(estado=estado, texto_a_decir="")

    pregunta = _PREGUNTAS[estado.paso]
    limpio = limpiar_texto(completo[:_LONGITUD_MAXIMA_ENTRADA])
    valor = _interpretar(interprete, pregunta, limpio, trato)
    if valor is None and estado.intentos < _MAX_FALLOS:
        aviso = f"{TEXTOS[trato].no_entendido} "
        return Turno(
            estado=replace(estado, intentos=estado.intentos + 1),
            texto_a_decir=_decir(estado.paso, trato, nombre, aviso),
        )
    siguiente = _siguiente(pregunta, valor)
    observaciones = () if valor is None else (_observacion(pregunta, valor, limpio),)
    return Turno(
        estado=EstadoCheckin(siguiente),
        texto_a_decir=_decir(siguiente, trato, nombre),
        observaciones=observaciones,
    )
