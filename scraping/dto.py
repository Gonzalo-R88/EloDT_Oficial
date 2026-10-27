"""Estructuras de datos (DTO) del pipeline de ingesta."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Fixture:
    """Partido listado en el fixture de una competencia/temporada."""

    match_id: int
    competition_code: str
    season: int
    date: Optional[str]  # ISO YYYY-MM-DD
    matchday: Optional[str]
    home_club_tm_id: int
    home_club_name: str
    away_club_tm_id: int
    away_club_name: str
    home_goals: int
    away_goals: int


@dataclass
class TimelineEvent:
    """Evento de la línea de tiempo del partido."""

    team: str  # "home" | "away"
    type: str  # "goal" | "sub" | "card"
    position: float  # porcentaje del eje temporal (orden cronológico)


@dataclass
class MatchReport:
    """Detalle extraído del reporte de un partido."""

    match_id: int
    final_home_goals: int
    final_away_goals: int
    home_coach_tm_id: Optional[int]
    home_coach_name: Optional[str]
    away_coach_tm_id: Optional[int]
    away_coach_name: Optional[str]
    # Fecha real del partido según el reporte (ISO). La del fixture no es confiable:
    # Transfermarkt imprime la fecha una sola vez por bloque y las filas siguientes
    # quedan vacías. En reportes cacheados antes de este campo queda en None.
    fecha: Optional[str] = None
    events: list[TimelineEvent] = field(default_factory=list)
    marcador_pre_cambios_local: Optional[str] = None
    marcador_pre_cambios_visita: Optional[str] = None
    impacto_banco_local: int = 0
    impacto_banco_visita: int = 0


@dataclass
class NormalizedMatch:
    """Partido listo para persistir y procesar en el motor de ELO."""

    tm_match_id: int
    competition_code: str
    date: str
    factor_k: int
    home_club_tm_id: int
    home_club_name: str
    away_club_tm_id: int
    away_club_name: str
    home_goals: int
    away_goals: int
    home_coach_tm_id: Optional[int]
    home_coach_name: Optional[str]
    away_coach_tm_id: Optional[int]
    away_coach_name: Optional[str]
    marcador_pre_cambios_local: Optional[str]
    marcador_pre_cambios_visita: Optional[str]
    impacto_banco_local: int
    impacto_banco_visita: int
