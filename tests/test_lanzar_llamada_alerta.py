"""`POST /avisos` con `{"alert_id": ...}`: ruta nueva con `ServicioAviso`."""

import base64
import io
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest

import handlers.lanzar_llamada as modulo
from adapters.aurora import AuroraAdapter
from adapters.connect import ConnectAdapter
from core.alerta import Alerta
from core.avisar import Desenlace, Resultado, ServicioAviso
from core.destinatario import Destinatario
from core.errores import (
    DatosInvalidos,
    ErrorBaseDatos,
    ErrorConfiguracion,
    ErrorConnect,
)
from tests.dobles import CanalFalso, RepositorioFalso

ALERT_ID = "0b6f1c1e-4a52-4d0e-9d6a-1f2b3c4d5e6f"
PERSON_ID = "11111111-1111-4111-8111-111111111111"
TELEFONO = "+447700900001"
NOMBRE_PERSONA = "Persona Prueba"
NOMBRE_FAMILIAR = "Familiar Prueba"
RESPUESTA_FIJA = {"estado": "recibido"}
ENTORNO = {
    "LLAMADAS_ACTIVAS": "true",
    "LISTA_BLANCA": TELEFONO,
    "DB_CLUSTER_ARN": "arn:aws:rds:eu-west-1:000000000000:cluster:falso",
    "DB_SECRET_ARN": "arn:aws:secretsmanager:eu-west-1:000000000000:secret:falso",
    "DB_NAME": "falsa",
}


@dataclass
class ContextoFalso:
    function_name: str = "vita-dev-callbot-lanzar-llamada"
    memory_limit_in_mb: int = 128
    invoked_function_arn: str = "arn:aws:lambda:eu-central-1:000000000000:function:f"
    aws_request_id: str = "req-1"


def _alerta(**cambios: Any) -> Alerta:
    datos: dict[str, Any] = {
        "alert_id": ALERT_ID,
        "person_id": PERSON_ID,
        "rule_id": "sos",
        "severity": "critical",
        "antiguedad_segundos": 10,
        "persona_nombre": NOMBRE_PERSONA,
    }
    return Alerta(**{**datos, **cambios})


def _repositorio() -> RepositorioFalso:
    repo = RepositorioFalso()
    repo.alertas[ALERT_ID] = _alerta()
    repo.consentimientos.add((PERSON_ID, "alert_calls"))
    repo.contactos[PERSON_ID] = Destinatario(
        contacto_id="22222222-2222-4222-8222-222222222222",
        nombre=NOMBRE_FAMILIAR,
        telefono=TELEFONO,
    )
    return repo


@pytest.fixture
def canal() -> CanalFalso:
    return CanalFalso(contact_id="contacto-123")


@pytest.fixture
def repo(
    monkeypatch: pytest.MonkeyPatch, canal: CanalFalso
) -> Iterator[RepositorioFalso]:
    """Entorno válido con Aurora y Connect falsos (sin AWS)."""
    for nombre, valor in ENTORNO.items():
        monkeypatch.setenv(nombre, valor)
    falso = _repositorio()
    monkeypatch.setattr(
        AuroraAdapter, "desde_entorno", classmethod(lambda _c, _e: falso)
    )
    monkeypatch.setattr(
        ConnectAdapter, "desde_entorno", classmethod(lambda _c, _e: canal)
    )
    modulo.limpiar_cache()
    yield falso
    modulo.limpiar_cache()


@pytest.fixture
def salida_logs() -> Iterator[io.StringIO]:
    manejador = modulo.logger.registered_handler
    buffer = io.StringIO()
    anterior = manejador.setStream(buffer)
    yield buffer
    manejador.setStream(anterior)


def _registros(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(x) for x in buffer.getvalue().splitlines() if x.strip()]


def _evento(cuerpo: object = None) -> dict[str, Any]:
    texto = json.dumps({"alert_id": ALERT_ID} if cuerpo is None else cuerpo)
    return {"httpMethod": "POST", "path": "/avisos", "body": texto}


