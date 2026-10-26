import xml.etree.ElementTree as ET

import pytest

from core.mensaje import construir_mensaje, construir_ssml
from core.tipos import Caso


def test_construir_ssml_envuelve_el_texto() -> None:
    esperado = '<speak><prosody rate="90%">Hola</prosody></speak>'

    assert construir_ssml("Hola") == esperado


def test_construir_ssml_escapa_caracteres_especiales() -> None:
    ssml = construir_ssml("a & b < c > d")

    assert "a &amp; b &lt; c &gt; d" in ssml


def test_construir_ssml_produce_xml_bien_formado() -> None:
    raiz = ET.fromstring(construir_ssml("Ana <b> & Co"))

    assert raiz.tag == "speak"
    assert "".join(raiz.itertext()) == "Ana <b> & Co"


@pytest.mark.parametrize("caso", list(Caso))
def test_mensaje_con_nombres_hostiles_es_xml_valido(caso: Caso) -> None:
    ssml = construir_mensaje(caso, "Ana <b> & Co", "Luis </speak><x/>")

    raiz = ET.fromstring(ssml)
    texto = "".join(raiz.itertext())
    assert "Ana <b> & Co" in texto
    assert "Luis </speak><x/>" in texto
    assert raiz.find(".//x") is None
    assert raiz.find(".//b") is None


def test_mensaje_no_escapa_dos_veces() -> None:
    ssml = construir_mensaje(Caso.SUENO_IRREGULAR, "A & B", "Familiar Prueba")

    assert "A &amp; B" in ssml
    assert "&amp;amp;" not in ssml


@pytest.mark.parametrize("caso", list(Caso))
@pytest.mark.parametrize("caracter", ["a", "&"])
def test_mensaje_con_nombres_de_100_caracteres_cabe_en_el_limite_de_tts(
    caso: Caso, caracter: str
) -> None:
    nombre = caracter * 100

    assert len(construir_mensaje(caso, nombre, nombre)) < 3000
