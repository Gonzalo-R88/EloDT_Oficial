"""Tests de las reglas de publicación (`publicacion.py`)."""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import Base, Club, Coach, Competition, MatchCoach
from publicacion import (
    ETIQUETA_INTERINO,
    ETIQUETA_PROVISORIO,
    MOTIVO_COBERTURA,
    MOTIVO_INACTIVO,
    MOTIVO_POCOS_PARTIDOS,
    MOTIVO_SIN_CLUB,
    MOTIVO_SIN_LIGA,
    codigos_del_mismo_pais,
    cobertura_liga,
    dt_actual_por_club,
    es_publicable,
    estado_publicacion,
    ligas_domesticas,
    ranking_por_club,
)

HOY = date(2026, 6, 1)


@pytest.fixture
def cobertura(tmp_path) -> Path:
    """Cobertura de prueba: una liga sana, una al 80 %, una sin datos y una cerrada."""
    datos = {
        "AR1N": {a: {"fixtures": 100, "cargados": 100, "ratio": 1.0} for a in (2024, 2025, 2026)},
        "BO1A": {a: {"fixtures": 100, "cargados": 80, "ratio": 0.8} for a in (2024, 2025, 2026)},
        "VZ1C": {a: {"fixtures": 0, "cargados": 0, "ratio": 0.0} for a in (2024, 2025, 2026)},
        "CDLP": {"2023": {"fixtures": 10, "cargados": 10, "ratio": 1.0}},
    }
    ruta = tmp_path / "cobertura.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    def liga(codigo, pais="Argentina"):
        return Competition(codigo=codigo, nombre=codigo, pais=pais, tipo="liga",
                           nivel="A", coeficiente=Decimal("1.0"))

    comp_ok = liga("AR1N")
    comp_baja = liga("BO1A", "Bolivia")
    comp_vacia = liga("VZ1C", "Venezuela")
    comp_int = Competition(codigo="CLI", nombre="Libertadores", pais="Conmebol",
                           tipo="internacional", nivel="S", coeficiente=Decimal("1.3"))
    session.add_all([comp_ok, comp_baja, comp_vacia, comp_int])
    session.commit()

    # Un club por entrenador (como en la realidad: el DT actual es el del último
    # partido de SU club).
    club_30 = Club(transfermarkt_id=1, nombre="Club Treinta", pais="Argentina")
    club_20 = Club(transfermarkt_id=2, nombre="Club Veinte", pais="Argentina")
    club_14 = Club(transfermarkt_id=3, nombre="Club Catorce", pais="Argentina")
    club_3 = Club(transfermarkt_id=5, nombre="Club Tres", pais="Argentina")
    club_baja = Club(transfermarkt_id=6, nombre="Club BO", pais="Bolivia")
    club_vacio = Club(transfermarkt_id=7, nombre="Club VZ", pais="Venezuela")
    club_int = Club(transfermarkt_id=8, nombre="Club Inter", pais="desconocido")
    club_rotacion = Club(transfermarkt_id=10, nombre="Club Rotación", pais="Argentina")
    club_inactivo = Club(transfermarkt_id=11, nombre="Club Inactivo", pais="Argentina")
    filler = Club(transfermarkt_id=9, nombre="Rival", pais="Argentina")
    session.add_all([club_30, club_20, club_14, club_3, club_baja, club_vacio,
                     club_int, club_rotacion, club_inactivo, filler])
    session.commit()

    def entrenador(tm_id, apellido):
        return Coach(transfermarkt_id=tm_id, nombre="DT", apellido=apellido)

    dt30 = entrenador(30, "Treinta")
    dt20 = entrenador(20, "Veinte")
    dt14 = entrenador(14, "Catorce")
    dt3 = entrenador(3, "Tres")
    dt_baja = entrenador(40, "Bolivia")
    dt_vacio = entrenador(41, "Venezuela")
    dt_int = entrenador(42, "Internacional")
    dt_inactivo = entrenador(43, "Inactivo")
    dt_despedido = entrenador(44, "Despedido")
    dt_nuevo = entrenador(45, "Nuevo")
    relleno = entrenador(99, "Relleno")
    session.add_all([dt30, dt20, dt14, dt3, dt_baja, dt_vacio, dt_int, dt_inactivo,
                     dt_despedido, dt_nuevo, relleno])
    session.commit()

    siguiente = {"id": 1}

    def serie(dt, club, comp, cantidad, ultima_fecha):
        """Crea `cantidad` partidos de `dt` como local, con uno cada 7 días."""
        for paso in range(cantidad):
            fecha = ultima_fecha - timedelta(days=7 * (cantidad - 1 - paso))
            session.add(
                MatchCoach(
                    transfermarkt_match_id=siguiente["id"],
                    fecha=fecha,
                    competencia_id=comp.competencia_id,
                    dt_local_id=dt.dt_id,
                    dt_visita_id=relleno.dt_id,
                    club_local_id=club.club_id,
                    club_visita_id=filler.club_id,
                    elo_local_previo=1000, elo_local_nuevo=1000,
                    elo_visita_previo=1000, elo_visita_nuevo=1000,
                    goles_local=1, goles_visita=0, factor_k=20,
                )
            )
            siguiente["id"] += 1

    serie(dt30, club_30, comp_ok, 30, HOY - timedelta(days=5))
    serie(dt20, club_20, comp_ok, 20, HOY - timedelta(days=10))
    serie(dt14, club_14, comp_ok, 14, HOY - timedelta(days=12))
    serie(dt3, club_3, comp_ok, 3, HOY - timedelta(days=15))
    serie(dt_baja, club_baja, comp_baja, 30, HOY - timedelta(days=20))
    serie(dt_vacio, club_vacio, comp_vacia, 30, HOY - timedelta(days=25))
    serie(dt_int, club_int, comp_int, 30, HOY - timedelta(days=30))
    serie(dt_inactivo, club_inactivo, comp_ok, 30, HOY - timedelta(days=settings.activo_dias + 40))
    # Rotación en un mismo club: "despedido" dirigió hasta hace 40 días y luego
    # asumió "nuevo" (último partido hace 5 días).
    serie(dt_despedido, club_rotacion, comp_ok, 20, HOY - timedelta(days=40))
    serie(dt_nuevo, club_rotacion, comp_ok, 6, HOY - timedelta(days=5))
    session.commit()

    ids = {
        "dt30": dt30.dt_id, "dt20": dt20.dt_id, "dt14": dt14.dt_id, "dt3": dt3.dt_id,
        "dt_baja": dt_baja.dt_id, "dt_vacio": dt_vacio.dt_id, "dt_int": dt_int.dt_id,
        "dt_inactivo": dt_inactivo.dt_id, "dt_despedido": dt_despedido.dt_id,
        "dt_nuevo": dt_nuevo.dt_id,
    }
    yield session, ids
    session.close()


