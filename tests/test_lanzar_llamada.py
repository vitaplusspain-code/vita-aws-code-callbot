import base64
import importlib
import io
import json
import subprocess
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

import handlers.lanzar_llamada as modulo
from adapters.connect import ConnectAdapter
from core.errores import ErrorCallbot, ErrorConfiguracion, ErrorConnect
from core.mensaje import construir_mensaje
from core.telefono import enmascarar_telefono
from core.tipos import Caso

RAIZ = Path(__file__).resolve().parent.parent
# Rangos reservados para ficción: no son marcables.
DESTINO = "+447700900001"
OTRO = "+447700900099"
ORIGEN = "+15550100001"
NOMBRE_PERSONA = "Persona Prueba"
NOMBRE_FAMILIAR = "Familiar Prueba"
INSTANCE_ID = "11111111-2222-3333-4444-555555555555"
CONTACT_FLOW_ID = "66666666-7777-8888-9999-000000000000"
ENTORNO = {
    "LLAMADAS_ACTIVAS": "true",
    "CONNECT_INSTANCE_ID": INSTANCE_ID,
    "CONNECT_CONTACT_FLOW_ID": CONTACT_FLOW_ID,
    "CONNECT_NUMERO_ORIGEN": ORIGEN,
    "LISTA_BLANCA": DESTINO,
    "DEMO_PERSONA_NOMBRE": NOMBRE_PERSONA,
    "DEMO_FAMILIAR_NOMBRE": NOMBRE_FAMILIAR,
    "DEMO_FAMILIAR_TELEFONO": DESTINO,
}
CUERPO_OK = json.dumps({"persona_id": "demo-01", "caso": "sin_actividad_hoy"})
SSML_ESPERADO = construir_mensaje(
    Caso.SIN_ACTIVIDAD_HOY, NOMBRE_PERSONA, NOMBRE_FAMILIAR
)


@dataclass
class ContextoFalso:
    function_name: str = "vita-dev-callbot-lanzar-llamada"
    memory_limit_in_mb: int = 128
    invoked_function_arn: str = "arn:aws:lambda:eu-central-1:000000000000:function:f"
    aws_request_id: str = "req-1"


class ClienteFalso:
    """Cliente de Connect falso: guarda las llamadas y devuelve un ContactId."""

    def __init__(self) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def fallar_con(self, error: Exception) -> None:
        """Hace que las siguientes llamadas lancen `error`."""
        self.error = error

    def start_outbound_voice_contact(self, **kwargs: Any) -> Mapping[str, Any]:
        self.llamadas.append(kwargs)
        if self.error:
            raise self.error
        return {"ContactId": "contacto-123"}


def _parchear_cliente(monkeypatch: pytest.MonkeyPatch, cliente: Any) -> None:
    def crear(cls: type[ConnectAdapter], *args: str) -> ConnectAdapter:
        return cls(cliente, *args)

    monkeypatch.setattr(ConnectAdapter, "crear", classmethod(crear))


