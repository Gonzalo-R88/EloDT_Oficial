"""Matemática pura del sistema ELO para Directores Técnicos.

Fórmula central (documento maestro v1):

    ΔELO = K · C · G · (R − E)

donde K es el factor de volatilidad, C el coeficiente de competencia, G el
multiplicador por margen de victoria (MOV), R el resultado real y E la
expectativa. La localía se modela como una ventaja virtual de +30 puntos.
"""

from __future__ import annotations

import math

HOME_ADVANTAGE: float = 30.0
ELO_SCALE: float = 400.0
INITIAL_ELO: float = 1000.0

VALID_FACTOR_K = (20, 30, 40)
VALID_BENCH_IMPACT = (-1, 0, 1)


def calculate_expectation(elo_a: float, elo_b: float) -> float:
    """Probabilidad esperada de victoria de A frente a B (logística de 400 pts)."""
    return 1.0 / (1.0 + math.pow(10, (elo_b - elo_a) / ELO_SCALE))


def expected_result_local(elo_local: float, elo_visita: float) -> float:
    """Expectativa del local incorporando la ventaja de localía."""
    return calculate_expectation(elo_local + HOME_ADVANTAGE, elo_visita)


def calculate_margin_of_victory_multiplier(goals_a: int, goals_b: int) -> float:
    """Multiplicador por margen de victoria (MOV).

    - Empate o diferencia de 1 gol: 1.0
    - Diferencia de 2 goles: 1.5
    - Diferencia de 3 o más goles: (1.75 + |diff|) / 3
    """
    goal_diff: int = abs(goals_a - goals_b)
    if goal_diff <= 1:
        return 1.0
    if goal_diff == 2:
        return 1.5
    return (1.75 + goal_diff) / 3.0


def result_from_goals(goles_local: int, goles_visita: int) -> tuple[float, float]:
    """Devuelve (R_local, R_visita): 1.0 victoria, 0.5 empate, 0.0 derrota."""
    if goles_local > goles_visita:
        return 1.0, 0.0
    if goles_local < goles_visita:
        return 0.0, 1.0
    return 0.5, 0.5


def compute_elo_delta(
    elo_local: float,
    elo_visita: float,
    goles_local: int,
    goles_visita: int,
    factor_k: int,
    coeficiente: float,
    apply_mov: bool = True,
) -> tuple[float, float, float]:
    """Calcula (delta_local, delta_visita, mov).

    El intercambio es de suma cero: delta_visita = -delta_local.
    """
    if factor_k not in VALID_FACTOR_K:
        raise ValueError(f"factor_k inválido: {factor_k}. Valores permitidos: {VALID_FACTOR_K}")

    e_local = expected_result_local(elo_local, elo_visita)
    r_local, r_visita = result_from_goals(goles_local, goles_visita)
    mov = calculate_margin_of_victory_multiplier(goles_local, goles_visita) if apply_mov else 1.0

    delta_local = factor_k * coeficiente * mov * (r_local - e_local)
    delta_visita = factor_k * coeficiente * mov * (r_visita - (1.0 - e_local))
    return delta_local, delta_visita, mov


def classify_bench_impact(
    team_goals_before: int,
    opp_goals_before: int,
    team_goals_final: int,
    opp_goals_final: int,
) -> int:
    """Clasifica el impacto del banco de suplentes.

    +1: el equipo mejoró su diferencia tras los cambios.
     0: mantuvo la misma diferencia.
    -1: empeoró su diferencia.
    """
    before = team_goals_before - opp_goals_before
    after = team_goals_final - opp_goals_final
    if after > before:
        return 1
    if after < before:
        return -1
    return 0