def _lanzar(ev: Any) -> dict[str, Any]:
    return modulo.handler(ev, ContextoFalso())


def _json(respuesta: dict[str, Any]) -> dict[str, Any]:
    return json.loads(respuesta["body"])


def test_alerta_valida_llama_y_responde_202_fijo(
    repo: RepositorioFalso, canal: CanalFalso
) -> None:
    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 202
    assert _json(respuesta) == RESPUESTA_FIJA
    assert [d for d, _ in canal.llamadas] == [TELEFONO]
    assert repo.recibidas == [ALERT_ID]


def test_uuid_en_mayusculas_se_normaliza(repo: RepositorioFalso) -> None:
    _lanzar(_evento({"alert_id": ALERT_ID.upper()}))

    assert repo.recibidas == [ALERT_ID]


@pytest.mark.parametrize("resultado", list(Resultado))
def test_cualquier_desenlace_da_la_misma_respuesta(
    repo: RepositorioFalso,
    monkeypatch: pytest.MonkeyPatch,
    resultado: Resultado,
) -> None:
    monkeypatch.setattr(
        ServicioAviso, "avisar", lambda _s, _a: Desenlace(resultado, "c-1", "e")
    )

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 202
    assert respuesta["body"] == json.dumps(RESPUESTA_FIJA)


def _sin_alerta(repo: RepositorioFalso, _canal: CanalFalso) -> None:
    repo.alertas.clear()


def _antigua(repo: RepositorioFalso, _canal: CanalFalso) -> None:
    repo.alertas[ALERT_ID] = _alerta(antiguedad_segundos=901)


def _leve(repo: RepositorioFalso, _canal: CanalFalso) -> None:
    repo.alertas[ALERT_ID] = _alerta(severity="low")


def _sin_consentimiento(repo: RepositorioFalso, _canal: CanalFalso) -> None:
    repo.consentimientos.clear()


def _sin_contacto(repo: RepositorioFalso, _canal: CanalFalso) -> None:
    repo.contactos.clear()


def _canal_roto(_repo: RepositorioFalso, canal: CanalFalso) -> None:
    canal.error = ErrorConnect("x")


@pytest.mark.parametrize(
    "preparar",
    [_sin_alerta, _antigua, _leve, _sin_consentimiento, _sin_contacto, _canal_roto],
)
def test_resultados_reales_no_se_distinguen_en_la_respuesta(
    repo: RepositorioFalso,
    canal: CanalFalso,
    preparar: Callable[[RepositorioFalso, CanalFalso], None],
) -> None:
    preparar(repo, canal)

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 202
    assert _json(respuesta) == RESPUESTA_FIJA


def test_ya_avisada_responde_igual_y_no_llama_dos_veces(
    repo: RepositorioFalso, canal: CanalFalso
) -> None:
    primera = _lanzar(_evento())
    segunda = _lanzar(_evento())

    assert primera == segunda
    assert len(canal.llamadas) == 1


def test_log_aviso_procesado_lleva_resultado_y_alert_id(
    repo: RepositorioFalso, salida_logs: io.StringIO
) -> None:
    _lanzar(_evento())

    texto = salida_logs.getvalue()
    (registro,) = _registros(salida_logs)
    assert registro["message"] == "aviso_procesado"
    assert registro["level"] == "INFO"
    assert registro["resultado"] == "llamada"
    assert registro["alert_id"] == ALERT_ID
    for secreto in (TELEFONO, NOMBRE_PERSONA, NOMBRE_FAMILIAR, "contacto-123"):
        assert secreto not in texto


def test_log_registra_el_resultado_aunque_no_se_llame(
    repo: RepositorioFalso, salida_logs: io.StringIO
) -> None:
    repo.alertas.clear()

    _lanzar(_evento())

    (registro,) = _registros(salida_logs)
    assert registro["resultado"] == "no_abierta"