@pytest.fixture
def entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Variables válidas y caché de dependencias limpia."""
    for nombre, valor in ENTORNO.items():
        monkeypatch.setenv(nombre, valor)
    modulo.limpiar_cache()


@pytest.fixture
def cliente(entorno: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[ClienteFalso]:
    """Entorno válido y cliente de Connect falso en lugar del de boto3."""
    falso = ClienteFalso()
    _parchear_cliente(monkeypatch, falso)
    yield falso
    modulo.limpiar_cache()


@pytest.fixture
def salida_logs() -> Iterator[io.StringIO]:
    """Redirige el handler real de Powertools a un buffer durante el test."""
    manejador = modulo.logger.registered_handler
    buffer = io.StringIO()
    anterior = manejador.setStream(buffer)
    yield buffer
    manejador.setStream(anterior)


def registros(buffer: io.StringIO) -> list[dict[str, Any]]:
    """Líneas JSON que escribió Powertools."""
    lineas = buffer.getvalue().splitlines()
    return [json.loads(linea) for linea in lineas if linea.strip()]


def evento(
    cuerpo: str | None = CUERPO_OK, *, base64_activo: bool = False
) -> dict[str, Any]:
    return {
        "httpMethod": "POST",
        "path": "/avisos",
        "body": cuerpo,
        "isBase64Encoded": base64_activo,
    }


def lanzar(ev: Any) -> dict[str, Any]:
    return modulo.handler(ev, ContextoFalso())


def cuerpo_de(respuesta: dict[str, Any]) -> dict[str, Any]:
    return json.loads(respuesta["body"])


def codigo_de(respuesta: dict[str, Any]) -> str:
    return cuerpo_de(respuesta)["error"]["codigo"]


def test_aviso_valido_devuelve_200_con_contact_id(cliente: ClienteFalso) -> None:
    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 200
    assert cuerpo_de(respuesta) == {"contact_id": "contacto-123"}
    assert respuesta["headers"]["Content-Type"] == "application/json"


def test_camino_feliz_con_cliente_boto3_y_stubber(
    entorno: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    boto = boto3.client(
        "connect",
        region_name="eu-central-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    _parchear_cliente(monkeypatch, boto)
    esperados = {
        "DestinationPhoneNumber": DESTINO,
        "ContactFlowId": CONTACT_FLOW_ID,
        "InstanceId": INSTANCE_ID,
        "SourcePhoneNumber": ORIGEN,
        "Attributes": {"mensaje": SSML_ESPERADO},
    }
    with Stubber(boto) as stubber:
        stubber.add_response(
            "start_outbound_voice_contact",
            {"ContactId": "contacto-stub"},
            expected_params=esperados,
        )

        respuesta = lanzar(evento())

        stubber.assert_no_pending_responses()
    assert respuesta["statusCode"] == 200
    assert cuerpo_de(respuesta) == {"contact_id": "contacto-stub"}
    modulo.limpiar_cache()


def test_llama_al_familiar_con_el_mensaje_del_caso(cliente: ClienteFalso) -> None:
    lanzar(evento())

    (llamada,) = cliente.llamadas
    assert llamada["DestinationPhoneNumber"] == DESTINO
    assert llamada["Attributes"]["mensaje"] == SSML_ESPERADO
    assert "112" in SSML_ESPERADO


def test_llamadas_desactivadas_devuelve_503_sin_leer_body(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLAMADAS_ACTIVAS", "false")

    class EventoQueExplota(dict[str, object]):
        def get(self, *_: object) -> None:
            raise AssertionError("se ha leído el evento")

    respuesta = lanzar(EventoQueExplota())

    assert respuesta["statusCode"] == 503
    assert codigo_de(respuesta) == "llamadas_desactivadas"
    assert cliente.llamadas == []


def test_llamadas_ausente_es_503_y_no_construye_nada(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    for nombre in ENTORNO:
        monkeypatch.delenv(nombre)

    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 503
    assert cliente.llamadas == []


@pytest.mark.parametrize(
    "ev",
    [
        evento(None),
        evento(""),
        evento("no es json"),
        evento("[]"),
        evento('{"persona_id": "demo-01"}'),
        evento('{"persona_id": "demo-01", "caso": "otro"}'),
        evento('{"persona_id": "a", "persona_id": "b", "caso": "sueno_irregular"}'),
        evento("x" * 5000),
        evento("!!!no base64!!!", base64_activo=True),
        evento(None, base64_activo=True),
        evento("", base64_activo=True),
    ],
)
def test_body_invalido_devuelve_400(cliente: ClienteFalso, ev: dict[str, Any]) -> None:
    respuesta = lanzar(ev)

    assert respuesta["statusCode"] == 400
    assert codigo_de(respuesta) == "aviso_invalido"
    assert cliente.llamadas == []


def test_configuracion_rota_con_body_invalido_devuelve_400(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONNECT_INSTANCE_ID", "")
    modulo.limpiar_cache()

    respuesta = lanzar(evento("no es json"))

    assert respuesta["statusCode"] == 400
    assert codigo_de(respuesta) == "aviso_invalido"


def test_evento_que_no_es_un_diccionario_devuelve_400(cliente: ClienteFalso) -> None:
    respuesta = lanzar(None)

    assert respuesta["statusCode"] == 400


def test_body_en_base64_se_decodifica(cliente: ClienteFalso) -> None:
    codificado = base64.b64encode(CUERPO_OK.encode()).decode()

    respuesta = lanzar(evento(codificado, base64_activo=True))

    assert respuesta["statusCode"] == 200
    assert len(cliente.llamadas) == 1


def _json_con_bytes(total: int) -> str:
    """Aviso válido rellenado con espacios hasta `total` bytes."""
    return CUERPO_OK + " " * (total - len(CUERPO_OK))


def test_base64_en_el_limite_exacto_se_decodifica(cliente: ClienteFalso) -> None:
    codificado = base64.b64encode(_json_con_bytes(1024).encode()).decode()
    assert len(codificado) == modulo._MAXIMO_BASE64

    respuesta = lanzar(evento(codificado, base64_activo=True))

    assert respuesta["statusCode"] == 200


def test_base64_un_caracter_por_encima_del_limite_no_se_decodifica(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_decodificar(*_: object, **__: object) -> bytes:
        raise AssertionError("no debería decodificar")

    monkeypatch.setattr(modulo.base64, "b64decode", no_decodificar)
    codificado = "A" * (modulo._MAXIMO_BASE64 + 1)

    respuesta = lanzar(evento(codificado, base64_activo=True))

    assert respuesta["statusCode"] == 400
    assert cliente.llamadas == []


def test_base64_que_no_es_utf8_devuelve_400(cliente: ClienteFalso) -> None:
    codificado = base64.b64encode(b"\xff\xfe\x00{").decode()

    respuesta = lanzar(evento(codificado, base64_activo=True))

    assert respuesta["statusCode"] == 400


def test_base64_activo_con_cuerpo_no_codificado_devuelve_400(
    cliente: ClienteFalso,
) -> None:
    respuesta = lanzar(evento(CUERPO_OK, base64_activo=True))

    assert respuesta["statusCode"] == 400
    assert cliente.llamadas == []


def test_persona_inexistente_devuelve_400(cliente: ClienteFalso) -> None:
    cuerpo = json.dumps({"persona_id": "sentinela-persona", "caso": "sueno_irregular"})

    respuesta = lanzar(evento(cuerpo))

    assert respuesta["statusCode"] == 400
    assert codigo_de(respuesta) == "persona_no_encontrada"
    assert "sentinela-persona" not in respuesta["body"]
    assert cliente.llamadas == []


def test_telefono_fuera_de_lista_blanca_devuelve_403_sin_llamar(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LISTA_BLANCA", OTRO)
    modulo.limpiar_cache()

    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 403
    assert codigo_de(respuesta) == "telefono_no_permitido"
    assert cliente.llamadas == []


def test_lista_blanca_vacia_devuelve_403(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LISTA_BLANCA", "")
    modulo.limpiar_cache()

    assert lanzar(evento())["statusCode"] == 403
    assert cliente.llamadas == []


def test_lista_blanca_ausente_devuelve_500_de_configuracion(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LISTA_BLANCA")
    modulo.limpiar_cache()

    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 500
    assert codigo_de(respuesta) == "error_configuracion"
    assert cliente.llamadas == []


def test_error_de_connect_devuelve_500(cliente: ClienteFalso) -> None:
    cliente.fallar_con(ErrorConnect("sentinela-interna"))

    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 500
    assert codigo_de(respuesta) == "error_connect"
    assert "sentinela-interna" not in respuesta["body"]


def test_excepcion_inesperada_devuelve_500_generico(cliente: ClienteFalso) -> None:
    cliente.fallar_con(RuntimeError(f"sentinela-secreta {DESTINO}"))

    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 500
    assert codigo_de(respuesta) == "error_interno"
    assert "sentinela-secreta" not in respuesta["body"]
    assert DESTINO not in respuesta["body"]


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("CONNECT_NUMERO_ORIGEN", "SENTINELA-ORIGEN"),
        ("LISTA_BLANCA", "SENTINELA-LISTA"),
        ("DEMO_FAMILIAR_TELEFONO", "SENTINELA-TELEFONO"),
    ],
)
def test_configuracion_incorrecta_devuelve_500_sin_reflejar_el_valor(
    cliente: ClienteFalso,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    valor: str,
) -> None:
    monkeypatch.setenv(variable, valor)
    modulo.limpiar_cache()

    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 500
    assert codigo_de(respuesta) == "error_configuracion"
    assert valor not in respuesta["body"]
    assert cliente.llamadas == []


def test_instance_id_vacio_devuelve_500_de_configuracion(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONNECT_INSTANCE_ID", "")
    modulo.limpiar_cache()

    assert codigo_de(lanzar(evento())) == "error_configuracion"


# (código, estado HTTP, texto fijo, nivel del log)
CASOS_DE_ERROR = [
    (
        "llamadas_desactivadas",
        503,
        "El servicio de llamadas no está activo.",
        "WARNING",
    ),
    ("aviso_invalido", 400, "El aviso no es válido.", "WARNING"),
    ("persona_no_encontrada", 400, "La persona indicada no existe.", "WARNING"),
    (
        "telefono_no_permitido",
        403,
        "No se permite llamar a ese teléfono.",
        "WARNING",
    ),
    ("error_connect", 500, "No se pudo iniciar la llamada.", "ERROR"),
    (
        "error_configuracion",
        500,
        "El servicio no está bien configurado.",
        "ERROR",
    ),
    ("error_interno", 500, "Error interno.", "ERROR"),
]


def _provocar(
    codigo: str, cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Prepara el entorno para que la petición acabe en `codigo`."""
    ev = evento()
    if codigo == "llamadas_desactivadas":
        monkeypatch.setenv("LLAMADAS_ACTIVAS", "no")
    elif codigo == "aviso_invalido":
        ev = evento("no es json")
    elif codigo == "persona_no_encontrada":
        ev = evento(json.dumps({"persona_id": "otra", "caso": "sueno_irregular"}))
    elif codigo == "telefono_no_permitido":
        monkeypatch.setenv("LISTA_BLANCA", OTRO)
    elif codigo == "error_connect":
        cliente.fallar_con(ErrorConnect("detalle"))
    elif codigo == "error_configuracion":
        monkeypatch.setenv("CONNECT_NUMERO_ORIGEN", "mal")
    else:
        cliente.fallar_con(RuntimeError("detalle"))
    modulo.limpiar_cache()
    return ev


