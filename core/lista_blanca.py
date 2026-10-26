"""Lista blanca de teléfonos a los que se permite llamar."""

from dataclasses import dataclass

from core.errores import ErrorConfiguracion
from core.telefono import es_telefono_e164


def _error_formato(posicion: int) -> ErrorConfiguracion:
    """Error de formato que indica la posición, sin incluir el valor."""
    return ErrorConfiguracion(f"La entrada nº {posicion} no tiene formato E.164.")


@dataclass(frozen=True)
class ListaBlanca:
    """Conjunto inmutable de teléfonos E.164 permitidos."""

    telefonos: frozenset[str]

    def __post_init__(self) -> None:
        """Valida cada teléfono y normaliza a `frozenset`."""
        telefonos = frozenset(self.telefonos)
        if not all(es_telefono_e164(t) for t in telefonos):
            raise ErrorConfiguracion(
                "La lista blanca contiene una entrada sin formato E.164."
            )
        object.__setattr__(self, "telefonos", telefonos)

    @classmethod
    def desde_texto(cls, texto: str) -> "ListaBlanca":
        """Crea la lista desde una cadena separada por comas.

        Lanza `ErrorConfiguracion` si alguna entrada no está en formato E.164
        (el mensaje indica la posición, no el valor). Una cadena vacía da una
        lista vacía que no permite nada.
        """
        entradas = [e.strip() for e in texto.split(",")]
        telefonos = [e for e in entradas if e]
        for posicion, telefono in enumerate(telefonos, start=1):
            if not es_telefono_e164(telefono):
                raise _error_formato(posicion)
        return cls(telefonos=frozenset(telefonos))

    def permite(self, telefono: str) -> bool:
        """Indica si el teléfono está en la lista."""
        return isinstance(telefono, str) and telefono in self.telefonos
