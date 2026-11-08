import xml.etree.ElementTree as ET

import pytest

from core.mensaje import construir_mensaje, construir_mensaje_aviso, construir_ssml
from core.motivos import texto_detalle, texto_saludo
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


def test_mensaje_de_aviso_tiene_saludo_y_detalle_en_ssml() -> None:
    mensaje = construir_mensaje_aviso("x", "Carmen", "Francisco")

    saludo = "".join(ET.fromstring(mensaje.saludo).itertext())
    detalle = "".join(ET.fromstring(mensaje.detalle).itertext())
    assert saludo == texto_saludo("Francisco")
    assert detalle == texto_detalle("x", "Carmen")


def test_mensaje_de_aviso_con_nombres_hostiles_es_xml_valido() -> None:
    mensaje = construir_mensaje_aviso("x", "Ana <b> & Co", "Luis </speak><x/>")

    for ssml in (mensaje.saludo, mensaje.detalle):
        raiz = ET.fromstring(ssml)
        assert raiz.find(".//x") is None
        assert raiz.find(".//b") is None
    assert "Luis </speak><x/>" in "".join(ET.fromstring(mensaje.saludo).itertext())


def test_mensaje_de_aviso_es_inmutable() -> None:
    mensaje = construir_mensaje_aviso("x", "Carmen", "Francisco")

    with pytest.raises(AttributeError):
        mensaje.saludo = "otro"  # type: ignore[misc]


def test_mensaje_de_aviso_con_nombres_de_100_caracteres_es_corto() -> None:
    mensaje = construir_mensaje_aviso("x", "&" * 100, "&" * 100)

    assert len(mensaje.saludo) + len(mensaje.detalle) < 3000


def test_el_mensaje_de_aviso_no_ensena_los_nombres_en_su_representacion() -> None:
    mensaje = construir_mensaje_aviso("x", "Carmen", "Francisco")

    assert "Carmen" not in repr(mensaje)
    assert "Francisco" not in repr(mensaje)