# ---------------------------------------------------------------------------
# Cobertura
# ---------------------------------------------------------------------------
def test_cobertura_liga_promedia_la_ventana(cobertura):
    assert cobertura_liga("AR1N", HOY, ruta=cobertura) == 1.0
    assert cobertura_liga("BO1A", HOY, ruta=cobertura) == 0.8
    assert cobertura_liga("VZ1C", HOY, ruta=cobertura) == 0.0


def test_cobertura_liga_suma_las_ligas_del_mismo_pais(tmp_path):
    """Apertura y Clausura son competencias separadas: se miden juntas por país."""
    datos = {
        # Bolivia: Apertura sólo con 2025-2026 y Clausura sólo con 2024.
        "BO1A": {2025: {"fixtures": 240, "cargados": 240, "ratio": 1.0},
                 2026: {"fixtures": 160, "cargados": 160, "ratio": 1.0}},
        "BO1C": {2024: {"fixtures": 240, "cargados": 230, "ratio": 0.9583}},
    }
    ruta = tmp_path / "cobertura.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")

    agrupada = cobertura_liga("BO1A", HOY, ruta=ruta)
    sola = cobertura_liga("BO1A", HOY, ruta=ruta, agrupar_por_pais=False)

    assert agrupada > 0.9  # 1.0 con 230/240 del Clausura
    assert sola == 1.0
    # La cobertura agrupada se pondera por partidos: (240+160+230)/(240+160+240).
    assert agrupada == round(630 / 640, 4)


def test_codigos_del_mismo_pais_incluye_el_codigo_pedido():
    codigos = codigos_del_mismo_pais("BO1A")
    assert "BO1A" in codigos and "BO1C" in codigos


def test_cobertura_liga_sin_datos_en_la_ventana_devuelve_none(cobertura):
    # CDLP sólo tiene 2023 y la ventana es 2024-2026 (medida sola: agrupada por país
    # tomaría las ligas argentinas, que sí tienen datos).
    assert cobertura_liga("CDLP", HOY, ruta=cobertura, agrupar_por_pais=False) is None
    assert cobertura_liga("NOEXISTE", HOY, ruta=cobertura) is None


def test_cobertura_liga_respeta_la_cantidad_de_anios(cobertura):
    assert cobertura_liga("AR1N", date(2025, 6, 1), anios=1, ruta=cobertura) == 1.0
    assert cobertura_liga("BO1A", date(2025, 6, 1), anios=1, ruta=cobertura) == 0.8


# ---------------------------------------------------------------------------
# Liga doméstica del club
# ---------------------------------------------------------------------------
def test_ligas_domesticas_elige_la_liga_con_mas_partidos(db):
    session, _ = db
    ligas = ligas_domesticas(session, HOY - timedelta(days=365 * 3))

    # El club internacional no juega ninguna liga doméstica.
    assert "CLI" not in ligas.values()
    assert ligas


