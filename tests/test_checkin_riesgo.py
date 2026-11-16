import pytest

from core.checkin import (
    EstadoCheckin,
    Turno,
    avanzar,
    iniciar,
    turno_de_riesgo_sin_estado,
)
from core.checkin_guion import Paso, Trato
from core.errores import TratoInvalido
from core.interprete import InterpreteReglas
from core.riesgo import TipoRiesgo
from tests.dobles_checkin import InterpreteEspia, InterpreteFijo, InterpreteQueLanza

URGENCIA = (
    "Si es una urgencia, cuelgue y llame al 112 ahora mismo. "
    "Repito: llame al 112. Gracias, Carmen."
)
AUTOLESION = (
    "Siento mucho que se sienta así. Puede llamar ahora al 024, donde le "
    "atenderán a cualquier hora. Si está en peligro, llame al 112. "
    "Gracias por contármelo, Carmen."
)
AUTOLESION_TU = (
    "Siento mucho que te sientas así. Puedes llamar ahora al 024, donde te "
    "atenderán a cualquier hora. Si estás en peligro, llama al 112. "
    "Gracias por contármelo, Carmen."
)


def _avanzar(estado: EstadoCheckin, texto: object, trato: Trato = Trato.USTED) -> Turno:
    return avanzar(estado, texto, InterpreteReglas(), "Carmen", trato)  # type: ignore[arg-type]


@pytest.mark.parametrize("paso", list(Paso))
def test_riesgo_en_cada_paso_sin_llamar_al_interprete(paso: Paso) -> None:
    espia = InterpreteEspia()

    turno = avanzar(
        EstadoCheckin(paso, 0), "Socorro, me he caído", espia, "Carmen", Trato.USTED
    )

    assert espia.llamadas == []
    assert turno.terminado
    assert turno.estado == EstadoCheckin(Paso.FIN, 0)
    assert turno.texto_a_decir == URGENCIA
    assert turno.senal_riesgo is not None
    assert turno.senal_riesgo.kind is TipoRiesgo.FALL


def test_autolesion_usted_y_tu() -> None:
    usted = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "me quiero morir")
    tu = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "me quiero morir", Trato.TU)

    assert usted.texto_a_decir == AUTOLESION
    assert tu.texto_a_decir == AUTOLESION_TU
    assert usted.senal_riesgo is not None
    assert usted.senal_riesgo.kind is TipoRiesgo.SELF_HARM
    assert "buen día" not in usted.texto_a_decir


@pytest.mark.parametrize("nombre", ["", "Ana2", None, 5])
def test_riesgo_con_nombre_invalido_usa_variante_sin_nombre(nombre: object) -> None:
    turno = avanzar(
        EstadoCheckin(Paso.ANIMO_HOY, 0),
        "socorro",
        InterpreteReglas(),
        nombre,  # type: ignore[arg-type]
        Trato.USTED,
    )

    assert turno.senal_riesgo is not None
    assert turno.texto_a_decir.endswith("Repito: llame al 112. Gracias.")


def test_autolesion_con_nombre_invalido_usa_variante_sin_nombre() -> None:
    turno = avanzar(
        EstadoCheckin(Paso.ANIMO_HOY, 0),
        "me quiero morir",
        InterpreteReglas(),
        "",
        Trato.TU,
    )

    assert turno.texto_a_decir.endswith("llama al 112. Gracias por contármelo.")


@pytest.mark.parametrize("texto", [None, 123, b"bien", ["bien"]])
def test_texto_no_str_se_trata_como_vacio(texto: object) -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), texto)

    assert turno.estado == EstadoCheckin(Paso.ANIMO_HOY, 1)
    assert turno.observaciones == ()


def test_la_entrada_se_trunca_a_5000_caracteres() -> None:
    texto = "bien " + "y " * 2600 + "socorro"

    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), texto)

    assert turno.senal_riesgo is None
    assert turno.observaciones[0].value_code == "bien"


def test_riesgo_dentro_de_los_5000_caracteres_se_detecta() -> None:
    texto = "y " * 2000 + "socorro" + " y" * 3000

    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), texto)

    assert turno.senal_riesgo is not None


def test_conversacion_terminada_sin_riesgo_no_dice_nada() -> None:
    turno = _avanzar(EstadoCheckin(Paso.FIN, 0), "bien")

    assert turno.senal_riesgo is None
    assert turno.texto_a_decir == ""


