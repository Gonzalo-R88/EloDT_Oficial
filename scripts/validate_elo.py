"""Validación de sanidad del ELO tras el backfill.

Comprueba:
- Ausencia de duplicados por `transfermarkt_match_id`.
- Suma cero por partido (Δlocal + Δvisita ≈ 0).
- Conservación de la masa de puntos (Σ ELO = 1000 × n DTs).
- Cobertura de partidos por competencia.
- Top/bottom de DTs con un mínimo de partidos.

Uso:
    python scripts/validate_elo.py
    python scripts/validate_elo.py --min-partidos 10 --top 15
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from db import create_session  # noqa: E402
from elo import INITIAL_ELO  # noqa: E402
from models import Coach, Competition, MatchCoach  # noqa: E402

logger = logging.getLogger(__name__)


def _duplicate_match_ids(session) -> list[tuple[int, int]]:
    return list(
        session.execute(
            select(MatchCoach.transfermarkt_match_id, func.count())
            .where(MatchCoach.transfermarkt_match_id.is_not(None))
            .group_by(MatchCoach.transfermarkt_match_id)
            .having(func.count() > 1)
        ).all()
    )


def _non_zero_sum(session, matches, tolerance: float) -> int:
    bad = 0
    for match in matches:
        delta = (
            float(match.elo_local_nuevo - match.elo_local_previo)
            + float(match.elo_visita_nuevo - match.elo_visita_previo)
        )
        if abs(delta) > tolerance:
            bad += 1
    return bad


def _mass_report(session, n_coaches: int) -> tuple[float, float, bool]:
    total = float(
        session.execute(select(func.coalesce(func.sum(Coach.elo_actual), 0))).scalar_one()
    )
    expected = float(Decimal(str(INITIAL_ELO)) * n_coaches)
    ok = abs(total - expected) <= 0.5
    return total, expected, ok


def _coverage(session) -> list[tuple[str, str, int]]:
    rows = session.execute(
        select(Competition.codigo, Competition.nombre, func.count(MatchCoach.partido_id))
        .join(MatchCoach, MatchCoach.competencia_id == Competition.competencia_id)
        .group_by(Competition.competencia_id)
        .order_by(func.count(MatchCoach.partido_id).desc())
    ).all()
    return [(codigo or "?", nombre, count) for codigo, nombre, count in rows]


def _rankings(session, min_matches: int, top: int):
    matches = session.execute(select(MatchCoach)).scalars().all()
    counts: Counter[int] = Counter()
    for match in matches:
        counts[match.dt_local_id] += 1
        counts[match.dt_visita_id] += 1

    coaches = session.execute(select(Coach)).scalars().all()
    eligible = [c for c in coaches if counts.get(c.dt_id, 0) >= min_matches]
    eligible.sort(key=lambda c: float(c.elo_actual), reverse=True)

    def fmt(coach: Coach) -> tuple[str, float, int]:
        return f"{coach.nombre} {coach.apellido}", float(coach.elo_actual), counts[coach.dt_id]

    return [fmt(c) for c in eligible[:top]], [fmt(c) for c in eligible[-top:]]


def validate(session, min_matches: int = 5, top: int = 10, tolerance: float = 0.01) -> dict:
    matches = session.execute(select(MatchCoach)).scalars().all()
    n_coaches = session.execute(select(func.count()).select_from(Coach)).scalar_one()
    n_competitions = session.execute(select(func.count()).select_from(Competition)).scalar_one()

    duplicates = _duplicate_match_ids(session)
    bad_zero_sum = _non_zero_sum(session, matches, tolerance)
    mass_total, mass_expected, mass_ok = _mass_report(session, n_coaches)
    best, worst = _rankings(session, min_matches, top)

    return {
        "partidos": len(matches),
        "entrenadores": n_coaches,
        "competencias": n_competitions,
        "tm_match_id_duplicados": len(duplicates),
        "partidos_no_suma_cero": bad_zero_sum,
        "masa_elo_total": mass_total,
        "masa_elo_esperada": mass_expected,
        "masa_elo_ok": mass_ok,
        "cobertura": _coverage(session),
        "top": best,
        "bottom": worst,
    }


def print_report(report: dict) -> None:
    print("=" * 60)
    print("VALIDACIÓN ELO - PROYECTO AEP")
    print("=" * 60)
    print(f"Partidos:            {report['partidos']}")
    print(f"Entrenadores:        {report['entrenadores']}")
    print(f"Competencias:        {report['competencias']}")
    print(f"Duplicados tm_id:    {report['tm_match_id_duplicados']}")
    print(f"Partidos no suma 0:  {report['partidos_no_suma_cero']}")
    print(
        f"Masa ELO:            {report['masa_elo_total']:.2f} "
        f"(esperada {report['masa_elo_esperada']:.2f}) -> "
        f"{'OK' if report['masa_elo_ok'] else 'FALLA'}"
    )
    print("-" * 60)
    print("Cobertura por competencia:")
    for codigo, nombre, count in report["cobertura"]:
        print(f"  {codigo:5} | {nombre:40} | {count:5} partidos")
    print("-" * 60)
    print("Top DTs (mínimo de partidos alcanzado):")
    for nombre, elo, count in report["top"]:
        print(f"  {elo:8.2f}  {nombre:35} ({count} PJ)")
    print("Bottom DTs:")
    for nombre, elo, count in report["bottom"]:
        print(f"  {elo:8.2f}  {nombre:35} ({count} PJ)")
    print("=" * 60)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Valida la sanidad del ELO almacenado.")
    parser.add_argument("--min-partidos", type=int, default=5, help="Mínimo de PJ para rankear.")
    parser.add_argument("--top", type=int, default=10, help="Cantidad de DTs en top/bottom.")
    args = parser.parse_args()

    session = create_session()
    try:
        report = validate(session, min_matches=args.min_partidos, top=args.top)
        print_report(report)
    finally:
        session.close()


if __name__ == "__main__":
    main()
