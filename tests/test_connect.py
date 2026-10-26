import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    NoRegionError,
    PartialCredentialsError,
)
from botocore.stub import Stubber

import adapters.connect as modulo_connect
from adapters.connect import (
    CODIGOS_AWS_CONOCIDOS,
    CONFIG_CONNECT,
    LONGITUD_MAXIMA_ATRIBUTO,
    ConnectAdapter,
)
from core.errores import ErrorConfiguracion, ErrorConnect

INSTANCE_ID = "11111111-2222-3333-4444-555555555555"
CONTACT_FLOW_ID = "66666666-7777-8888-9999-000000000000"
ORIGEN = "+15550000001"
DESTINO = "+34600000001"
SSML = "<speak>Mensaje de prueba</speak>"
PARAMETROS = {
    "DestinationPhoneNumber": DESTINO,
    "ContactFlowId": CONTACT_FLOW_ID,
    "InstanceId": INSTANCE_ID,
    "SourcePhoneNumber": ORIGEN,
    "Attributes": {"mensaje": SSML},
}


def _cliente() -> Any:
    return boto3.client(
        "connect",
        region_name="eu-central-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _adaptador(cliente: Any) -> ConnectAdapter:
    return ConnectAdapter(cliente, INSTANCE_ID, CONTACT_FLOW_ID, ORIGEN)


class _ClienteQueFalla:
    """Cliente falso: lanza siempre `error` y cuenta las llamadas."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.llamadas = 0

    def start_outbound_voice_contact(self, **_: object) -> dict[str, str]:
        self.llamadas += 1
        raise self._error


class _ClienteQueDevuelve:
    """Cliente falso: devuelve siempre `respuesta`."""

    def __init__(self, respuesta: dict[str, Any]) -> None:
        self._respuesta = respuesta

    def start_outbound_voice_contact(self, **_: object) -> dict[str, Any]:
        return self._respuesta


def _error_aws(codigo: str | None) -> ClientError:
    cuerpo = {} if codigo is None else {"Code": codigo}
    return ClientError({"Error": cuerpo}, "StartOutboundVoiceContact")


def test_inicia_la_llamada_con_los_parametros_exactos() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_response(
            "start_outbound_voice_contact",
            {"ContactId": "contacto-prueba"},
            expected_params=PARAMETROS,
        )

        contacto = _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

        stubber.assert_no_pending_responses()
    assert contacto == "contacto-prueba"


@pytest.mark.parametrize(
    "codigo",
    [
        "ResourceNotFoundException",
        "LimitExceededException",
        "DestinationNotAllowedException",
        "AccessDeniedException",
        "ThrottlingException",
    ],
)
def test_client_error_se_traduce_a_error_connect_con_el_codigo(codigo: str) -> None:
    cliente = _ClienteQueFalla(_error_aws(codigo))

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    assert str(info.value) == f"Connect rechazó la llamada (código: {codigo})."
    assert info.value.__context__ is None
    assert info.value.__cause__ is None


def test_el_error_no_filtra_telefono_ssml_ni_texto_de_aws() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_client_error(
            "start_outbound_voice_contact",
            service_error_code="AccessDeniedException",
            service_message=f"secreto {DESTINO} {SSML}",
        )

        with pytest.raises(ErrorConnect) as info:
            _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    texto = str(info.value) + repr(info.value)
    for dato in (DESTINO, "600000001", SSML, "Mensaje de prueba", "secreto"):
        assert dato not in texto


def test_codigos_conocidos_incluyen_modelo_y_acceso() -> None:
    esperados = {
        "InvalidRequestException",
        "InvalidParameterException",
        "ResourceNotFoundException",
        "InternalServiceException",
        "LimitExceededException",
        "DestinationNotAllowedException",
        "OutboundContactNotPermittedException",
        "ThrottlingException",
        "AccessDeniedException",
    }
    assert esperados == set(CODIGOS_AWS_CONOCIDOS)


def test_codigo_desconocido_no_se_refleja() -> None:
    cliente = _ClienteQueFalla(_error_aws("x34600000001"))

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    assert str(info.value) == "Connect rechazó la llamada."


def test_client_error_sin_codigo_usa_mensaje_sin_codigo() -> None:
    cliente = _ClienteQueFalla(_error_aws(None))

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    assert str(info.value) == "Connect rechazó la llamada."


@pytest.mark.parametrize(
    "error",
    [
        NoCredentialsError(),
        PartialCredentialsError(provider="p", cred_var="v"),
        NoRegionError(),
    ],
)
def test_configuracion_de_aws_incompleta(error: Exception) -> None:
    cliente = _ClienteQueFalla(error)

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    mensaje = "Configuración de AWS incompleta para llamar a Connect."
    assert str(info.value) == mensaje
    assert info.value.__context__ is None


def test_error_generico_de_botocore_se_traduce_a_error_connect() -> None:
    cliente = _ClienteQueFalla(
        EndpointConnectionError(endpoint_url=f"https://{DESTINO}.invalid")
    )

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    assert str(info.value) == "Fallo al comunicarse con Connect."
    assert DESTINO not in str(info.value)
    assert info.value.__context__ is None


def test_el_fallo_se_registra_con_tipo_y_codigo_sin_datos(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_client_error(
            "start_outbound_voice_contact",
            service_error_code="LimitExceededException",
            service_message=f"detalle {DESTINO} {SSML}",
        )
        with (
            caplog.at_level(logging.WARNING, logger="adapters.connect"),
            pytest.raises(ErrorConnect),
        ):
            _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    (registro,) = caplog.records
    assert registro.getMessage() == "connect_fallo"
    assert registro.tipo == "LimitExceededException"  # excepción modelada
    assert registro.codigo == "LimitExceededException"
    texto = caplog.text + repr(registro.__dict__)
    for dato in (DESTINO, "600000001", SSML, "Mensaje de prueba", "detalle"):
        assert dato not in texto


def test_codigo_desconocido_no_se_registra(caplog: pytest.LogCaptureFixture) -> None:
    cliente = _ClienteQueFalla(_error_aws("x34600000001"))
    with (
        caplog.at_level(logging.WARNING, logger="adapters.connect"),
        pytest.raises(ErrorConnect),
    ):
        _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    assert caplog.records[0].codigo is None
    assert "34600000001" not in caplog.text + repr(caplog.records[0].__dict__)


def test_error_del_stubber_se_ve_en_el_log(caplog: pytest.LogCaptureFixture) -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_response(
            "start_outbound_voice_contact",
            {"ContactId": "c-1"},
            expected_params={"InstanceId": "otro"},
        )
        with (
            caplog.at_level(logging.WARNING, logger="adapters.connect"),
            pytest.raises(ErrorConnect),
        ):
            _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    assert caplog.records[0].tipo == "StubAssertionError"
    assert caplog.records[0].codigo is None


@pytest.mark.parametrize("destino", ["", "600000001", "+34 600000001", "+0600000001"])
def test_destino_invalido_no_llama_a_connect(destino: str) -> None:
    cliente = _ClienteQueFalla(RuntimeError("no debe llamarse"))

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(destino, SSML)

    assert cliente.llamadas == 0
    assert str(info.value) == "El teléfono de destino no es válido."


def test_mensaje_demasiado_largo_no_llama_a_connect() -> None:
    cliente = _ClienteQueFalla(RuntimeError("no debe llamarse"))
    largo = "a" * (LONGITUD_MAXIMA_ATRIBUTO + 1)

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(DESTINO, largo)

    assert cliente.llamadas == 0
    assert "aaaa" not in str(info.value)


def test_el_limite_se_mide_en_bytes_utf8() -> None:
    cliente = _ClienteQueFalla(RuntimeError("no debe llamarse"))
    # Caracteres de 2 bytes: 32768 bytes en total, uno por encima del límite.
    con_tildes = "á" * ((LONGITUD_MAXIMA_ATRIBUTO + 1) // 2)
    assert len(con_tildes) < LONGITUD_MAXIMA_ATRIBUTO

    with pytest.raises(ErrorConnect):
        _adaptador(cliente).iniciar_llamada(DESTINO, con_tildes)

    assert cliente.llamadas == 0


def test_mensaje_con_tildes_justo_en_el_limite_se_envia() -> None:
    cliente = _cliente()
    justo = "á" * (LONGITUD_MAXIMA_ATRIBUTO // 2) + "a"
    assert len(justo.encode("utf-8")) == LONGITUD_MAXIMA_ATRIBUTO
    with Stubber(cliente) as stubber:
        stubber.add_response(
            "start_outbound_voice_contact",
            {"ContactId": "c-1"},
            expected_params={**PARAMETROS, "Attributes": {"mensaje": justo}},
        )

        assert _adaptador(cliente).iniciar_llamada(DESTINO, justo) == "c-1"

        stubber.assert_no_pending_responses()


def test_mensaje_vacio_no_llama_a_connect() -> None:
    cliente = _ClienteQueFalla(RuntimeError("no debe llamarse"))

    with pytest.raises(ErrorConnect):
        _adaptador(cliente).iniciar_llamada(DESTINO, "")

    assert cliente.llamadas == 0


def test_dos_llamadas_consumen_dos_respuestas_encoladas() -> None:
    cliente = _cliente()
    with Stubber(cliente) as stubber:
        stubber.add_response("start_outbound_voice_contact", {"ContactId": "c-1"})
        stubber.add_response("start_outbound_voice_contact", {"ContactId": "c-2"})
        adaptador = _adaptador(cliente)

        primero = adaptador.iniciar_llamada(DESTINO, SSML)
        segundo = adaptador.iniciar_llamada(DESTINO, SSML)

        stubber.assert_no_pending_responses()
    assert (primero, segundo) == ("c-1", "c-2")


@pytest.mark.parametrize("respuesta", [{}, {"ContactId": None}, {"ContactId": ""}])
def test_contact_id_ausente_o_vacio_es_error(respuesta: dict[str, Any]) -> None:
    cliente = _ClienteQueDevuelve(respuesta)

    with pytest.raises(ErrorConnect) as info:
        _adaptador(cliente).iniciar_llamada(DESTINO, SSML)

    assert str(info.value) == "Connect no devolvió el identificador del contacto."


def test_origen_invalido_lanza_error_de_configuracion() -> None:
    with pytest.raises(ErrorConfiguracion) as info:
        ConnectAdapter(_cliente(), INSTANCE_ID, CONTACT_FLOW_ID, "no-es-telefono")

    assert "no-es-telefono" not in str(info.value)


@pytest.mark.parametrize("campo", ["instance_id", "contact_flow_id"])
def test_ids_vacios_lanzan_error_de_configuracion(campo: str) -> None:
    ids = {"instance_id": INSTANCE_ID, "contact_flow_id": CONTACT_FLOW_ID}
    ids[campo] = ""

    with pytest.raises(ErrorConfiguracion, match=campo):
        ConnectAdapter(_cliente(), ids["instance_id"], ids["contact_flow_id"], ORIGEN)


def _parchear_boto3(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    llamadas: list[dict[str, Any]] = []

    def cliente_falso(*args: object, **kwargs: Any) -> object:
        llamadas.append({"args": args, **kwargs})
        return object()

    monkeypatch.setattr(modulo_connect.boto3, "client", cliente_falso)
    return llamadas


def test_crear_usa_la_configuracion_de_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas = _parchear_boto3(monkeypatch)

    adaptador = ConnectAdapter.crear(INSTANCE_ID, CONTACT_FLOW_ID, ORIGEN)

    assert isinstance(adaptador, ConnectAdapter)
    (llamada,) = llamadas
    assert llamada["args"] == ("connect",)
    config = llamada["config"]
    assert config is CONFIG_CONNECT
    assert config.region_name == "eu-central-1"
    assert config.retries == {"total_max_attempts": 1, "mode": "standard"}
    assert config.connect_timeout == 3
    assert config.read_timeout == 10


ENTORNO = {
    "CONNECT_INSTANCE_ID": INSTANCE_ID,
    "CONNECT_CONTACT_FLOW_ID": CONTACT_FLOW_ID,
    "CONNECT_NUMERO_ORIGEN": ORIGEN,
}


def test_desde_entorno_crea_el_adaptador(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas = _parchear_boto3(monkeypatch)

    adaptador = ConnectAdapter.desde_entorno(ENTORNO)

    assert isinstance(adaptador, ConnectAdapter)
    assert len(llamadas) == 1


@pytest.mark.parametrize("variable", sorted(ENTORNO))
def test_desde_entorno_con_variable_ausente(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    llamadas = _parchear_boto3(monkeypatch)
    entorno = {k: v for k, v in ENTORNO.items() if k != variable}

    with pytest.raises(ErrorConfiguracion) as info:
        ConnectAdapter.desde_entorno(entorno)

    assert variable in str(info.value)
    assert llamadas == []


@pytest.mark.parametrize("variable", sorted(ENTORNO))
def test_desde_entorno_con_valor_vacio(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    _parchear_boto3(monkeypatch)

    with pytest.raises(ErrorConfiguracion) as info:
        ConnectAdapter.desde_entorno({**ENTORNO, variable: ""})

    assert variable in str(info.value)


def test_desde_entorno_con_origen_invalido_no_muestra_el_valor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _parchear_boto3(monkeypatch)

    with pytest.raises(ErrorConfiguracion) as info:
        ConnectAdapter.desde_entorno({**ENTORNO, "CONNECT_NUMERO_ORIGEN": "secreto"})

    assert "CONNECT_NUMERO_ORIGEN" in str(info.value)
    assert "secreto" not in str(info.value)


RAIZ_REPO = Path(__file__).resolve().parent.parent


def test_importar_el_modulo_no_crea_clientes() -> None:
    guion = (
        "import boto3\n"
        "def falso(*a, **k):\n"
        "    raise SystemExit('se creó un cliente al importar')\n"
        "boto3.client = falso\n"
        "import adapters.connect\n"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", guion],
        cwd=RAIZ_REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr


def test_sin_stubber_la_red_bloqueada_corta_la_llamada() -> None:
    # Cliente real sin Stubber: el único freno es el bloqueo de red del conftest.
    cliente = _cliente()

    with pytest.raises(Exception, match="red bloqueada en tests") as info:
        cliente.start_outbound_voice_contact(**PARAMETROS)

    assert not isinstance(info.value, ClientError)
