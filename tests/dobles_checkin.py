"""Intérpretes falsos para probar la conversación sin reglas reales."""

from core.checkin_guion import Pregunta, Trato


class InterpreteFijo:
    """Devuelve siempre lo mismo (o `None`)."""

    def __init__(self, valor: str | None) -> None:
        self.valor = valor

    def interpretar(self, pregunta: Pregunta, texto: str, trato: Trato) -> str | None:
        return self.valor


class InterpreteEspia:
    """Anota las llamadas; un test de riesgo exige que no haya ninguna."""

    def __init__(self) -> None:
        self.llamadas: list[tuple[Pregunta, str, Trato]] = []

    def interpretar(self, pregunta: Pregunta, texto: str, trato: Trato) -> str | None:
        self.llamadas.append((pregunta, texto, trato))
        return None


class InterpreteQueLanza:
    """Rompe siempre, como un modelo caído."""

    def interpretar(self, pregunta: Pregunta, texto: str, trato: Trato) -> str | None:
        raise RuntimeError("fallo del modelo")