def test_interruptor_apagado_es_503_antes_de_tocar_nada(
    repo: RepositorioFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLAMADAS_ACTIVAS", "no")

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 503
    assert repo.recibidas == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"alert_id": "no-es-uuid"},
        {"alert_id": 5},
        {"alert_id": ALERT_ID, "extra": 1},
        {"alert_id": ALERT_ID, "persona_id": "demo-01", "caso": "sueno_irregular"},
        {"alert_id": ALERT_ID, "caso": "sueno_irregular"},
        {"ALERT_ID": ALERT_ID},
        {},
    ],
)
def test_cuerpos_invalidos_son_400_sin_tocar_aurora(
    repo: RepositorioFalso, canal: CanalFalso, cuerpo: dict[str, Any]
) -> None:
    respuesta = _lanzar(_evento(cuerpo))

    assert respuesta["statusCode"] == 400
    assert _json(respuesta)["error"]["codigo"] == "aviso_invalido"
    assert repo.recibidas == []
    assert canal.llamadas == []


def test_cuerpo_demasiado_grande_es_400(repo: RepositorioFalso) -> None:
    respuesta = _lanzar(_evento({"alert_id": ALERT_ID, "x": "a" * 2000}))

    assert respuesta["statusCode"] == 400


def test_cuerpo_en_base64_se_acepta(repo: RepositorioFalso) -> None:
    ev = _evento()
    ev["body"] = base64.b64encode(ev["body"].encode()).decode()
    ev["isBase64Encoded"] = True

    assert _lanzar(ev)["statusCode"] == 202


def test_error_de_base_datos_es_500_con_codigo_propio(
    repo: RepositorioFalso,
    canal: CanalFalso,
    monkeypatch: pytest.MonkeyPatch,
    salida_logs: io.StringIO,
) -> None:
    def fallar(_alert_id: str) -> None:
        raise ErrorBaseDatos("detalle-secreto")

    monkeypatch.setattr(repo, "registrar_recepcion", fallar)

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 500
    assert _json(respuesta) == {
        "error": {
            "codigo": "error_base_datos",
            "mensaje": "No se pudo registrar el aviso.",
        }
    }
    assert "detalle-secreto" not in respuesta["body"]
    assert "detalle-secreto" not in salida_logs.getvalue()
    assert canal.llamadas == []


@pytest.mark.parametrize("variable", ["DB_CLUSTER_ARN", "DB_SECRET_ARN", "DB_NAME"])
def test_sin_variables_de_aurora_es_error_de_configuracion(
    monkeypatch: pytest.MonkeyPatch, canal: CanalFalso, variable: str
) -> None:
    for nombre, valor in ENTORNO.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.delenv(variable)
    monkeypatch.setattr(
        ConnectAdapter, "desde_entorno", classmethod(lambda _c, _e: canal)
    )
    modulo.limpiar_cache()

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 500
    assert _json(respuesta)["error"]["codigo"] == "error_configuracion"


