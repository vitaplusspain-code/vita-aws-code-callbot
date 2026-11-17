"""El flujo de Connect del check-in cumple el Flow language y encaja con el código.

Referencia: Amazon Connect, "Flow language" (ConnectParticipantWithLexBot,
MessageParticipant, UpdateContactTextToSpeechVoice, DisconnectParticipant).

Guion: voz Lucia, Lex lleva la conversación con el `call_id` en la sesión y,
al cerrar el intent, se cuelga (la despedida la dice la Lambda). Cualquier
otra salida dice un cierre fijo, sin nombres y con el 112, y cuelga.
"""

import json
import re
from pathlib import Path

import pytest

from adapters.connect import ATRIBUTO_CALL_ID
from adapters.lex import CLAVE_CALL_ID, TIEMPOS_VOZ, construir_respuesta
from core.checkin_guion import TEXTOS, Trato
from core.conversar import turno_de_cierre_error

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = RAIZ / "connect" / "flujo-checkin.json"
GUIA = RAIZ / "connect" / "flujo-checkin.md"

# Marcador que se sustituye por el ARN del alias al importar (ver la guía).
MARCADOR_ALIAS = "SUSTITUIR_ARN_ALIAS_BOT_CHECKIN"
ERRORES_LEX = {"InputTimeLimitExceeded", "NoMatchingCondition", "NoMatchingError"}
PREFIJO_TIEMPOS = ("x-amz-lex:audio:start-timeout-ms", "x-amz-lex:audio:end-timeout-ms")

Accion = dict[str, object]
Acciones = dict[str, Accion]


