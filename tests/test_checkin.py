import pytest

from core.checkin import (
    EstadoCheckin,
    Observacion,
    Turno,
    avanzar,
    hay_estado,
    iniciar,
    trato_o_usted,
)
from core.checkin_guion import TEXTOS, VERSION_GUION_CHECKIN, Paso, Trato
from core.errores import EstadoInvalido, NombreInvalido
from core.interprete import InterpreteReglas
from core.riesgo import TipoRiesgo
from tests.dobles_checkin import InterpreteEspia, InterpreteFijo

URGENCIA = (
    "Si es una urgencia, cuelgue y llame al 112 ahora mismo. "
    "Repito: llame al 112. Gracias, Carmen."
)
URGENCIA_TU = (
    "Si es una urgencia, cuelga y llama al 112 ahora mismo. "
    "Repito: llama al 112. Gracias, Carmen."
)
DESPEDIDA = "Muchas gracias, Carmen. Que tenga un buen día. Hasta mañana."


def _avanzar(estado: EstadoCheckin, texto: str, trato: Trato = Trato.USTED) -> Turno:
    return avanzar(estado, texto, InterpreteReglas(), "Carmen", trato)


def test_version_del_guion() -> None:
    assert VERSION_GUION_CHECKIN == "checkin-v1"


def test_iniciar_usted_saluda_y_pregunta() -> None:
    turno = iniciar("Carmen", Trato.USTED)

    assert turno.texto_a_decir == (
        "Hola, Carmen. Le llama el asistente automático de VitaPlus para saber "
        "qué tal está. ¿Qué tal se encuentra hoy?"
    )
    assert turno.estado == EstadoCheckin(Paso.ANIMO_HOY, 0)
    assert not turno.terminado
    assert turno.observaciones == ()
    assert turno.senal_riesgo is None


def test_iniciar_tu() -> None:
    turno = iniciar("Carmen", Trato.TU)

    assert turno.texto_a_decir == (
        "Hola, Carmen. Te llama el asistente automático de VitaPlus para saber "
        "qué tal estás. ¿Qué tal te encuentras hoy?"
    )


@pytest.mark.parametrize("nombre", ["", "   ", "Ana2", "Ana\x00"])
def test_iniciar_rechaza_nombre_invalido(nombre: str) -> None:
    with pytest.raises(NombreInvalido):
        iniciar(nombre, Trato.USTED)


def test_avanzar_rechaza_nombre_invalido() -> None:
    with pytest.raises(NombreInvalido):
        avanzar(
            EstadoCheckin(Paso.ANIMO_HOY, 0), "bien", InterpreteReglas(), "", Trato.TU
        )


def test_nombre_se_recorta() -> None:
    assert "Hola, Carmen." in iniciar("  Carmen ", Trato.USTED).texto_a_decir


def test_recorrido_completo_con_comida() -> None:
    turno = iniciar("Carmen", Trato.USTED)

    turno = _avanzar(turno.estado, "Muy bien, gracias")
    assert turno.texto_a_decir == "¿Y qué tal ha ido la semana?"
    assert turno.observaciones == (
        Observacion("animo_hoy", "bien", None, "Muy bien, gracias"),
    )

    turno = _avanzar(turno.estado, "regular")
    assert turno.texto_a_decir == "¿Ha comido hoy?"

    turno = _avanzar(turno.estado, "Sí, ya he comido")
    assert turno.texto_a_decir == "¿Qué ha comido?"
    assert turno.observaciones[0].value_code == "si"

    turno = _avanzar(turno.estado, "Un poco de sopa y fruta")
    assert turno.texto_a_decir == DESPEDIDA
    assert turno.terminado
    assert turno.estado.terminado
    assert turno.observaciones == (
        Observacion(
            "que_ha_comido", None, "Un poco de sopa y fruta", "Un poco de sopa y fruta"
        ),
    )
    assert turno.senal_riesgo is None


def test_sin_comida_salta_la_pregunta_de_que_ha_comido() -> None:
    estado = EstadoCheckin(Paso.COMIDA, 0)

    turno = _avanzar(estado, "todavía no")

    assert turno.terminado
    assert turno.texto_a_decir == DESPEDIDA
    assert turno.observaciones == (
        Observacion("comida_tomada", "no", None, "todavía no"),
    )


