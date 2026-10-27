"""Fachada de compatibilidad del módulo DT.

La lógica canónica vive en módulos separados (`models`, `elo`, `services`,
`db`, `config`). Este módulo re-exporta los símbolos históricos para no romper
importaciones previas (incluido `Proyecto DT.py`).
"""

from __future__ import annotations

from config import settings
from db import SessionFactory, create_session, engine
from elo import (
    ELO_SCALE,
    HOME_ADVANTAGE,
    INITIAL_ELO,
    calculate_expectation,
    calculate_margin_of_victory_multiplier,
    classify_bench_impact,
    compute_elo_delta,
    expected_result_local,
    result_from_goals,
)
from models import Base, Club, Coach, Competition, MatchCoach
from services import process_match_elo, recompute_all_elo

# Aliases en español para compatibilidad con código previo
calcular_esperanza = calculate_expectation
calcular_multiplicador_goles = calculate_margin_of_victory_multiplier
procesar_partido_elo = process_match_elo

__all__ = [
    "Base",
    "Coach",
    "Competition",
    "Club",
    "MatchCoach",
    "engine",
    "SessionFactory",
    "create_session",
    "settings",
    "calculate_expectation",
    "calculate_margin_of_victory_multiplier",
    "classify_bench_impact",
    "compute_elo_delta",
    "expected_result_local",
    "result_from_goals",
    "process_match_elo",
    "recompute_all_elo",
    "calcular_esperanza",
    "calcular_multiplicador_goles",
    "procesar_partido_elo",
    "HOME_ADVANTAGE",
    "ELO_SCALE",
    "INITIAL_ELO",
]
