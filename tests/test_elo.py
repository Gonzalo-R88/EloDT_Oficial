import math

import pytest

from elo import (
    EloParams,
    calculate_expectation,
    calculate_margin_of_victory_multiplier,
    classify_bench_impact,
    compute_elo_delta,
    expected_result_local,
    match_calibracion,
    mov_multiplier,
    result_from_goals,
)


def test_expectation_equal_ratings():
    assert math.isclose(calculate_expectation(1000.0, 1000.0), 0.5, rel_tol=1e-9)


def test_expectation_favorite_and_underdog_sum_to_one():
    favorite = calculate_expectation(1400.0, 1000.0)
    underdog = calculate_expectation(1000.0, 1400.0)
    assert favorite > 0.5
    assert math.isclose(favorite + underdog, 1.0, rel_tol=1e-9)


def test_home_advantage_increases_expectation():
    assert expected_result_local(1000.0, 1000.0) > calculate_expectation(1000.0, 1000.0)


@pytest.mark.parametrize(
    ("goals_a", "goals_b", "expected"),
    [
        (0, 0, 1.0),
        (1, 0, 1.0),
        (2, 0, 1.5),
        (3, 0, (1.75 + 3) / 3.0),
        (5, 1, (1.75 + 4) / 3.0),
    ],
)
def test_margin_of_victory_multiplier(goals_a, goals_b, expected):
    assert math.isclose(calculate_margin_of_victory_multiplier(goals_a, goals_b), expected)


def test_result_from_goals():
    assert result_from_goals(2, 1) == (1.0, 0.0)
    assert result_from_goals(1, 2) == (0.0, 1.0)
    assert result_from_goals(1, 1) == (0.5, 0.5)


def test_elo_delta_is_zero_sum():
    delta_local, delta_visita, _ = compute_elo_delta(1000.0, 1200.0, 1, 0, 20, 1.0)
    assert math.isclose(delta_local + delta_visita, 0.0, abs_tol=1e-9)
    assert delta_local > 0  # el local gana contra un rival más fuerte


def test_elo_delta_invalid_factor_k():
    with pytest.raises(ValueError):
        compute_elo_delta(1000.0, 1000.0, 1, 0, 25, 1.0)


# ---------------------------------------------------------------------------
# Parámetros del modelo (EloParams)
# ---------------------------------------------------------------------------
def test_parametros_por_defecto_reproducen_el_modelo_original():
    """`EloParams()` no puede cambiar ningún número respecto del modelo original."""
    for goles_local, goles_visita in [(1, 0), (0, 0), (0, 2), (3, 3), (5, 1)]:
        sin_params = compute_elo_delta(1350.0, 1180.0, goles_local, goles_visita, 20, 1.3)
        con_params = compute_elo_delta(
            1350.0, 1180.0, goles_local, goles_visita, 20, 1.3, params=EloParams()
        )
        assert sin_params == con_params


def test_la_ventaja_de_local_cambia_con_hfa():
    base = expected_result_local(1000.0, 1000.0)
    ampliada = expected_result_local(1000.0, 1000.0, EloParams(hfa=60.0))

    assert ampliada > base
    delta_base, _, _ = compute_elo_delta(1000.0, 1000.0, 1, 0, 20, 1.0)
    delta_ampliada, _, _ = compute_elo_delta(
        1000.0, 1000.0, 1, 0, 20, 1.0, params=EloParams(hfa=60.0)
    )
    assert delta_ampliada < delta_base  # ganar siendo más favorito mueve menos


def test_mov_con_tope():
    params = EloParams(mov_mode="cap", mov_cap=2.0)

    assert mov_multiplier(5, 0, 1000.0, 1000.0, params) == 2.0
    assert mov_multiplier(2, 0, 1000.0, 1000.0, params) == 1.5


def test_mov_amortiguado_premia_al_que_gana_siendo_debil():
    params = EloParams(mov_mode="amortiguado")
    # Mismo 3-0, pero cambia quién lo gana: el favorito (1500) o el débil (1000).
    favorito_gana = mov_multiplier(3, 0, 1500.0, 1000.0, params)
    debil_gana = mov_multiplier(3, 0, 1000.0, 1500.0, params)

    assert debil_gana > favorito_gana
    # Un 1-0 de un favorito claro mueve menos que 1,0.
    assert mov_multiplier(1, 0, 1500.0, 1000.0, params) < 1.0


def test_mov_amortiguado_empate_no_cambia_nada():
    assert mov_multiplier(1, 1, 1500.0, 1000.0, EloParams(mov_mode="amortiguado")) == 1.0
    assert mov_multiplier(0, 0, 1000.0, 1400.0, EloParams(mov_mode="amortiguado")) == 1.0


def test_calibracion_arranca_alto_y_baja_a_uno():
    params = EloParams(calibracion_n=30, calibracion_mult=2.0)

    assert match_calibracion(0, params) == 2.0
    assert match_calibracion(15, params) == 1.5
    assert match_calibracion(30, params) == 1.0
    assert match_calibracion(80, params) == 1.0
    # Desactivada por defecto.
    assert match_calibracion(0, EloParams()) == 1.0


def test_inactividad_trata_al_dt_como_si_tuviera_partidos_previos():
    params = EloParams(calibracion_n=30, calibracion_mult=2.0, inactividad_dias=365)

    sin_inactividad = match_calibracion(2, params, dias_desde_ultimo=100)
    con_inactividad = match_calibracion(2, params, dias_desde_ultimo=400)

    assert sin_inactividad > con_inactividad  # vuelve más "calibrado"
    assert con_inactividad == match_calibracion(15, params)


def test_el_k_efectivo_promedia_las_calibraciones_y_sigue_siendo_suma_cero():
    normal, _, _ = compute_elo_delta(1000.0, 1000.0, 1, 0, 20, 1.0)
    doble, _, _ = compute_elo_delta(
        1000.0, 1000.0, 1, 0, 20, 1.0, mult_local=2.0, mult_visita=2.0
    )
    mixto, _, _ = compute_elo_delta(
        1000.0, 1000.0, 1, 0, 20, 1.0, mult_local=2.0, mult_visita=1.0
    )

    assert math.isclose(doble, normal * 2, rel_tol=1e-9)
    assert math.isclose(mixto, normal * 1.5, rel_tol=1e-9)


def test_params_invalidos():
    with pytest.raises(ValueError):
        EloParams(mov_mode="inventado")
    with pytest.raises(ValueError):
        EloParams(mov_mode="cap")  # falta el tope
    with pytest.raises(ValueError):
        EloParams(calibracion_n=-1)
    with pytest.raises(ValueError):
        EloParams(calibracion_mult=0.5)


def test_classify_bench_impact():
    assert classify_bench_impact(0, 0, 1, 0) == 1
    assert classify_bench_impact(1, 0, 1, 0) == 0
    assert classify_bench_impact(1, 0, 1, 1) == -1
    assert classify_bench_impact(0, 1, 1, 1) == 1
