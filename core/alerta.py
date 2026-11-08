"""Alerta de VitaPlus y reglas que deciden si merece un aviso (decisión 29)."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from core.errores import ErrorConfiguracion
from core.tipos import NombrePersona, ReglaId, Uuid

__all__ = ["SEVERIDAD_CRITICA", "Alerta", "ReglasAviso", "es_grave", "es_reciente"]

SEVERIDAD_CRITICA = "critical"

_REGLA = TypeAdapter(ReglaId)

# Las mismas que admite el CHECK de `callbot_call.alert_severity`.
Severidad = Literal["info", "low", "medium", "high", "critical"]


class Alerta(BaseModel):
    """Alerta abierta, leída de `callbot_open_alert` con el nombre de la persona."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    alert_id: Uuid
    person_id: Uuid
    rule_id: ReglaId
    severity: Severidad
    # Negativa si el reloj de quien abrió la alerta va adelantado: cuenta como
    # reciente (ante la duda, mejor avisar de un SOS).
    antiguedad_segundos: int
    persona_nombre: NombrePersona = Field(repr=False)


@dataclass(frozen=True)
class ReglasAviso:
    """Qué alertas avisan: las críticas, las de `reglas_siempre` y no antiguas."""

    reglas_siempre: frozenset[str]
    antiguedad_maxima_segundos: int

    def __post_init__(self) -> None:
        """Valida el límite y cada regla, y normaliza las reglas a `frozenset`."""
        if self.antiguedad_maxima_segundos <= 0:
            raise ErrorConfiguracion("La antigüedad máxima tiene que ser positiva.")
        reglas = frozenset(self.reglas_siempre)
        if not all(_es_regla_valida(r) for r in reglas):
            raise ErrorConfiguracion("La lista de reglas tiene una regla no válida.")
        object.__setattr__(self, "reglas_siempre", reglas)


def _es_regla_valida(regla: object) -> bool:
    """Indica si `regla` cumple el formato de `ReglaId`."""
    try:
        _REGLA.validate_python(regla)
    except ValidationError:
        return False
    return True


def es_grave(alerta: Alerta, reglas: ReglasAviso) -> bool:
    """Indica si la alerta es crítica o de una regla que siempre avisa."""
    return (
        alerta.severity == SEVERIDAD_CRITICA or alerta.rule_id in reglas.reglas_siempre
    )


def es_reciente(alerta: Alerta, reglas: ReglasAviso) -> bool:
    """Indica si la alerta no supera la antigüedad máxima."""
    return alerta.antiguedad_segundos <= reglas.antiguedad_maxima_segundos
