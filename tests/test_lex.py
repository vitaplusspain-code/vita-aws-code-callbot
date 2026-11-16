from typing import Any

import pytest

from adapters.lex import (
    TIEMPOS_VOZ,
    EntradaLex,
    construir_respuesta,
    parsear_evento,
)
from core.checkin import EstadoCheckin, Turno
from core.checkin_guion import TEXTOS, Paso, Trato

CALL_ID = "0b6c1f0e-1111-4222-8333-444455556666"
CONTACTO = "5f0a9c2e-7777-4888-9999-aaaabbbbcccc"


def _evento(**cambios: Any) -> dict[str, Any]:
    evento: dict[str, Any] = {
        "messageVersion": "1.0",
        "invocationSource": "DialogCodeHook",
        "inputMode": "Speech",
        "inputTranscript": "me encuentro bien",
        "sessionId": CONTACTO,
        "bot": {"localeId": "es_ES"},
        "sessionState": {
            "sessionAttributes": {"call_id": CALL_ID},
            "intent": {"name": "Conversacion", "slots": {}, "state": "InProgress"},
        },
        "requestAttributes": None,
        "transcriptions": [{"transcription": "me encuentro bien"}],
    }
    evento.update(cambios)
    return evento


def _turno(paso: Paso = Paso.COMIDA, texto: str = "¿Ha comido hoy?") -> Turno:
    return Turno(estado=EstadoCheckin(paso), texto_a_decir=texto)


# ---- parsear_evento --------------------------------------------------------


def test_parsea_un_evento_normal() -> None:
    entrada = parsear_evento(_evento())

    assert entrada == EntradaLex(
        call_id=CALL_ID,
        texto="me encuentro bien",
        atributos={"call_id": CALL_ID},
        session_id=CONTACTO,
        contacto_id=CONTACTO,
    )


def test_parsea_un_evento_minimo() -> None:
    entrada = parsear_evento({})

    assert entrada.call_id == ""
    assert entrada.texto == ""
    assert entrada.atributos == {}
    assert entrada.session_id == ""
    assert entrada.contacto_id == ""


def test_el_contacto_sale_del_session_id_en_minusculas() -> None:
    entrada = parsear_evento(_evento(sessionId=CONTACTO.upper()))

    assert entrada.contacto_id == CONTACTO


@pytest.mark.parametrize(
    "session_id", ["", "sesion-1", CONTACTO + "x", f" {CONTACTO}", "1' OR '1'='1", 7]
)
def test_un_session_id_que_no_es_un_contacto_valido_cuenta_como_ausente(
    session_id: object,
) -> None:
    assert parsear_evento(_evento(sessionId=session_id)).contacto_id == ""


def test_el_session_id_se_acota() -> None:
    assert len(parsear_evento(_evento(sessionId="s" * 500)).session_id) == 100


@pytest.mark.parametrize("evento", [None, "texto", 7, []])
def test_un_evento_que_no_es_un_mapa_cuenta_como_vacio(evento: object) -> None:
    assert parsear_evento(evento).atributos == {}


def test_ignora_campos_desconocidos() -> None:
    entrada = parsear_evento(_evento(campoNuevo={"x": 1}, otro=[1, 2]))

    assert entrada.texto == "me encuentro bien"


@pytest.mark.parametrize("atributos", [None, "texto", ["a"], 3])
def test_atributos_de_sesion_que_no_son_un_mapa_son_vacios(atributos: object) -> None:
    evento = _evento()
    evento["sessionState"]["sessionAttributes"] = atributos

    entrada = parsear_evento(evento)

    assert entrada.atributos == {}
    assert entrada.call_id == ""


@pytest.mark.parametrize("estado_sesion", [None, "x", [1]])
def test_session_state_que_no_es_un_mapa_se_ignora(estado_sesion: object) -> None:
    entrada = parsear_evento(_evento(sessionState=estado_sesion))

    assert entrada.atributos == {}


def test_descarta_los_valores_que_no_son_texto() -> None:
    evento = _evento()
    evento["sessionState"]["sessionAttributes"] = {
        "call_id": CALL_ID,
        "numero": 5,
        "nulo": None,
        "lista": ["a"],
        "ok": "si",
        3: "clave numerica",
    }

    entrada = parsear_evento(evento)

    assert entrada.atributos == {"call_id": CALL_ID, "ok": "si"}


@pytest.mark.parametrize("transcripcion", [None, 5, ["a"], {"a": "b"}])
def test_transcripcion_que_no_es_texto_es_vacia(transcripcion: object) -> None:
    assert parsear_evento(_evento(inputTranscript=transcripcion)).texto == ""