@pytest.mark.parametrize(("codigo", "estado", "texto", "_nivel"), CASOS_DE_ERROR)
def test_cada_error_devuelve_su_estado_y_su_texto_fijo(
    cliente: ClienteFalso,
    monkeypatch: pytest.MonkeyPatch,
    codigo: str,
    estado: int,
    texto: str,
    _nivel: str,
) -> None:
    respuesta = lanzar(_provocar(codigo, cliente, monkeypatch))

    assert respuesta["statusCode"] == estado
    assert cuerpo_de(respuesta) == {"error": {"codigo": codigo, "mensaje": texto}}


@pytest.mark.parametrize(("codigo", "_estado", "_texto", "nivel"), CASOS_DE_ERROR)
def test_el_nivel_del_log_depende_del_estado_http(
    cliente: ClienteFalso,
    monkeypatch: pytest.MonkeyPatch,
    salida_logs: io.StringIO,
    codigo: str,
    _estado: int,
    _texto: str,
    nivel: str,
) -> None:
    lanzar(_provocar(codigo, cliente, monkeypatch))

    (registro,) = registros(salida_logs)
    assert registro["level"] == nivel
    assert registro["codigo"] == codigo


def test_error_solo_contiene_codigo_y_mensaje(cliente: ClienteFalso) -> None:
    cuerpo = json.dumps({"persona_id": "demo-01", "caso": "x", "extra": "FILTRADO"})

    respuesta = lanzar(evento(cuerpo))

    assert set(cuerpo_de(respuesta)) == {"error"}
    assert set(cuerpo_de(respuesta)["error"]) == {"codigo", "mensaje"}
    assert "FILTRADO" not in respuesta["body"]
    assert "extra" not in respuesta["body"]