# ---------------------------------------------------------------------------
# Estado de publicación
# ---------------------------------------------------------------------------
def test_dt_con_treinta_partidos_es_publicable_sin_etiqueta(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt30"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable
    assert estado.etiqueta is None
    assert estado.motivo is None
    assert estado.liga == "AR1N"
    assert estado.cobertura == 1.0
    assert estado.en_movimientos is True


def test_dt_provisorio_entre_15_y_29_partidos(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt20"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable
    assert estado.etiqueta == ETIQUETA_PROVISORIO


def test_dt_con_catorce_partidos_es_interino_y_no_va_a_rankings(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt14"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable is False
    assert estado.interino is True
    assert estado.etiqueta == ETIQUETA_INTERINO
    assert estado.en_movimientos is True  # sí en "subidas y bajadas"


def test_dt_con_menos_de_cinco_partidos_no_se_muestra(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt3"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable is False
    assert estado.interino is False
    assert estado.motivo == MOTIVO_POCOS_PARTIDOS
    assert estado.en_movimientos is False


def test_dt_inactivo_no_se_publica(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt_inactivo"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable is False
    assert estado.motivo == MOTIVO_INACTIVO
    assert estado.en_movimientos is False


def test_liga_con_cobertura_80_por_ciento_no_se_publica(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt_baja"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable is False
    assert estado.motivo == MOTIVO_COBERTURA
    assert estado.cobertura == 0.8
    assert estado.en_movimientos is False


def test_liga_sin_fixtures_no_publica_a_nadie(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt_vacio"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable is False
    assert estado.motivo == MOTIVO_COBERTURA
    assert estado.cobertura == 0.0


def test_dt_sin_liga_domestica_no_se_publica(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt_int"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.publicable is False
    assert estado.motivo == MOTIVO_SIN_LIGA
    assert estado.liga is None


def test_estado_publicacion_evalua_a_todos(db, cobertura):
    session, ids = db
    estados = estado_publicacion(session, hasta=HOY, ruta_cobertura=cobertura)

    publicables = {dt for dt, e in estados.items() if e.publicable}
    assert ids["dt30"] in publicables
    assert ids["dt20"] in publicables
    assert ids["dt14"] not in publicables
    assert ids["dt_inactivo"] not in publicables


# ---------------------------------------------------------------------------
# Técnico actual del club
# ---------------------------------------------------------------------------
def test_dt_actual_por_club_es_el_del_ultimo_partido(db):
    session, ids = db
    vigentes = dt_actual_por_club(session)

    valores = {info["dt_id"] for info in vigentes.values()}
    assert ids["dt30"] in valores
    # En el club con rotación, el actual es el que dirigió el último partido.
    assert ids["dt_nuevo"] in valores
    assert ids["dt_despedido"] not in valores


def test_dt_que_ya_no_dirige_su_club_no_es_publicable(db, cobertura):
    """El DT saliente sigue en el ELO, pero no en el ranking del club."""
    session, ids = db
    estado = es_publicable(session, ids["dt_despedido"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.es_vigente is False
    assert estado.publicable is False
    assert estado.sin_trabajo is True
    assert estado.motivo == MOTIVO_SIN_CLUB


def test_el_dt_nuevo_del_club_es_el_publicable(db, cobertura):
    session, ids = db
    estado = es_publicable(session, ids["dt_nuevo"], hasta=HOY, ruta_cobertura=cobertura)

    assert estado.es_vigente is True
    # 6 partidos: entra como interino, no como publicable.
    assert estado.publicable is False
    assert estado.interino is True


def test_ranking_por_club_muestra_un_solo_dt_por_club(db, cobertura):
    """En un club con cambio de DT, el ranking lista sólo al actual."""
    session, ids = db
    ranking = ranking_por_club(session, hasta=HOY, ruta_cobertura=cobertura)

    clubs = [entrada.club_id for entrada in ranking]
    assert len(clubs) == len(set(clubs)), "un DT por club"
    dts = {entrada.dt_id for entrada in ranking}
    assert ids["dt_nuevo"] not in dts  # interino, no va al ranking
    assert ids["dt_despedido"] not in dts
    assert ids["dt30"] in dts
    # Ordenado por ELO descendente.
    assert [e.elo for e in ranking] == sorted((e.elo for e in ranking), reverse=True)


def test_estado_publicacion_sin_cobertura_no_publica_nada(db, tmp_path):
    """Sin `cobertura.json` (p. ej. antes de la primera auditoría) no se publica nada."""
    session, _ = db
    estados = estado_publicacion(session, hasta=HOY, ruta_cobertura=tmp_path / "no-existe.json")

    assert all(not estado.publicable for estado in estados.values())
