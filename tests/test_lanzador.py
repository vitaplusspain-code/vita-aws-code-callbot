import logging
from datetime import UTC, datetime, time
from itertools import count

import pytest

from core.errores import ErrorBaseDatos, ErrorConnect
from core.lanzador import (
    HORA_MAXIMA_CALL_TIME,
    HORA_MINIMA_LLAMADA,
    LIMITE_POR_INVOCACION,
    VENTANA_TOLERANCIA,
    VERSION_GUION_LLAMADA,
    CanalCheckin,
    Candidato,
    RepositorioCheckinDiario,
    ReservaCheckin,
    ServicioCheckin,
    toca_llamar,
)
from core.lista_blanca import ListaBlanca
from tests.dobles_lanzador import CanalCheckinFalso, RepositorioDiarioFalso

TEL = "+34611111111"
TEL_2 = "+34622222222"
# 2026-11-16 es lunes. En noviembre Madrid va en UTC+1.
LUNES_18_00 = datetime(2026, 11, 16, 17, 0, tzinfo=UTC)
LUNES_18_10 = datetime(2026, 11, 16, 17, 10, tzinfo=UTC)


def _persona(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _candidato(
    n: int = 1,
    telefono: str = TEL,
    hora: time = time(18, 0),
    dias: frozenset[int] | None = None,
) -> Candidato:
    return Candidato(_persona(n), telefono, hora, dias)


def _servicio(
    repo: RepositorioDiarioFalso,
    canal: CanalCheckinFalso,
    lista: ListaBlanca | None = None,
) -> ServicioCheckin:
    ids = count(1)
    return ServicioCheckin(
        repositorio=repo,
        canal=canal,
        lista_blanca=lista or ListaBlanca(frozenset({TEL, TEL_2})),
        nuevo_id=lambda: f"00000000-0000-0000-0000-{next(ids) + 900:012d}",
    )


def test_los_dobles_cumplen_los_puertos() -> None:
    assert isinstance(RepositorioDiarioFalso(), RepositorioCheckinDiario)
    assert isinstance(CanalCheckinFalso(), CanalCheckin)


# --- toca_llamar -------------------------------------------------------------


def test_toca_en_la_hora_exacta() -> None:
    assert toca_llamar(_candidato(), LUNES_18_00)


def test_toca_dentro_de_la_ventana() -> None:
    assert toca_llamar(_candidato(), LUNES_18_10)


def test_no_toca_antes_de_la_hora() -> None:
    antes = datetime(2026, 11, 16, 16, 59, tzinfo=UTC)

    assert not toca_llamar(_candidato(), antes)


def test_no_toca_cuando_la_ventana_ha_pasado() -> None:
    limite = LUNES_18_00 + VENTANA_TOLERANCIA

    assert not toca_llamar(_candidato(), limite)
    assert toca_llamar(_candidato(), limite - (limite - LUNES_18_00) / 100)


def test_usa_la_hora_de_madrid_no_la_utc() -> None:
    # 18:00 UTC son las 19:00 en Madrid en noviembre.
    assert not toca_llamar(_candidato(), datetime(2026, 11, 16, 18, 0, tzinfo=UTC))


def test_usa_el_horario_de_verano_de_madrid() -> None:
    # En julio Madrid va en UTC+2: 18:00 locales son las 16:00 UTC.
    verano = datetime(2026, 7, 6, 16, 0, tzinfo=UTC)

    assert toca_llamar(_candidato(), verano)


@pytest.mark.parametrize(
    ("dias", "esperado"),
    [
        (None, True),
        (frozenset({1, 3, 5}), True),
        (frozenset({2, 4}), False),
        (frozenset(), False),
    ],
)
def test_filtra_por_dia_de_la_semana_iso(
    dias: frozenset[int] | None, esperado: bool
) -> None:
    assert toca_llamar(_candidato(dias=dias), LUNES_18_00) is esperado


def test_ahora_sin_zona_horaria_se_rechaza() -> None:
    sin_zona = datetime(2026, 11, 16, 18, 0)  # noqa: DTZ001

    with pytest.raises(ValueError, match="zona horaria"):
        toca_llamar(_candidato(), sin_zona)


# --- Franja horaria permitida (call_time) -------------------------------------


def test_la_franja_del_call_time_es_de_09_00_a_20_45() -> None:
    assert HORA_MINIMA_LLAMADA == time(9, 0)
    assert HORA_MAXIMA_CALL_TIME == time(20, 45)


@pytest.mark.parametrize(
    ("hora", "esperado"),
    [
        (time(3, 0), False),
        (time(8, 59), False),
        (time(9, 0), True),
        (time(20, 45), True),
        (time(20, 50), False),
        (time(23, 45), False),
    ],
)
def test_solo_llama_si_el_call_time_esta_en_la_franja(
    hora: time, esperado: bool
) -> None:
    # Noviembre: Madrid = UTC+1; se prueba justo a la hora del perfil.
    ahora = datetime(2026, 11, 16, hora.hour - 1, hora.minute, tzinfo=UTC)

    assert toca_llamar(_candidato(hora=hora), ahora) is esperado


def test_a_las_tres_de_la_madrugada_nunca_llama() -> None:
    ahora = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)  # 03:00 en Madrid

    assert not toca_llamar(_candidato(hora=time(3, 0)), ahora)


