"""Lectura de la configuración de las Lambdas desde variables de entorno."""

from collections.abc import Mapping

from adapters.aurora import VARIABLES_AURORA
from core.alerta import ReglasAviso
from core.errores import ErrorConfiguracion
from core.lista_blanca import ListaBlanca

__all__ = [
    "ANTIGUEDAD_POR_DEFECTO_SEGUNDOS",
    "ANTIGUEDAD_TOPE_SEGUNDOS",
    "VAR_ANTIGUEDAD_MAXIMA",
    "VAR_DEMO_ACTIVA",
    "VAR_LISTA_BLANCA",
    "VAR_LLAMADAS_ACTIVAS",
    "VAR_REGLAS_SIEMPRE",
    "aurora_configurada",
    "demo_activa",
    "lista_blanca_desde_entorno",
    "llamadas_activas",
    "reglas_desde_entorno",
]

VAR_LLAMADAS_ACTIVAS = "LLAMADAS_ACTIVAS"
VAR_LISTA_BLANCA = "LISTA_BLANCA"
VAR_DEMO_ACTIVA = "DEMO_ACTIVA"
VAR_ANTIGUEDAD_MAXIMA = "ANTIGUEDAD_MAXIMA_SEGUNDOS"
VAR_REGLAS_SIEMPRE = "REGLAS_SIEMPRE"
ANTIGUEDAD_POR_DEFECTO_SEGUNDOS = 900
# Igual que el máximo de la plantilla SAM (un día).
ANTIGUEDAD_TOPE_SEGUNDOS = 86400
# Un texto más largo que el tope ya no cabe: se rechaza antes de `int()`.
_MAX_CIFRAS_ANTIGUEDAD = len(str(ANTIGUEDAD_TOPE_SEGUNDOS)) + 1


def llamadas_activas(entorno: Mapping[str, str]) -> bool:
    """Indica si se permite llamar: solo `true` (sin mayúsculas ni espacios).

    Falla cerrado: cualquier otro valor, o la ausencia, es desactivado.
    """
    return entorno.get(VAR_LLAMADAS_ACTIVAS, "").strip().lower() == "true"


def aurora_configurada(entorno: Mapping[str, str]) -> bool:
    """Indica si hay alguna variable `DB_*` con valor (se quiere usar Aurora).

    Con alguna basta: si faltan otras, el adaptador falla nombrándolas, en vez
    de caer en silencio a la memoria.
    """
    return any(entorno.get(variable, "").strip() for variable in VARIABLES_AURORA)


def demo_activa(entorno: Mapping[str, str]) -> bool:
    """Indica si la demo temporal está encendida: solo `true` exacto.

    Falla cerrado: cualquier otro valor, o la ausencia, es apagada.
    """
    return entorno.get(VAR_DEMO_ACTIVA, "").strip().lower() == "true"


def lista_blanca_desde_entorno(entorno: Mapping[str, str]) -> ListaBlanca:
    """Crea la lista blanca desde `LISTA_BLANCA` (teléfonos separados por comas).

    La variable debe existir (puede estar vacía: no permite nada). Las entradas
    que no son E.164 se rechazan con `ErrorConfiguracion`, no se corrigen.
    """
    if VAR_LISTA_BLANCA not in entorno:
        raise ErrorConfiguracion(f"Falta la variable {VAR_LISTA_BLANCA}.")
    return ListaBlanca.desde_texto(entorno[VAR_LISTA_BLANCA])


def _antiguedad_maxima(entorno: Mapping[str, str]) -> int:
    """Lee la antigüedad máxima: entero de 1 a `ANTIGUEDAD_TOPE_SEGUNDOS`."""
    if VAR_ANTIGUEDAD_MAXIMA not in entorno:
        return ANTIGUEDAD_POR_DEFECTO_SEGUNDOS
    texto = entorno[VAR_ANTIGUEDAD_MAXIMA].strip()
    valido = (
        len(texto) <= _MAX_CIFRAS_ANTIGUEDAD
        and texto.isascii()
        and texto.isdigit()
        and 0 < int(texto) <= ANTIGUEDAD_TOPE_SEGUNDOS
    )
    if not valido:
        raise ErrorConfiguracion(
            f"La variable {VAR_ANTIGUEDAD_MAXIMA} debe ser un entero entre 1 y "
            f"{ANTIGUEDAD_TOPE_SEGUNDOS}."
        )
    return int(texto)


def reglas_desde_entorno(entorno: Mapping[str, str]) -> ReglasAviso:
    """Crea las reglas de aviso desde `ANTIGUEDAD_MAXIMA_SEGUNDOS` y `REGLAS_SIEMPRE`.

    Ambas son opcionales (900 s y ninguna regla). Los errores nombran la
    variable, nunca su valor.
    """
    antiguedad = _antiguedad_maxima(entorno)
    crudas = entorno.get(VAR_REGLAS_SIEMPRE, "").split(",")
    reglas = frozenset(r.strip() for r in crudas if r.strip())
    try:
        return ReglasAviso(reglas, antiguedad)
    except ErrorConfiguracion:
        raise ErrorConfiguracion(
            f"La variable {VAR_REGLAS_SIEMPRE} no es válida."
        ) from None
