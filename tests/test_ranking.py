from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Club, Coach, Competition
from ranking import (
    compute_power_ranking,
    resolve_competition_id,
    resolve_window,
)
from services import process_match_elo


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    liga = Competition(
        codigo="AR1N", nombre="Liga Profesional", pais="Argentina",
        tipo="liga", nivel="A", coeficiente=Decimal("1.00"),
    )
    copa = Competition(
        codigo="ARCA", nombre="Copa Argentina", pais="Argentina",
        tipo="copa", nivel="B", coeficiente=Decimal("0.80"),
    )
    coaches = [
        Coach(transfermarkt_id=1, nombre="Uno", apellido="A"),
        Coach(transfermarkt_id=2, nombre="Dos", apellido="B"),
        Coach(transfermarkt_id=3, nombre="Tres", apellido="C"),
        Coach(transfermarkt_id=4, nombre="Cuatro", apellido="D"),
    ]
    clubs = [
        Club(transfermarkt_id=10, nombre="Club A"),
        Club(transfermarkt_id=20, nombre="Club B"),
        Club(transfermarkt_id=30, nombre="Club C"),
    ]
    session.add_all([liga, copa, *coaches, *clubs])
    session.commit()

    data = {
        "liga": liga.competencia_id,
        "copa": copa.competencia_id,
        "coach_1": coaches[0].dt_id,
        "coach_2": coaches[1].dt_id,
        "coach_3": coaches[2].dt_id,
        "coach_4": coaches[3].dt_id,
        "club_a": clubs[0].club_id,
        "club_b": clubs[1].club_id,
        "club_c": clubs[2].club_id,
    }
    yield session, data
    session.close()


def _play(session, data, *, tm_id, local, visita, gl, gv, fecha, comp_key="liga"):
    return process_match_elo(
        dt_local_id=local,
        dt_visita_id=visita,
        goles_local=gl,
        goles_visita=gv,
        competencia_id=data[comp_key],
        club_local_id=data["club_a"],
        club_visita_id=data["club_b"],
        fecha=fecha,
        transfermarkt_match_id=tm_id,
        session=session,
    )


def test_resolve_window_defaults_to_last_match(db):
    session, data = db
    _play(session, data, tm_id=1, local=data["coach_1"], visita=data["coach_2"],
          gl=1, gv=0, fecha="2024-05-11")
    _play(session, data, tm_id=2, local=data["coach_3"], visita=data["coach_4"],
          gl=2, gv=1, fecha="2024-05-18")

    desde, hasta = resolve_window(session, dias=7)
    assert hasta.isoformat() == "2024-05-18"
    assert desde.isoformat() == "2024-05-12"


def test_power_ranking_orders_movers(db):
    session, data = db
    _play(session, data, tm_id=1, local=data["coach_1"], visita=data["coach_2"],
          gl=4, gv=0, fecha="2024-05-11")
    _play(session, data, tm_id=2, local=data["coach_3"], visita=data["coach_4"],
          gl=0, gv=3, fecha="2024-05-11")

    ranking = compute_power_ranking(session, desde="2024-05-01", hasta="2024-05-31", top=5)

    assert ranking.total_partidos == 2
    assert ranking.subidas[0].dt_id == data["coach_1"]
    assert ranking.bajadas[0].dt_id == data["coach_2"]
    assert all(entry.delta > 0 for entry in ranking.subidas)
    assert all(entry.delta < 0 for entry in ranking.bajadas)
    for entry in ranking.subidas + ranking.bajadas:
        assert round(entry.elo_actual - entry.elo_previo, 2) == entry.delta
        assert entry.club in {"Club A", "Club B"}


def test_multiple_matches_are_aggregated(db):
    session, data = db
    _play(session, data, tm_id=1, local=data["coach_1"], visita=data["coach_2"],
          gl=1, gv=0, fecha="2024-05-11")
    _play(session, data, tm_id=2, local=data["coach_1"], visita=data["coach_3"],
          gl=2, gv=0, fecha="2024-05-18")

    ranking = compute_power_ranking(session, desde="2024-05-01", hasta="2024-05-31", top=5)
    leader = next(e for e in ranking.subidas if e.dt_id == data["coach_1"])
    assert leader.partidos == 2
    assert leader.elo_actual > leader.elo_previo
    assert round(leader.elo_actual - leader.elo_previo, 2) == leader.delta


def test_draw_reflects_home_advantage(db):
    session, data = db
    _play(session, data, tm_id=1, local=data["coach_1"], visita=data["coach_2"],
          gl=0, gv=0, fecha="2024-05-11")

    ranking = compute_power_ranking(session, desde="2024-05-01", hasta="2024-05-31", top=5)
    assert {e.dt_id for e in ranking.bajadas} == {data["coach_1"]}
    assert {e.dt_id for e in ranking.subidas} == {data["coach_2"]}


def test_competition_filter(db):
    session, data = db
    _play(session, data, tm_id=1, local=data["coach_1"], visita=data["coach_2"],
          gl=3, gv=0, fecha="2024-05-11", comp_key="liga")
    _play(session, data, tm_id=2, local=data["coach_3"], visita=data["coach_4"],
          gl=3, gv=0, fecha="2024-05-11", comp_key="copa")

    copa_id = resolve_competition_id(session, "ARCA")
    ranking = compute_power_ranking(
        session, desde="2024-05-01", hasta="2024-05-31", top=5, competencia_id=copa_id
    )

    assert ranking.total_partidos == 1
    assert {e.dt_id for e in ranking.subidas} == {data["coach_3"]}
    assert {e.dt_id for e in ranking.bajadas} == {data["coach_4"]}