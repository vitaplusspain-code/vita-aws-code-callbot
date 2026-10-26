"""El flujo de Connect exportable cumple el Flow language y encaja con el código.

Referencia: Amazon Connect, "Flow language" (MessageParticipant,
GetParticipantInput, UpdateContactTextToSpeechVoice, DisconnectParticipant).
"""

import json
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from adapters.connect import ATRIBUTO_MENSAJE
from core.mensaje import construir_mensaje
from core.tipos import Caso

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = RAIZ / "connect" / "flujo-aviso.json"
GUIA = RAIZ / "connect" / "flujo-aviso.md"

# Etiquetas SSML y atributos de <prosody> que admite una voz neural de Polly.
ETIQUETAS_NEURAL = {"speak", "break", "lang", "mark", "p", "phoneme", "prosody", "s"}
ATRIBUTOS_PROSODY_NEURAL = {"rate", "volume"}


@pytest.fixture(scope="module")
def flujo() -> dict[str, object]:
    return json.loads(FLUJO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def acciones(flujo: dict[str, object]) -> dict[str, dict[str, object]]:
    return {a["Identifier"]: a for a in flujo["Actions"]}


def _de_tipo(acciones: dict[str, dict[str, object]], tipo: str) -> dict[str, object]:
    (accion,) = [a for a in acciones.values() if a["Type"] == tipo]
    return accion


def _destinos(accion: dict[str, object]) -> list[str]:
    transiciones = accion["Transitions"]
    destinos = [transiciones["NextAction"]] if "NextAction" in transiciones else []
    destinos += [c["NextAction"] for c in transiciones.get("Conditions", [])]
    destinos += [e["NextAction"] for e in transiciones.get("Errors", [])]
    return destinos


def _errores(accion: dict[str, object]) -> set[str]:
    return {e["ErrorType"] for e in accion["Transitions"].get("Errors", [])}


def test_version_y_accion_de_inicio(
    flujo: dict[str, object], acciones: dict[str, dict[str, object]]
) -> None:
    assert flujo["Version"] == "2019-10-30"
    assert flujo["StartAction"] in acciones
    assert len(acciones) == len(flujo["Actions"])  # identificadores únicos


def test_todas_las_transiciones_apuntan_a_acciones_existentes(
    acciones: dict[str, dict[str, object]],
) -> None:
    for accion in acciones.values():
        for destino in _destinos(accion):
            assert destino in acciones, (accion["Identifier"], destino)


def test_todas_las_acciones_son_alcanzables(
    flujo: dict[str, object], acciones: dict[str, dict[str, object]]
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
    flujo: dict[str, object], acciones: dict[str, dict[str, object]]
) -> None:
    voz = acciones[flujo["StartAction"]]

    assert voz["Type"] == "UpdateContactTextToSpeechVoice"
    assert voz["Parameters"] == {
        "TextToSpeechVoice": "Lucia",
        "TextToSpeechEngine": "neural",
        "TextToSpeechStyle": "None",
    }
    assert _errores(voz) == {"NoMatchingError"}
    # Sin voz española no se lee nada: se cuelga.
    error = voz["Transitions"]["Errors"][0]["NextAction"]
    assert acciones[error]["Type"] == "DisconnectParticipant"


def test_reproduce_el_ssml_del_atributo_que_envia_el_adaptador(
    acciones: dict[str, dict[str, object]],
) -> None:
    entrada = _de_tipo(acciones, "GetParticipantInput")

    assert entrada["Parameters"]["SSML"] == f"$.Attributes.{ATRIBUTO_MENSAJE}"
    assert "Text" not in entrada["Parameters"]
    assert "PromptId" not in entrada["Parameters"]
    assert entrada["Parameters"]["StoreInput"] == "False"
    assert int(entrada["Parameters"]["InputTimeLimitSeconds"]) > 0


def test_pulsar_1_repite_el_mensaje(acciones: dict[str, dict[str, object]]) -> None:
    entrada = _de_tipo(acciones, "GetParticipantInput")
    (condicion,) = entrada["Transitions"]["Conditions"]

    assert condicion["Condition"] == {"Operator": "Equals", "Operands": ["1"]}
    assert condicion["NextAction"] == entrada["Identifier"]


def test_la_entrada_define_todos_sus_errores(
    acciones: dict[str, dict[str, object]],
) -> None:
    entrada = _de_tipo(acciones, "GetParticipantInput")

    assert _errores(entrada) == {
        "InputTimeLimitExceeded",
        "NoMatchingCondition",
        "NoMatchingError",
    }


def test_despedida_y_cuelgue(acciones: dict[str, dict[str, object]]) -> None:
    despedida = _de_tipo(acciones, "MessageParticipant")
    colgar = _de_tipo(acciones, "DisconnectParticipant")

    assert despedida["Parameters"]["Text"]
    assert despedida["Transitions"]["NextAction"] == colgar["Identifier"]
    assert _errores(despedida) == {"NoMatchingError"}
    assert colgar["Transitions"] == {}


def test_el_flujo_no_lleva_datos_de_cuenta_ni_telefonos() -> None:
    texto = FLUJO.read_text(encoding="utf-8")

    assert "arn:" not in texto
    assert not re.search(r"\d{12}", texto)  # identificador de cuenta de AWS
    assert not re.search(r"\+\d{6,}", texto)


def test_la_guia_nombra_el_atributo_y_la_voz() -> None:
    guia = GUIA.read_text(encoding="utf-8")

    assert f"$.Attributes.{ATRIBUTO_MENSAJE}" in guia
    assert "Lucia" in guia


@pytest.mark.parametrize("caso", list(Caso))
def test_el_ssml_solo_usa_lo_que_admite_una_voz_neural(caso: Caso) -> None:
    raiz = ElementTree.fromstring(construir_mensaje(caso, "Ana", "Luis"))

    for elemento in raiz.iter():
        assert elemento.tag in ETIQUETAS_NEURAL
        if elemento.tag == "prosody":
            assert set(elemento.attrib) <= ATRIBUTOS_PROSODY_NEURAL
