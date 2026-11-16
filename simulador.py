"""Simulador en texto de la conversación diaria: `python -m simulador`.

Solo para probar el guion en local: no usa AWS ni red.
"""

import argparse
import sys
from collections.abc import Sequence

from core.checkin import Observacion, Turno, avanzar, iniciar
from core.checkin_guion import Trato
from core.errores import NombreInvalido
from core.interprete import InterpreteReglas

__all__ = ["main"]


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="simulador", description=__doc__)
    parser.add_argument("--nombre", default="Carmen")
    parser.add_argument(
        "--trato", choices=[t.value for t in Trato], default=Trato.USTED.value
    )
    return parser.parse_args(argv)


def _resumen(observaciones: list[Observacion], turno: Turno) -> None:
    print("\n--- Resumen ---")
    if not observaciones:
        print("Observaciones: ninguna")
    for obs in observaciones:
        valor = obs.value_code if obs.value_code is not None else repr(obs.value_text)
        print(f"  {obs.indicator_code}={valor} (verbatim: {obs.verbatim!r})")
    if turno.senal_riesgo is None:
        print("Sin señal de riesgo")
    else:
        senal = turno.senal_riesgo
        print(f"Señal de riesgo: {senal.kind.value} (verbatim: {senal.verbatim!r})")


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta la conversación por consola; devuelve el código de salida."""
    args = _argumentos(argv)
    trato = Trato(args.trato)
    interprete = InterpreteReglas()
    try:
        turno = iniciar(args.nombre, trato)
    except NombreInvalido:
        print("El nombre no es válido.", file=sys.stderr)
        return 2
    observaciones: list[Observacion] = []
    print(f"Callbot: {turno.texto_a_decir}")
    try:
        while not turno.terminado:
            respuesta = input("Tú: ")
            turno = avanzar(turno.estado, respuesta, interprete, args.nombre, trato)
            observaciones.extend(turno.observaciones)
            print(f"Callbot: {turno.texto_a_decir}")
    except (EOFError, KeyboardInterrupt):
        print("\nConversación interrumpida.")
        return 0
    _resumen(observaciones, turno)
    return 0


if __name__ == "__main__":
    sys.exit(main())
