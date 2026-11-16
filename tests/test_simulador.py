import runpy

import pytest

from simulador import main


def _entradas(monkeypatch: pytest.MonkeyPatch, respuestas: list[str]) -> None:
    iterador = iter(respuestas)
    monkeypatch.setattr("builtins.input", lambda _="": next(iterador))


def test_recorrido_completo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _entradas(monkeypatch, ["bien", "regular", "sí", "lentejas"])

    codigo = main([])

    salida = capsys.readouterr().out
    assert codigo == 0
    assert "Hola, Carmen. Le llama el asistente automático" in salida
    assert "Hasta mañana." in salida
    assert "animo_hoy=bien" in salida
    assert "animo_semana=regular" in salida
    assert "comida_tomada=si" in salida
    assert "que_ha_comido='lentejas'" in salida
    assert "Sin señal de riesgo" in salida


def test_recorrido_con_riesgo_y_tuteo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _entradas(monkeypatch, ["me he caído"])

    codigo = main(["--nombre", "Luis", "--trato", "tu"])

    salida = capsys.readouterr().out
    assert codigo == 0
    assert "Hola, Luis. Te llama" in salida
    assert "Si es una urgencia, cuelga y llama al 112" in salida
    assert "Señal de riesgo: fall" in salida
    assert "me he caído" in salida
    assert "Observaciones: ninguna" in salida


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_salida_limpia_con_eof_o_ctrl_c(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: type[BaseException],
) -> None:
    def _input(_: str = "") -> str:
        raise error

    monkeypatch.setattr("builtins.input", _input)

    codigo = main([])

    assert codigo == 0
    assert "Conversación interrumpida" in capsys.readouterr().out


def test_nombre_invalido_da_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    codigo = main(["--nombre", "Ana2"])

    assert codigo == 2
    assert "nombre" in capsys.readouterr().err.lower()


def test_trato_desconocido_lo_rechaza_argparse() -> None:
    with pytest.raises(SystemExit):
        main(["--trato", "vos"])


def test_se_puede_ejecutar_como_modulo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _entradas(monkeypatch, ["socorro"])
    monkeypatch.setattr("sys.argv", ["simulador"])

    with pytest.raises(SystemExit) as salida:
        runpy.run_module("simulador", run_name="__main__")

    assert salida.value.code == 0
    assert "Señal de riesgo: other" in capsys.readouterr().out


def test_estoy_en_el_suelo_da_caida(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _entradas(monkeypatch, ["estoy en el suelo"])

    main([])

    salida = capsys.readouterr().out
    assert "Señal de riesgo: fall" in salida
    assert "buen día" not in salida


def test_me_quiero_morir_da_autolesion_y_024(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _entradas(monkeypatch, ["me quiero morir"])

    main([])

    salida = capsys.readouterr().out
    assert "Señal de riesgo: self_harm" in salida
    assert "024" in salida
