from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Base, Club, Coach, Competition, MatchCoach
from elo import EloParams
from services import (
    STATUS_DUPLICATE,
    STATUS_PROCESSED,
    process_match_elo,
    recompute_all_elo,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    competition = Competition(
        codigo="AR1N", nombre="Liga Profesional", pais="Argentina",
        tipo="liga", nivel="A", coeficiente=Decimal("1.00"),
    )
    coach_a = Coach(transfermarkt_id=1, nombre="Entrenador", apellido="A")
    coach_b = Coach(transfermarkt_id=2, nombre="Entrenador", apellido="B")
    coach_c = Coach(transfermarkt_id=3, nombre="Entrenador", apellido="C")
    club_a = Club(transfermarkt_id=10, nombre="Club A")
    club_b = Club(transfermarkt_id=20, nombre="Club B")
    club_c = Club(transfermarkt_id=30, nombre="Club C")
    session.add_all([competition, coach_a, coach_b, coach_c, club_a, club_b, club_c])
    session.commit()

    data = {
        "competencia_id": competition.competencia_id,
        "coach_a": coach_a.dt_id,
        "coach_b": coach_b.dt_id,
        "coach_c": coach_c.dt_id,
        "club_a": club_a.club_id,
        "club_b": club_b.club_id,
        "club_c": club_c.club_id,
    }
    yield session, data
    session.close()


def _play(session, data, *, tm_id, local, visita, gl, gv, fecha):
    return process_match_elo(
        dt_local_id=local,
        dt_visita_id=visita,
        goles_local=gl,
        goles_visita=gv,
        competencia_id=data["competencia_id"],
        club_local_id=data["club_a"],
        club_visita_id=data["club_b"],
        fecha=fecha,
        transfermarkt_match_id=tm_id,
        session=session,
    )


def _elo(session, coach_id):
    return float(session.get(Coach, coach_id).elo_actual)


def test_process_match_is_zero_sum(db):
    session, data = db
    status = _play(
        session, data, tm_id=100, local=data["coach_a"], visita=data["coach_b"],
        gl=1, gv=0, fecha="2024-05-11",
    )
    assert status == STATUS_PROCESSED
    elo_a = _elo(session, data["coach_a"])
    elo_b = _elo(session, data["coach_b"])
    assert elo_a > 1000.0
    assert elo_b < 1000.0
    assert round(elo_a + elo_b, 2) == 2000.00


def test_duplicate_match_is_skipped(db):
    session, data = db
    _play(session, data, tm_id=100, local=data["coach_a"], visita=data["coach_b"],
          gl=1, gv=0, fecha="2024-05-11")
    elo_a_before = _elo(session, data["coach_a"])

    status = _play(session, data, tm_id=100, local=data["coach_a"], visita=data["coach_b"],
                   gl=3, gv=0, fecha="2024-05-11")
    assert status == STATUS_DUPLICATE
    assert _elo(session, data["coach_a"]) == elo_a_before


def test_recompute_con_calibracion_conserva_la_masa(db):
    """Con la calibración activa, la suma de ELO sigue siendo 1000 × cantidad de DTs."""
    session, data = db
    _play(session, data, tm_id=100, local=data["coach_a"], visita=data["coach_b"],
          gl=1, gv=0, fecha="2024-05-11")
    _play(session, data, tm_id=101, local=data["coach_b"], visita=data["coach_c"],
          gl=2, gv=2, fecha="2024-05-18")
    _play(session, data, tm_id=102, local=data["coach_c"], visita=data["coach_a"],
          gl=0, gv=3, fecha="2024-05-25")

    recompute_all_elo(session=session, params=EloParams(calibracion_n=30, calibracion_mult=2.0))

    total = sum(_elo(session, cid) for cid in (data["coach_a"], data["coach_b"], data["coach_c"]))
    assert round(total, 2) == 3000.0
    # Y cada partido sigue siendo de suma cero.
    for match in session.execute(select(MatchCoach)).scalars():
        delta = float(match.elo_local_nuevo - match.elo_local_previo) + float(
            match.elo_visita_nuevo - match.elo_visita_previo
        )
        assert abs(delta) < 0.02


def test_la_calibracion_duplica_el_movimiento_del_primer_partido(db):
    """Dos DTs sin historial juegan con K doble: el mismo partido mueve el doble."""
    session, data = db
    _play(session, data, tm_id=200, local=data["coach_a"], visita=data["coach_b"],
          gl=1, gv=0, fecha="2024-05-11")

    recompute_all_elo(session=session)
    sin_calibracion = _elo(session, data["coach_a"])

    recompute_all_elo(session=session, params=EloParams(calibracion_n=30, calibracion_mult=2.0))
    con_calibracion = _elo(session, data["coach_a"])

    assert round(con_calibracion - 1000, 2) == round(2 * (sin_calibracion - 1000), 2)


def test_recompute_is_deterministic(db):
    session, data = db
    _play(session, data, tm_id=100, local=data["coach_a"], visita=data["coach_b"],
          gl=1, gv=0, fecha="2024-05-11")
    _play(session, data, tm_id=101, local=data["coach_b"], visita=data["coach_c"],
          gl=2, gv=2, fecha="2024-05-18")
    _play(session, data, tm_id=102, local=data["coach_c"], visita=data["coach_a"],
          gl=0, gv=3, fecha="2024-05-25")

    recompute_all_elo(session=session)
    first = {cid: _elo(session, cid) for cid in (data["coach_a"], data["coach_b"], data["coach_c"])}
    recompute_all_elo(session=session)
    second = {cid: _elo(session, cid) for cid in (data["coach_a"], data["coach_b"], data["coach_c"])}

    assert first == second
    assert len(session.execute(select(MatchCoach)).scalars().all()) == 3
