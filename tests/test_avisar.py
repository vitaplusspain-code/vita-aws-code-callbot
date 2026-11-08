import pytest

from core.alerta import Alerta, ReglasAviso
from core.avisar import (
    CODIGO_FALLO_INTERNO,
    PERMISO_AVISOS,
    Desenlace,
    Resultado,
    ServicioAviso,
)
from core.destinatario import Destinatario
from core.errores import AvisoInvalido, ErrorBaseDatos, ErrorConnect
from core.lista_blanca import ListaBlanca
from core.motivos import VERSION_GUION
from core.puertos import CanalAviso, RepositorioAvisos
from tests.dobles import CanalFalso, RepositorioFalso

ALERTA_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"
PERSONA_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
CONTACTO_ID = "3b241101-e2bb-4255-8caf-4136c566a962"
CALL_ID = "9a1c2b3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d"
TELEFONO = "+34600000003"

ALERTA = Alerta(
    alert_id=ALERTA_ID,
    person_id=PERSONA_ID,
    rule_id="fall.detected",
    severity="critical",
    antiguedad_segundos=30,
    persona_nombre="Carmen",
)
DESTINATARIO = Destinatario(
    contacto_id=CONTACTO_ID, nombre="Francisco", telefono=TELEFONO
)
REGLAS = ReglasAviso(reglas_siempre=frozenset({"sos"}), antiguedad_maxima_segundos=3600)


def _repositorio(alerta: Alerta = ALERTA) -> RepositorioFalso:
    return RepositorioFalso(
        alertas={alerta.alert_id: alerta},
        consentimientos={(PERSONA_ID, PERMISO_AVISOS)},
        contactos={PERSONA_ID: DESTINATARIO},
    )


def _servicio(
    repositorio: RepositorioFalso,
    canal: CanalFalso | None = None,
    telefonos: frozenset[str] = frozenset({TELEFONO}),
) -> ServicioAviso:
    return ServicioAviso(
        repositorio=repositorio,
        canal=canal or CanalFalso(),
        lista_blanca=ListaBlanca(telefonos=telefonos),
        reglas=REGLAS,
        nuevo_id=lambda: CALL_ID,
    )


def test_los_dobles_cumplen_los_puertos() -> None:
    assert isinstance(RepositorioFalso(), RepositorioAvisos)
    assert isinstance(CanalFalso(), CanalAviso)


def test_el_permiso_exigido_es_alert_calls() -> None:
    assert PERMISO_AVISOS == "alert_calls"


def test_una_alerta_valida_termina_en_llamada_registrada() -> None:
    repositorio = _repositorio()
    canal = CanalFalso(contact_id="c-123")

    desenlace = _servicio(repositorio, canal).avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.LLAMADA, contact_id="c-123")
    assert repositorio.recibidas == [ALERTA_ID]
    assert len(canal.llamadas) == 1
    assert canal.llamadas[0][0] == TELEFONO
    assert repositorio.contactos_registrados == [(CALL_ID, "c-123")]


def test_la_reserva_lleva_la_alerta_el_destinatario_y_la_version() -> None:
    repositorio = _repositorio()

    _servicio(repositorio).avisar(ALERTA_ID)

    (reserva,) = repositorio.reservas
    assert reserva.call_id == CALL_ID
    assert reserva.alerta == ALERTA
    assert reserva.destinatario == DESTINATARIO
    assert reserva.version_guion == VERSION_GUION


def test_el_mensaje_nombra_al_familiar_en_el_saludo_y_a_la_persona_en_el_detalle() -> (
    None
):
    canal = CanalFalso()

    _servicio(_repositorio(), canal).avisar(ALERTA_ID)

    mensaje = canal.llamadas[0][1]
    assert "Francisco" in mensaje.saludo
    assert "Carmen" not in mensaje.saludo
    assert "Carmen" in mensaje.detalle


def test_la_recepcion_se_registra_aunque_la_alerta_no_exista() -> None:
    repositorio = RepositorioFalso()

    desenlace = _servicio(repositorio).avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.NO_ABIERTA)
    assert repositorio.recibidas == [ALERTA_ID]


@pytest.mark.parametrize(
    ("cambios", "resultado"),
    [
        ({"antiguedad_segundos": 3601}, Resultado.ANTIGUA),
        ({"severity": "high", "rule_id": "otra"}, Resultado.NO_GRAVE),
    ],
)
def test_una_alerta_antigua_o_no_grave_no_llama(
    cambios: dict[str, object], resultado: Resultado
) -> None:
    alerta = ALERTA.model_copy(update=cambios)
    repositorio = _repositorio(alerta)
    canal = CanalFalso()

    desenlace = _servicio(repositorio, canal).avisar(ALERTA_ID)

    assert desenlace == Desenlace(resultado)
    assert canal.llamadas == []
    assert repositorio.reservas == []


def test_una_alerta_no_critica_de_una_regla_que_siempre_avisa_llama() -> None:
    alerta = ALERTA.model_copy(update={"severity": "high", "rule_id": "sos"})

    desenlace = _servicio(_repositorio(alerta)).avisar(ALERTA_ID)

    assert desenlace.resultado is Resultado.LLAMADA


def test_sin_consentimiento_no_llama() -> None:
    repositorio = _repositorio()
    repositorio.consentimientos = {(PERSONA_ID, "calls")}
    canal = CanalFalso()

    desenlace = _servicio(repositorio, canal).avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.SIN_CONSENTIMIENTO)
    assert canal.llamadas == []


def test_sin_contacto_principal_no_llama() -> None:
    repositorio = _repositorio()
    repositorio.contactos = {}

    desenlace = _servicio(repositorio).avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.SIN_CONTACTO)


