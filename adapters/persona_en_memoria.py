"""Repositorio de personas en memoria: solo la persona de demostración."""

from collections.abc import Mapping
from typing import Self

from pydantic import ValidationError

from core.errores import ErrorConfiguracion, PersonaNoEncontrada
from core.persona import Persona

__all__ = ["PERSONA_DEMO_ID", "PersonaEnMemoria"]

PERSONA_DEMO_ID = "demo-01"

_VAR_PERSONA = "DEMO_PERSONA_NOMBRE"
_VAR_FAMILIAR = "DEMO_FAMILIAR_NOMBRE"
_VAR_TELEFONO = "DEMO_FAMILIAR_TELEFONO"
_VARIABLES = (_VAR_PERSONA, _VAR_FAMILIAR, _VAR_TELEFONO)
# Ruta (`loc`) del error de pydantic -> variable de entorno de origen.
_VARIABLE_POR_CAMPO = {
    ("nombre",): _VAR_PERSONA,
    ("familiar", "nombre"): _VAR_FAMILIAR,
    ("familiar", "telefono"): _VAR_TELEFONO,
}


class PersonaEnMemoria:
    """Implementa `PersonaRepository` conociendo solo a `demo-01`."""

    def __init__(self, persona: Persona) -> None:
        """Guarda la persona de demostración."""
        self._persona = persona

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> Self:
        """Construye el repositorio con las variables `DEMO_*` de `entorno`.

        Lanza `ErrorConfiguracion` nombrando la variable, nunca su valor.
        """
        for variable in _VARIABLES:
            if variable not in entorno:
                raise ErrorConfiguracion(f"Falta la variable {variable}.")
        try:
            persona = Persona.model_validate(
                {
                    "persona_id": PERSONA_DEMO_ID,
                    "nombre": entorno[_VAR_PERSONA],
                    "familiar": {
                        "nombre": entorno[_VAR_FAMILIAR],
                        "telefono": entorno[_VAR_TELEFONO],
                    },
                }
            )
        except ValidationError as error:
            variable = _variable_invalida(error)
        else:
            return cls(persona)
        raise ErrorConfiguracion(f"La variable {variable} no es válida.")

    def obtener(self, persona_id: str) -> Persona:
        """Devuelve la persona demo o lanza `PersonaNoEncontrada`."""
        if persona_id != PERSONA_DEMO_ID:
            raise PersonaNoEncontrada("La persona indicada no existe.")
        return self._persona


def _variable_invalida(error: ValidationError) -> str:
    """Variable de entorno del primer campo inválido, sin mirar los valores."""
    ruta = tuple(str(parte) for parte in error.errors()[0]["loc"])
    return _VARIABLE_POR_CAMPO[ruta]
