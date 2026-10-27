from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from duel import compute_duel, resolve_coach
from models import Base, Club, Coach, Competition
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
    coach_a = Coach(transfermarkt_id=1, nombre="Marcelo", apellido="Gallardo")
    coach_b = Coach(transfermarkt_id=2, nombre="Gustavo", apellido="Costas")
    coach_c = Coach(transfermarkt_id=3, nombre="Sin", apellido="Partidos")
    club_a = Club(transfermarkt_id=10, nombre="River Plate")
    club_b = Club(transfermarkt_id=20, nombre="Racing Club")
    session.add_all([liga, coach_a, coach_b, coach_c, club_a, club_b])
    session.commit()

    data = {
        "liga": liga.competencia_id,
        "a": coach_a.dt_id,
        "b": coach_b.dt_id,
        "c": coach_c.dt_id,
        "club_a": club_a.club_id,
        "club_b": club_b.club_id,
    }
    yield session, data
    session.close()


def _play(session, data, *, tm_id, local, visita, gl, gv, fecha):
    return process_match_elo(
        dt_local_id=local,
        dt_visita_id=visita,
        goles_local=gl,
        goles_visita=gv,
        competencia_id=data["liga"],
        club_local_id=data["club_a"],
        club_visita_id=data["club_b"],
        fecha=fecha,
        transfermarkt_match_id=tm_id,
        session=session,
    )


def _three_matches(session, data):
    _play(session, data, tm_id=1, local=data["a"], visita=data["b"],
          gl=2, gv=0, fecha="2024-05-11")
    _play(session, data, tm_id=2, local=data["b"], visita=data["a"],
          gl=1, gv=1, fecha="2024-05-18")
    _play(session, data, tm_id=3, local=data["a"], visita=data["b"],
          gl=0, gv=3, fecha="2024-05-25")


def test_compute_duel_aggregates_each_side(db):
    session, data = db
    _three_matches(session, data)

    duel = compute_duel(session, data["a"], data["b"])

    assert duel.a.partidos == 3
    assert (duel.a.victorias, duel.a.empates, duel.a.derrotas) == (1, 1, 1)
    assert (duel.a.goles_favor, duel.a.goles_contra) == (3, 4)
    assert duel.a.diferencia == -1
    assert duel.a.forma == ("D", "E", "V")

    assert duel.b.partidos == 3
    assert (duel.b.victorias, duel.b.empates, duel.b.derrotas) == (1, 1, 1)
    assert (duel.b.goles_favor, duel.b.goles_contra) == (4, 3)
    assert duel.b.forma == ("V", "E", "D")
    assert duel.a.club == "River Plate"


def test_head_to_head_record(db):
    session, data = db
    _three_matches(session, data)

    duel = compute_duel(session, data["a"], data["b"])
    assert duel.enfrentamientos == 3
    assert (duel.victorias_a, duel.empates, duel.victorias_b) == (1, 1, 1)


def test_coach_without_matches(db):
    session, data = db
    _three_matches(session, data)

    duel = compute_duel(session, data["a"], data["c"])
    assert duel.b.partidos == 0
    assert duel.b.forma == ()
    assert duel.b.club is None
    assert duel.enfrentamientos == 0


def test_resolve_coach_by_id_and_name(db):
    session, data = db

    by_id = resolve_coach(session, data["a"])
    assert by_id.dt_id == data["a"]

    by_name = resolve_coach(session, "Costas")
    assert by_name.dt_id == data["b"]

    with pytest.raises(ValueError):
        resolve_coach(session, "Inexistente")


def test_self_duel_is_rejected(db):
    session, data = db
    with pytest.raises(ValueError):
        compute_duel(session, data["a"], data["a"])