@pytest.fixture(scope="module")
def flujo() -> dict[str, object]:
    return json.loads(FLUJO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def acciones(flujo: dict[str, object]) -> Acciones:
    return {a["Identifier"]: a for a in flujo["Actions"]}


@pytest.fixture(scope="module")
def lex(acciones: Acciones) -> Accion:
    (accion,) = _de_tipo(acciones, "ConnectParticipantWithLexBot")
    return accion


def _de_tipo(acciones: Acciones, tipo: str) -> list[Accion]:
    return [a for a in acciones.values() if a["Type"] == tipo]


def _destinos(accion: Accion) -> list[str]:
    transiciones = accion["Transitions"]
    destinos = [transiciones["NextAction"]] if "NextAction" in transiciones else []
    destinos += [c["NextAction"] for c in transiciones.get("Conditions", [])]
    destinos += [e["NextAction"] for e in transiciones.get("Errors", [])]
    return destinos


def _errores(accion: Accion) -> dict[str, str]:
    return {
        e["ErrorType"]: e["NextAction"] for e in accion["Transitions"].get("Errors", [])
    }


def _tipo_de(acciones: Acciones, identificador: str) -> str:
    return acciones[identificador]["Type"]


def _intent_de_la_lambda() -> str:
    """Nombre del intent con el que la Lambda cierra la conversación."""
    respuesta = construir_respuesta(turno_de_cierre_error(), {})
    return respuesta["sessionState"]["intent"]["name"]


def test_version_y_accion_de_inicio(
    flujo: dict[str, object], acciones: Acciones
) -> None:
    assert flujo["Version"] == "2019-10-30"
    assert flujo["StartAction"] in acciones
    assert len(acciones) == len(flujo["Actions"])  # identificadores únicos


def test_todas_las_transiciones_apuntan_a_acciones_existentes(
    acciones: Acciones,
) -> None:
    for accion in acciones.values():
        for destino in _destinos(accion):
            assert destino in acciones, (accion["Identifier"], destino)


def test_todas_las_acciones_son_alcanzables(
    flujo: dict[str, object], acciones: Acciones
) -> None:
    vistas: set[str] = set()
    pendientes = [flujo["StartAction"]]
    while pendientes:
        actual = pendientes.pop()
        if actual not in vistas:
            vistas.add(actual)
            pendientes.extend(_destinos(acciones[actual]))

    assert vistas == set(acciones)


def test_empieza_fijando_la_voz_lucia_neural_y_pasa_a_lex(
    flujo: dict[str, object], acciones: Acciones, lex: Accion
) -> None:
    voz = acciones[flujo["StartAction"]]

    assert voz["Type"] == "UpdateContactTextToSpeechVoice"
    assert voz["Parameters"] == {
        "TextToSpeechVoice": "Lucia",
        "TextToSpeechEngine": "neural",
        "TextToSpeechStyle": "None",
    }
    assert voz["Transitions"]["NextAction"] == lex["Identifier"]
    # Sin voz española no se habla: se cuelga.
    errores = _errores(voz)
    assert set(errores) == {"NoMatchingError"}
    assert _tipo_de(acciones, errores["NoMatchingError"]) == "DisconnectParticipant"


def test_lex_usa_el_alias_como_marcador(lex: Accion) -> None:
    parametros = lex["Parameters"]

    assert parametros["LexV2Bot"] == {"AliasArn": MARCADOR_ALIAS}
    assert "LexBot" not in parametros  # Lex V1 no
    # La inicialización con mensaje solo existe en chat.
    assert "LexInitializationData" not in parametros


def test_lex_recibe_el_call_id_del_contacto(lex: Accion) -> None:
    atributos = lex["Parameters"]["LexSessionAttributes"]

    assert atributos[CLAVE_CALL_ID] == f"$.Attributes.{ATRIBUTO_CALL_ID}"


def test_los_tiempos_de_voz_del_primer_turno_son_los_de_la_lambda(
    lex: Accion,
) -> None:
    """Hasta que responde la Lambda, Lex usa los del flujo (comodín `*:*`)."""
    atributos = lex["Parameters"]["LexSessionAttributes"]
    del_flujo = {k: v for k, v in atributos.items() if k.startswith(PREFIJO_TIEMPOS)}
    de_la_lambda = {k.rsplit(":", 2)[0]: v for k, v in TIEMPOS_VOZ.items()}

    assert del_flujo == {f"{k}:*:*": v for k, v in de_la_lambda.items()}
    assert set(atributos) == {CLAVE_CALL_ID, *del_flujo}


def test_el_aviso_inicial_es_un_texto_fijo_sin_datos(lex: Accion) -> None:
    parametros = lex["Parameters"]
    texto = parametros["Text"]

    assert texto
    assert "$." not in texto
    assert "{" not in texto  # sin nombre: quien coge puede no ser la persona
    assert not {"SSML", "PromptId", "Media"} & set(parametros)


def test_el_aviso_inicial_se_identifica_como_asistente_automatico(
    lex: Accion,
) -> None:
    """Decisión 9: se identifica desde la primera frase, aunque nadie conteste."""
    texto = lex["Parameters"]["Text"]

    assert "asistente automático" in texto
    assert "VitaPlus" in texto


def test_el_flujo_no_toca_la_grabacion_ni_los_registros(acciones: Acciones) -> None:
    """Solo los cuatro bloques del guion: nada de grabar ni de registrar."""
    tipos = {a["Type"] for a in acciones.values()}

    assert tipos == {
        "UpdateContactTextToSpeechVoice",
        "ConnectParticipantWithLexBot",
        "MessageParticipant",
        "DisconnectParticipant",
    }


def test_al_cerrar_el_intent_cuelga_sin_mas(acciones: Acciones, lex: Accion) -> None:
    """La despedida (o el 112) ya la dice la Lambda en su último mensaje."""
    (condicion,) = lex["Transitions"]["Conditions"]

    assert condicion["Condition"] == {
        "Operator": "Equals",
        "Operands": [_intent_de_la_lambda()],
    }
    assert _tipo_de(acciones, condicion["NextAction"]) == "DisconnectParticipant"


def test_las_demas_salidas_de_lex_dicen_el_cierre_fijo(
    acciones: Acciones, lex: Accion
) -> None:
    errores = _errores(lex)
    (cierre,) = _de_tipo(acciones, "MessageParticipant")

    assert set(errores) == ERRORES_LEX
    assert set(errores.values()) == {cierre["Identifier"]}
    assert lex["Transitions"]["NextAction"] == cierre["Identifier"]


def test_el_cierre_fijo_menciona_el_112_sin_nombres_y_cuelga(
    acciones: Acciones,
) -> None:
    (cierre,) = _de_tipo(acciones, "MessageParticipant")
    texto = cierre["Parameters"]["Text"]

    assert texto == TEXTOS[Trato.USTED].cierre_error  # el mismo que la Lambda
    assert "112" in texto
    assert "024" in texto
    assert "{" not in texto
    assert "$." not in texto
    assert set(_errores(cierre)) == {"NoMatchingError"}
    destinos = {cierre["Transitions"]["NextAction"], *_errores(cierre).values()}
    assert {_tipo_de(acciones, d) for d in destinos} == {"DisconnectParticipant"}
    (colgar,) = _de_tipo(acciones, "DisconnectParticipant")
    assert colgar["Transitions"] == {}


def test_el_flujo_no_lleva_datos_de_cuenta_ni_telefonos() -> None:
    texto = FLUJO.read_text(encoding="utf-8")

    assert "arn:" not in texto
    assert not re.search(r"\d{12}", texto)  # identificador de cuenta de AWS
    assert not re.search(r"\+\d{6,}", texto)
    assert not re.search(r"bot-alias/|TSTALIASID", texto)


def test_la_guia_no_lleva_datos_de_cuenta_ni_telefonos() -> None:
    texto = GUIA.read_text(encoding="utf-8")

    assert not re.search(r"\d{12}", texto)  # identificador de cuenta de AWS
    assert not re.search(r"\+\d{6,}", texto)
    for arn in re.findall(r"arn:aws:\S+", texto):
        assert "<cuenta>" in arn, arn  # solo ARN de ejemplo, con marcadores


def test_la_guia_pide_que_la_grabacion_siga_apagada() -> None:
    assert "grabación" in GUIA.read_text(encoding="utf-8").lower()


def test_la_guia_nombra_el_marcador_el_atributo_y_la_voz() -> None:
    guia = GUIA.read_text(encoding="utf-8")

    assert MARCADOR_ALIAS in guia
    assert f"$.Attributes.{ATRIBUTO_CALL_ID}" in guia
    assert "Lucia" in guia
