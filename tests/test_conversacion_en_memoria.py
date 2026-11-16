import pytest

from adapters.conversacion_en_memoria import (
    ContextoEnMemoria,
    RegistroSinPersistencia,
)
from core.checkin import EstadoCheckin, Turno
from core.checkin_guion import Paso, Trato
from core.errores import ErrorConfiguracion

CALL_ID = "0b6c1f0e-1111-4222-8333-444455556666"


def test_devuelve_nombre_y_trato_del_entorno() -> None:
    contexto = ContextoEnMemoria.desde_entorno(
        {"DEMO_PERSONA_NOMBRE": "Marisol", "DEMO_TRATO": "tu"}
    )

    datos = contexto.datos(CALL_ID)

    assert datos is not None
    assert datos.nombre == "Marisol"
    assert datos.trato is Trato.TU


def test_el_trato_por_defecto_es_usted() -> None:
    contexto = ContextoEnMemoria.desde_entorno({"DEMO_PERSONA_NOMBRE": "Marisol"})

    datos = contexto.datos(CALL_ID)

    assert datos is not None
    assert datos.trato is Trato.USTED


@pytest.mark.parametrize("call_id", ["", "   "])
def test_sin_call_id_no_hay_datos(call_id: str) -> None:
    contexto = ContextoEnMemoria.desde_entorno({"DEMO_PERSONA_NOMBRE": "Marisol"})

    assert contexto.datos(call_id) is None


@pytest.mark.parametrize(
    ("entorno", "variable"),
    [
        ({}, "DEMO_PERSONA_NOMBRE"),
        ({"DEMO_PERSONA_NOMBRE": "Ana2"}, "DEMO_PERSONA_NOMBRE"),
        ({"DEMO_PERSONA_NOMBRE": "Ana", "DEMO_TRATO": "vos"}, "DEMO_TRATO"),
    ],
)
def test_configuracion_invalida_nombra_la_variable_sin_su_valor(
    entorno: dict[str, str], variable: str
) -> None:
    with pytest.raises(ErrorConfiguracion) as info:
        ContextoEnMemoria.desde_entorno(entorno)

    assert variable in str(info.value)
    assert "Ana2" not in str(info.value)
    assert "vos" not in str(info.value)


def test_el_registro_sin_persistencia_acepta_turnos() -> None:
    turno = Turno(estado=EstadoCheckin(Paso.FIN), texto_a_decir="")

    assert RegistroSinPersistencia().guardar_turno(CALL_ID, turno) is None