def test_el_ultimo_disparo_de_las_20_45_llama_al_perfil_de_las_20_45() -> None:
    ahora = datetime(2026, 11, 16, 19, 45, tzinfo=UTC)  # 20:45 en Madrid

    assert toca_llamar(_candidato(hora=time(20, 45)), ahora)


# --- ServicioCheckin ---------------------------------------------------------


def test_reserva_y_llama_con_el_mismo_call_id_y_guarda_el_contacto() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato()])
    canal = CanalCheckinFalso()

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    reserva = repo.reservas[0]
    assert reserva.version_guion == VERSION_GUION_LLAMADA
    assert canal.llamadas == [(TEL, reserva.call_id)]
    assert repo.contactos == [(reserva.call_id, "contacto-1")]
    assert resumen.llamadas == 1


def test_reserva_la_fila_antes_de_llamar() -> None:
    orden: list[str] = []

    class Repo(RepositorioDiarioFalso):
        def reservar_llamada(self, reserva: ReservaCheckin) -> bool:
            orden.append("reservar")
            return super().reservar_llamada(reserva)

    class Canal(CanalCheckinFalso):
        def iniciar_llamada_checkin(self, destino: str, call_id: str) -> str:
            orden.append("llamar")
            return super().iniciar_llamada_checkin(destino, call_id)

    _servicio(Repo(candidatos_hoy=[_candidato()]), Canal()).lanzar(LUNES_18_00)

    assert orden == ["reservar", "llamar"]


def test_una_segunda_invocacion_no_duplica_llamadas() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato(1), _candidato(2)])
    canal = CanalCheckinFalso()
    servicio = _servicio(repo, canal)

    primera = servicio.lanzar(LUNES_18_00)
    segunda = servicio.lanzar(LUNES_18_10)

    assert primera.llamadas == 2
    assert segunda.llamadas == 0
    assert len(canal.llamadas) == 2


def test_si_otra_invocacion_reservo_antes_no_se_llama() -> None:
    repo = RepositorioDiarioFalso(
        candidatos_hoy=[_candidato()], ignorar_reservas_al_leer=True
    )
    repo.reservar_llamada(ReservaCheckin("x", repo.candidatos_hoy[0], "v"))
    canal = CanalCheckinFalso()

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    assert canal.llamadas == []
    assert resumen.ya_reservadas == 1
    assert resumen.llamadas == 0


def test_relanzar_a_mitad_de_lote_solo_llama_a_los_pendientes() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato(n) for n in (1, 2, 3)])
    canal = CanalCheckinFalso()
    # La invocación anterior murió tras reservar a la primera persona.
    previa = ReservaCheckin("previa", repo.candidatos_hoy[0], VERSION_GUION_LLAMADA)
    repo.reservar_llamada(previa)

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    assert resumen.llamadas == 2
    assert all(call_id != "previa" for _, call_id in canal.llamadas)
    assert len(canal.llamadas) == 2


def test_no_llama_a_quien_no_le_toca() -> None:
    repo = RepositorioDiarioFalso(
        candidatos_hoy=[
            _candidato(1, hora=time(9, 0)),
            _candidato(2, dias=frozenset({2})),
            _candidato(3),
        ]
    )
    canal = CanalCheckinFalso()

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    assert [r.candidato.person_id for r in repo.reservas] == [_persona(3)]
    assert resumen.llamadas == 1


def test_no_llama_ni_reserva_fuera_de_la_lista_blanca() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato(1, "+34699999999")])
    canal = CanalCheckinFalso()

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    assert repo.reservas == []
    assert canal.llamadas == []
    assert resumen.fuera_lista_blanca == 1


def test_lista_blanca_vacia_no_permite_nada() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato()])
    canal = CanalCheckinFalso()

    _servicio(repo, canal, ListaBlanca(frozenset())).lanzar(LUNES_18_00)

    assert canal.llamadas == []


def test_respeta_el_limite_por_invocacion_y_el_resto_queda_pendiente() -> None:
    total = LIMITE_POR_INVOCACION + 3
    repo = RepositorioDiarioFalso(
        candidatos_hoy=[_candidato(n) for n in range(1, total + 1)]
    )
    canal = CanalCheckinFalso()
    servicio = _servicio(repo, canal)

    primera = servicio.lanzar(LUNES_18_00)
    segunda = servicio.lanzar(LUNES_18_10)

    assert primera.llamadas == LIMITE_POR_INVOCACION
    assert primera.pendientes == 3
    assert segunda.llamadas == 3
    assert len(canal.llamadas) == total


