"""Aislamiento común: sin credenciales ni red reales en ningún test."""

import os
import socket
from collections.abc import Iterator

import pytest

_PREFIJO_ENDPOINT = "AWS_ENDPOINT_URL"


def _red_bloqueada(*_: object, **__: object) -> None:
    raise RuntimeError("red bloqueada en tests")


@pytest.fixture(autouse=True)
def _aislar_aws_y_red(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fija credenciales falsas, anula la configuración local y corta la red."""
    for variable in list(os.environ):
        if variable.startswith(_PREFIJO_ENDPOINT):
            monkeypatch.delenv(variable)
    for variable in ("AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_CONFIG_FILE", os.devnull)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", os.devnull)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(socket.socket, "connect", _red_bloqueada)
    monkeypatch.setattr(socket.socket, "connect_ex", _red_bloqueada)
    monkeypatch.setattr(socket, "create_connection", _red_bloqueada)
    yield
