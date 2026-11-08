import pytest

from core.errores import (
    AvisoInvalido,
    ErrorBaseDatos,
    ErrorCallbot,
    ErrorCanal,
    ErrorConfiguracion,
    ErrorConnect,
    LlamadasDesactivadas,
    PersonaNoEncontrada,
    TelefonoNoPermitido,
)


@pytest.mark.parametrize(
    ("clase", "codigo"),
    [
        (AvisoInvalido, "aviso_invalido"),
        (PersonaNoEncontrada, "persona_no_encontrada"),
        (TelefonoNoPermitido, "telefono_no_permitido"),
        (ErrorCanal, "error_canal"),
        (ErrorConnect, "error_connect"),
        (ErrorBaseDatos, "error_base_datos"),
        (ErrorConfiguracion, "error_configuracion"),
        (LlamadasDesactivadas, "llamadas_desactivadas"),
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


def test_el_error_de_connect_es_un_error_del_canal_de_aviso() -> None:
    assert issubclass(ErrorConnect, ErrorCanal)