def test_error_del_dominio_sin_codigo_conocido_devuelve_error_interno(
    cliente: ClienteFalso, salida_logs: io.StringIO
) -> None:
    cliente.fallar_con(ErrorCallbot("detalle"))

    respuesta = lanzar(evento())

    assert respuesta["statusCode"] == 500
    assert codigo_de(respuesta) == "error_interno"
    (registro,) = registros(salida_logs)
    assert registro["codigo"] == "error_interno"
    assert registro["level"] == "ERROR"


def test_importar_sin_variables_de_entorno_no_construye_nada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nombre in ENTORNO:
        monkeypatch.delenv(nombre, raising=False)

    def no_crear(*_: object) -> None:
        raise AssertionError("se construyó el adaptador al importar")

    monkeypatch.setattr(ConnectAdapter, "crear", classmethod(no_crear))

    recargado = importlib.reload(modulo)

    assert callable(recargado.handler)
    assert recargado._dependencias.cache_info().currsize == 0


def test_importar_en_proceso_aislado_sin_entorno_no_falla() -> None:
    codigo = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import handlers.lanzar_llamada as m; print(callable(m.handler))"
    )

    resultado = subprocess.run(
        [sys.executable, "-I", "-c", codigo, str(RAIZ)],
        cwd=RAIZ,
        env={},
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "True"


def test_dependencias_se_crean_una_sola_vez(cliente: ClienteFalso) -> None:
    lanzar(evento())
    primera = modulo._dependencias()
    lanzar(evento())

    assert modulo._dependencias() is primera


def test_fallo_de_construccion_no_se_cachea(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONNECT_INSTANCE_ID", "")
    modulo.limpiar_cache()
    assert lanzar(evento())["statusCode"] == 500

    monkeypatch.setenv("CONNECT_INSTANCE_ID", INSTANCE_ID)

    assert lanzar(evento())["statusCode"] == 200


def test_error_de_configuracion_se_propaga_desde_dependencias(
    cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LISTA_BLANCA")
    modulo.limpiar_cache()

    with pytest.raises(ErrorConfiguracion):
        modulo._dependencias()


def test_logs_de_exito_llevan_el_telefono_enmascarado(
    cliente: ClienteFalso, salida_logs: io.StringIO
) -> None:
    lanzar(evento())

    texto = salida_logs.getvalue()
    (registro,) = registros(salida_logs)
    assert registro["telefono"] == enmascarar_telefono(DESTINO)
    assert registro["contact_id"] == "contacto-123"
    assert DESTINO not in texto
    assert "<speak" not in texto
    assert NOMBRE_PERSONA not in texto
    assert NOMBRE_FAMILIAR not in texto


def test_logs_de_rechazo_registran_codigo_sin_datos_del_cliente(
    cliente: ClienteFalso, salida_logs: io.StringIO
) -> None:
    lanzar(evento(json.dumps({"persona_id": "SENTINELA", "caso": "x"})))

    (registro,) = registros(salida_logs)
    assert registro["codigo"] == "aviso_invalido"
    assert "SENTINELA" not in salida_logs.getvalue()


def test_logs_de_excepcion_inesperada_no_incluyen_str_de_la_excepcion(
    cliente: ClienteFalso, salida_logs: io.StringIO
) -> None:
    cliente.fallar_con(RuntimeError(f"sentinela-fuga {DESTINO} {SSML_ESPERADO}"))

    lanzar(evento())

    texto = salida_logs.getvalue()
    (registro,) = registros(salida_logs)
    assert registro["tipo"] == "RuntimeError"
    assert "sentinela-fuga" not in texto
    assert DESTINO not in texto
    assert "<speak" not in texto
    assert NOMBRE_PERSONA not in texto
    assert NOMBRE_FAMILIAR not in texto


def test_log_de_excepcion_inesperada_indica_el_origen_sin_ruta(
    cliente: ClienteFalso, salida_logs: io.StringIO
) -> None:
    cliente.fallar_con(RuntimeError("detalle"))

    lanzar(evento())

    (registro,) = registros(salida_logs)
    fichero, _, linea = registro["origen"].rpartition(":")
    assert fichero == Path(__file__).name
    assert linea.isdigit()
    assert "/" not in registro["origen"]
    assert "\\" not in registro["origen"]


def test_no_se_loguea_el_evento_completo_ni_con_log_event_en_el_entorno(
    cliente: ClienteFalso,
    monkeypatch: pytest.MonkeyPatch,
    salida_logs: io.StringIO,
) -> None:
    monkeypatch.setenv("POWERTOOLS_LOGGER_LOG_EVENT", "true")
    importlib.reload(modulo)
    ev = evento() | {"headers": {"x-api-key": "SENTINELA-CLAVE"}}

    try:
        lanzar(ev)
    finally:
        monkeypatch.delenv("POWERTOOLS_LOGGER_LOG_EVENT")
        importlib.reload(modulo)

    texto = salida_logs.getvalue()
    assert texto
    for dato in ("SENTINELA-CLAVE", "persona_id", "httpMethod"):
        assert dato not in texto


def test_el_logger_usa_el_servicio_callbot(
    cliente: ClienteFalso, salida_logs: io.StringIO
) -> None:
    lanzar(evento())

    (registro,) = registros(salida_logs)
    assert registro["service"] == "callbot"


def test_origen_de_una_excepcion_sin_traza_es_desconocido() -> None:
    assert modulo._origen(RuntimeError("nunca lanzada")) == "desconocido"
