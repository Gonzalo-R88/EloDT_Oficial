"""Capa de datos del "Power Ranking de la Fecha".

Calcula, para una ventana temporal (por defecto la última semana con partidos
cargados), los DTs que más ELO ganaron y perdieron. Es lógica pura de consulta
y agregación sobre `partidos_dt`/`entrenadores`; el dibujo vive en
`visualization.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, Union

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Club, Coach, Competition, MatchCoach

DIAS_VENTANA_DEFAULT = 7


@dataclass(frozen=True)
class RankingEntry:
    """Un DT dentro del ranking, con su movimiento de ELO en la ventana."""

    dt_id: int
    nombre: str
    club: Optional[str]
    elo_previo: float
    elo_actual: float
    delta: float
    partidos: int


@dataclass(frozen=True)
class PowerRanking:
    """Resultado completo del ranking para una ventana temporal."""

    desde: date
    hasta: date
    subidas: list[RankingEntry] = field(default_factory=list)
    bajadas: list[RankingEntry] = field(default_factory=list)
    total_partidos: int = 0


def _normalize_date(value: Union[date, str]) -> date:
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


def resolve_window(
    session: Session,
    desde: Optional[Union[date, str]] = None,
    hasta: Optional[Union[date, str]] = None,
    dias: int = DIAS_VENTANA_DEFAULT,
) -> tuple[date, date]:
    """Determina la ventana temporal a analizar.

    Si no se provee `hasta`, se usa la fecha del partido más reciente cargado.
    Si no se provee `desde`, se retrocede `dias` días desde `hasta`.
    """
    if dias < 1:
        raise ValueError("`dias` debe ser al menos 1.")

    if hasta is None:
        max_fecha = session.execute(select(func.max(MatchCoach.fecha))).scalar_one_or_none()
        if max_fecha is None:
            raise ValueError("No hay partidos cargados para resolver la ventana.")
        hasta_date = max_fecha
    else:
        hasta_date = _normalize_date(hasta)

    desde_date = _normalize_date(desde) if desde is not None else hasta_date - timedelta(days=dias - 1)
    if desde_date > hasta_date:
        raise ValueError(f"Rango inválido: desde={desde_date} > hasta={hasta_date}.")
    return desde_date, hasta_date


@dataclass
class _Accumulator:
    first_previo: float
    last_nuevo: float
    delta: float
    partidos: int
    club_id: Optional[int]
    fecha: date
    partido_id: int


def _accumulate(
    accumulators: dict[int, _Accumulator],
    *,
    dt_id: int,
    club_id: Optional[int],
    elo_previo: float,
    elo_nuevo: float,
    fecha: date,
    partido_id: int,
) -> None:
    current = accumulators.get(dt_id)
    if current is None:
        accumulators[dt_id] = _Accumulator(
            first_previo=elo_previo,
            last_nuevo=elo_nuevo,
            delta=elo_nuevo - elo_previo,
            partidos=1,
            club_id=club_id,
            fecha=fecha,
            partido_id=partido_id,
        )
        return

    current.delta += elo_nuevo - elo_previo
    current.partidos += 1
    order = (fecha, partido_id)
    if order >= (current.fecha, current.partido_id):
        current.last_nuevo = elo_nuevo
        current.club_id = club_id
        current.fecha = fecha
        current.partido_id = partido_id


def compute_power_ranking(
    session: Session,
    desde: Optional[Union[date, str]] = None,
    hasta: Optional[Union[date, str]] = None,
    dias: int = DIAS_VENTANA_DEFAULT,
    top: int = 5,
    competencia_id: Optional[int] = None,
    tipo: Optional[str] = None,
) -> PowerRanking:
    """Calcula las mayores subidas y caídas de ELO en la ventana indicada.

    `tipo` filtra por el tipo de competencia ("selecciones" para las fechas FIFA,
    "liga" para los torneos domésticos) sin tener que pasar código por código.
    """
    desde_date, hasta_date = resolve_window(session, desde, hasta, dias)

    query = (
        select(MatchCoach)
        .where(MatchCoach.fecha >= desde_date, MatchCoach.fecha <= hasta_date)
        .order_by(
            MatchCoach.fecha.asc(),
            MatchCoach.transfermarkt_match_id.asc().nulls_first(),
            MatchCoach.partido_id.asc(),
        )
    )
    if competencia_id is not None:
        query = query.where(MatchCoach.competencia_id == competencia_id)
    if tipo is not None:
        query = query.join(
            Competition, Competition.competencia_id == MatchCoach.competencia_id
        ).where(Competition.tipo == tipo)

    matches = session.execute(query).scalars().all()

    coaches = {
        coach.dt_id: coach for coach in session.execute(select(Coach)).scalars().all()
    }
    clubs = {
        club.club_id: club.nombre for club in session.execute(select(Club)).scalars().all()
    }

    accumulators: dict[int, _Accumulator] = {}
    for match in matches:
        _accumulate(
            accumulators,
            dt_id=match.dt_local_id,
            club_id=match.club_local_id,
            elo_previo=float(match.elo_local_previo),
            elo_nuevo=float(match.elo_local_nuevo),
            fecha=match.fecha,
            partido_id=match.partido_id,
        )
        _accumulate(
            accumulators,
            dt_id=match.dt_visita_id,
            club_id=match.club_visita_id,
            elo_previo=float(match.elo_visita_previo),
            elo_nuevo=float(match.elo_visita_nuevo),
            fecha=match.fecha,
            partido_id=match.partido_id,
        )

    entries: list[RankingEntry] = []
    for dt_id, acc in accumulators.items():
        coach = coaches.get(dt_id)
        nombre = f"{coach.nombre} {coach.apellido}" if coach else f"DT {dt_id}"
        entries.append(
            RankingEntry(
                dt_id=dt_id,
                nombre=nombre,
                club=clubs.get(acc.club_id) if acc.club_id is not None else None,
                elo_previo=round(acc.first_previo, 2),
                elo_actual=round(acc.last_nuevo, 2),
                delta=round(acc.delta, 2),
                partidos=acc.partidos,
            )
        )

    subidas = sorted((e for e in entries if e.delta > 0), key=lambda e: e.delta, reverse=True)
    bajadas = sorted((e for e in entries if e.delta < 0), key=lambda e: e.delta)

    return PowerRanking(
        desde=desde_date,
        hasta=hasta_date,
        subidas=subidas[:top],
        bajadas=bajadas[:top],
        total_partidos=len(matches),
    )


def resolve_competition_id(session: Session, codigo: str) -> int:
    """Resuelve el `competencia_id` interno a partir del código (ej. AR1N)."""
    competencia_id = session.execute(
        select(Competition.competencia_id).where(Competition.codigo == codigo)
    ).scalar_one_or_none()
    if competencia_id is None:
        raise ValueError(f"No se encontró la competencia con código '{codigo}'.")
    return competencia_id