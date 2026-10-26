import pytest

from core.errores import (
    AvisoInvalido,
    ErrorCallbot,
    ErrorConfiguracion,
    ErrorConnect,
    PersonaNoEncontrada,
    TelefonoNoPermitido,
)


@pytest.mark.parametrize(
    ("clase", "codigo"),
    [
        (AvisoInvalido, "aviso_invalido"),
        (PersonaNoEncontrada, "persona_no_encontrada"),
        (TelefonoNoPermitido, "telefono_no_permitido"),
        (ErrorConnect, "error_connect"),
        (ErrorConfiguracion, "error_configuracion"),
    ],
)
def test_cada_error_tiene_su_codigo_y_hereda_de_la_base(
    clase: type[ErrorCallbot], codigo: str
) -> None:
    error = clase("detalle")

    assert isinstance(error, ErrorCallbot)
    assert error.codigo == codigo
    assert str(error) == "detalle"


def test_la_base_tiene_un_codigo_generico() -> None:
    assert ErrorCallbot.codigo == "error_callbot"
