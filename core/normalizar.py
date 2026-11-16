"""Limpieza y normalización de lo que dice la persona mayor."""

import string
import unicodedata
from collections.abc import Iterator

__all__ = ["limpiar_texto", "normalizar", "normalizar_con_posiciones"]

_CATEGORIAS_PROHIBIDAS = frozenset({"Cc", "Cf", "Cs", "Cn"})
_ALFANUMERICOS = frozenset(string.ascii_lowercase + string.digits)


def limpiar_texto(texto: str) -> str:
    """Quita caracteres de control y de formato y colapsa los espacios."""
    visibles = (
        " " if c.isspace() else c
        for c in texto
        if c.isspace() or unicodedata.category(c) not in _CATEGORIAS_PROHIBIDAS
    )
    return " ".join("".join(visibles).split())


def _caracteres(texto: str) -> Iterator[tuple[int, str]]:
    """Pares (posición original, carácter normalizado o espacio)."""
    for posicion, caracter in enumerate(texto):
        if caracter.isspace():
            yield posicion, " "
        elif unicodedata.category(caracter) not in _CATEGORIAS_PROHIBIDAS:
            for parte in unicodedata.normalize("NFKD", caracter.lower()):
                if not unicodedata.combining(parte):
                    yield posicion, parte if parte in _ALFANUMERICOS else " "


def normalizar_con_posiciones(texto: str) -> tuple[str, tuple[int, ...]]:
    """Como `normalizar`, más la posición original de cada carácter."""
    letras: list[str] = []
    posiciones: list[int] = []
    for posicion, caracter in _caracteres(texto):
        if caracter == " " and (not letras or letras[-1] == " "):
            continue
        letras.append(caracter)
        posiciones.append(posicion)
    if letras and letras[-1] == " ":
        letras.pop()
        posiciones.pop()
    return "".join(letras), tuple(posiciones)


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin puntuación y con espacios simples."""
    return normalizar_con_posiciones(texto)[0]