def test_se_detiene_si_no_queda_tiempo() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato(n) for n in (1, 2, 3)])
    canal = CanalCheckinFalso()
    respuestas = iter([True, False])

    resumen = _servicio(repo, canal).lanzar(
        LUNES_18_00, queda_tiempo=lambda: next(respuestas)
    )

    assert resumen.llamadas == 1
    assert resumen.pendientes == 2


def test_un_fallo_de_connect_marca_la_fila_y_sigue_con_los_demas() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato(1), _candidato(2)])
    canal = CanalCheckinFalso(error=ErrorConnect("fallo"), fallar_la_primera=True)

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    assert repo.fallos == [(repo.reservas[0].call_id, ErrorConnect.codigo)]
    assert resumen.fallos == 1
    assert resumen.llamadas == 1


def test_un_fallo_que_no_se_puede_registrar_se_cuenta_aparte() -> None:
    repo = RepositorioDiarioFalso(
        candidatos_hoy=[_candidato()], error_al_registrar_fallo=ErrorBaseDatos("x")
    )
    canal = CanalCheckinFalso(error=ErrorConnect("x"))

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    assert resumen.fallos_sin_registro == 1
    assert resumen.fallos == 0


def test_un_fallo_sin_registrar_deja_un_log_fijo_sin_datos_personales(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = RepositorioDiarioFalso(
        candidatos_hoy=[_candidato()], error_al_registrar_fallo=ErrorBaseDatos(TEL)
    )
    canal = CanalCheckinFalso(error=ErrorConnect("x"))

    registro = logging.getLogger("core.lanzador")
    # Powertools puede dejar el logger sin propagar al raíz: se engancha directo.
    registro.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="core.lanzador"):
            _servicio(repo, canal).lanzar(LUNES_18_00)
    finally:
        registro.removeHandler(caplog.handler)

    assert {r.getMessage() for r in caplog.records} == {"checkin_fallo_sin_registrar"}
    texto = caplog.text + repr(caplog.records[0].__dict__)
    assert TEL not in texto
    assert repo.reservas[0].call_id not in texto


def test_error_inesperado_marca_la_fila_y_se_propaga() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato()])
    canal = CanalCheckinFalso(error=RuntimeError("x"))

    with pytest.raises(RuntimeError):
        _servicio(repo, canal).lanzar(LUNES_18_00)

    assert repo.fallos == [(repo.reservas[0].call_id, "error_interno")]


def test_si_no_se_guarda_el_contacto_la_llamada_cuenta_sin_registro() -> None:
    repo = RepositorioDiarioFalso(
        candidatos_hoy=[_candidato()], error_al_registrar_contacto=ErrorBaseDatos("x")
    )
    canal = CanalCheckinFalso()

    resumen = _servicio(repo, canal).lanzar(LUNES_18_00)

    assert len(canal.llamadas) == 1
    assert resumen.llamadas_sin_registro == 1
    assert resumen.llamadas == 0


def test_si_aurora_falla_al_leer_o_reservar_se_propaga_sin_llamar() -> None:
    canal = CanalCheckinFalso()
    leer = RepositorioDiarioFalso(error_al_leer=ErrorBaseDatos("x"))
    reservar = RepositorioDiarioFalso(
        candidatos_hoy=[_candidato()], error_al_reservar=ErrorBaseDatos("x")
    )

    with pytest.raises(ErrorBaseDatos):
        _servicio(leer, canal).lanzar(LUNES_18_00)
    with pytest.raises(ErrorBaseDatos):
        _servicio(reservar, canal).lanzar(LUNES_18_00)

    assert canal.llamadas == []


def test_el_resumen_y_el_candidato_no_llevan_datos_personales() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato()])

    resumen = _servicio(repo, CanalCheckinFalso()).lanzar(LUNES_18_00)

    assert TEL not in repr(resumen)
    assert TEL not in repr(_candidato())
    assert set(resumen.como_dict()) == {
        "llamadas",
        "llamadas_sin_registro",
        "fallos",
        "fallos_sin_registro",
        "ya_reservadas",
        "fuera_lista_blanca",
        "pendientes",
    }


def test_el_servicio_usa_uuid_por_defecto() -> None:
    repo = RepositorioDiarioFalso(candidatos_hoy=[_candidato()])
    servicio = ServicioCheckin(repo, CanalCheckinFalso(), ListaBlanca(frozenset({TEL})))

    servicio.lanzar(LUNES_18_00)

    assert len(repo.reservas[0].call_id) == 36
