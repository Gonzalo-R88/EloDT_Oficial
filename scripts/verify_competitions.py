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


def verify(
    candidate: LeagueCandidate,
    season: int,
    client: TransfermarktClient,
    no_align_check: bool = False,
) -> dict:
    try:
        html = client.get(build_fixture_url(candidate, season))
        fixtures = parse_schedule(html, candidate.code, season)
    except Exception as exc:  # noqa: BLE001 - reportamos y seguimos
        return {"code": candidate.code, "status": "ERROR", "fixtures": 0, "detalle": str(exc)}

    count = len(fixtures)
    fechas = sorted(f.date for f in fixtures if f.date)
    if count == 0 or not fechas:
        return {"code": candidate.code, "status": "VACIO", "fixtures": count, "detalle": "sin partidos"}

    years = [int(fecha[:4]) for fecha in fechas]
    min_year, max_year = min(years), max(years)
    rango = f"{min_year}-{max_year}"
    detalle = f"fechas={fechas[0]}..{fechas[-1]} ({rango})"
    # Una configuración correcta de `saison_offset` hace que la temporada real
    # `season` caiga dentro del rango de fechas del fixture. Se exige que el año
    # pedido sea >= year mínimo (TM devolvió otra temporada, típicamente la actual).
    # Las temporadas partidas (agosto-junio) arrancan el año anterior: por eso se
    # acepta `season` dentro del rango y no solo como año de arranque.
    # `--no-align-check` sirve para diagnosticar: muestra el fixture tal cual.
    if not no_align_check and not (min_year <= season <= max_year):
        return {"code": candidate.code, "status": "FUERA", "fixtures": count, "detalle": detalle}

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
    parser.add_argument("--saison-offset", type=int, default=None,
                        help="Offset para códigos fuera del catálogo (default: el del catálogo, o 1).")
    parser.add_argument("--path", default="wettbewerb",
                        help="camino de TM para códigos fuera del catálogo: wettbewerb | pokalwettbewerb")
    parser.add_argument("--no-align-check", action="store_true",
                        help="No marcar FUERA cuando la temporada pedida no cae en el rango de fechas.")
    args = parser.parse_args(argv)

    by_code = {c.code.upper(): c for c in CATALOG}
    if args.codes:
        seleccion = [c.strip().upper() for c in args.codes.split(",") if c.strip()]
        candidates = []
        for code in seleccion:
            conocido = by_code.get(code)
            if conocido is not None:
                candidates.append(conocido)
            else:
                # Código fuera del catálogo: se arma un candidato para poder probarlo.
                candidates.append(
                    LeagueCandidate(
                        code=code, name=code, country="", confederation="", kind="liga",
                        saison_offset=args.saison_offset or 1, est_matches=0, tier="C",
                        coefficient=1.0, path=args.path,
                    )
                )
        candidates = tuple(candidates)
    else:
        candidates = CATALOG

    # Con VPN, TM responde el challenge JS de AWS WAF: sin el solver no se puede
    # verificar nada (el cliente reintenta y termina en "challenge AWS WAF").
    waf_solver = None
    if settings.waf_solver:
        from scraping.waf import WafChallengeSolver

        waf_solver = WafChallengeSolver(
            domain=settings.transfermarkt_domain,
            headless=settings.waf_headless,
            wait_seconds=settings.waf_wait_seconds,
        )
    client = TransfermarktClient(
        delay_min=settings.request_delay_min,
        delay_max=settings.request_delay_max,
        max_retries=settings.max_retries,
        timeout=settings.request_timeout,
        blocked_wait=settings.blocked_wait,
        blocked_retries=settings.blocked_retries,
        impersonate=settings.impersonate,
        domain=settings.transfermarkt_domain,
        waf_solver=waf_solver,
    )
    client.warm_up()

    print(f"{'CÓD':7} {'ESTADO':8} {'FIXTURES':>9}  {'EST.':>6}  DETALLE")
    print("-" * 70)
    counts = {"OK": 0, "REVISAR": 0, "VACIO": 0, "FUERA": 0, "ERROR": 0}
    for candidate in candidates:
        result = verify(candidate, args.season, client, no_align_check=args.no_align_check)
        counts[result["status"]] += 1
        print(
            f"{result['code']:7} {result['status']:8} {result['fixtures']:>9}  "
            f"{candidate.est_matches:>6}  {result['detalle']}"
        )
    print("-" * 70)
    print("Resumen:", counts)


if __name__ == "__main__":
    main()