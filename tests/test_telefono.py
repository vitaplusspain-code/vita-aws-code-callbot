import pytest

from core.telefono import enmascarar_telefono, es_telefono_e164


@pytest.mark.parametrize("telefono", ["+34600000001", "+12345678", "+123456789012345"])
def test_acepta_telefonos_e164_validos(telefono: str) -> None:
    assert es_telefono_e164(telefono) is True


@pytest.mark.parametrize(
    "telefono",
    [
        "",
        "34600000001",
        "+0600000001",
        "+1234567",
        "+1234567890123456",
        "+34 600000001",
        "+3460000000a",
        "+34600000001\n",
    ],
)
def test_rechaza_telefonos_mal_formados(telefono: str) -> None:
    assert es_telefono_e164(telefono) is False


def test_enmascara_dejando_prefijo_y_ultimos_cuatro() -> None:
    assert enmascarar_telefono("+34600123456") == "+34*****3456"


def test_el_enmascarado_conserva_la_longitud() -> None:
    telefono = "+34600123456"

    assert len(enmascarar_telefono(telefono)) == len(telefono)


@pytest.mark.parametrize("valor", ["", "+34", "1234567", "+346001234"])
def test_enmascara_por_completo_lo_demasiado_corto(valor: str) -> None:
    assert enmascarar_telefono(valor) == "*" * len(valor)


def test_con_11_caracteres_ya_enmascara_el_centro() -> None:
    assert enmascarar_telefono("+3460012345") == "+34****2345"


def test_con_12_caracteres_enmascara_cinco() -> None:
    assert enmascarar_telefono("+34600123456") == "+34*****3456"