def test_turno_de_riesgo_sin_estado_detecta() -> None:
    turno = turno_de_riesgo_sin_estado("estoy en el suelo", Trato.TU)

    assert turno is not None
    assert turno.terminado
    assert turno.estado == EstadoCheckin(Paso.FIN, 0)
    assert turno.texto_a_decir.endswith("Repito: llama al 112. Gracias.")
    assert turno.senal_riesgo is not None
    assert turno.senal_riesgo.kind is TipoRiesgo.FALL


def test_turno_de_riesgo_sin_estado_autolesion_con_trato_como_texto() -> None:
    turno = turno_de_riesgo_sin_estado("no quiero vivir", "usted")  # type: ignore[arg-type]

    assert turno is not None
    assert "024" in turno.texto_a_decir
    assert turno.texto_a_decir.endswith("Gracias por contármelo.")


@pytest.mark.parametrize("texto", ["bien", "", None, 7])
def test_turno_de_riesgo_sin_estado_sin_riesgo(texto: object) -> None:
    assert turno_de_riesgo_sin_estado(texto, Trato.USTED) is None  # type: ignore[arg-type]


def test_turno_de_riesgo_sin_estado_con_trato_invalido_habla_de_usted() -> None:
    turno = turno_de_riesgo_sin_estado("socorro", "vos")  # type: ignore[arg-type]

    assert turno is not None
    assert "cuelgue" in turno.texto_a_decir


def test_riesgo_con_trato_invalido_habla_de_usted() -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "socorro", None)  # type: ignore[arg-type]

    assert turno.texto_a_decir == URGENCIA


def test_trato_invalido_da_error_de_dominio_sin_reflejarlo() -> None:
    with pytest.raises(TratoInvalido) as error:
        avanzar(
            EstadoCheckin(Paso.ANIMO_HOY, 0),
            "bien",
            InterpreteReglas(),
            "Carmen",
            "SECRETO",  # type: ignore[arg-type]
        )

    assert "SECRETO" not in str(error.value)


def test_trato_invalido_en_iniciar() -> None:
    with pytest.raises(TratoInvalido):
        iniciar("Carmen", None)  # type: ignore[arg-type]


def test_trato_como_texto_se_acepta() -> None:
    turno = iniciar("Carmen", "tu")  # type: ignore[arg-type]

    assert "Te llama" in turno.texto_a_decir


def test_interprete_que_lanza_se_trata_como_no_entendido() -> None:
    turno = avanzar(
        EstadoCheckin(Paso.ANIMO_HOY, 0),
        "bien",
        InterpreteQueLanza(),
        "Carmen",
        Trato.USTED,
    )

    assert turno.estado == EstadoCheckin(Paso.ANIMO_HOY, 1)
    assert turno.observaciones == ()
    assert turno.texto_a_decir.startswith("Perdone, no le he entendido.")


def test_interprete_recibe_pregunta_texto_limpio_y_trato() -> None:
    espia = InterpreteEspia()

    avanzar(EstadoCheckin(Paso.COMIDA, 0), " sí\x00 \n ya ", espia, "Carmen", Trato.TU)

    pregunta, texto, trato = espia.llamadas[0]
    assert pregunta.paso is Paso.COMIDA
    assert texto == "sí ya"
    assert trato is Trato.TU


def test_value_text_se_limpia_aunque_lo_devuelva_otro_interprete() -> None:
    turno = avanzar(
        EstadoCheckin(Paso.QUE_COMIDO, 0),
        "sopa",
        InterpreteFijo("so\x00pa \n y​ fruta"),
        "Carmen",
        Trato.USTED,
    )

    assert turno.observaciones[0].value_text == "sopa y fruta"


def test_texto_libre_que_queda_vacio_tras_limpiar_es_no_entendido() -> None:
    turno = avanzar(
        EstadoCheckin(Paso.QUE_COMIDO, 0),
        "sopa",
        InterpreteFijo("\x00​"),
        "Carmen",
        Trato.USTED,
    )

    assert turno.estado.intentos == 1


def test_verbatim_de_la_observacion_se_limpia() -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "bien\x00,\n gracias")

    assert turno.observaciones[0].verbatim == "bien, gracias"


def test_turno_terminado_se_deriva_del_estado() -> None:
    assert Turno(EstadoCheckin(Paso.FIN), "x").terminado
    assert not Turno(EstadoCheckin(Paso.COMIDA), "x").terminado
