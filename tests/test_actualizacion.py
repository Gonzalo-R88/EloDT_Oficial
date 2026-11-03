"""Tests de correcciones y validación del pipeline (`actualizacion.py`)."""

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from actualizacion import (
    Correccion,
    aplicar_correcciones,
    detectar_correcciones,
    recomputar_con_tiempo,
    validar_invariantes,
)
from models import Base, Club, Coach, Competition, MatchCoach
from services import process_match_elo
from scraping.storage import RawStore

HOY = date(2026, 11, 2)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    comp = Competition(codigo="AR1N", nombre="Liga", pais="Argentina",
                       tipo="liga", nivel="A", coeficiente=Decimal("1.0"))
    club_a = Club(transfermarkt_id=10, nombre="Club A", pais="Argentina")
    club_b = Club(transfermarkt_id=20, nombre="Club B", pais="Argentina")
    dt_a = Coach(transfermarkt_id=1, nombre="DT", apellido="A")
    dt_b = Coach(transfermarkt_id=2, nombre="DT", apellido="B")
    session.add_all([comp, club_a, club_b, dt_a, dt_b])
    session.commit()

    def jugar(tm_id, gl, gv, fecha="2026-10-25"):
        process_match_elo(
            dt_local_id=dt_a.dt_id, dt_visita_id=dt_b.dt_id,
            goles_local=gl, goles_visita=gv,
            competencia_id=comp.competencia_id,
            club_local_id=club_a.club_id, club_visita_id=club_b.club_id,
            fecha=fecha, transfermarkt_match_id=tm_id, session=session,
        )

    yield session, {"jugar": jugar, "club_a": club_a, "club_b": club_b}
    session.close()


def _cache(tmp_path, partidos):
    """Arma un caché mínimo: fixture + reporte por partido.

    `partidos`: [(match_id, gl_db, gv_db, gl_reporte, gv_reporte)]
    """
    store = RawStore(tmp_path)
    fixtures = []
    for tm_id, gl, gv, _gl_rep, _gv_rep in partidos:
        fixtures.append({
            "match_id": tm_id, "competition_code": "AR1N", "season": 2026,
            "date": "2026-10-25", "matchday": "1.Matchday",
            "home_club_tm_id": 10, "home_club_name": "Club A",
            "away_club_tm_id": 20, "away_club_name": "Club B",
            "home_goals": gl, "away_goals": gv,
        })
    store.write_fixtures("AR1N", 2026, fixtures)
    for tm_id, _gl, _gv, gl_rep, gv_rep in partidos:
        store.write_match("AR1N", 2026, tm_id, {
            "match_id": tm_id, "final_home_goals": gl_rep, "final_away_goals": gv_rep,
            "home_coach_tm_id": 1, "home_coach_name": "DT A",
            "away_coach_tm_id": 2, "away_coach_name": "DT B",
            "fecha": "2026-10-25",
        })
    return store


def test_detecta_una_correccion_del_reporte(db, tmp_path):
    session, datos = db
    datos["jugar"](500, 1, 0)
    _cache(tmp_path, [(500, 1, 0, 2, 0)])  # el reporte dice 2-0

    correcciones = detectar_correcciones(session, tmp_path, desde=date(2026, 10, 1))

    assert len(correcciones) == 1
    assert correcciones[0].tm_match_id == 500
    assert correcciones[0].goles_db == (1, 0)
    assert correcciones[0].goles_cache == (2, 0)
    assert correcciones[0].origen == "reporte"


def test_no_hay_correccion_si_coincide(db, tmp_path):
    session, datos = db
    datos["jugar"](501, 2, 1)
    _cache(tmp_path, [(501, 2, 1, 2, 1)])

    assert detectar_correcciones(session, tmp_path, desde=date(2026, 10, 1)) == []


def test_ignora_partidos_anteriores_a_la_ventana(db, tmp_path):
    session, datos = db
    datos["jugar"](502, 1, 0)
    _cache(tmp_path, [(502, 1, 0, 2, 0)])

    assert detectar_correcciones(session, tmp_path, desde=date(2026, 10, 26)) == []


def test_aplicar_corrige_los_goles(db, tmp_path):
    session, datos = db
    datos["jugar"](503, 1, 0)
    _cache(tmp_path, [(503, 1, 0, 3, 2)])
    correcciones = detectar_correcciones(session, tmp_path, desde=date(2026, 10, 1))

    aplicadas = aplicar_correcciones(session, correcciones)

    assert aplicadas == 1
    fila = session.execute(
        select(MatchCoach).where(MatchCoach.transfermarkt_match_id == 503)
    ).scalar_one()
    assert (fila.goles_local, fila.goles_visita) == (3, 2)


def test_validar_invariantes_ok(db):
    session, datos = db
    datos["jugar"](504, 1, 0)
    recomputar_con_tiempo(session)

    ok, detalle = validar_invariantes(session)

    assert ok, detalle
    assert detalle["duplicados"] == 0
    assert detalle["masa"] == detalle["masa_esperada"]


def test_validar_invariantes_detecta_desbalance(db):
    session, datos = db
    datos["jugar"](505, 1, 0)
    fila = session.execute(
        select(MatchCoach).where(MatchCoach.transfermarkt_match_id == 505)
    ).scalar_one()
    fila.elo_local_nuevo = fila.elo_local_previo + 50  # rompe la suma cero
    session.commit()

    ok, detalle = validar_invariantes(session)

    assert not ok
    assert detalle["desbalanceados"] == 1


def test_recomputar_es_determinista_y_devuelve_segundos(db):
    session, datos = db
    datos["jugar"](506, 3, 1, fecha="2026-10-20")
    datos["jugar"](507, 0, 2, fecha="2026-10-25")

    primero = recomputar_con_tiempo(session)
    elo_1 = [float(c.elo_actual) for c in session.execute(select(Coach)).scalars()]
    segundo = recomputar_con_tiempo(session)
    elo_2 = [float(c.elo_actual) for c in session.execute(select(Coach)).scalars()]

    assert primero >= 0 and segundo >= 0
    assert elo_1 == elo_2