def test_despedida_tu() -> None:
    turno = _avanzar(EstadoCheckin(Paso.COMIDA, 0), "no", Trato.TU)

    assert turno.texto_a_decir == (
        "Muchas gracias, Carmen. Que tengas un buen día. Hasta mañana."
    )


def test_no_entendido_repite_con_disculpa_una_vez() -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "el tiempo está raro")

    assert (
        turno.texto_a_decir == "Perdone, no le he entendido. ¿Qué tal se encuentra hoy?"
    )
    assert turno.estado == EstadoCheckin(Paso.ANIMO_HOY, 1)
    assert turno.observaciones == ()
    assert not turno.terminado


def test_no_entendido_tu() -> None:
    turno = _avanzar(EstadoCheckin(Paso.COMIDA, 0), "mmm", Trato.TU)

    assert turno.texto_a_decir == "Perdona, no te he entendido. ¿Has comido hoy?"


def test_segundo_fallo_pasa_a_la_siguiente_sin_observacion() -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 1), "no sé qué decir")

    assert turno.texto_a_decir == "¿Y qué tal ha ido la semana?"
    assert turno.estado == EstadoCheckin(Paso.ANIMO_SEMANA, 0)
    assert turno.observaciones == ()


def test_segundo_fallo_en_comida_termina() -> None:
    turno = _avanzar(EstadoCheckin(Paso.COMIDA, 1), "eh")

    assert turno.terminado
    assert turno.observaciones == ()


@pytest.mark.parametrize("texto", ["", "   ", "\n"])
def test_silencio_cuenta_como_no_entendido(texto: str) -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), texto)

    assert turno.estado == EstadoCheckin(Paso.ANIMO_HOY, 1)
    assert turno.texto_a_decir.startswith("Perdone, no le he entendido.")


def test_silencio_no_llama_al_interprete() -> None:
    espia = InterpreteEspia()

    turno = avanzar(EstadoCheckin(Paso.COMIDA, 0), " \x00", espia, "Carmen", Trato.TU)

    assert turno.estado.intentos == 1
    assert espia.llamadas == []


def test_valor_fuera_del_guion_del_interprete_se_trata_como_no_entendido() -> None:
    turno = avanzar(
        EstadoCheckin(Paso.ANIMO_HOY, 0),
        "bien",
        InterpreteFijo("excelente"),
        "Carmen",
        Trato.USTED,
    )

    assert turno.estado.intentos == 1
    assert turno.observaciones == ()


def test_texto_libre_del_interprete_se_recorta_otra_vez() -> None:
    turno = avanzar(
        EstadoCheckin(Paso.QUE_COMIDO, 0),
        "x",
        InterpreteFijo("a" * 500),
        "Carmen",
        Trato.USTED,
    )

    assert turno.observaciones[0].value_text == "a" * 200


def test_verbatim_se_recorta_a_mil() -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "bien " + "y" * 2000)

    assert len(turno.observaciones[0].verbatim) == 1000


@pytest.mark.parametrize("paso", [Paso.ANIMO_HOY, Paso.COMIDA, Paso.QUE_COMIDO])
def test_riesgo_en_cualquier_turno_termina(paso: Paso) -> None:
    turno = _avanzar(EstadoCheckin(paso, 0), "Me he caído en el baño")

    assert turno.texto_a_decir == URGENCIA
    assert turno.terminado
    assert turno.observaciones == ()
    assert turno.senal_riesgo is not None
    assert turno.senal_riesgo.kind is TipoRiesgo.FALL
    assert turno.senal_riesgo.verbatim == "Me he caído en el baño"


def test_riesgo_tu() -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "socorro", Trato.TU)

    assert turno.texto_a_decir == URGENCIA_TU


def test_riesgo_gana_a_la_interpretacion() -> None:
    turno = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "bien pero no puedo respirar")

    assert turno.senal_riesgo is not None
    assert turno.senal_riesgo.kind is TipoRiesgo.BREATHING
    assert turno.observaciones == ()


def test_conversacion_terminada_no_avanza() -> None:
    turno = _avanzar(EstadoCheckin(Paso.FIN, 0), "hola")

    assert turno.terminado
    assert turno.texto_a_decir == ""
    assert turno.observaciones == ()


