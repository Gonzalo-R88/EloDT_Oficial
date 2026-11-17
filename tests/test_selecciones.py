"""Tests de la capa de fecha FIFA (`selecciones.py`), con SQLite en memoria."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Club, Coach, Competition
from selecciones import (
    MIN_PJ_DEBUTANTE,
    MovimientosSelecciones,
    dias_con_partidos,
    es_juvenil,
    movers_selecciones,
    partidos_en_ventana,
    ventana_cerrada,
    ventana_fifa,
)
from services import process_match_elo

HOY = date(2026, 11, 19)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    competencias = {
        "unla": Competition(codigo="UNLA", nombre="Nations League A", pais="UEFA",
                            tipo="selecciones", nivel="A", coeficiente=Decimal("1.0")),
        "fs": Competition(codigo="FS", nombre="Amistosos", pais="Mundo",
                          tipo="selecciones", nivel="C", coeficiente=Decimal("0.60")),
        "liga": Competition(codigo="AR1N", nombre="Liga AR", pais="Argentina",
                            tipo="liga", nivel="A", coeficiente=Decimal("1.0")),
    }
    session.add_all(competencias.values())
    session.commit()

    def seleccion(tm_id, nombre):
        return Club(transfermarkt_id=tm_id, nombre=nombre, pais="desconocido",
                    tipo="seleccion")

    equipos = {
        "argentina": seleccion(1, "Argentina"),
        "uruguay": seleccion(2, "Uruguay"),
        "brasil": seleccion(3, "Brazil"),
        "japon": seleccion(4, "Japan"),
        "frances_u21": seleccion(5, "France U21"),
        "alemania_u21": seleccion(6, "Germany U21"),
    }
    # Pool para los partidos masivos: la base no permite el mismo par DT-día dentro de
    # una competencia, así que cada partido extra usa una pareja distinta.
    pool = [seleccion(100 + i, f"Pais {i}") for i in range(20)]
    session.add_all([*equipos.values(), *pool])
    session.commit()

    def dt(tm_id, nombre):
        partes = nombre.split()
        coach = Coach(transfermarkt_id=tm_id, nombre=partes[0],
                      apellido=" ".join(partes[1:]) or "-")
        session.add(coach)
        session.commit()
        return coach

    dts = {
        "scaloni": dt(10, "Lionel Scaloni"),
        "bielsa": dt(11, "Marcelo Bielsa"),
        "ancelotti": dt(12, "Carlo Ancelotti"),
        "moriiyasu": dt(13, "Hajime Moriyasu"),
        "debutante": dt(14, "Juan Debutante"),
    }
    pool_dts = [dt(200 + i, f"Tecnico {i}") for i in range(20)]

    partido = {"id": 5000}

    def jugar(dt_local, club_local, dt_visita, club_visita, fecha, gl, gv, comp, k=20):
        partido["id"] += 1
        process_match_elo(
            dt_local_id=dt_local.dt_id, dt_visita_id=dt_visita.dt_id,
            goles_local=gl, goles_visita=gv, competencia_id=comp.competencia_id,
            club_local_id=club_local.club_id, club_visita_id=club_visita.club_id,
            fecha=fecha, transfermarkt_match_id=partido["id"], factor_k=k,
            session=session,
        )

    def jugar_varios(fecha, cantidad, comp):
        """`cantidad` partidos de selecciones en un día, con parejas todas distintas."""
        for indice in range(cantidad):
            jugar(pool_dts[2 * indice], pool[2 * indice],
                  pool_dts[2 * indice + 1], pool[2 * indice + 1],
                  fecha, 2, 1, comp)

    yield session, {
        "competencias": competencias,
        "equipos": equipos,
        "dts": dts,
        "pool_dts": pool_dts,
        "jugar": jugar,
        "jugar_varios": jugar_varios,
    }
    session.close()


def test_es_juvenil_reconoce_las_categorias():
    assert es_juvenil("France U21")
    assert es_juvenil("Germany U18")
    assert es_juvenil("Türkiye U23")
    assert es_juvenil("Uzbekistan U17")
    # Países que contienen una "U" pero no son juveniles.
    assert not es_juvenil("Uzbekistan")
    assert not es_juvenil("Uruguay")
    assert not es_juvenil("United Arab Emirates")
    assert not es_juvenil(None)


def test_dias_con_partidos_ignora_las_categorias_juveniles(db):
    session, datos = db
    eq, dts, jugar = datos["equipos"], datos["dts"], datos["jugar"]
    jugar(dts["scaloni"], eq["argentina"], dts["bielsa"], eq["uruguay"],
          date(2026, 11, 14), 1, 0, datos["competencias"]["unla"])
    jugar(dts["debutante"], eq["frances_u21"], dts["moriiyasu"], eq["alemania_u21"],
          date(2026, 11, 14), 2, 2, datos["competencias"]["fs"])

    conteo = dias_con_partidos(session, date(2026, 11, 1), HOY)

    assert conteo == {date(2026, 11, 14): 1}


def test_ventana_fifa_une_los_dias_de_la_misma_fecha(db):
    session, datos = db
    datos["jugar_varios"](date(2026, 11, 12), 6, datos["competencias"]["unla"])
    datos["jugar_varios"](date(2026, 11, 13), 6, datos["competencias"]["unla"])
    datos["jugar_varios"](date(2026, 11, 2), 6, datos["competencias"]["unla"])

    ventana = ventana_fifa(session, hoy=HOY)

    assert ventana is not None
    assert ventana.desde == date(2026, 11, 12)
    assert ventana.hasta == date(2026, 11, 13)
    assert ventana.partidos == 12


def test_ventana_fifa_ignora_los_dias_flojos(db):
    """Un día con dos partidos no define una fecha FIFA."""
    session, datos = db
    datos["jugar_varios"](date(2026, 11, 12), 6, datos["competencias"]["unla"])
    datos["jugar_varios"](date(2026, 11, 14), 2, datos["competencias"]["unla"])

    ventana = ventana_fifa(session, hoy=HOY)

    assert ventana.desde == date(2026, 11, 12)
    assert ventana.hasta == date(2026, 11, 12)


def test_ventana_fifa_sin_partidos_devuelve_none(db):
    session, _ = db
    assert ventana_fifa(session, hoy=HOY) is None


def test_ventana_cerrada_solo_despues_del_ultimo_dia(db):
    session, datos = db
    datos["jugar_varios"](date(2026, 11, 16), 6, datos["competencias"]["unla"])
    datos["jugar_varios"](date(2026, 11, 17), 6, datos["competencias"]["unla"])

    ventana = ventana_fifa(session, hoy=date(2026, 11, 17))

    assert ventana.hasta == date(2026, 11, 17)
    assert not ventana_cerrada(ventana, date(2026, 11, 16))
    assert not ventana_cerrada(ventana, date(2026, 11, 17))
    assert ventana_cerrada(ventana, date(2026, 11, 18))
    assert ventana_cerrada(ventana, date(2026, 11, 19))


def test_movers_selecciones_ordena_y_etiqueta_al_debutante(db):
    session, datos = db
    eq, dts, jugar = datos["equipos"], datos["dts"], datos["jugar"]
    comp = datos["competencias"]["unla"]

    # Scaloni y Bielsa acumulan historial; después Bielsa le gana a Scaloni.
    for paso in range(6):
        jugar(dts["scaloni"], eq["argentina"], dts["bielsa"], eq["uruguay"],
              date(2026, 10, 1) + timedelta(days=paso), 1, 0, comp)
    jugar(dts["scaloni"], eq["argentina"], dts["bielsa"], eq["uruguay"],
          date(2026, 11, 14), 0, 2, comp)
    # El debutante gana en su primer partido de toda la base.
    jugar(dts["debutante"], eq["brasil"], dts["ancelotti"], eq["japon"],
          date(2026, 11, 14), 3, 0, comp)

    mov = movers_selecciones(session, date(2026, 11, 10), date(2026, 11, 17), n=5)

    assert isinstance(mov, MovimientosSelecciones)
    assert mov.total_partidos == 2
    etiquetas = {entrada.dt_id: entrada.etiqueta for entrada in mov.subidas + mov.bajadas}
    assert etiquetas[dts["bielsa"].dt_id] is None
    assert etiquetas[dts["scaloni"].dt_id] is None
    assert etiquetas[dts["debutante"].dt_id] == "debutante"
    assert etiquetas[dts["ancelotti"].dt_id] == "debutante"
    # Bielsa ganó 2-0: tiene que estar entre las subidas.
    assert dts["bielsa"].dt_id in [entrada.dt_id for entrada in mov.subidas]


def test_movers_selecciones_trae_el_nombre_de_la_seleccion(db):
    session, datos = db
    eq, dts, jugar = datos["equipos"], datos["dts"], datos["jugar"]
    jugar(dts["scaloni"], eq["argentina"], dts["bielsa"], eq["uruguay"],
          date(2026, 11, 14), 3, 0, datos["competencias"]["unla"])

    mov = movers_selecciones(session, date(2026, 11, 10), date(2026, 11, 17))
    entrada = mov.subidas[0]

    assert entrada.club == "Argentina"
    assert entrada.dt == "Lionel Scaloni"


def test_movers_selecciones_solo_mira_partidos_de_selecciones(db):
    session, datos = db
    eq, dts, jugar = datos["equipos"], datos["dts"], datos["jugar"]
    # Un partido de clubes en la ventana no puede entrar al ranking de seleccionadores.
    jugar(dts["scaloni"], eq["argentina"], dts["bielsa"], eq["uruguay"],
          date(2026, 11, 14), 3, 0, datos["competencias"]["liga"])

    mov = movers_selecciones(session, date(2026, 11, 10), date(2026, 11, 17))

    assert mov.subidas == []
    assert mov.bajadas == []
    assert mov.total_partidos == 0


def test_partidos_en_ventana_cuenta_solo_mayores(db):
    session, datos = db
    eq, dts, jugar = datos["equipos"], datos["dts"], datos["jugar"]
    jugar(dts["scaloni"], eq["argentina"], dts["bielsa"], eq["uruguay"],
          date(2026, 11, 14), 1, 0, datos["competencias"]["unla"])

    assert partidos_en_ventana(session, date(2026, 11, 10), date(2026, 11, 17)) == 1
    assert partidos_en_ventana(session, date(2026, 11, 15), date(2026, 11, 17)) == 0


def test_el_minimo_de_debutante_es_bajo_a_proposito():
    """El primer partido mueve el ELO igual que cualquier otro: no se filtra, se etiqueta."""
    assert MIN_PJ_DEBUTANTE == 5
