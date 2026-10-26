"""Excepciones del dominio del callbot."""

from typing import ClassVar


class ErrorCallbot(Exception):  # noqa: N818 (nombre de dominio en español)
    """Base de los errores del dominio.

    El handler devuelve al cliente solo el `codigo` y un texto fijo, nunca
    `str(e)`: el mensaje es para los logs y puede mencionar datos internos.
    """

    codigo: ClassVar[str] = "error_callbot"


class AvisoInvalido(ErrorCallbot):
    """El aviso recibido no cumple el formato esperado."""

    codigo = "aviso_invalido"


class PersonaNoEncontrada(ErrorCallbot):
    """No existe la persona indicada en el aviso."""

    codigo = "persona_no_encontrada"


class TelefonoNoPermitido(ErrorCallbot):
    """El teléfono del familiar no está en la lista blanca."""

    codigo = "telefono_no_permitido"


class ErrorConnect(ErrorCallbot):
    """Fallo al pedir la llamada a Amazon Connect (lo lanza el adaptador)."""

    codigo = "error_connect"


class ErrorConfiguracion(ErrorCallbot):
    """La configuración de la aplicación es incorrecta."""

    codigo = "error_configuracion"