def test_un_telefono_fuera_de_la_lista_blanca_no_se_reserva_ni_se_llama() -> None:
    repositorio = _repositorio()
    canal = CanalFalso()

    desenlace = _servicio(repositorio, canal, telefonos=frozenset()).avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.FUERA_LISTA_BLANCA)
    assert repositorio.reservas == []
    assert canal.llamadas == []


def test_una_alerta_ya_avisada_no_vuelve_a_llamar() -> None:
    repositorio = _repositorio()
    canal = CanalFalso()
    servicio = _servicio(repositorio, canal)
    servicio.avisar(ALERTA_ID)

    desenlace = servicio.avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.YA_AVISADA)
    assert len(canal.llamadas) == 1


def test_si_el_canal_falla_se_registra_el_fallo_y_no_se_reintenta() -> None:
    repositorio = _repositorio()
    canal = CanalFalso(error=ErrorConnect("Connect rechazó la llamada."))

    desenlace = _servicio(repositorio, canal).avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.FALLO_CANAL, codigo_error="error_connect")
    assert repositorio.fallos == [(CALL_ID, "error_connect")]
    assert len(canal.llamadas) == 1
    assert repositorio.contactos_registrados == []


def test_si_no_se_puede_guardar_el_contacto_la_llamada_cuenta_como_hecha() -> None:
    repositorio = _repositorio()
    repositorio.fallar_al_registrar_contacto = ErrorBaseDatos("Aurora no responde.")

    desenlace = _servicio(repositorio, CanalFalso(contact_id="c-9")).avisar(ALERTA_ID)

    assert desenlace == Desenlace(Resultado.LLAMADA_SIN_REGISTRO, contact_id="c-9")


def test_un_fallo_de_base_de_datos_antes_de_llamar_se_propaga() -> None:
    class RepositorioRoto(RepositorioFalso):
        def alerta_abierta(self, alert_id: str) -> Alerta | None:
            raise ErrorBaseDatos("Aurora no responde.")

    canal = CanalFalso()

    with pytest.raises(ErrorBaseDatos):
        _servicio(RepositorioRoto(), canal).avisar(ALERTA_ID)
    assert canal.llamadas == []


def test_el_id_de_llamada_por_defecto_es_un_uuid_nuevo_cada_vez() -> None:
    servicio = ServicioAviso(
        repositorio=_repositorio(),
        canal=CanalFalso(),
        lista_blanca=ListaBlanca(telefonos=frozenset({TELEFONO})),
        reglas=REGLAS,
    )

    assert servicio.nuevo_id() != servicio.nuevo_id()
    assert len(servicio.nuevo_id()) == 36


def test_un_alert_id_en_mayusculas_se_normaliza() -> None:
    repositorio = _repositorio()

    desenlace = _servicio(repositorio).avisar(ALERTA_ID.upper())

    assert desenlace.resultado is Resultado.LLAMADA
    assert repositorio.recibidas == [ALERTA_ID]


@pytest.mark.parametrize("alert_id", ["no-es-uuid", "", "x" * 5000, None, 12])
def test_un_alert_id_invalido_no_toca_la_base_de_datos(alert_id: object) -> None:
    repositorio = _repositorio()

    with pytest.raises(AvisoInvalido) as info:
        _servicio(repositorio).avisar(alert_id)  # type: ignore[arg-type]

    assert repositorio.recibidas == []
    assert "no-es-uuid" not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_si_falla_la_auditoria_no_se_llama() -> None:
    class AuditoriaRota(RepositorioFalso):
        def registrar_recepcion(self, alert_id: str) -> None:
            raise ErrorBaseDatos("Aurora no responde.")

    repositorio = AuditoriaRota(
        alertas={ALERTA_ID: ALERTA},
        consentimientos={(PERSONA_ID, PERMISO_AVISOS)},
        contactos={PERSONA_ID: DESTINATARIO},
    )
    canal = CanalFalso()

    with pytest.raises(ErrorBaseDatos):
        _servicio(repositorio, canal).avisar(ALERTA_ID)
    assert canal.llamadas == []


def test_si_no_se_puede_construir_el_mensaje_no_se_reserva(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def roto(*_: object) -> None:
        raise ValueError("plantilla rota")

    monkeypatch.setattr("core.avisar.construir_mensaje_aviso", roto)
    repositorio = _repositorio()

    with pytest.raises(ValueError, match="plantilla rota"):
        _servicio(repositorio).avisar(ALERTA_ID)
    assert repositorio.reservas == []


def test_un_error_inesperado_del_canal_marca_el_fallo_y_se_propaga() -> None:
    repositorio = _repositorio()
    canal = CanalFalso(error=RuntimeError("inesperado"))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="inesperado"):
        _servicio(repositorio, canal).avisar(ALERTA_ID)
    assert repositorio.fallos == [(CALL_ID, CODIGO_FALLO_INTERNO)]


def test_si_no_se_puede_guardar_el_fallo_se_indica_en_el_desenlace() -> None:
    repositorio = _repositorio()
    repositorio.fallar_al_registrar_fallo = ErrorBaseDatos("Aurora no responde.")
    canal = CanalFalso(error=ErrorConnect("Connect rechazó la llamada."))

    desenlace = _servicio(repositorio, canal).avisar(ALERTA_ID)

    assert desenlace == Desenlace(
        Resultado.FALLO_CANAL_SIN_REGISTRO, codigo_error="error_connect"
    )


def test_un_error_inesperado_se_propaga_aunque_no_se_pueda_guardar_el_fallo() -> None:
    repositorio = _repositorio()
    repositorio.fallar_al_registrar_fallo = ErrorBaseDatos("Aurora no responde.")
    canal = CanalFalso(error=RuntimeError("inesperado"))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="inesperado"):
        _servicio(repositorio, canal).avisar(ALERTA_ID)
