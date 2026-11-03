"""CLI del scraper de Transfermarkt y pipeline de ELO (proyecto AEP).

Ejemplos:
    python scraper_transfermarkt.py list
    python scraper_transfermarkt.py scrape --competition AR1N --season 2023
    python scraper_transfermarkt.py load --competition AR1N --season 2023
    python scraper_transfermarkt.py ingest --competition AR1N --season 2023
    python scraper_transfermarkt.py recompute
    python scraper_transfermarkt.py coverage --competition AR1N --season 2023
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

from config import settings
from services import recompute_all_elo
from scraping.client import TransfermarktClient
from scraping.competitions import COMPETITIONS, CompetitionConfig, get_competition
from scraping.pipeline import (
    coverage_report,
    load_normalized,
    persist_matches,
    scrape_season,
)
from scraping.storage import RawStore
from scraping.waf import WafChallengeSolver


def configure_logging() -> None:
    """Registra en consola y en archivo (la caché permite reanudar tras cortes)."""
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = logging.FileHandler(log_dir / "ingest.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)


def resolve_seasons(args: argparse.Namespace) -> list[int]:
    if args.season is not None:
        return [args.season]
    if args.from_year is not None and args.to_year is not None:
        return list(range(args.from_year, args.to_year + 1))
    raise SystemExit("Indicá --season N o bien --from AÑO --to AÑO.")


def resolve_competitions(args: argparse.Namespace) -> list[CompetitionConfig]:
    if args.leagues:
        codes = [code.strip().upper() for code in args.leagues.split(",") if code.strip()]
        return [get_competition(code) for code in codes]
    if args.all_competitions:
        return list(COMPETITIONS.values())
    if not args.competition:
        raise SystemExit("Indicá --competition CÓDIGO, --leagues A,B o --all-competitions.")
    return [get_competition(args.competition)]


def build_client() -> TransfermarktClient:
    waf_solver = None
    if settings.waf_solver:
        waf_solver = WafChallengeSolver(
            domain=settings.transfermarkt_domain,
            headless=settings.waf_headless,
            wait_seconds=settings.waf_wait_seconds,
        )
    return TransfermarktClient(
        delay_min=settings.request_delay_min,
        delay_max=settings.request_delay_max,
        max_retries=settings.max_retries,
        timeout=settings.request_timeout,
        blocked_wait=settings.blocked_wait,
        blocked_retries=settings.blocked_retries,
        max_waf_solves=settings.max_waf_solves,
        impersonate=settings.impersonate,
        domain=settings.transfermarkt_domain,
        waf_solver=waf_solver,
    )


def cmd_list() -> None:
    print("Competencias registradas:")
    for config in sorted(COMPETITIONS.values(), key=lambda c: (c.country, c.code)):
        print(
            f"  {config.code:5} | {config.name:32} | {config.country:10} "
            f"| nivel {config.tier} | coef {config.coefficient:.2f} | {config.kind}"
        )


def cmd_scrape(args: argparse.Namespace) -> None:
    client = build_client()
    client.warm_up()
    store = RawStore(settings.data_dir)
    for config in resolve_competitions(args):
        for season in resolve_seasons(args):
            try:
                fixtures = scrape_season(
                    config, season, client, store,
                    refresh=args.refresh, limit=args.limit,
                )
            except RuntimeError as exc:
                logging.warning(
                    "[scrape] %s %s falló tras agotar reintentos (%s); se omite y continúa.",
                    config.code, season, exc,
                )
                continue
            print(f"[scrape] {config.code} {season}: {len(fixtures)} partidos en fixture.")


def cmd_update(args: argparse.Namespace) -> None:
    """Baja sólo los partidos nuevos de las temporadas en curso (actualización semanal)."""
    from datetime import date as _date

    from scraping.pipeline import scrape_incremental

    client = None if args.dry_run else build_client()
    if client is not None:
        client.warm_up()
    store = RawStore(settings.data_dir)

    semana_fin = args.semana_fin
    total = {"fixtures": 0, "reportes": 0, "omitidos_fecha": 0, "errores": 0}
    for config in resolve_competitions(args):
        try:
            stats = scrape_incremental(
                config, client, store,
                semana_fin=semana_fin, dry_run=args.dry_run, limit=args.limit,
            )
        except RuntimeError as exc:
            logging.warning("[update] %s falló: %s", config.code, exc)
            total["errores"] += 1
            continue
        for clave, valor in stats.items():
            total[clave] = total.get(clave, 0) + valor
        print(f"[update] {config.code}: {stats}")

    modo = " (dry-run: sólo cuenta fixtures)" if args.dry_run else ""
    print(f"[update] TOTAL{modo}: {total}")


def cmd_load(args: argparse.Namespace) -> None:
    store = RawStore(settings.data_dir)
    for config in resolve_competitions(args):
        for season in resolve_seasons(args):
            if not store.has_fixtures(config.code, season):
                print(f"[load] {config.code} {season}: sin fixture cacheado; se omite.")
                continue
            matches = load_normalized(config, season, store)
            stats = persist_matches(matches)
            print(f"[load] {config.code} {season}: {stats}")


def cmd_ingest(args: argparse.Namespace) -> None:
    cmd_scrape(args)
    cmd_load(args)


def cmd_recompute(_: argparse.Namespace) -> None:
    total = recompute_all_elo()
    print(f"[recompute] {total} partidos reproducidos.")


def cmd_coverage(args: argparse.Namespace) -> None:
    store = RawStore(settings.data_dir)
    for config in resolve_competitions(args):
        for season in resolve_seasons(args):
            report = coverage_report(config, season, store)
            print(f"[coverage] {config.code} {season}:")
            for key, value in report.items():
                print(f"    {key}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scraper Transfermarkt + pipeline ELO (AEP)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--competition", help="Código de competencia (ej. AR1N, CL).")
        sub.add_argument("--leagues", help="Varios códigos separados por coma (ej. GB1,ES1,BRA1).")
        sub.add_argument("--all-competitions", action="store_true", help="Todas las competencias registradas.")
        sub.add_argument("--season", type=int, help="Temporada (año real), ej. 2024.")
        sub.add_argument("--from", dest="from_year", type=int, help="Año inicial del rango.")
        sub.add_argument("--to", dest="to_year", type=int, help="Año final del rango.")

    sub_list = subparsers.add_parser("list", help="Lista las competencias registradas.")
    sub_list.set_defaults(func=lambda args: cmd_list())

    sub_scrape = subparsers.add_parser("scrape", help="Descarga y cachea fixture + reportes.")
    add_common(sub_scrape)
    sub_scrape.add_argument("--refresh", action="store_true", help="Ignora la caché y vuelve a descargar.")
    sub_scrape.add_argument("--limit", type=int, default=None, help="Máximo de reportes a descargar (pruebas).")
    sub_scrape.set_defaults(func=cmd_scrape)

    sub_load = subparsers.add_parser("load", help="Normaliza y persiste (upsert + ELO).")
    add_common(sub_load)
    sub_load.set_defaults(func=cmd_load)

    sub_ingest = subparsers.add_parser("ingest", help="scrape + load.")
    add_common(sub_ingest)
    sub_ingest.add_argument("--refresh", action="store_true", help="Ignora la caché y vuelve a descargar.")
    sub_ingest.add_argument("--limit", type=int, default=None, help="Máximo de reportes a descargar (pruebas).")
    sub_ingest.set_defaults(func=cmd_ingest)

    sub_update = subparsers.add_parser(
        "update", help="Baja sólo los partidos nuevos de las temporadas en curso."
    )
    add_common(sub_update)
    sub_update.add_argument("--semana-fin", type=lambda v: __import__("datetime").date.fromisoformat(v),
                            default=None,
                            help="Sólo se descargan partidos con fecha <= esta (YYYY-MM-DD).")
    sub_update.add_argument("--limit", type=int, default=None,
                            help="Máximo de reportes por competencia (pruebas).")
    sub_update.add_argument("--dry-run", action="store_true",
                            help="No descarga: informa cuántos fixtures pediría.")
    sub_update.set_defaults(func=cmd_update)

    sub_recompute = subparsers.add_parser("recompute", help="Recalcula el ELO desde cero.")
    sub_recompute.set_defaults(func=cmd_recompute)

    sub_coverage = subparsers.add_parser("coverage", help="Reporte de cobertura de una temporada.")
    add_common(sub_coverage)
    sub_coverage.set_defaults(func=cmd_coverage)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning(
            "Interrumpido por el usuario. La caché en disco permite reanudar "
            "volviendo a ejecutar el mismo comando."
        )
        sys.exit(130)


if __name__ == "__main__":
    main()
