import ast
import importlib
from pathlib import Path

import pytest


@pytest.mark.parametrize("paquete", ["core", "adapters", "handlers"])
def test_paquetes_de_la_arquitectura_hexagonal_se_importan(paquete: str) -> None:
    modulo = importlib.import_module(paquete)

    assert modulo.__doc__


@pytest.mark.parametrize(
    "modulo", ["conversar", "puertos_checkin", "checkin", "lanzador"]
)
def test_el_nucleo_de_la_conversacion_no_importa_aws_ni_capas_externas(
    modulo: str,
) -> None:
    ruta = Path(__file__).resolve().parent.parent / "core" / f"{modulo}.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    importados = {
        (nodo.module or "") if isinstance(nodo, ast.ImportFrom) else alias.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Import | ast.ImportFrom)
        for alias in (nodo.names if isinstance(nodo, ast.Import) else [nodo])
    }
    raices = {nombre.split(".")[0] for nombre in importados}

    assert not raices & {"adapters", "handlers", "boto3", "botocore"}
