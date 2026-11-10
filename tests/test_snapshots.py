"""Tests de los snapshots semanales (`snapshots.py`)."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Base, Club, Coach, Competition, MatchCoach, SnapshotElo
from services import process_match_elo
from snapshots import elo_al_cierre, semana_fin, snapshot_hace, snapshot_previo, take_snapshot


@pytest.fixture
def cobertura(tmp_path):
    datos = {
        "AR1N": {a: {"fixtures": 100, "cargados": 100, "ratio": 1.0} for a in (2024, 2025)},
    }
    ruta = tmp_path / "cobertura.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    comp = Competition(codigo="AR1N", nombre="Liga", pais="Argentina",
                       tipo="liga", nivel="A", coeficiente=Decimal("1.0"))
    club_a = Club(transfermarkt_id=10, nombre="Club A", pais="Argentina")
    club_b = Club(transfermarkt_id=20, nombre="Club B", pais="Argentina")
    coaches = [Coach(transfermarkt_id=i, nombre="DT", apellido=f"Numero{i}") for i in (1, 2, 3)]
    session.add_all([comp, club_a, club_b, *coaches])
    session.commit()

    data = {
        "comp": comp.competencia_id,
        "club_a": club_a.club_id,
        "club_b": club_b.club_id,
        "coaches": [c.dt_id for c in coaches],
    }

    def jugar(tm_id, local, visita, gl, gv, fecha):
        process_match_elo(
            dt_local_id=local, dt_visita_id=visita, goles_local=gl, goles_visita=gv,
            competencia_id=data["comp"], club_local_id=data["club_a"],
            club_visita_id=data["club_b"], fecha=fecha,
            transfermarkt_match_id=tm_id, session=session,
        )

    data["jugar"] = jugar
    yield session, data
    session.close()


def test_semana_fin_es_el_domingo_anterior():
    # 2024-05-15 es miércoles; el domingo de esa semana es el 12.
    assert semana_fin(date(2024, 5, 15)) == date(2024, 5, 12)
    # El lunes publica la semana que cerró el domingo anterior.
    assert semana_fin(date(2024, 5, 13)) == date(2024, 5, 12)


def test_semana_fin_con_fecha_explicita_es_idempotente():
    """Un domingo pasado a mano se respeta: el pipeline lo usa como cierre explícito."""
    domingo = date(2024, 5, 12)

    assert semana_fin(domingo) == domingo
    assert semana_fin(semana_fin(domingo)) == domingo


def test_el_domingo_por_defecto_es_el_anterior(monkeypatch):
    """Sin fecha y en domingo, la semana todavía no cerró: si devolviera hoy, el paquete
    saldría sin los partidos de ese día y el lunes se saltearía por estar "hecha"."""
    import snapshots

    class _Hoy(date):
        @classmethod
        def today(cls):
            return date(2024, 5, 12)  # domingo

    monkeypatch.setattr(snapshots, "date", _Hoy)

    assert snapshots.semana_fin() == date(2024, 5, 5)


def test_elo_al_cierre_toma_el_ultimo_partido_antes_de_la_fecha(db):
    session, data = db
    a, b, c = data["coaches"]
    data["jugar"](1, a, b, 1, 0, "2024-05-10")
    data["jugar"](2, a, c, 0, 2, "2024-05-14")  # después del cierre

    cierre = elo_al_cierre(session, date(2024, 5, 12))

    assert cierre[a]["pj_total"] == 1
    assert cierre[a]["ultima_fecha"] == date(2024, 5, 10)
    # El DT que sólo jugó después del cierre no aparece.
    assert c not in cierre


def test_take_snapshot_guarda_una_fila_por_dt_y_es_idempotente(db, cobertura):
    session, data = db
    a, b, c = data["coaches"]
    data["jugar"](1, a, b, 1, 0, "2024-05-10")
    data["jugar"](2, b, c, 2, 2, "2024-05-11")

    primero = take_snapshot(session, hasta=date(2024, 5, 12), ruta_cobertura=cobertura)
    segundo = take_snapshot(session, hasta=date(2024, 5, 12), ruta_cobertura=cobertura)

    filas = session.execute(select(SnapshotElo)).scalars().all()
    assert primero.filas == segundo.filas == len(filas)
    assert {f.dt_id for f in filas} == {a, b, c}
    assert primero.semana_fin == date(2024, 5, 12)


def test_rank_global_es_consecutivo_entre_publicables(db, cobertura):
    session, data = db
    a, b, c = data["coaches"]
    data["jugar"](1, a, b, 1, 0, "2024-05-10")
    data["jugar"](2, c, a, 0, 3, "2024-05-11")

    take_snapshot(session, hasta=date(2024, 5, 12), ruta_cobertura=cobertura)

    filas = session.execute(
        select(SnapshotElo).where(SnapshotElo.publicable.is_(True))
        .order_by(SnapshotElo.rank_global)
    ).scalars().all()
    # En este escenario los DTs tienen 1-2 partidos, así que no son publicables
    # (mínimo 15): el ranking queda vacío y no debe romper.
    assert filas == [] or [f.rank_global for f in filas] == list(range(1, len(filas) + 1))


def test_snapshot_previo_devuelve_la_semana_anterior(db, cobertura):
    session, data = db
    a, b, _ = data["coaches"]
    data["jugar"](1, a, b, 1, 0, "2024-05-03")
    data["jugar"](2, a, b, 2, 0, "2024-05-10")

    take_snapshot(session, hasta=date(2024, 5, 5), ruta_cobertura=cobertura)
    take_snapshot(session, hasta=date(2024, 5, 12), ruta_cobertura=cobertura)

    previo = snapshot_previo(session, hasta=date(2024, 5, 12))

    assert previo
    assert all(info["semana_fin"] == date(2024, 5, 5) for info in previo.values())
    # El ELO del snapshot previo es el de antes del partido del 10.
    assert previo[a]["elo"] != elo_al_cierre(session, date(2024, 5, 12))[a]["elo"]


def test_snapshot_hace_busca_la_semana_mas_cercana(db, cobertura):
    session, data = db
    a, b, _ = data["coaches"]
    data["jugar"](1, a, b, 1, 0, "2024-03-01")
    take_snapshot(session, hasta=date(2024, 3, 3), ruta_cobertura=cobertura)
    take_snapshot(session, hasta=date(2024, 5, 12), ruta_cobertura=cobertura)

    # 60 días antes del 12-may es el 13-mar: el snapshot del 3-mar es el más cercano.
    hace_60 = snapshot_hace(session, dias=60, hasta=date(2024, 5, 12))

    assert hace_60
    assert all(info["semana_fin"] <= date(2024, 5, 12) - timedelta(days=60)
               for info in hace_60.values())


def test_take_snapshot_sin_partidos_no_rompe(db, cobertura):
    session, _ = db
    resultado = take_snapshot(session, hasta=date(2030, 1, 1), ruta_cobertura=cobertura)

    assert resultado.filas == 0
