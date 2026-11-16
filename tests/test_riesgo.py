import unicodedata

import pytest

from core.riesgo import LONGITUD_MAXIMA_VERBATIM, TipoRiesgo, detectar_riesgo

F = TipoRiesgo.FALL
C = TipoRiesgo.CHEST_PAIN
B = TipoRiesgo.BREATHING
O = TipoRiesgo.OTHER  # noqa: E741
S = TipoRiesgo.SELF_HARM

FRASES: list[tuple[TipoRiesgo, str]] = [
    (F, "me he caído"),
    (F, "me caí"),
    (F, "me caigo"),
    (F, "me he vuelto a caer"),
    (F, "me he resbalado"),
    (F, "me he tropezado"),
    (F, "me he dado un golpe"),
    (F, "me he roto la cadera"),
    (F, "estoy en el suelo"),
    (F, "estoy tirado en el baño"),
    (F, "no me puedo levantar"),
    (F, "no puedo levantarme"),
    (F, "no puedo moverme"),
    (F, "no consigo levantarme"),
    (F, "tuve una caída"),
    (C, "me duele el pecho"),
    (C, "me duele mucho aquí el pecho"),
    (C, "me duele un poco el pecho"),
    (C, "me duele el corazón"),
    (C, "dolor fuerte en el pecho"),
    (C, "me aprieta el pecho"),
    (C, "opresión"),
    (C, "infarto"),
    (C, "ataque al corazón"),
    (C, "dolor en el brazo izquierdo"),
    (C, "dolor de pecho"),
    (B, "no puedo respirar"),
    (B, "no puedo ni respirar"),
    (B, "no puedo casi respirar"),
    (B, "no respiro"),
    (B, "me cuesta respirar"),
    (B, "me ahogo"),
    (B, "me estoy ahogando"),
    (B, "me falta el aire"),
    (B, "no me entra el aire"),
    (B, "me he atragantado"),
    (O, "no siento el brazo"),
    (O, "no puedo mover la pierna"),
    (O, "se me ha dormido la cara"),
    (O, "no puedo hablar"),
    (O, "me cuesta hablar"),
    (O, "hablo raro"),
    (O, "veo doble"),
    (O, "ictus"),
    (O, "derrame"),
    (O, "me he desmayado"),
    (O, "me mareo"),
    (O, "me he mareado"),
    (O, "he perdido el conocimiento"),
    (O, "sangre"),
    (O, "sangro"),
    (O, "estoy sangrando"),
    (O, "hemorragia"),
    (O, "tengo un dolor muy fuerte"),
    (O, "me duele muchísimo"),
    (O, "me voy a morir"),
    (O, "me muero"),
    (O, "me estoy muriendo"),
    (O, "estoy grave"),
    (O, "estoy fatal"),
    (O, "me encuentro fatal"),
    (O, "me encuentro muy mal"),
    (O, "socorro"),
    (O, "auxilio"),
    (O, "ayuda"),
    (O, "ayúdame"),
    (O, "ayúdeme"),
    (O, "ayúdenme"),
    (O, "llama a una ambulancia"),
    (O, "necesito un médico"),
    (S, "me quiero morir"),
    (S, "quiero morirme"),
    (S, "no quiero vivir"),
    (S, "no quiero seguir viviendo"),
    (S, "quiero acabar con todo"),
    (S, "me quiero matar"),
    (S, "suicidarme"),
    (S, "suicidio"),
    (S, "quitarme la vida"),
    (S, "mejor estaría muerto"),
    (S, "estoy cansado de vivir"),
    (S, "no quiero despertar"),
]


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


@pytest.mark.parametrize(("tipo", "frase"), FRASES)
def test_riesgo_detectado_con_variantes(tipo: TipoRiesgo, frase: str) -> None:
    variantes = [
        frase,
        _sin_tildes(frase),
        frase.upper(),
        f"¡{frase.capitalize()}!",
        f"Pues... {_sin_tildes(frase).upper()}, sí.",
    ]
    for texto in variantes:
        senal = detectar_riesgo(texto)

        assert senal is not None, texto
        assert senal.kind is tipo, texto


@pytest.mark.parametrize(
    ("texto", "tipo"),
    [
        ("me quiero morir y me ahogo", S),
        ("me duele el pecho y no puedo respirar", C),
        ("no puedo respirar y me he caído", B),
        ("me he caído, socorro", F),
        ("socorro, quiero morirme", S),
        ("me he caído y me quiero morir", S),
    ],
)
def test_prioridad_entre_tipos(texto: str, tipo: TipoRiesgo) -> None:
    senal = detectar_riesgo(texto)

    assert senal is not None
    assert senal.kind is tipo


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "estoy bien",
        "me encuentro bien",
        "me encuentro mal",
        "estoy mal",
        "he comido pecho de pollo",
        "me duele la rodilla",
    ],
)
def test_sin_riesgo(texto: str) -> None:
    assert detectar_riesgo(texto) is None


def test_ancho_cero_dentro_de_la_frase_no_esconde_el_riesgo() -> None:
    senal = detectar_riesgo("me he ca\u200bído")

    assert senal is not None
    assert senal.kind is F
    assert senal.verbatim == "me he caído"


@pytest.mark.parametrize(
    ("texto", "tipo"),
    [
        ("no me he caído", F),  # limitación documentada: no hay negaciones
        ("me ayuda mi hija", O),  # limitación documentada: «ayuda» suelto
    ],
)
def test_limitaciones_conocidas_disparan(texto: str, tipo: TipoRiesgo) -> None:
    senal = detectar_riesgo(texto)

    assert senal is not None
    assert senal.kind is tipo


def test_verbatim_limpio() -> None:
    senal = detectar_riesgo("  me he caído\x00 \n en  casa ")

    assert senal is not None
    assert senal.verbatim == "me he caído en casa"


def test_verbatim_largo_empieza_por_el_acierto_cercano_al_inicio() -> None:
    senal = detectar_riesgo("  socorro " + "z" * 3000)

    assert senal is not None
    assert len(senal.verbatim) <= LONGITUD_MAXIMA_VERBATIM
    assert senal.verbatim.startswith("socorro")


def test_verbatim_largo_se_recorta_alrededor_del_acierto() -> None:
    texto = "bla " * 800 + "me he caído en el baño" + " bla" * 800

    senal = detectar_riesgo(texto)

    assert senal is not None
    assert len(senal.verbatim) <= LONGITUD_MAXIMA_VERBATIM
    assert "me he caído" in senal.verbatim


def test_verbatim_largo_con_acierto_al_final() -> None:
    texto = "bla " * 800 + "socorro"

    senal = detectar_riesgo(texto)

    assert senal is not None
    assert len(senal.verbatim) <= LONGITUD_MAXIMA_VERBATIM
    assert senal.verbatim.endswith("socorro")


def test_repr_no_expone_la_frase() -> None:
    senal = detectar_riesgo("me he caído")

    assert senal is not None
    assert "caído" not in repr(senal)
