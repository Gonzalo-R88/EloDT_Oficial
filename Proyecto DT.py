"""
Módulo de compatibilidad y redirección hacia el módulo canónico unificado DT.py.
Proyecto: Analítica de Entrenadores & Performance (AEP)
"""

import logging
from DT import (
    Base,
    Club,
    Coach,
    Competition,
    MatchCoach,
    SessionFactory,
    calculate_expectation,
    calculate_margin_of_victory_multiplier,
    calcular_esperanza,
    calcular_multiplicador_goles,
    engine,
    process_match_elo,
    procesar_partido_elo,
)

__all__ = [
    "Base",
    "Coach",
    "Competition",
    "Club",
    "MatchCoach",
    "engine",
    "SessionFactory",
    "calculate_expectation",
    "calculate_margin_of_victory_multiplier",
    "process_match_elo",
    "calcular_esperanza",
    "calcular_multiplicador_goles",
    "procesar_partido_elo",
]

if __name__ == "__main__":
    logging.info("Módulo Proyecto DT ejecutado como alias unificado de DT.py.")