"""Tests de la capa de contenido (`content.py`)."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from content import duelo_de_la_semana, movers, revelacion, top_n, top_por_pais
from models import Base, Club, Coach, Competition, MatchCoach
from services import process_match_elo
from snapshots import take_snapshot

CIERRE = date(2026, 6, 7)  # domingo


@pytest.fixture
def cobertura(tmp_path):
    datos = {
        "AR1N": {a: {"fixtures": 100, "cargados": 100, "ratio": 1.0} for a in (2025, 2026)},
        "ES1": {a: {"fixtures": 100, "cargados": 100, "ratio": 1.0} for a in (2025, 2026)},
    }
    ruta = tmp_path / "cobertura.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    liga_ar = Competition(codigo="AR1N", nombre="Liga AR", pais="Argentina",
                          tipo="liga", nivel="A", coeficiente=Decimal("1.0"))
    liga_es = Competition(codigo="ES1", nombre="Liga ES", pais="España",
                          tipo="liga", nivel="A", coeficiente=Decimal("1.0"))
    session.add_all([liga_ar, liga_es])
    session.commit()

    def club(tm_id, nombre, pais):
        return Club(transfermarkt_id=tm_id, nombre=nombre, pais=pais)

    clubes = {
        "bueno": club(10, "Club Bueno", "Argentina"),
        "medio": club(11, "Club Medio", "Argentina"),
        "flojo": club(12, "Club Flojo", "Argentina"),
        "espanol": club(13, "Club Español", "España"),
        "interino": club(14, "Club Interino", "Argentina"),
    }
    session.add_all(clubes.values())
    session.commit()

    def dt(tm_id, apellido):
        return Coach(transfermarkt_id=tm_id, nombre="DT", apellido=apellido)

    # Cada DT tiene su propio rival (que acumula pocos partidos y no es publicable).
    dts = {clave: dt(i, clave.capitalize()) for i, clave in enumerate(clubes, start=1)}
    rivales = {clave: dt(100 + i, f"Rival{i}") for i, clave in enumerate(clubes, start=1)}
    club_rival = {
        clave: Club(transfermarkt_id=200 + i, nombre=f"Rival de {clave}", pais="Argentina")
        for i, clave in enumerate(clubes, start=1)
    }
    session.add_all([*dts.values(), *rivales.values(), *club_rival.values()])
    session.commit()

    partido = {"id": 1000}

    def jugar(dt_local, club_local, dt_visita, club_visita, fecha, gl, gv, comp):
        partido["id"] += 1
        process_match_elo(
            dt_local_id=dt_local.dt_id, dt_visita_id=dt_visita.dt_id,
            goles_local=gl, goles_visita=gv, competencia_id=comp.competencia_id,
            club_local_id=club_local.club_id, club_visita_id=club_visita.club_id,
            fecha=fecha, transfermarkt_match_id=partido["id"], session=session,
        )

    def serie(clave, cantidad, ultima, gl, gv, comp, dt_local=None):
        """`cantidad` partidos con `clave` como local, uno cada 7 días."""
        for paso in range(cantidad):
            jugar(
                dt_local or dts[clave], clubes[clave], rivales[clave], club_rival[clave],
                ultima - timedelta(days=7 * (cantidad - 1 - paso)), gl, gv, comp,
            )

    # Tres clubes argentinos con historial largo y resultados distintos (ELO distinto).
    serie("bueno", 40, CIERRE - timedelta(days=3), 3, 0, liga_ar)
    serie("medio", 35, CIERRE - timedelta(days=4), 2, 1, liga_ar)
    serie("flojo", 30, CIERRE - timedelta(days=5), 0, 2, liga_ar)
    serie("espanol", 30, CIERRE - timedelta(days=40), 1, 0, liga_es)
    serie("interino", 8, CIERRE - timedelta(days=2), 2, 0, liga_ar)
    session.commit()

    yield session, {"dts": dts, "clubes": clubes, "liga_ar": liga_ar, "liga_es": liga_es}
    session.close()


def test_top_n_devuelve_uno_por_club_y_ordena_por_elo(db, cobertura):
    session, _ = db
    top = top_n(session, semana_fin=CIERRE, n=10, ruta_cobertura=cobertura)

    assert top
    assert len({entrada.club for entrada in top}) == len(top)
    assert [e.puesto for e in top] == list(range(1, len(top) + 1))
    assert [e.elo for e in top] == sorted((e.elo for e in top), reverse=True)


def test_top_por_pais_filtra(db, cobertura):
    session, _ = db
    argentina = top_por_pais(session, "Argentina", semana_fin=CIERRE, ruta_cobertura=cobertura)
    todos = top_n(session, semana_fin=CIERRE, n=20, ruta_cobertura=cobertura)

    assert argentina
    assert all(entrada.pais == "Argentina" for entrada in argentina)
    assert len(argentina) < len(todos)  # el español queda afuera


def test_top_n_excluye_al_interino(db, cobertura):
    session, datos = db
    top = top_n(session, semana_fin=CIERRE, n=20, ruta_cobertura=cobertura)

    assert datos["dts"]["interino"].dt_id not in {entrada.dt_id for entrada in top}


def test_top_n_marca_la_variacion_contra_el_snapshot_anterior(db, cobertura):
    session, datos = db
    take_snapshot(session, hasta=CIERRE - timedelta(days=7), ruta_cobertura=cobertura)

    # En la última semana el "flojo" gana y el "bueno" pierde: se mueven posiciones.
    jugar = None
    for i, (clave, gl, gv) in enumerate([("flojo", 4, 0), ("bueno", 0, 3)]):
        process_match_elo(
            dt_local_id=datos["dts"][clave].dt_id,
            dt_visita_id=datos["dts"]["bueno"].dt_id,
            goles_local=gl, goles_visita=gv,
            competencia_id=datos["liga_ar"].competencia_id,
            club_local_id=datos["clubes"][clave].club_id,
            club_visita_id=datos["clubes"]["bueno"].club_id,
            fecha=CIERRE - timedelta(days=1),
            transfermarkt_match_id=7000 + i, session=session,
        )
    session.commit()
    take_snapshot(session, hasta=CIERRE, ruta_cobertura=cobertura)

    top = top_n(session, semana_fin=CIERRE, n=10, ruta_cobertura=cobertura)

    assert all(entrada.puesto_previo is not None for entrada in top)
    assert any(entrada.variacion not in (None, 0) for entrada in top)


def test_movers_incluye_interinos_y_excluye_lo_que_no_jugo(db, cobertura):
    session, datos = db
    mov = movers(session, semana_fin=CIERRE, dias=7, ruta_cobertura=cobertura)

    aparecen = {e.dt_id for e in mov.subidas + mov.bajadas}
    assert datos["dts"]["interino"].dt_id in aparecen
    # El español no jugó en la ventana.
    assert datos["dts"]["espanol"].dt_id not in aparecen


def test_movers_marca_la_etiqueta_del_interino(db, cobertura):
    session, datos = db
    mov = movers(session, semana_fin=CIERRE, dias=7, ruta_cobertura=cobertura)

    interino = next(
        (e for e in mov.subidas + mov.bajadas
         if e.dt_id == datos["dts"]["interino"].dt_id),
        None,
    )
    assert interino is not None
    assert interino.etiqueta == "interino"


def test_duelo_de_la_semana_elige_el_partido_con_mas_elo(db, cobertura):
    session, datos = db
    process_match_elo(
        dt_local_id=datos["dts"]["bueno"].dt_id,
        dt_visita_id=datos["dts"]["medio"].dt_id,
        goles_local=1, goles_visita=1,
        competencia_id=datos["liga_ar"].competencia_id,
        club_local_id=datos["clubes"]["bueno"].club_id,
        club_visita_id=datos["clubes"]["medio"].club_id,
        fecha=CIERRE - timedelta(days=1),
        transfermarkt_match_id=8000, session=session,
    )
    session.commit()

    duelo = duelo_de_la_semana(session, semana_fin=CIERRE, ruta_cobertura=cobertura)

    assert duelo is not None
    assert {duelo.dt_a_id, duelo.dt_b_id} == {
        datos["dts"]["bueno"].dt_id, datos["dts"]["medio"].dt_id
    }
    assert duelo.resultado == "1-1"


def test_revelacion_elige_a_un_dt_publicable_reciente(db, cobertura):
    session, _ = db
    take_snapshot(session, hasta=CIERRE, ruta_cobertura=cobertura)

    elegido = revelacion(session, semana_fin=CIERRE, ruta_cobertura=cobertura)

    assert elegido is not None
    assert elegido.pj >= 15
    assert elegido.desde_primera_fecha >= CIERRE - timedelta(days=365 * 2)