@pytest.mark.parametrize(
    "call_id",
    ["", "no-es-uuid", "x" * 5000, CALL_ID + "x", " " + CALL_ID, "1' OR '1'='1"],
)
def test_un_call_id_que_no_es_uuid_cuenta_como_ausente(call_id: str) -> None:
    evento = _evento()
    evento["sessionState"]["sessionAttributes"]["call_id"] = call_id

    assert parsear_evento(evento).call_id == ""


def test_el_repr_no_expone_la_frase() -> None:
    assert "encuentro" not in repr(parsear_evento(_evento()))


# ---- construir_respuesta ---------------------------------------------------


def test_forma_exacta_de_elicit_slot() -> None:
    turno = _turno()

    respuesta = construir_respuesta(turno, {"call_id": CALL_ID})

    assert respuesta == {
        "sessionState": {
            "dialogAction": {"type": "ElicitSlot", "slotToElicit": "respuesta"},
            "intent": {
                "name": "Conversacion",
                "state": "InProgress",
                "slots": {"respuesta": None},
            },
            "sessionAttributes": {
                "call_id": CALL_ID,
                **turno.estado.a_atributos(),
                **TIEMPOS_VOZ,
            },
        },
        "messages": [{"contentType": "PlainText", "content": "¿Ha comido hoy?"}],
    }


def test_forma_exacta_de_close() -> None:
    turno = _turno(Paso.FIN, "Hasta mañana.")

    respuesta = construir_respuesta(turno, {"call_id": CALL_ID})

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert respuesta["sessionState"]["intent"] == {
        "name": "Conversacion",
        "state": "Fulfilled",
        "slots": {"respuesta": None},
    }
    assert respuesta["messages"] == [
        {"contentType": "PlainText", "content": "Hasta mañana."}
    ]


def test_un_cierre_sin_texto_usa_el_cierre_de_error() -> None:
    respuesta = construir_respuesta(_turno(Paso.FIN, ""), {})

    assert respuesta["sessionState"]["dialogAction"] == {"type": "Close"}
    assert respuesta["messages"] == [
        {"contentType": "PlainText", "content": TEXTOS[Trato.USTED].cierre_error}
    ]


def test_solo_devuelve_call_id_y_las_claves_propias_y_las_nuestras_mandan() -> None:
    entrada = {
        "call_id": CALL_ID,
        "otra": "valor",
        "checkin_paso": "animo_hoy",
        "x-amz-lex:audio:start-timeout-ms:Conversacion:respuesta": "1",
    }
    turno = _turno(Paso.COMIDA)

    atributos = construir_respuesta(turno, entrada)["sessionState"]["sessionAttributes"]

    assert atributos == {
        "call_id": CALL_ID,
        **turno.estado.a_atributos(),
        **TIEMPOS_VOZ,
    }


def test_no_devuelve_un_call_id_invalido() -> None:
    entrada = {"call_id": "<script>"}

    atributos = construir_respuesta(_turno(), entrada)["sessionState"][
        "sessionAttributes"
    ]

    assert "call_id" not in atributos
    assert "<script>" not in str(atributos)


def test_no_modifica_los_atributos_de_entrada() -> None:
    entrada = {"call_id": CALL_ID}

    construir_respuesta(_turno(), entrada)

    assert entrada == {"call_id": CALL_ID}


def test_tiempos_de_voz_para_personas_mayores() -> None:
    # Atributos de sesión de voz de Lex V2: llevan sufijo de intent y de slot.
    assert TIEMPOS_VOZ == {
        "x-amz-lex:audio:start-timeout-ms:Conversacion:respuesta": "6000",
        "x-amz-lex:audio:end-timeout-ms:Conversacion:respuesta": "1200",
    }


def test_no_hace_eco_de_atributos_ajenos_aunque_sean_enormes() -> None:
    entrada = {"call_id": CALL_ID, "grande": "ñ" * 7000, "otra": "x" * 7000}

    atributos = construir_respuesta(_turno(), entrada)["sessionState"][
        "sessionAttributes"
    ]

    assert set(atributos) == {"call_id", *_turno().estado.a_atributos(), *TIEMPOS_VOZ}
    assert len(str(atributos).encode()) < 1024


def test_un_cierre_con_texto_conserva_su_texto() -> None:
    respuesta = construir_respuesta(_turno(Paso.FIN, "Adiós."), {})

    assert respuesta["messages"][0]["content"] == "Adiós."


def test_un_turno_sin_texto_y_sin_terminar_no_inventa_mensaje() -> None:
    respuesta = construir_respuesta(_turno(Paso.COMIDA, ""), {})

    assert "messages" not in respuesta
