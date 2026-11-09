import xml.etree.ElementTree as ET
from types import MappingProxyType

import pytest

from core.casos import FRASES_CASOS
from core.mensaje import (
    MensajeAviso,
    construir_mensaje_aviso,
    construir_mensaje_caso,
    construir_ssml,
)
from core.motivos import texto_detalle, texto_saludo
from core.tipos import Caso


def _texto(ssml: str) -> str:
    return "".join(ET.fromstring(ssml).itertext())


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


def test_mensaje_de_aviso_tiene_saludo_y_detalle_en_ssml() -> None:
    mensaje = construir_mensaje_aviso("x", "Carmen", "Francisco")

    assert _texto(mensaje.saludo) == texto_saludo("Francisco")
    assert _texto(mensaje.detalle) == texto_detalle("x", "Carmen")


def test_mensaje_de_aviso_usa_las_frases_indicadas() -> None:
    frases = MappingProxyType({"sos": "{persona} ha pulsado el botón de ayuda."})

    mensaje = construir_mensaje_aviso("sos", "Carmen", "Francisco", frases=frases)

    assert _texto(mensaje.detalle).startswith("Carmen ha pulsado el botón de ayuda.")


@pytest.mark.parametrize("caso", list(Caso))
def test_mensaje_del_caso_usa_la_frase_del_caso(caso: Caso) -> None:
    mensaje = construir_mensaje_caso(caso, "Carmen", "Francisco")

    assert mensaje == construir_mensaje_aviso(
        caso.value, "Carmen", "Francisco", frases=FRASES_CASOS
    )
    assert "no es una emergencia" in _texto(mensaje.detalle)


def _todos(persona: str, familiar: str) -> list[MensajeAviso]:
    casos = [construir_mensaje_caso(c, persona, familiar) for c in Caso]
    return [*casos, construir_mensaje_aviso("x", persona, familiar)]


@pytest.mark.parametrize("indice", range(len(Caso) + 1))
def test_mensajes_con_nombres_hostiles_son_xml_valido(indice: int) -> None:
    mensaje = _todos("Ana <b> & Co", "Luis </speak><x/>")[indice]

    for ssml in (mensaje.saludo, mensaje.detalle):
        raiz = ET.fromstring(ssml)
        assert raiz.find(".//x") is None
        assert raiz.find(".//b") is None
    assert "Luis </speak><x/>" in _texto(mensaje.saludo)
    assert "Ana <b> & Co" in _texto(mensaje.detalle)


def test_el_saludo_no_nombra_a_la_persona_en_ningun_mensaje() -> None:
    for mensaje in _todos("Carmen", "Francisco"):
        assert "Carmen" not in mensaje.saludo
        assert "Francisco" in mensaje.saludo


def test_los_nombres_no_se_escapan_dos_veces() -> None:
    mensaje = construir_mensaje_caso(Caso.SUENO_IRREGULAR, "A & B", "C & D")

    assert "A &amp; B" in mensaje.detalle
    assert "C &amp; D" in mensaje.saludo
    assert "&amp;amp;" not in mensaje.detalle + mensaje.saludo


def test_mensaje_de_aviso_es_inmutable() -> None:
    mensaje = construir_mensaje_aviso("x", "Carmen", "Francisco")

    with pytest.raises(AttributeError):
        mensaje.saludo = "otro"  # type: ignore[misc]


@pytest.mark.parametrize("caracter", ["a", "&"])
def test_mensajes_con_nombres_de_100_caracteres_son_cortos(caracter: str) -> None:
    nombre = caracter * 100

    for mensaje in _todos(nombre, nombre):
        assert len(mensaje.saludo) + len(mensaje.detalle) < 3000


def test_el_mensaje_de_aviso_no_ensena_los_nombres_en_su_representacion() -> None:
    mensaje = construir_mensaje_aviso("x", "Carmen", "Francisco")

    assert "Carmen" not in repr(mensaje)
    assert "Francisco" not in repr(mensaje)
