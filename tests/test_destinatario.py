import pytest
from pydantic import ValidationError

from core.destinatario import Destinatario

DATOS = {
    "contacto_id": "3b241101-e2bb-4255-8caf-4136c566a962",
    "nombre": "Francisco",
    "telefono": "+34600000003",
}


def test_destinatario_valido_se_construye() -> None:
    destinatario = Destinatario.model_validate(DATOS)

    assert destinatario.telefono == "+34600000003"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("telefono", "600000003"),
        ("telefono", "+34 600 000 003"),
        ("contacto_id", "no-es-un-uuid"),
        ("nombre", ""),
    ],
)
def test_destinatario_con_datos_invalidos_se_rechaza(campo: str, valor: str) -> None:
    with pytest.raises(ValidationError):
        Destinatario.model_validate(DATOS | {campo: valor})


def test_ni_el_telefono_ni_el_nombre_salen_en_la_representacion() -> None:
    texto = repr(Destinatario.model_validate(DATOS))

    assert "600000003" not in texto
    assert "Francisco" not in texto


def test_el_error_no_incluye_el_telefono() -> None:
    with pytest.raises(ValidationError) as info:
        Destinatario.model_validate(DATOS | {"telefono": "+34 699 123 456"})

    assert "699" not in str(info.value)
