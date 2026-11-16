import logging

import pytest

from core.checkin import EstadoCheckin
from core.checkin_guion import TEXTOS, Paso, Trato
from core.conversar import ServicioConversacion
from core.interprete import Interprete, InterpreteReglas
from core.puertos_checkin import (
    ContextoConversacion,
    DatosConversacion,
    RegistroCheckin,
)
from core.riesgo import TipoRiesgo
from tests.dobles_checkin import (
    ContextoFijo,
    ContextoQueLanza,
    InterpreteEspia,
    RegistroEnMemoria,
    RegistroQueLanza,
)

CALL_ID = "0b6c1f0e-1111-4222-8333-444455556666"
DATOS = DatosConversacion(nombre="Marisol", trato=Trato.USTED)
ESTADO_COMIDA = EstadoCheckin(Paso.COMIDA).a_atributos()
URGENCIA_SIN_NOMBRE = TEXTOS[Trato.USTED].urgencia.replace(", {nombre}", "")


def _servicio(
    contexto: ContextoConversacion | None = None,
    registro: RegistroCheckin | None = None,
    interprete: Interprete | None = None,
) -> ServicioConversacion:
    return ServicioConversacion(
        contexto or ContextoFijo(DATOS),
        registro or RegistroEnMemoria(),
        interprete or InterpreteReglas(),
    )


@pytest.fixture(autouse=True)
def _logs_del_core_hacia_caplog(monkeypatch: pytest.MonkeyPatch) -> None:
    """El handler de Lambda redirige el logger `core`; aquí vuelve a `logging`."""
    nucleo = logging.getLogger("core")
    monkeypatch.setattr(nucleo, "handlers", [])
    monkeypatch.setattr(nucleo, "propagate", True)


def test_sin_estado_saluda_y_hace_la_primera_pregunta() -> None:
    registro = RegistroEnMemoria()

    turno = _servicio(registro=registro).responder(CALL_ID, {}, "")

    assert "Hola, Marisol" in turno.texto_a_decir
    assert "¿Qué tal se encuentra hoy?" in turno.texto_a_decir
    assert turno.estado.paso is Paso.ANIMO_HOY
    assert registro.turnos == [(CALL_ID, turno)]


def test_sin_estado_con_riesgo_atiende_la_urgencia_sin_interprete() -> None:
    espia = InterpreteEspia()

    turno = _servicio(interprete=espia).responder(CALL_ID, {}, "me he caído")

    assert turno.senal_riesgo is not None
    assert turno.senal_riesgo.kind is TipoRiesgo.FALL
    assert turno.texto_a_decir == URGENCIA_SIN_NOMBRE
    assert turno.terminado
    assert espia.llamadas == []


def test_con_estado_valido_avanza_y_guarda_el_turno() -> None:
    registro = RegistroEnMemoria()

    turno = _servicio(registro=registro).responder(
        CALL_ID, ESTADO_COMIDA, "sí, ya he comido"
    )

    assert turno.estado.paso is Paso.QUE_COMIDO
    assert [o.indicator_code for o in turno.observaciones] == ["comida_tomada"]
    assert registro.turnos == [(CALL_ID, turno)]


def test_estado_manipulado_con_riesgo_atiende_la_urgencia_sin_nombre() -> None:
    turno = _servicio().responder(
        CALL_ID, {"checkin_paso": "hackeado"}, "me duele el pecho"
    )

    assert turno.senal_riesgo is not None
    assert "112" in turno.texto_a_decir
    assert "Marisol" not in turno.texto_a_decir


def test_estado_manipulado_sin_riesgo_cierra_con_el_texto_de_error() -> None:
    turno = _servicio().responder(CALL_ID, {"checkin_paso": "hackeado"}, "bien")

    assert turno.texto_a_decir == TEXTOS[Trato.USTED].cierre_error
    assert turno.terminado
    assert turno.senal_riesgo is None


@pytest.mark.parametrize("contexto", [ContextoFijo(None), ContextoQueLanza()])
def test_sin_contexto_el_riesgo_se_atiende_en_usted(
    contexto: ContextoConversacion,
) -> None:
    turno = _servicio(contexto=contexto).responder(CALL_ID, {}, "no puedo respirar")

    assert turno.senal_riesgo is not None
    assert turno.texto_a_decir == URGENCIA_SIN_NOMBRE


