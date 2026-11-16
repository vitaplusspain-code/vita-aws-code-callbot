import pytest

from core.checkin_guion import GUION, Pregunta, TipoRespuesta, Trato
from core.interprete import LONGITUD_MAXIMA_TEXTO, InterpreteReglas

_PREGUNTAS = {p.tipo: p for p in GUION}


def _interpretar(tipo: TipoRespuesta, texto: str) -> str | None:
    return InterpreteReglas().interpretar(_PREGUNTAS[tipo], texto, Trato.USTED)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("bien", "bien"),
        ("Muy bien, gracias", "bien"),
        ("estupendo", "bien"),
        ("Genial", "bien"),
        ("fenomenal", "bien"),
        ("perfecto", "bien"),
        ("no me puedo quejar", "bien"),
        ("no hay quejas, estoy bien", "bien"),
        ("no, estoy bien", "bien"),
        ("no sé, bien", "bien"),
        ("no te preocupes, bien", "bien"),
        ("mal", "mal"),
        ("muy mal", "mal"),
        ("Fatal", "mal"),
        ("no muy bien", "mal"),
        ("no estoy bien", "mal"),
        ("no me encuentro bien hoy", "mal"),
        ("no me encuentro muy bien", "mal"),
        ("no estoy nada bien", "mal"),
        ("no del todo bien", "mal"),
        ("regular", "regular"),
        ("más o menos", "regular"),
        ("así así", "regular"),
        ("normal", "regular"),
        ("tirando", "regular"),
        ("mas o menos bien", "regular"),
        ("ni bien ni mal", "regular"),
        ("no estoy mal", "regular"),
        ("no me encuentro mal", "regular"),
        ("no estoy nada mal", "regular"),
        ("el tiempo está raro", None),
        ("no sé", None),
        ("", None),
        ("bienvenido", None),
    ],
)
def test_animo(texto: str, esperado: str | None) -> None:
    assert _interpretar(TipoRespuesta.ANIMO, texto) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("sí", "si"),
        ("claro que sí", "si"),
        ("por supuesto", "si"),
        ("ya he comido", "si"),
        ("he comido", "si"),
        ("sí he comido", "si"),
        ("comí", "si"),
        ("sí, no se preocupe", "si"),
        ("no", "no"),
        ("todavía no", "no"),
        ("aún no", "no"),
        ("no he comido", "no"),
        ("ya no", "no"),
        ("claro que no", "no"),
        ("por supuesto que no", "no"),
        ("que va", "no"),
        ("claro", None),
        ("ya", None),
        ("no sé", None),
        ("no lo sé", None),
        ("no me acuerdo", None),
        ("no estoy seguro", None),
        ("no sabría decir", None),
        ("no lo sé, creo que sí", None),
        ("sí y no", None),
        ("no, sí he comido", None),
        ("quizá luego", None),
        ("", None),
    ],
)
def test_si_no(texto: str, esperado: str | None) -> None:
    assert _interpretar(TipoRespuesta.SI_NO, texto) == esperado


def test_texto_libre_recorta_y_limpia() -> None:
    assert _interpretar(TipoRespuesta.TEXTO_LIBRE, "  sopa \n y  fruta ") == (
        "sopa y fruta"
    )
    assert _interpretar(TipoRespuesta.TEXTO_LIBRE, "a\x00b\u200bc") == "abc"
    largo = _interpretar(TipoRespuesta.TEXTO_LIBRE, "x" * 500)
    assert largo == "x" * LONGITUD_MAXIMA_TEXTO


@pytest.mark.parametrize("texto", ["", "   ", "\x00\n"])
def test_texto_libre_vacio_es_none(texto: str) -> None:
    assert _interpretar(TipoRespuesta.TEXTO_LIBRE, texto) is None


def test_tipo_desconocido() -> None:
    pregunta = Pregunta(GUION[0].paso, "otro", "a", "b")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="desconocido"):
        InterpreteReglas().interpretar(pregunta, "hola", Trato.TU)
