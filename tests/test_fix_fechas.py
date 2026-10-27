"""Tests de la corrección de fechas (`scripts/fix_fechas.py`).

El módulo vive en `scripts/` (no es un módulo de nivel superior como `ranking.py`),
así que se carga por ruta.
"""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Base, Club, Coach, Competition, MatchCoach

RUTA_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fix_fechas.py"


@pytest.fixture(scope="module")
def fix_fechas():
    spec = importlib.util.spec_from_file_location("fix_fechas", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    comp = Competition(codigo="AR1N", nombre="Liga", nivel="A",
                       coeficiente=Decimal("1.0"), tipo="liga")
    dt_a = Coach(transfermarkt_id=1, nombre="A", apellido="A")
    dt_b = Coach(transfermarkt_id=2, nombre="B", apellido="B")
    dt_c = Coach(transfermarkt_id=3, nombre="C", apellido="C")
    club_1 = Club(transfermarkt_id=10, nombre="X")
    club_2 = Club(transfermarkt_id=20, nombre="Y")
    session.add_all([comp, dt_a, dt_b, dt_c, club_1, club_2])
    session.commit()

    def partido(match_id, fecha, local, visita):
        session.add(
            MatchCoach(
                transfermarkt_match_id=match_id, fecha=fecha,
                competencia_id=comp.competencia_id,
                dt_local_id=local.dt_id, dt_visita_id=visita.dt_id,
                club_local_id=club_1.club_id, club_visita_id=club_2.club_id,
                elo_local_previo=1000, elo_local_nuevo=1000,
                elo_visita_previo=1000, elo_visita_nuevo=1000,
                goles_local=1, goles_visita=0, factor_k=20,
            )
        )

    partido(1, date(2005, 5, 3), dt_a, dt_b)
    partido(2, date(2005, 5, 3), dt_a, dt_c)
    partido(3, date(2005, 6, 1), dt_b, dt_c)
    session.commit()

    yield session, {"dt_a": dt_a, "dt_b": dt_b, "dt_c": dt_c}
    session.close()


def test_plan_de_cambios_solo_incluye_fechas_distintas(fix_fechas, db):
    session, _ = db
    fix_fechas._CACHE_REPORTES.clear()
    fix_fechas._CACHE_REPORTES.update({1: "2005-05-16", 2: None, 3: "2005-06-01"})

    cambios = fix_fechas.plan_de_cambios(session, [1, 2, 3])

    assert cambios == [(1, "", "2005-05-03", "2005-05-16")]


def test_aplicar_escribe_la_fecha_como_date(fix_fechas, db):
    """Regresión: `UPDATE ... values(fecha="2005-05-16")` falla con la columna Date."""
    session, _ = db
    cambios = [(1, "", "2005-05-03", "2005-05-16"), (3, "", "2005-06-01", "2005-06-05")]

    aplicados, fallidos = fix_fechas.aplicar(session, cambios)

    assert (aplicados, fallidos) == (2, 0)
    fechas = {
        fila.transfermarkt_match_id: fila.fecha
        for fila in session.execute(select(MatchCoach)).scalars()
    }
    assert fechas[1] == date(2005, 5, 16)
    assert fechas[3] == date(2005, 6, 5)


def test_aplicar_es_idempotente(fix_fechas, db):
    session, _ = db
    cambios = [(1, "", "2005-05-03", "2005-05-16")]
    fix_fechas.aplicar(session, cambios)

    fix_fechas._CACHE_REPORTES.clear()
    fix_fechas._CACHE_REPORTES.update({1: "2005-05-16"})
    assert fix_fechas.plan_de_cambios(session, [1]) == []


def test_ids_objetivo_incluye_el_bloque_completo(fix_fechas):
    mapa = {
        1: {"codigo": "AR1N", "temporada": 2005, "fecha": "2005-05-03", "matchday": "4"},
        2: {"codigo": "AR1N", "temporada": 2005, "fecha": "2005-05-03", "matchday": "5"},
        3: {"codigo": "AR1N", "temporada": 2005, "fecha": "2005-06-01", "matchday": "6"},
        4: {"codigo": "GB1", "temporada": 2005, "fecha": "2005-05-03", "matchday": "4"},
    }
    conflictos = [{"match_ids": [1]}]

    assert fix_fechas.ids_objetivo(conflictos, mapa, bloques=False) == [1]
    # El bloque es (competencia, temporada, fecha): incluye el 2, no el 4 (otra liga).
    assert fix_fechas.ids_objetivo(conflictos, mapa, bloques=True) == [1, 2]
