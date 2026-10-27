"""Capa de datos del "Duelo de Pizarras" (cara a cara entre dos DTs).

Calcula el historial agregado de cada entrenador (PJ, G-E-P, goles, forma
reciente, ELO) y el historial de enfrentamientos directos. Lógica pura de
consulta; el dibujo vive en `visualization.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Union

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models import Club, Coach, MatchCoach

FORMA_DEFAULT = 5


@dataclass(frozen=True)
class DuelSide:
    """Resumen de un DT para el duelo."""

    dt_id: int
    nombre: str
    apellido: str
    club: Optional[str]
    elo_actual: float
    partidos: int
    victorias: int
    empates: int
    derrotas: int
    goles_favor: int
    goles_contra: int
    forma: tuple[str, ...]

    @property
    def diferencia(self) -> int:
        return self.goles_favor - self.goles_contra

    @property
    def puntos_por_partido(self) -> float:
        if self.partidos == 0:
            return 0.0
        return round((3 * self.victorias + self.empates) / self.partidos, 2)


@dataclass(frozen=True)
class Duel:
    """Resultado completo del cara a cara."""

    a: DuelSide
    b: DuelSide
    enfrentamientos: int
    victorias_a: int
    empates: int
    victorias_b: int
    desde: Optional[date]
    hasta: Optional[date]


def resolve_coach(session: Session, value: Union[int, str]) -> Coach:
    """Resuelve un DT por `dt_id` numérico o por coincidencia de nombre/apellido."""
    raw = str(value).strip()
    if not raw:
        raise ValueError("Indicá un DT por id o por nombre.")

    if raw.isdigit():
        coach = session.get(Coach, int(raw))
        if coach is None:
            raise ValueError(f"No se encontró el DT con id {raw}.")
        return coach

    pattern = f"%{raw}%"
    coaches = (
        session.execute(
            select(Coach).where(
                or_(Coach.nombre.ilike(pattern), Coach.apellido.ilike(pattern))
            )
        )
        .scalars()
        .all()
    )
    if not coaches:
        raise ValueError(f"No se encontró ningún DT que coincida con '{raw}'.")
    if len(coaches) > 1:
        opciones = ", ".join(f"{c.dt_id}:{c.nombre} {c.apellido}" for c in coaches[:8])
        raise ValueError(f"'{raw}' es ambiguo. Candidatos: {opciones}")
    return coaches[0]


def _result(gf: int, gc: int) -> str:
    if gf > gc:
        return "V"
    if gf < gc:
        return "D"
    return "E"


def _goals(match: MatchCoach, coach_id: int) -> tuple[int, int]:
    """Goles (favor, contra) del DT indicado en el partido."""
    if match.dt_local_id == coach_id:
        return match.goles_local, match.goles_visita
    return match.goles_visita, match.goles_local


def _side_stats(
    coach: Coach,
    matches: list[MatchCoach],
    club_names: dict[int, str],
    n_forma: int,
) -> DuelSide:
    ordered = sorted(
        matches,
        key=lambda m: (m.fecha, m.transfermarkt_match_id or 0, m.partido_id),
    )

    victorias = empates = derrotas = gf_total = gc_total = 0
    club_name: Optional[str] = None
    for match in ordered:
        gf, gc = _goals(match, coach.dt_id)
        resultado = _result(gf, gc)
        if resultado == "V":
            victorias += 1
        elif resultado == "E":
            empates += 1
        else:
            derrotas += 1
        gf_total += gf
        gc_total += gc

        club_id = match.club_local_id if match.dt_local_id == coach.dt_id else match.club_visita_id
        if club_id is not None:
            club_name = club_names.get(club_id, club_name)

    forma = tuple(_result(*_goals(m, coach.dt_id)) for m in reversed(ordered[-n_forma:]))

    return DuelSide(
        dt_id=coach.dt_id,
        nombre=f"{coach.nombre} {coach.apellido}",
        apellido=coach.apellido,
        club=club_name,
        elo_actual=round(float(coach.elo_actual), 2),
        partidos=len(ordered),
        victorias=victorias,
        empates=empates,
        derrotas=derrotas,
        goles_favor=gf_total,
        goles_contra=gc_total,
        forma=forma,
    )


def compute_duel(
    session: Session,
    dt_a_id: int,
    dt_b_id: int,
    n_forma: int = FORMA_DEFAULT,
) -> Duel:
    """Construye el cara a cara entre dos DTs a partir de todo su historial."""
    if dt_a_id == dt_b_id:
        raise ValueError("Un DT no puede enfrentarse a sí mismo.")

    coach_a = session.get(Coach, dt_a_id)
    coach_b = session.get(Coach, dt_b_id)
    if coach_a is None or coach_b is None:
        raise ValueError("Alguno de los DTs indicados no existe.")

    matches = (
        session.execute(
            select(MatchCoach)
            .where(
                or_(
                    MatchCoach.dt_local_id.in_((dt_a_id, dt_b_id)),
                    MatchCoach.dt_visita_id.in_((dt_a_id, dt_b_id)),
                )
            )
            .order_by(MatchCoach.fecha.asc(), MatchCoach.partido_id.asc())
        )
        .scalars()
        .all()
    )

    club_names = {
        club.club_id: club.nombre
        for club in session.execute(select(Club)).scalars().all()
    }

    matches_a = [m for m in matches if dt_a_id in (m.dt_local_id, m.dt_visita_id)]
    matches_b = [m for m in matches if dt_b_id in (m.dt_local_id, m.dt_visita_id)]

    side_a = _side_stats(coach_a, matches_a, club_names, n_forma)
    side_b = _side_stats(coach_b, matches_b, club_names, n_forma)

    h2h = [
        m for m in matches if {m.dt_local_id, m.dt_visita_id} == {dt_a_id, dt_b_id}
    ]
    victorias_a = empates = victorias_b = 0
    for match in h2h:
        goles_a, goles_b = _goals(match, dt_a_id)
        if goles_a > goles_b:
            victorias_a += 1
        elif goles_a < goles_b:
            victorias_b += 1
        else:
            empates += 1

    fechas = [m.fecha for m in matches]
    return Duel(
        a=side_a,
        b=side_b,
        enfrentamientos=len(h2h),
        victorias_a=victorias_a,
        empates=empates,
        victorias_b=victorias_b,
        desde=min(fechas) if fechas else None,
        hasta=max(fechas) if fechas else None,
    )