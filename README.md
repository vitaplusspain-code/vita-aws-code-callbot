# vita-aws-code-callbot

Lógica en Python del callbot de VitaPlus. En la fase 1, un aviso (`POST /avisos`) hace que Amazon Connect llame al familiar y una voz de Polly le cuente el caso.

La infraestructura (plantilla SAM y guía de despliegue) vive en el repo `vita-aws-infra-callbot`.

## Estructura

- `core/`: lógica pura, sin AWS (aviso, casos, mensaje SSML, lista blanca).
- `adapters/`: lo único que habla con AWS (Connect) y los repositorios de datos.
- `handlers/`: puntos de entrada de las Lambdas.
- `tests/`: pruebas con pytest. Ninguna hace llamadas de red: AWS se simula con `botocore.stub.Stubber`.
- `events/`: eventos de ejemplo para `sam local invoke`.
- `docs/`: [contrato de la API de avisos](docs/contrato-api.md), para quien la llame desde la web.

Este repo es público: no contiene teléfonos, identificadores de cuenta o de Connect ni datos de personas. Todo eso llega por variables de entorno desde la plantilla.

## Entorno local

Requiere Python 3.13.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt    # Windows
# .venv/bin/python -m pip install -r requirements-dev.txt      # Linux / macOS
.venv/Scripts/python -m pip install -r requirements-tools.txt  # SAM CLI, opcional
```

- `requirements.txt`: dependencias de la Lambda (las empaqueta `sam build`).
- `requirements-dev.txt`: lo anterior más pruebas y lint.
- `requirements-tools.txt`: SAM CLI, aparte porque fija sus propias versiones de boto3.

## Comprobaciones

```bash
ruff check .
ruff format --check .
pytest --cov=core --cov=adapters --cov=handlers --cov-fail-under=80
```

El estilo es PEP 8, comprobado con ruff (configuración en `pyproject.toml`).
