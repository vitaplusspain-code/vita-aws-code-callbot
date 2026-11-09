"""El flujo de Connect exportable cumple el Flow language y encaja con el código.

Referencia: Amazon Connect, "Flow language" (MessageParticipant,
GetParticipantInput, UpdateContactTextToSpeechVoice, DisconnectParticipant).

Guion (decisión 37): saludo que solo nombra al familiar y pide pulsar 1; con
el 1 se cuenta el detalle (y 1 lo repite); sin pulsar, o con otra tecla, se
despide sin dar ningún detalle.
"""

import json
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from adapters.connect import ATRIBUTO_DETALLE, ATRIBUTO_SALUDO
from core.mensaje import MensajeAviso, construir_mensaje_aviso, construir_mensaje_caso
from core.tipos import Caso

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = RAIZ / "connect" / "flujo-aviso.json"
GUIA = RAIZ / "connect" / "flujo-aviso.md"

# Etiquetas SSML y atributos de <prosody> que admite una voz neural de Polly.
ETIQUETAS_NEURAL = {"speak", "break", "lang", "mark", "p", "phoneme", "prosody", "s"}
ATRIBUTOS_PROSODY_NEURAL = {"rate", "volume"}
ERRORES_ENTRADA = {"InputTimeLimitExceeded", "NoMatchingCondition", "NoMatchingError"}

Acciones = dict[str, dict[str, object]]


