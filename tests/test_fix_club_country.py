"""Tests de la corrección de país de clubes (`scripts/fix_club_country.py`)."""

import importlib.util
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Base, Club, Coach, Competition, MatchCoach

RUTA_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fix_club_country.py"


@pytest.fixture(scope="module")
def fix_pais():
    spec = importlib.util.spec_from_file_location("fix_club_country", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    liga_arg = Competition(codigo="AR1N", nombre="Liga", pais="Argentina",
                           tipo="liga", nivel="A", coeficiente=Decimal("1.0"))
    copa_arg = Competition(codigo="ARCA", nombre="Copa Argentina", pais="Argentina",
                           tipo="copa", nivel="B", coeficiente=Decimal("0.8"))
    libertadores = Competition(codigo="CLI", nombre="Libertadores", pais="Conmebol",
                              tipo="internacional", nivel="S", coeficiente=Decimal("1.3"))
    dt_a = Coach(transfermarkt_id=1, nombre="A", apellido="A")
    dt_b = Coach(transfermarkt_id=2, nombre="B", apellido="B")
    session.add_all([liga_arg, copa_arg, libertadores, dt_a, dt_b])
    session.commit()

    data = {"liga": liga_arg, "copa": copa_arg, "internacional": libertadores,
            "dt_a": dt_a, "dt_b": dt_b}
    yield session, data
    session.close()


def _club(session, tm_id, nombre, pais):
    club = Club(transfermarkt_id=tm_id, nombre=nombre, pais=pais)
    session.add(club)
    session.commit()
    return club


def _partido(session, data, competencia, local, visita, match_id, fecha=None):
    # La tabla no permite el mismo par de DTs dos veces en la misma fecha y competencia.
    fecha = fecha or (date(2024, 5, 1) + timedelta(days=match_id))
    session.add(
        MatchCoach(
            transfermarkt_match_id=match_id, fecha=fecha,
            competencia_id=competencia.competencia_id,
            dt_local_id=data["dt_a"].dt_id, dt_visita_id=data["dt_b"].dt_id,
            club_local_id=local.club_id, club_visita_id=visita.club_id,
            elo_local_previo=1000, elo_local_nuevo=1000,
            elo_visita_previo=1000, elo_visita_nuevo=1000,
            goles_local=1, goles_visita=0, factor_k=20,
        )
    )


def test_elegir_pais_prioriza_la_liga_con_mas_partidos(fix_pais):
    assert fix_pais.elegir_pais(Counter({"Argentina": 5, "Brasil": 2}), Counter()) == "Argentina"
    # Sin liga, usa la copa doméstica.
    assert fix_pais.elegir_pais(Counter(), Counter({"Argentina": 1})) == "Argentina"
    # Sin competencias domésticas, queda desconocido.
    assert fix_pais.elegir_pais(Counter(), Counter()) == "desconocido"


def test_elegir_pais_desempata_por_orden_alfabetico(fix_pais):
    assert fix_pais.elegir_pais(Counter({"Perú": 2, "Bolivia": 2}), Counter()) == "Bolivia"


def test_plan_de_cambios_usa_la_liga_domestica(fix_pais, db):
    session, data = db
    conmebol = _club(session, 100, "FBC Melgar", "Conmebol")
    rival = _club(session, 200, "Alianza Lima", "Argentina")

    for i in range(3):
        _partido(session, data, data["liga"], conmebol, rival, i)
    for i in range(1):
        _partido(session, data, data["internacional"], conmebol, rival, 10 + i)
    session.commit()

    cambios = fix_pais.plan_de_cambios(session)

    assert [(c[1], c[2], c[3]) for c in cambios] == [("FBC Melgar", "Conmebol", "Argentina")]
    # Los partidos internacionales no cuentan para decidir el país.
    assert cambios[0][4] == 3


def test_plan_de_cambios_deja_desconocido_si_solo_juega_internacionales(fix_pais, db):
    session, data = db
    solo_int = _club(session, 300, "Club Sin Liga", "Conmebol")
    rival = _club(session, 301, "Otro", "Argentina")
    _partido(session, data, data["internacional"], solo_int, rival, 20)
    session.commit()

    cambios = fix_pais.plan_de_cambios(session)

    assert [(c[1], c[3]) for c in cambios] == [("Club Sin Liga", "desconocido")]


def test_plan_de_cambios_no_toca_los_que_ya_tienen_pais(fix_pais, db):
    session, data = db
    _club(session, 400, "Boca Juniors", "Argentina")
    session.commit()

    assert fix_pais.plan_de_cambios(session) == []


def test_aplicar_es_idempotente(fix_pais, db):
    session, data = db
    conmebol = _club(session, 500, "Talleres", "Conmebol")
    rival = _club(session, 501, "Racing", "Argentina")
    for i in range(2):
        _partido(session, data, data["liga"], conmebol, rival, 30 + i)
    session.commit()

    cambios = fix_pais.plan_de_cambios(session)
    assert fix_pais.aplicar(session, cambios) == 1
    assert session.get(Club, conmebol.club_id).pais == "Argentina"
    # Los dos clubes quedan con Argentina: no hay nada más que corregir.
    assert fix_pais.plan_de_cambios(session) == []
