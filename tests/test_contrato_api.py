import json
import re
from pathlib import Path

import pytest

import handlers.lanzar_llamada as modulo
from core.aviso import TAMANO_MAXIMO_CUERPO, parsear_aviso_json
from core.tipos import Caso

RAIZ = Path(__file__).resolve().parent.parent
EVENTO_DEMO = RAIZ / "events" / "aviso-demo.json"
CONTRATO = RAIZ / "docs" / "contrato-api.md"


@pytest.fixture(scope="module")
def evento() -> dict[str, object]:
    return json.loads(EVENTO_DEMO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contrato() -> str:
    return CONTRATO.read_text(encoding="utf-8")


def test_evento_demo_es_un_post_a_avisos(evento: dict[str, object]) -> None:
    assert evento["httpMethod"] == "POST"
    assert evento["path"] == "/avisos"
    assert evento["resource"] == "/avisos"
    assert evento["isBase64Encoded"] is False


def test_evento_demo_lleva_un_aviso_valido(evento: dict[str, object]) -> None:
    aviso = parsear_aviso_json(evento["body"])

    assert aviso.persona_id == "demo-01"
    assert aviso.caso is Caso.MEDICACION_7_DIAS


def test_evento_demo_no_lleva_telefonos(evento: dict[str, object]) -> None:
    texto = EVENTO_DEMO.read_text(encoding="utf-8")

    assert not re.search(r"\+\d{6,}", texto)


@pytest.mark.parametrize(
    ("codigo", "estado", "mensaje"),
    [(c, e, m) for c, (e, m) in modulo._RESPUESTAS_ERROR.items()],
)
def test_contrato_documenta_cada_error(
    contrato: str, codigo: str, estado: int, mensaje: str
) -> None:
    fila = next(
        (linea for linea in contrato.splitlines() if f"`{codigo}`" in linea), ""
    )

    assert str(estado) in fila
    assert mensaje in fila


@pytest.mark.parametrize("caso", list(Caso))
def test_contrato_documenta_cada_caso(contrato: str, caso: Caso) -> None:
    assert f"`{caso.value}`" in contrato


def test_contrato_documenta_el_tamano_maximo(contrato: str) -> None:
    assert f"{TAMANO_MAXIMO_CUERPO} bytes" in contrato
