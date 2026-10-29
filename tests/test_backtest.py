"""Tests del harness de backtest (`backtest.py`)."""

from datetime import date, timedelta

import pytest

from backtest import (
    PartidoBacktest,
    brier_constante,
    evaluar,
    probabilidades_1x2,
)
from elo import EloParams


def _partido(n, goles_local=1, goles_visita=0, local=1, visita=2, anio=2024, factor_k=20):
    return PartidoBacktest(
        tm_match_id=n,
        fecha=date(anio, 1, 1) + timedelta(days=n),
        dt_local=local,
        dt_visita=visita,
        goles_local=goles_local,
        goles_visita=goles_visita,
        factor_k=factor_k,
        coeficiente=1.0,
        nivel="A",
    )


def test_probabilidades_1x2_suman_uno_y_respetan_la_expectativa():
    for e_local in (0.1, 0.35, 0.5, 0.7, 0.95):
        p_local, p_empate, p_visita = probabilidades_1x2(e_local)
        assert p_local + p_empate + p_visita == pytest.approx(1.0)
        # E es la expectativa de puntos del local.
        assert p_local + p_empate / 2 == pytest.approx(e_local, abs=1e-9)


def test_probabilidades_1x2_empate_mas_alto_cuando_estan_parejos():
    _, empate_parejo, _ = probabilidades_1x2(0.5)
    _, empate_desparejo, _ = probabilidades_1x2(0.9)

    assert empate_parejo > empate_desparejo


def test_evaluar_cuenta_los_partidos_y_mide_brier():
    partidos = [_partido(n) for n in range(1, 6)]

    metricas = evaluar(partidos)

    assert metricas.partidos == 5
    assert 0 < metricas.brier < 1
    assert 0 < metricas.logloss < 5


def test_evaluar_filtra_por_partidos_previos():
    partidos = [_partido(n) for n in range(1, 11)]

    todos = evaluar(partidos)
    con_historial = evaluar(partidos, min_pj_previos=5)

    assert todos.partidos == 10
    # Con 5 partidos previos de cada DT, recién se evalúa desde el 6º partido de cada uno.
    assert con_historial.partidos < todos.partidos


def test_evaluar_filtra_por_fecha():
    partidos = [_partido(n, anio=2020) for n in range(1, 4)] + [
        _partido(n, anio=2024) for n in range(10, 13)
    ]

    metricas = evaluar(partidos, desde=date(2024, 1, 1))

    assert metricas.partidos == 3
    assert set(metricas.por_anio) == {2024}


def test_evaluar_registra_calibracion_por_tramo():
    partidos = [_partido(n) for n in range(1, 21)]

    metricas = evaluar(partidos)
    resumen = metricas.resumen_calibracion()

    assert resumen
    assert sum(cantidad for _, _, cantidad in resumen) == metricas.partidos


def test_brier_de_un_modelo_perfecto_es_cero():
    """Si la expectativa coincide con el resultado, el Brier es 0."""
    # Local mucho más fuerte, con HFA enorme: E ≈ 1 y gana el local.
    metricas = evaluar([_partido(1)], params=EloParams(hfa=2000.0))

    assert metricas.brier < 0.01


def test_brier_constante_es_una_linea_base_razonable():
    """La constante (predecir siempre la frecuencia observada) da un Brier creíble."""
    resultados = [(1, 0), (0, 1), (1, 1), (2, 0), (0, 2), (1, 1), (1, 0), (0, 0)]
    partidos = [_partido(n, gl, gv) for n, (gl, gv) in enumerate(resultados, start=1)]

    constante = brier_constante(partidos)

    assert 0.1 < constante < 0.3