@pytest.mark.parametrize("contexto", [ContextoFijo(None), ContextoQueLanza()])
def test_sin_contexto_y_sin_riesgo_cierra_con_el_texto_de_error(
    contexto: ContextoConversacion,
) -> None:
    turno = _servicio(contexto=contexto).responder(CALL_ID, ESTADO_COMIDA, "bien")

    assert turno.texto_a_decir == TEXTOS[Trato.USTED].cierre_error
    assert turno.terminado


def test_nombre_invalido_sin_riesgo_cierra_con_el_texto_de_error() -> None:
    datos = DatosConversacion(nombre="Ana2", trato=Trato.TU)
    servicio = _servicio(contexto=ContextoFijo(datos))

    inicio = servicio.responder(CALL_ID, {}, "")
    avance = servicio.responder(CALL_ID, ESTADO_COMIDA, "sí")

    assert inicio.texto_a_decir == TEXTOS[Trato.TU].cierre_error
    assert avance.texto_a_decir == TEXTOS[Trato.TU].cierre_error


def test_trato_invalido_se_trata_de_usted() -> None:
    datos = DatosConversacion(nombre="Marisol", trato="vos")  # type: ignore[arg-type]

    turno = _servicio(contexto=ContextoFijo(datos)).responder(CALL_ID, {}, "")

    assert turno.texto_a_decir.startswith("Hola, Marisol. Le llama")


def test_si_guardar_falla_se_devuelve_el_turno_y_se_registra_sin_datos(
    caplog: pytest.LogCaptureFixture,
) -> None:
    servicio = _servicio(registro=RegistroQueLanza())

    with caplog.at_level(logging.WARNING):
        turno = servicio.responder(CALL_ID, ESTADO_COMIDA, "sí, he comido pan")

    salida = caplog.text
    assert turno.estado.paso is Paso.QUE_COMIDO
    assert "ErrorBaseDatos" in salida
    assert "pan" not in salida
    assert "Marisol" not in salida


def test_conversacion_terminada_devuelve_texto_vacio() -> None:
    atributos = EstadoCheckin(Paso.FIN).a_atributos()

    turno = _servicio().responder(CALL_ID, atributos, "hola")

    assert turno.texto_a_decir == ""
    assert turno.terminado


def test_un_fallo_inesperado_en_el_turno_no_lanza_y_mantiene_el_trato(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError("fallo con zanahoria")

    monkeypatch.setattr("core.conversar.avanzar", _rompe)
    datos = DatosConversacion(nombre="Marisol", trato=Trato.TU)
    registro = RegistroEnMemoria()
    servicio = _servicio(contexto=ContextoFijo(datos), registro=registro)

    with caplog.at_level(logging.WARNING):
        turno = servicio.responder(CALL_ID, ESTADO_COMIDA, "bien")

    assert turno.texto_a_decir == TEXTOS[Trato.TU].cierre_error
    assert registro.turnos == [(CALL_ID, turno)]
    salida = caplog.text
    assert "RuntimeError" in salida
    assert "zanahoria" not in salida


def test_un_fallo_inesperado_en_el_turno_atiende_el_riesgo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _rompe(*_: object, **__: object) -> None:
        raise RuntimeError("fallo")

    monkeypatch.setattr("core.conversar.avanzar", _rompe)

    turno = _servicio().responder(CALL_ID, ESTADO_COMIDA, "no puedo respirar")

    assert turno.senal_riesgo is not None
    assert turno.texto_a_decir == URGENCIA_SIN_NOMBRE


def test_un_estado_con_claves_checkin_pero_sin_paso_cierra_con_error() -> None:
    interprete = InterpreteEspia()

    turno = _servicio(interprete=interprete).responder(
        CALL_ID, {"checkin_intentos": "0"}, "bien"
    )

    assert turno.texto_a_decir == TEXTOS[Trato.USTED].cierre_error
    assert interprete.llamadas == []