def test_repr_no_expone_la_frase_ni_el_texto() -> None:
    turno = _avanzar(EstadoCheckin(Paso.QUE_COMIDO, 0), "lentejas")
    riesgo = _avanzar(EstadoCheckin(Paso.ANIMO_HOY, 0), "me he caído")

    assert "lentejas" not in repr(turno.observaciones)
    assert riesgo.senal_riesgo is not None
    assert "caído" not in repr(riesgo.senal_riesgo)


def test_atributos_ida_y_vuelta() -> None:
    estado = EstadoCheckin(Paso.COMIDA, 1)

    atributos = estado.a_atributos()

    assert atributos == {
        "checkin_version": "checkin-v1",
        "checkin_paso": "comida_tomada",
        "checkin_intentos": "1",
    }
    assert EstadoCheckin.desde_atributos(atributos) == estado


def test_atributos_extra_de_otros_se_ignoran() -> None:
    atributos = {**EstadoCheckin(Paso.FIN, 0).a_atributos(), "otro": "x"}

    assert EstadoCheckin.desde_atributos(atributos).terminado


@pytest.mark.parametrize(
    "atributos",
    [
        {},
        {"checkin_version": "checkin-v1"},
        {"checkin_version": "v0", "checkin_paso": "animo_hoy", "checkin_intentos": "0"},
        {"checkin_version": "checkin-v1", "checkin_paso": "x", "checkin_intentos": "0"},
        {
            "checkin_version": "checkin-v1",
            "checkin_paso": "animo_hoy",
            "checkin_intentos": "2",
        },
        {
            "checkin_version": "checkin-v1",
            "checkin_paso": "animo_hoy",
            "checkin_intentos": "-1",
        },
        {
            "checkin_version": "checkin-v1",
            "checkin_paso": None,
            "checkin_intentos": "0",
        },
        {
            "checkin_version": "checkin-v1",
            "checkin_paso": "animo_hoy",
            "checkin_intentos": 0,
        },
        None,
        "texto",
    ],
)
def test_atributos_rotos_dan_error_de_dominio_sin_reflejar(atributos: object) -> None:
    with pytest.raises(EstadoInvalido) as error:
        EstadoCheckin.desde_atributos(atributos)  # type: ignore[arg-type]

    assert "animo_hoy" not in str(error.value)


def test_atributos_manipulados_no_se_reflejan_en_el_error() -> None:
    atributos = {
        "checkin_version": "checkin-v1",
        "checkin_paso": "SECRETO-X",
        "checkin_intentos": "0",
    }

    with pytest.raises(EstadoInvalido) as error:
        EstadoCheckin.desde_atributos(atributos)

    assert "SECRETO" not in str(error.value)


def test_hay_estado_detecta_la_clave_del_paso() -> None:
    assert hay_estado({}) is False
    assert hay_estado({"otra": "x"}) is False
    assert hay_estado(EstadoCheckin(Paso.COMIDA).a_atributos()) is True
    assert hay_estado({"checkin_paso": "basura"}) is True


@pytest.mark.parametrize(
    "atributos",
    [
        {"checkin_version": "checkin-v1"},
        {"checkin_intentos": "0"},
        {"checkin_version": "checkin-v1", "checkin_intentos": "0"},
    ],
)
def test_claves_de_checkin_sin_paso_son_estado_invalido_no_sesion_nueva(
    atributos: dict[str, str],
) -> None:
    assert hay_estado(atributos) is True
    with pytest.raises(EstadoInvalido):
        EstadoCheckin.desde_atributos(atributos)


def test_repr_del_turno_no_expone_el_texto_a_decir() -> None:
    turno = iniciar("Marisol", Trato.USTED)

    assert "Marisol" not in repr(turno)


@pytest.mark.parametrize("trato", list(Trato))
def test_cierre_error_es_fijo_sin_nombre_y_remite_al_112(trato: Trato) -> None:
    texto = TEXTOS[trato].cierre_error

    assert "{" not in texto
    assert "112" in texto
    assert "024" in texto


@pytest.mark.parametrize(
    ("trato", "esperado"),
    [
        ("tu", Trato.TU),
        (Trato.USTED, Trato.USTED),
        ("vos", Trato.USTED),
        ("", Trato.USTED),
    ],
)
def test_trato_o_usted_cae_en_usted_si_no_es_valido(
    trato: str, esperado: Trato
) -> None:
    assert trato_o_usted(trato) is esperado