@pytest.fixture(scope="module")
def flujo() -> dict[str, object]:
    return json.loads(FLUJO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def acciones(flujo: dict[str, object]) -> Acciones:
    return {a["Identifier"]: a for a in flujo["Actions"]}


def _de_tipo(acciones: Acciones, tipo: str) -> list[dict[str, object]]:
    return [a for a in acciones.values() if a["Type"] == tipo]


def _entrada(acciones: Acciones, atributo: str) -> dict[str, object]:
    (accion,) = [
        a
        for a in _de_tipo(acciones, "GetParticipantInput")
        if a["Parameters"]["SSML"] == f"$.Attributes.{atributo}"
    ]
    return accion


def _destinos(accion: dict[str, object]) -> list[str]:
    transiciones = accion["Transitions"]
    destinos = [transiciones["NextAction"]] if "NextAction" in transiciones else []
    destinos += [c["NextAction"] for c in transiciones.get("Conditions", [])]
    destinos += [e["NextAction"] for e in transiciones.get("Errors", [])]
    return destinos


def _errores(accion: dict[str, object]) -> dict[str, str]:
    return {
        e["ErrorType"]: e["NextAction"] for e in accion["Transitions"].get("Errors", [])
    }


def _tipo_de(acciones: Acciones, identificador: str) -> str:
    return acciones[identificador]["Type"]


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


def test_empieza_fijando_la_voz_lucia_neural(
    flujo: dict[str, object], acciones: Acciones
) -> None:
    voz = acciones[flujo["StartAction"]]

    assert voz["Type"] == "UpdateContactTextToSpeechVoice"
    assert voz["Parameters"] == {
        "TextToSpeechVoice": "Lucia",
        "TextToSpeechEngine": "neural",
        "TextToSpeechStyle": "None",
    }
    # Sin voz española no se lee nada: se cuelga.
    errores = _errores(voz)
    assert set(errores) == {"NoMatchingError"}
    assert _tipo_de(acciones, errores["NoMatchingError"]) == "DisconnectParticipant"
    # Lo primero que se oye es el saludo.
    saludo = _entrada(acciones, ATRIBUTO_SALUDO)
    assert voz["Transitions"]["NextAction"] == saludo["Identifier"]


@pytest.mark.parametrize("atributo", [ATRIBUTO_SALUDO, ATRIBUTO_DETALLE])
def test_cada_parte_se_lee_de_su_atributo_en_ssml(
    acciones: Acciones, atributo: str
) -> None:
    entrada = _entrada(acciones, atributo)

    assert "Text" not in entrada["Parameters"]
    assert "PromptId" not in entrada["Parameters"]
    assert entrada["Parameters"]["StoreInput"] == "False"
    assert int(entrada["Parameters"]["InputTimeLimitSeconds"]) > 0
    assert set(_errores(entrada)) == ERRORES_ENTRADA


def test_pulsar_1_en_el_saludo_lleva_al_detalle(acciones: Acciones) -> None:
    saludo = _entrada(acciones, ATRIBUTO_SALUDO)
    detalle = _entrada(acciones, ATRIBUTO_DETALLE)
    (condicion,) = saludo["Transitions"]["Conditions"]

    assert condicion["Condition"] == {"Operator": "Equals", "Operands": ["1"]}
    assert condicion["NextAction"] == detalle["Identifier"]


def test_sin_confirmar_se_despide_sin_detalle_y_cuelga(acciones: Acciones) -> None:
    saludo = _entrada(acciones, ATRIBUTO_SALUDO)
    errores = _errores(saludo)
    despedida = acciones[errores["InputTimeLimitExceeded"]]

    assert despedida["Type"] == "MessageParticipant"
    assert errores["NoMatchingCondition"] == despedida["Identifier"]
    assert saludo["Transitions"]["NextAction"] == despedida["Identifier"]
    assert _tipo_de(acciones, errores["NoMatchingError"]) == "DisconnectParticipant"
    assert _tipo_de(acciones, despedida["Transitions"]["NextAction"]) == (
        "DisconnectParticipant"
    )


def test_al_detalle_solo_se_llega_pulsando_1(acciones: Acciones) -> None:
    """Guardarraíl: ningún camino cuenta el motivo sin confirmar la identidad."""
    saludo = _entrada(acciones, ATRIBUTO_SALUDO)
    detalle = _entrada(acciones, ATRIBUTO_DETALLE)
    origenes = {
        accion["Identifier"]
        for accion in acciones.values()
        if detalle["Identifier"] in _destinos(accion)
    }

    assert origenes == {saludo["Identifier"], detalle["Identifier"]}
    entradas_al_detalle = [
        c
        for c in saludo["Transitions"]["Conditions"]
        if c["NextAction"] == detalle["Identifier"]
    ]
    assert len(entradas_al_detalle) == 1
    assert saludo["Transitions"]["NextAction"] != detalle["Identifier"]
    assert detalle["Identifier"] not in _errores(saludo).values()


def test_pulsar_1_en_el_detalle_lo_repite(acciones: Acciones) -> None:
    detalle = _entrada(acciones, ATRIBUTO_DETALLE)
    (condicion,) = detalle["Transitions"]["Conditions"]

    assert condicion["Condition"] == {"Operator": "Equals", "Operands": ["1"]}
    assert condicion["NextAction"] == detalle["Identifier"]


def test_tras_el_detalle_se_despide_y_cuelga(acciones: Acciones) -> None:
    detalle = _entrada(acciones, ATRIBUTO_DETALLE)
    errores = _errores(detalle)
    despedida = acciones[errores["InputTimeLimitExceeded"]]

    assert despedida["Type"] == "MessageParticipant"
    assert errores["NoMatchingCondition"] == despedida["Identifier"]
    assert detalle["Transitions"]["NextAction"] == despedida["Identifier"]
    assert _tipo_de(acciones, errores["NoMatchingError"]) == "DisconnectParticipant"


def test_las_despedidas_son_textos_fijos_que_cuelgan(acciones: Acciones) -> None:
    despedidas = _de_tipo(acciones, "MessageParticipant")

    assert len(despedidas) == 2
    for despedida in despedidas:
        texto = despedida["Parameters"]["Text"]
        assert texto
        assert "$." not in texto
        assert set(_errores(despedida)) == {"NoMatchingError"}
        destino = despedida["Transitions"]["NextAction"]
        assert _tipo_de(acciones, destino) == "DisconnectParticipant"
    (colgar,) = _de_tipo(acciones, "DisconnectParticipant")
    assert colgar["Transitions"] == {}


def test_el_flujo_no_lleva_datos_de_cuenta_ni_telefonos() -> None:
    texto = FLUJO.read_text(encoding="utf-8")

    assert "arn:" not in texto
    assert not re.search(r"\d{12}", texto)  # identificador de cuenta de AWS
    assert not re.search(r"\+\d{6,}", texto)


def test_la_guia_nombra_los_atributos_y_la_voz() -> None:
    guia = GUIA.read_text(encoding="utf-8")

    assert f"$.Attributes.{ATRIBUTO_SALUDO}" in guia
    assert f"$.Attributes.{ATRIBUTO_DETALLE}" in guia
    assert "Lucia" in guia


def _mensajes() -> list[MensajeAviso]:
    casos = [construir_mensaje_caso(c, "Ana", "Luis") for c in Caso]
    return [*casos, construir_mensaje_aviso("regla", "Ana", "Luis")]


@pytest.mark.parametrize("mensaje", _mensajes())
def test_el_ssml_solo_usa_lo_que_admite_una_voz_neural(mensaje: MensajeAviso) -> None:
    for ssml in (mensaje.saludo, mensaje.detalle):
        raiz = ElementTree.fromstring(ssml)
        for elemento in raiz.iter():
            assert elemento.tag in ETIQUETAS_NEURAL
            if elemento.tag == "prosody":
                assert set(elemento.attrib) <= ATRIBUTOS_PROSODY_NEURAL
