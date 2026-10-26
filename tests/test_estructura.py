import importlib

import pytest


@pytest.mark.parametrize("paquete", ["core", "adapters", "handlers"])
def test_paquetes_de_la_arquitectura_hexagonal_se_importan(paquete: str) -> None:
    modulo = importlib.import_module(paquete)

    assert modulo.__doc__
