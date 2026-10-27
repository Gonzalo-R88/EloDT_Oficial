import math

import pytest

from elo import (
    calculate_expectation,
    calculate_margin_of_victory_multiplier,
    classify_bench_impact,
    compute_elo_delta,
    expected_result_local,
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


def test_classify_bench_impact():
    assert classify_bench_impact(0, 0, 1, 0) == 1
    assert classify_bench_impact(1, 0, 1, 0) == 0
    assert classify_bench_impact(1, 0, 1, 1) == -1
    assert classify_bench_impact(0, 1, 1, 1) == 1
