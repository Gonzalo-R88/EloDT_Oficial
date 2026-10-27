"""Estimador del scraping total y planificador diario por ligas.

Uso:
    python scripts/plan_scraping.py
    python scripts/plan_scraping.py --from 2000 --to 2026 --workers 3 --hours-per-day 24
    python scripts/plan_scraping.py --target-days 30
    python scripts/plan_scraping.py --csv data/output/plan_scraping.csv

Modelo de tiempo:
    segundos_por_request = (delay_min + delay_max) / 2 + latencia_red
    horas_totales        = requests_totales * segundos_por_request / 3600
    dias                 = horas_totales / (workers * horas_por_dia)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.leagues_catalog import (  # noqa: E402
    CATALOG,
    LeagueCandidate,
    total_requests,
    total_seasons,
)


def _plan(candidates, first, last, workers, hours_per_day, seconds_per_request):
    rows = []
    for candidate in candidates:
        requests = total_requests(candidate, first, last)
        rows.append((candidate, total_seasons(candidate, first, last), requests))
    total = sum(r[2] for r in rows)
    total_hours = total * seconds_per_request / 3600
    effective_hours_day = workers * hours_per_day
    days = total_hours / effective_hours_day if effective_hours_day else float("inf")
    return rows, total, total_hours, days


def _schedule(rows, daily_capacity):
    """Empaqueta ligas en días con capacidad de requests diaria.

    Ordena de mayor a menor y, si una liga excede la capacidad diaria, la parte
    en varios días (el scraper es reanudable por partido, así que es seguro).
    """
    ordered = sorted(rows, key=lambda r: r[2], reverse=True)
    days: list[dict] = []
    current: dict = {"leagues": [], "requests": 0}
    for candidate, seasons, requests in ordered:
        remaining = requests
        while remaining > 0:
            space = daily_capacity - current["requests"]
            if space <= 0:
                days.append(current)
                current = {"leagues": [], "requests": 0}
                continue
            take = min(remaining, space)
            current["leagues"].append((candidate, seasons, take))
            current["requests"] += take
            remaining -= take
            if remaining > 0:
                days.append(current)
                current = {"leagues": [], "requests": 0}
    if current["leagues"]:
        days.append(current)
    return days


def _fmt_hours(hours: float) -> str:
    return f"{hours:,.1f} h ({hours / 24:,.1f} días 24/7)"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Plan del scraping total (AEP).")
    parser.add_argument("--from", dest="first", type=int, default=2000)
    parser.add_argument("--to", dest="last", type=int, default=2026)
    parser.add_argument("--delay-min", type=float, default=1.5)
    parser.add_argument("--delay-max", type=float, default=4.0)
    parser.add_argument("--network", type=float, default=0.3, help="Latencia de red media (s).")
    parser.add_argument("--workers", type=int, default=1, help="Sesiones paralelas (tmux).")
    parser.add_argument("--hours-per-day", type=float, default=24.0, help="Horas de corrida por día.")
    parser.add_argument(
        "--target-days", type=int, default=0,
        help="Días objetivo para el plan diario (0 = derivar de workers×horas/día).",
    )
    parser.add_argument("--csv", help="Exporta el detalle por liga a CSV.")
    args = parser.parse_args(argv)

    seconds_per_request = (args.delay_min + args.delay_max) / 2 + args.network
    rows, total, total_hours, days = _plan(
        CATALOG, args.first, args.last, args.workers, args.hours_per_day, seconds_per_request
    )

    print("=" * 78)
    print(f"PLAN DE SCRAPING TOTAL  ({args.first}-{args.last})")
    print(f"Competencias: {len(CATALOG)}  |  Requests: {total:,}")
    print(
        f"Modelo: {seconds_per_request:.2f}s/request  |  workers={args.workers}  "
        f"| {args.hours_per_day:g}h/día"
    )
    print("=" * 78)
    print(f"{'CÓD':6} {'COMPETENCIA':34} {'TEMPOR.':>7} {'PART/TEMP':>9} {'REQUESTS':>10}")
    print("-" * 78)
    for candidate, seasons, requests in sorted(rows, key=lambda r: r[2], reverse=True):
        print(
            f"{candidate.code:6} {candidate.name[:34]:34} {seasons:>7} "
            f"{candidate.est_matches:>9} {requests:>10,}"
        )
    print("-" * 78)
    print(f"{'TOTAL':41} {'':>7} {'':>9} {total:>10,}")
    print("=" * 78)

    print("ESCENARIOS DE TIEMPO")
    for workers in (1, 2, 3, 4, 6):
        horas = total * seconds_per_request / 3600 / workers
        print(
            f"  {workers} worker(s) 24/7: {_fmt_hours(horas)}   "
            f"| 8h/día: {horas / 8:,.1f} días"
        )
    print(f"\nEstimación con la config actual: {_fmt_hours(total_hours)} "
          f"(workers={args.workers}, {args.hours_per_day:g}h/día -> {days:,.1f} días)")

    daily_capacity = (
        total / args.target_days
        if args.target_days
        else args.workers * args.hours_per_day * 3600 / seconds_per_request
    )
    schedule = _schedule(rows, daily_capacity)
    print("\n" + "=" * 78)
    print(
        f"PLAN DIARIO  (~{daily_capacity:,.0f} requests/día con "
        f"{args.workers} worker(s) × {args.hours_per_day:g}h)"
    )
    print("=" * 78)
    for index, day in enumerate(schedule, start=1):
        detalle = " ".join(f"{c.code}({take:,})" for c, _, take in day["leagues"])
        print(f"Día {index:>2} ({day['requests']:>8,} req, {len(day['leagues']):>2} tramos): {detalle}")
    print(f"\nDías resultantes: {len(schedule)}")

    if args.csv:
        output = Path(args.csv)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["code", "name", "country", "confederation", "kind",
                             "seasons", "est_matches", "requests"])
            for candidate, seasons, requests in sorted(rows, key=lambda r: r[2], reverse=True):
                writer.writerow([candidate.code, candidate.name, candidate.country,
                                 candidate.confederation, candidate.kind,
                                 seasons, candidate.est_matches, requests])
        print(f"\nDetalle exportado a: {output}")


if __name__ == "__main__":
    main()