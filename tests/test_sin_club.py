"""Tests del ranking de técnicos sin club, con SQLite en memoria.

El ranking no se arma por semana: se consulta cuando hace falta. Sólo entran los DTs
que hoy no dirigen, cuyo último club es argentino y que dejaron de dirigir hace menos
de un año. El último club no se muestra en la imagen.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from content import top_sin_club
from models import Base, Club, Coach, Competition
from services import process_match_elo

HOY = date(2026, 11, 19)


@pytest.fixture
def cobertura(tmp_path):
    ruta = tmp_path / "cobertura.json"
    datos = {
        codigo: {anio: {"fixtures": 100, "cargados": 100, "ratio": 1.0}
                 for anio in (2024, 2025, 2026)}
        for codigo in ("ARG1", "ESP1")
    }
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    liga_ar = Competition(codigo="ARG1", nombre="Liga Argentina", pais="Argentina",
                          tipo="liga", nivel="A", coeficiente=Decimal("1"))
    liga_es = Competition(codigo="ESP1", nombre="Liga Española", pais="España",
                          tipo="liga", nivel="A", coeficiente=Decimal("1"))
    session.add_all([liga_ar, liga_es])
    session.commit()

    def club(tm_id, nombre, pais):
        cada = Club(transfermarkt_id=tm_id, nombre=nombre, pais=pais)
        session.add(cada)
        session.commit()
        return cada

    def dt(tm_id, nombre, apellido):
        cada = Coach(transfermarkt_id=tm_id, nombre=nombre, apellido=apellido)
        session.add(cada)
        session.commit()
        return cada

    club_a = club(1, "Club A", "Argentina")
    club_b = club(2, "Club B", "Argentina")
    club_c = club(3, "Club C", "Argentina")
    club_d = club(4, "Club D", "España")
    club_e = club(5, "Club E", "Argentina")
    rival_ar = club(6, "Rival AR", "Argentina")
    rival_es = club(7, "Rival ES", "España")

    libre_arg = dt(10, "Claudio", "Úbeda")
    libre_es = dt(11, "Diego", "Español")
    provisorio = dt(12, "Carlos", "Provisorio")
    inactivo = dt(13, "Viejo", "Inactivo")
    poquitos = dt(14, "Pocos", "Partidos")
    nuevo_a = dt(15, "Nuevo", "A")
    nuevo_b = dt(16, "Nuevo", "B")
    nuevo_c = dt(17, "Nuevo", "C")
    nuevo_d = dt(18, "Nuevo", "D")
    nuevo_e = dt(19, "Nuevo", "E")
    rival_ar_dt = dt(20, "Rival", "AR")
    rival_es_dt = dt(21, "Rival", "ES")

    partido = {"id": 1000}

    def jugar(dt_local, club_local, dt_visita, club_visita, fecha, gl, gv, comp):
        partido["id"] += 1
        process_match_elo(
            dt_local_id=dt_local.dt_id, dt_visita_id=dt_visita.dt_id,
            goles_local=gl, goles_visita=gv, competencia_id=comp.competencia_id,
            club_local_id=club_local.club_id, club_visita_id=club_visita.club_id,
            fecha=fecha, transfermarkt_match_id=partido["id"], session=session,
        )

    def serie(dt_local, club_local, rival, rival_dt, comp, cantidad, ultima, gl, gv):
        for paso in range(cantidad):
            jugar(dt_local, club_local, rival_dt, rival,
                  ultima - timedelta(days=7 * (cantidad - 1 - paso)), gl, gv, comp)

    serie(libre_arg, club_a, rival_ar, rival_ar_dt, liga_ar, 40,
          HOY - timedelta(days=30), 3, 0)
    serie(libre_es, club_d, rival_es, rival_es_dt, liga_es, 40,
          HOY - timedelta(days=40), 2, 0)
    serie(provisorio, club_b, rival_ar, rival_ar_dt, liga_ar, 20,
          HOY - timedelta(days=20), 1, 0)
    serie(inactivo, club_c, rival_ar, rival_ar_dt, liga_ar, 40,
          HOY - timedelta(days=400), 1, 0)
    serie(poquitos, club_e, rival_ar, rival_ar_dt, liga_ar, 10,
          HOY - timedelta(days=15), 1, 0)

    # El reemplazo dirige después del último partido del DT anterior: así deja de ser
    # "el técnico actual" del club y pasa a ser candidato al ranking de libres.
    jugar(nuevo_a, club_a, rival_ar_dt, rival_ar, HOY - timedelta(days=3), 0, 1, liga_ar)
    jugar(nuevo_b, club_b, rival_ar_dt, rival_ar, HOY - timedelta(days=2), 0, 1, liga_ar)
    jugar(nuevo_c, club_c, rival_ar_dt, rival_ar, HOY - timedelta(days=300), 0, 1, liga_ar)
    jugar(nuevo_d, club_d, rival_es_dt, rival_es, HOY - timedelta(days=5), 0, 1, liga_es)
    jugar(nuevo_e, club_e, rival_ar_dt, rival_ar, HOY - timedelta(days=1), 0, 1, liga_ar)
    session.commit()

    yield session, {
        "libre_arg": libre_arg,
        "libre_es": libre_es,
        "provisorio": provisorio,
        "inactivo": inactivo,
        "poquitos": poquitos,
    }
    session.close()


def test_solo_entran_libres_con_ultimo_club_argentino(db, cobertura):
    session, dts = db
    entradas = top_sin_club(session, hasta=HOY, ruta_cobertura=cobertura)
    ids = [entrada.dt_id for entrada in entradas]

    assert dts["libre_arg"].dt_id in ids
    assert dts["provisorio"].dt_id in ids
    # Último club en España: no entra al ranking argentino.
    assert dts["libre_es"].dt_id not in ids
    # Dirigió por última vez hace más de un año.
    assert dts["inactivo"].dt_id not in ids
    # Menos de 15 partidos: no entra a los rankings.
    assert dts["poquitos"].dt_id not in ids


def test_ordena_por_elo_y_etiqueta_al_provisorio(db, cobertura):
    session, dts = db
    entradas = top_sin_club(session, hasta=HOY, ruta_cobertura=cobertura)

    elos = [entrada.elo for entrada in entradas]
    assert elos == sorted(elos, reverse=True)
    assert [entrada.puesto for entrada in entradas] == list(range(1, len(entradas) + 1))

    provisorio = next(e for e in entradas if e.dt_id == dts["provisorio"].dt_id)
    assert provisorio.etiqueta == "provisorio"
    assert provisorio.pj == 20


def test_excluir_saca_al_dt_indicado(db, cobertura):
    session, dts = db
    entradas = top_sin_club(
        session, hasta=HOY, ruta_cobertura=cobertura,
        excluir_dt_ids=[dts["libre_arg"].dt_id],
    )

    assert dts["libre_arg"].dt_id not in [entrada.dt_id for entrada in entradas]


def test_la_ventana_de_dias_deja_afuera_al_que_dirigio_hace_mas(db, cobertura):
    session, dts = db
    entradas = top_sin_club(session, hasta=HOY, dias=25, ruta_cobertura=cobertura)
    ids = [entrada.dt_id for entrada in entradas]

    assert dts["libre_arg"].dt_id not in ids  # hace 30 días
    assert dts["provisorio"].dt_id in ids     # hace 20 días


def test_sin_filtro_de_pais_entra_el_del_exterior(db, cobertura):
    session, dts = db
    entradas = top_sin_club(session, hasta=HOY, pais=None, ruta_cobertura=cobertura)

    assert dts["libre_es"].dt_id in [entrada.dt_id for entrada in entradas]
