"""Lectura de la configuración de las Lambdas desde variables de entorno."""

from collections.abc import Mapping

from core.errores import ErrorConfiguracion
from core.lista_blanca import ListaBlanca

__all__ = [
    "VAR_LISTA_BLANCA",
    "VAR_LLAMADAS_ACTIVAS",
    "lista_blanca_desde_entorno",
    "llamadas_activas",
]

VAR_LLAMADAS_ACTIVAS = "LLAMADAS_ACTIVAS"
VAR_LISTA_BLANCA = "LISTA_BLANCA"


def llamadas_activas(entorno: Mapping[str, str]) -> bool:
    """Indica si se permite llamar: solo `true` (sin mayúsculas ni espacios).

    Falla cerrado: cualquier otro valor, o la ausencia, es desactivado.
    """
    return entorno.get(VAR_LLAMADAS_ACTIVAS, "").strip().lower() == "true"


def lista_blanca_desde_entorno(entorno: Mapping[str, str]) -> ListaBlanca:
    """Crea la lista blanca desde `LISTA_BLANCA` (teléfonos separados por comas).

    La variable debe existir (puede estar vacía: no permite nada). Las entradas
    que no son E.164 se rechazan con `ErrorConfiguracion`, no se corrigen.
    """
    if VAR_LISTA_BLANCA not in entorno:
        raise ErrorConfiguracion(f"Falta la variable {VAR_LISTA_BLANCA}.")
    return ListaBlanca.desde_texto(entorno[VAR_LISTA_BLANCA])
