import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auditoria import (
    CoberturaCelda,
    FixtureCrudo,
    cobertura_a_json,
    conflictos_dt_dia,
    construir_cobertura,
    estimar_dt_faltante,
    iter_fixtures,
    rangos_anios,
    resumir_competencias,
    ultimos_partidos,
)
from models import Base, Club, Coach, Competition, MatchCoach


def _fixture(codigo, anio, match_id, mes=6, dia=1):
    return FixtureCrudo(
        codigo=codigo,
        temporada=anio,
        match_id=match_id,
        fecha=date(anio, mes, dia),
    )


# ---------------------------------------------------------------------------
# Cobertura
# ---------------------------------------------------------------------------
def test_construir_cobertura_cuenta_fixtures_y_cargados():
    fixtures = [
        _fixture("AR1N", 2024, 1),
        _fixture("AR1N", 2024, 2),
        _fixture("AR1N", 2024, 3),
    ]
    cobertura, sin_fecha = construir_cobertura(
        fixtures, ids_en_db={1, 3}, primera_temporada={"AR1N": 2024}, anio_actual=2024
    )

    assert sin_fecha == {}
    celda = cobertura["AR1N"][2024]
    assert (celda.fixtures, celda.cargados) == (3, 2)
    assert celda.ratio == round(2 / 3, 4)


def test_cobertura_marca_huecos_con_ratio_cero():
    """Los años sin fixtures cacheados deben aparecer con ratio 0, no desaparecer."""
    fixtures = [_fixture("AR1N", 2024, 1)]
    cobertura, _ = construir_cobertura(
        fixtures, ids_en_db={1}, primera_temporada={"AR1N": 2022}, anio_actual=2026
    )

    assert sorted(cobertura["AR1N"]) == [2022, 2023, 2024, 2025, 2026]
    assert cobertura["AR1N"][2023].ratio == 0.0
    assert cobertura["AR1N"][2025].fixtures == 0
    assert cobertura["AR1N"][2024].ratio == 1.0


def test_cobertura_incluye_anos_previos_a_la_primera_temporada_del_catalogo():
    """Si el caché tiene años anteriores a `first_season`, se muestran igual."""
    fixtures = [_fixture("EC1N", 2019, 1)]
    cobertura, _ = construir_cobertura(
        fixtures, ids_en_db={1}, primera_temporada={"EC1N": 2025}, anio_actual=2026
    )

    assert min(cobertura["EC1N"]) == 2019
    assert cobertura["EC1N"][2019].ratio == 1.0


def test_cobertura_ignora_fixtures_sin_fecha_pero_los_informa():
    fixtures = [FixtureCrudo(codigo="AR1N", temporada=2024, match_id=9, fecha=None)]
    cobertura, sin_fecha = construir_cobertura(
        fixtures, ids_en_db=set(), primera_temporada={"AR1N": 2024}, anio_actual=2024
    )

    assert sin_fecha == {"AR1N": 1}
    assert cobertura["AR1N"][2024].fixtures == 0


def test_resumir_competencias_lista_huecos_e_incompletos():
    cobertura = {
        "AR1N": {
            2023: CoberturaCelda(10, 10),
            2024: CoberturaCelda(10, 8),
            2025: CoberturaCelda(0, 0),
        },
        "GB1": {2024: CoberturaCelda(10, 10), 2025: CoberturaCelda(10, 10)},
    }
    resumenes = {r.codigo: r for r in resumir_competencias(cobertura)}

    assert resumenes["AR1N"].anios_hueco == [2025]
    assert resumenes["AR1N"].anios_incompletos == [2024]
    assert resumenes["AR1N"].ratio == 0.9
    assert resumenes["GB1"].anios_hueco == []
    assert resumenes["GB1"].ratio == 1.0
    # Los peores van primero.
    assert [r.codigo for r in resumir_competencias(cobertura)][0] == "AR1N"


def test_rangos_anios_colapsa_consecutivos():
    assert rangos_anios([2017, 2018, 2019, 2020, 2025, 2026]) == "2017-2020, 2025-2026"
    assert rangos_anios([2024]) == "2024"
    assert rangos_anios([]) == ""


def test_cobertura_a_json_serializa_ratio():
    cobertura = {"AR1N": {2024: CoberturaCelda(4, 3)}}
    datos = cobertura_a_json(cobertura)

    assert datos == {"AR1N": {"2024": {"fixtures": 4, "cargados": 3, "ratio": 0.75}}}


def test_iter_fixtures_lee_el_layout_del_cache(tmp_path):
    carpeta = tmp_path / "raw" / "AR1N" / "2024"
    carpeta.mkdir(parents=True)
    (carpeta / "fixtures.json").write_text(
        json.dumps(
            [
                {"match_id": 1, "date": "2024-03-01"},
                {"match_id": 2, "date": None},
            ]
        ),
        encoding="utf-8",
    )

    fixtures = list(iter_fixtures(tmp_path))

    assert [(f.codigo, f.temporada, f.match_id, f.fecha) for f in fixtures] == [
        ("AR1N", 2024, 1, date(2024, 3, 1)),
        ("AR1N", 2024, 2, None),
    ]


