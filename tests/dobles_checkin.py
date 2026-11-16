"""Intérpretes falsos para probar la conversación sin reglas reales."""

from core.checkin import Turno
from core.checkin_guion import Pregunta, Trato
from core.errores import ErrorBaseDatos
from core.puertos_checkin import DatosConversacion


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


class ContextoFijo:
    """Contexto en memoria: devuelve unos datos fijos (o `None`)."""

    def __init__(self, datos: DatosConversacion | None) -> None:
        self.datos_fijos = datos
        self.consultas: list[str] = []

    def datos(self, call_id: str) -> DatosConversacion | None:
        self.consultas.append(call_id)
        return self.datos_fijos


class ContextoQueLanza:
    """Contexto con la base de datos caída."""

    def datos(self, call_id: str) -> DatosConversacion | None:
        raise ErrorBaseDatos("Aurora caída")


class RegistroEnMemoria:
    """Guarda los turnos en una lista."""

    def __init__(self) -> None:
        self.turnos: list[tuple[str, Turno]] = []

    def guardar_turno(self, call_id: str, turno: Turno) -> None:
        self.turnos.append((call_id, turno))


class RegistroQueLanza:
    """Registro que falla siempre al guardar."""

    def guardar_turno(self, call_id: str, turno: Turno) -> None:
        raise ErrorBaseDatos("no se pudo guardar")
