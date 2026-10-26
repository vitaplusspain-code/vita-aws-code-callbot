import socket

import pytest


def test_la_red_esta_bloqueada() -> None:
    with pytest.raises(RuntimeError, match="red bloqueada en tests"):
        socket.create_connection(("127.0.0.1", 9))
    with pytest.raises(RuntimeError, match="red bloqueada en tests"):
        socket.socket().connect(("127.0.0.1", 9))
    with pytest.raises(RuntimeError, match="red bloqueada en tests"):
        socket.socket().connect_ex(("127.0.0.1", 9))