# ---------------------------------------------------------------------------
# Conflictos de fecha y últimos partidos (SQLite)
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    comp = Competition(codigo="TDeC", nombre="Liga 1 Clausura", nivel="B",
                       coeficiente=Decimal("0.80"), tipo="liga")
    dt_a = Coach(transfermarkt_id=1, nombre="Gerardo", apellido="Pelusso")
    dt_b = Coach(transfermarkt_id=2, nombre="Otro", apellido="DT")
    dt_c = Coach(transfermarkt_id=3, nombre="Tercero", apellido="DT")
    club_1 = Club(transfermarkt_id=10, nombre="Alianza Lima")
    club_2 = Club(transfermarkt_id=20, nombre="Melgar")
    session.add_all([comp, dt_a, dt_b, dt_c, club_1, club_2])
    session.commit()

    def partido(fecha, dt_local, dt_visita, match_id):
        session.add(
            MatchCoach(
                transfermarkt_match_id=match_id,
                fecha=fecha,
                competencia_id=comp.competencia_id,
                dt_local_id=dt_local.dt_id,
                dt_visita_id=dt_visita.dt_id,
                club_local_id=club_1.club_id,
                club_visita_id=club_2.club_id,
                elo_local_previo=Decimal("1000"),
                elo_local_nuevo=Decimal("1000"),
                elo_visita_previo=Decimal("1000"),
                elo_visita_nuevo=Decimal("1000"),
                goles_local=1,
                goles_visita=0,
                factor_k=20,
            )
        )

    data = {"dt_a": dt_a, "dt_b": dt_b, "dt_c": dt_c}
    yield session, partido, data
    session.close()


def test_conflictos_detecta_dt_con_dos_partidos_el_mismo_dia(db):
    """Un DT con dos partidos el mismo día (con rivales distintos) es un conflicto.

    La tabla no permite el mismo par de DTs dos veces en la misma fecha y
    competencia (`uq_partido_fecha_dts`), así que el escenario realista es el DT
    que aparece en varios partidos con rivales diferentes.
    """
    session, partido, data = db
    fecha = date(2006, 7, 30)
    partido(fecha, data["dt_a"], data["dt_b"], 100)
    partido(fecha, data["dt_a"], data["dt_c"], 101)
    session.commit()

    conflictos = conflictos_dt_dia(session)

    assert len(conflictos) == 1
    assert conflictos[0].dt_id == data["dt_a"].dt_id
    assert conflictos[0].nombre == "Gerardo Pelusso"
    assert conflictos[0].partidos == 2
    assert conflictos[0].competencias == ["TDeC"]
    assert conflictos[0].match_ids == [100, 101]


def test_conflictos_ignora_partidos_en_fechas_distintas(db):
    session, partido, data = db
    partido(date(2006, 7, 30), data["dt_a"], data["dt_b"], 100)
    partido(date(2006, 8, 6), data["dt_a"], data["dt_b"], 101)
    session.commit()

    assert conflictos_dt_dia(session) == []


def test_ultimos_partidos_por_competencia(db):
    session, partido, data = db
    partido(date(2006, 7, 30), data["dt_a"], data["dt_b"], 100)
    partido(date(2006, 8, 6), data["dt_a"], data["dt_b"], 101)
    session.commit()

    ultimos = ultimos_partidos(session, hoy=date(2006, 8, 20))

    assert len(ultimos) == 1
    assert ultimos[0].codigo == "TDeC"
    assert ultimos[0].fecha == date(2006, 8, 6)
    assert ultimos[0].dias == 14
    assert ultimos[0].partidos == 2


# ---------------------------------------------------------------------------
# Muestra de reportes sin DT
# ---------------------------------------------------------------------------
def _reporte(tmp_path, codigo, temporada, match_id, con_dts=True):
    carpeta = tmp_path / "raw" / codigo / str(temporada) / "matches"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{match_id}.json"
    ruta.write_text(
        json.dumps(
            {
                "match_id": match_id,
                "home_coach_tm_id": 1 if con_dts else None,
                "away_coach_tm_id": 2,
            }
        ),
        encoding="utf-8",
    )
    return ruta


def test_estimar_dt_faltante_agrupa_por_quinquenio(tmp_path):
    rutas = [
        _reporte(tmp_path, "AR1N", 2006, 1, con_dts=False),
        _reporte(tmp_path, "AR1N", 2006, 2, con_dts=True),
        _reporte(tmp_path, "AR1N", 2024, 3, con_dts=True),
    ]

    muestra = estimar_dt_faltante(rutas, muestra=3)

    assert muestra[2005] == {"reportes": 2, "sin_dt": 1, "pct_sin_dt": 50.0}
    assert muestra[2020] == {"reportes": 1, "sin_dt": 0, "pct_sin_dt": 0.0}


def test_estimar_dt_faltante_sin_muestra_devuelve_vacio(tmp_path):
    rutas = [_reporte(tmp_path, "AR1N", 2024, 1)]
    assert estimar_dt_faltante(rutas, muestra=0) == {}