def test_antiguedad_invalida_es_error_de_configuracion_sin_el_valor(
    repo: RepositorioFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTIGUEDAD_MAXIMA_SEGUNDOS", "SENTINELA")
    modulo.limpiar_cache()

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 500
    assert _json(respuesta)["error"]["codigo"] == "error_configuracion"
    assert "SENTINELA" not in respuesta["body"]


def test_el_entorno_configura_las_reglas(
    repo: RepositorioFalso, canal: CanalFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.alertas[ALERT_ID] = _alerta(severity="low", rule_id="caida")
    monkeypatch.setenv("REGLAS_SIEMPRE", "caida")
    monkeypatch.setenv("ANTIGUEDAD_MAXIMA_SEGUNDOS", "5")
    modulo.limpiar_cache()

    _lanzar(_evento())
    assert canal.llamadas == []  # 10 s > 5 s

    monkeypatch.setenv("ANTIGUEDAD_MAXIMA_SEGUNDOS", "60")
    modulo.limpiar_cache()
    _lanzar(_evento())
    assert len(canal.llamadas) == 1


def test_servicio_se_crea_una_vez_y_limpiar_cache_lo_olvida(
    repo: RepositorioFalso,
) -> None:
    _lanzar(_evento())
    primero = modulo._servicio_aviso()

    assert modulo._servicio_aviso() is primero
    modulo.limpiar_cache()
    assert modulo._servicio_aviso() is not primero


def test_fallo_de_construccion_no_se_cachea(
    monkeypatch: pytest.MonkeyPatch, repo: RepositorioFalso
) -> None:
    intentos: list[int] = []

    def crear(_cls: type, _entorno: object) -> RepositorioFalso:
        intentos.append(1)
        if len(intentos) == 1:
            raise ErrorConfiguracion("Falta la variable DB_NAME.")
        return repo

    monkeypatch.setattr(AuroraAdapter, "desde_entorno", classmethod(crear))
    modulo.limpiar_cache()

    assert _lanzar(_evento())["statusCode"] == 500
    assert _lanzar(_evento())["statusCode"] == 202


def test_la_demo_no_construye_nada_de_la_ruta_nueva(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_crear(*_: object) -> None:
        raise AssertionError("la demo no debe crear Aurora")

    monkeypatch.setattr(AuroraAdapter, "desde_entorno", classmethod(no_crear))
    monkeypatch.setenv("LLAMADAS_ACTIVAS", "true")
    monkeypatch.setenv("DEMO_ACTIVA", "true")
    monkeypatch.delenv("CONNECT_INSTANCE_ID", raising=False)
    modulo.limpiar_cache()
    cuerpo = {"persona_id": "demo-01", "caso": "sueno_irregular"}

    respuesta = _lanzar(_evento(cuerpo))

    assert _json(respuesta)["error"]["codigo"] == "error_configuracion"


def test_la_ruta_alert_id_no_depende_de_demo_activa(
    repo: RepositorioFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_ACTIVA", "false")

    assert _lanzar(_evento())["statusCode"] == 202


def test_base64_invalido_es_400(repo: RepositorioFalso) -> None:
    ev = _evento()
    ev["body"] = "!!!no base64!!!"
    ev["isBase64Encoded"] = True

    respuesta = _lanzar(ev)

    assert respuesta["statusCode"] == 400
    assert _json(respuesta)["error"]["codigo"] == "aviso_invalido"
    assert repo.recibidas == []


def test_base64_por_encima_del_maximo_es_400(repo: RepositorioFalso) -> None:
    ev = _evento()
    ev["body"] = base64.b64encode(b"a" * 5000).decode()
    ev["isBase64Encoded"] = True

    respuesta = _lanzar(ev)

    assert respuesta["statusCode"] == 400
    assert repo.recibidas == []


def test_error_al_reservar_es_500_sin_llamar_a_connect(
    repo: RepositorioFalso,
    canal: CanalFalso,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fallar(_reserva: object) -> bool:
        raise ErrorBaseDatos("detalle-secreto")

    monkeypatch.setattr(repo, "reservar_llamada", fallar)

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 500
    assert _json(respuesta)["error"]["codigo"] == "error_base_datos"
    assert "detalle-secreto" not in respuesta["body"]
    assert canal.llamadas == []


def test_datos_invalidos_responde_202_igual_que_el_exito_y_lo_registra(
    repo: RepositorioFalso,
    canal: CanalFalso,
    monkeypatch: pytest.MonkeyPatch,
    salida_logs: io.StringIO,
) -> None:
    def fallar(_alert_id: str) -> None:
        raise DatosInvalidos("detalle-secreto")

    monkeypatch.setattr(repo, "alerta_abierta", fallar)

    respuesta = _lanzar(_evento())

    assert respuesta["statusCode"] == 202
    assert respuesta["body"] == json.dumps(RESPUESTA_FIJA)
    assert canal.llamadas == []
    (registro,) = _registros(salida_logs)
    assert registro["message"] == "aviso_fallido"
    assert registro["level"] == "ERROR"
    assert registro["codigo"] == "datos_invalidos"
    assert registro["alert_id"] == ALERT_ID
    assert "detalle-secreto" not in salida_logs.getvalue()
