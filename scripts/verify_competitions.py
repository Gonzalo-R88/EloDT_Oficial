"""Verifica contra Transfermarkt los códigos del catálogo de scraping total.

Descarga el fixture de una temporada de muestra por competencia y reporta la
cantidad de partidos parseados. Sirve para detectar códigos/slugs/offsets
inválidos antes de lanzar un backfill largo.

Uso:
    python scripts/verify_competitions.py
    python scripts/verify_competitions.py --season 2024 --codes GB1,ES1,BRA1
    python scripts/verify_competitions.py --refresh   # vuelve a consultar todo
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from scraping.client import TransfermarktClient  # noqa: E402
from scraping.leagues_catalog import CATALOG, LeagueCandidate  # noqa: E402
from scraping.parser import parse_schedule  # noqa: E402

logger = logging.getLogger(__name__)


def build_fixture_url(candidate: LeagueCandidate, season: int) -> str:
    saison_id = season - candidate.saison_offset
    return (
        f"https://{settings.transfermarkt_domain}/{candidate.code}/gesamtspielplan/"
        f"{candidate.path}/{candidate.code}?saison_id={saison_id}"
        f"&spieltagVon=1&spieltagBis=99"
    )


def verify(candidate: LeagueCandidate, season: int, client: TransfermarktClient) -> dict:
    try:
        html = client.get(build_fixture_url(candidate, season))
        fixtures = parse_schedule(html, candidate.code, season)
    except Exception as exc:  # noqa: BLE001 - reportamos y seguimos
        return {"code": candidate.code, "status": "ERROR", "fixtures": 0, "detalle": str(exc)}

    count = len(fixtures)
    fechas = [f.date for f in fixtures if f.date]
    if count == 0 or not fechas:
        return {"code": candidate.code, "status": "VACIO", "fixtures": count, "detalle": "sin partidos"}

    years = [int(fecha[:4]) for fecha in fechas]
    min_year, max_year = min(years), max(years)
    rango = f"{min_year}-{max_year}"
    # Una configuración correcta de `saison_offset` hace que la temporada real
    # `season` sea el año en que ARRANCA el fixture (min_year == season). Si no,
    # TM devolvió otra temporada (típicamente el fallback de la actual) y hay que
    # corregir el offset o el código.
    if min_year != season:
        return {"code": candidate.code, "status": "FUERA", "fixtures": count, "detalle": f"fechas={rango}"}

    if candidate.est_matches and abs(count - candidate.est_matches) / candidate.est_matches > 0.35:
        status = "REVISAR"
    else:
        status = "OK"
    return {"code": candidate.code, "status": status, "fixtures": count, "detalle": f"fechas={rango}"}


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Verifica códigos de competencias (AEP).")
    parser.add_argument("--season", type=int, default=2023, help="Temporada real de muestra (default 2023).")
    parser.add_argument("--codes", help="Lista separada por comas; por defecto, todo el catálogo.")
    args = parser.parse_args(argv)

    candidates = CATALOG
    if args.codes:
        wanted = {c.strip().upper() for c in args.codes.split(",")}
        candidates = tuple(c for c in CATALOG if c.code.upper() in wanted)

    client = TransfermarktClient(
        delay_min=settings.request_delay_min,
        delay_max=settings.request_delay_max,
        max_retries=settings.max_retries,
        timeout=settings.request_timeout,
    )

    print(f"{'CÓD':7} {'ESTADO':8} {'FIXTURES':>9}  {'EST.':>6}  DETALLE")
    print("-" * 70)
    counts = {"OK": 0, "REVISAR": 0, "VACIO": 0, "FUERA": 0, "ERROR": 0}
    for candidate in candidates:
        result = verify(candidate, args.season, client)
        counts[result["status"]] += 1
        print(
            f"{result['code']:7} {result['status']:8} {result['fixtures']:>9}  "
            f"{candidate.est_matches:>6}  {result['detalle']}"
        )
    print("-" * 70)
    print("Resumen:", counts)


if __name__ == "__main__":
    main()