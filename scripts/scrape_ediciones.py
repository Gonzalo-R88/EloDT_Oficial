"""Scrapea ediciones de competencias cuyo `saison_id` no sigue una regla fija.

Las competencias de selecciones no tienen un `saison_id` predecible (la Copa Oro 2023
vive en `saison_id=2022`, la Copa Asiática 2024 en 2022, la Eurocopa 2024 en 2023 y la
Copa América 2024 en 2024). Además, cuando el `saison_id` pedido no existe,
Transfermarkt devuelve la última edición: eso hacía que el guard de temporada descartara
temporadas válidas o repitiera la misma.

Este script recorre un rango de `saison_id`, descarta las respuestas repetidas (mismo
conjunto de partidos) y cachea cada edición distinta bajo el **año de su primer partido**,
que es lo que después lee `load`.

Uso:
    python3 scripts/scrape_ediciones.py --codes FIWC,COPA,EURO --from 2000 --to 2026
    python3 scripts/scrape_ediciones.py --codes AFAC --from 2015 --to 2026
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from scraping.client import TransfermarktClient  # noqa: E402
from scraping.competitions import get_competition  # noqa: E402
from scraping.dto import Fixture  # noqa: E402
from scraping.parser import parse_match_report, parse_schedule  # noqa: E402
from scraping.pipeline import build_match_url  # noqa: E402
from scraping.storage import RawStore  # noqa: E402
from scraping.waf import WafChallengeSolver  # noqa: E402


def _hora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def url_fixture(codigo: str, slug: str, path: str, saison_id: int) -> str:
    return (
        f"https://{settings.transfermarkt_domain}/{slug}/gesamtspielplan/{path}/"
        f"{codigo}?saison_id={saison_id}&spieltagVon=1&spieltagBis=99"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrapea ediciones por saison_id.")
    parser.add_argument("--codes", required=True, help="Códigos separados por coma.")
    parser.add_argument("--from", dest="desde", type=int, default=2000)
    parser.add_argument("--to", dest="hasta", type=int, default=2026)
    parser.add_argument("--sin-reportes", action="store_true",
                        help="Bajar sólo los fixtures (sin reportes de partido).")
    args = parser.parse_args(argv)

    client = TransfermarktClient(
        delay_min=settings.request_delay_min, delay_max=settings.request_delay_max,
        max_retries=settings.max_retries, timeout=settings.request_timeout,
        blocked_wait=settings.blocked_wait, blocked_retries=settings.blocked_retries,
        impersonate=settings.impersonate, domain=settings.transfermarkt_domain,
        waf_solver=WafChallengeSolver(domain=settings.transfermarkt_domain,
                                      headless=settings.waf_headless,
                                      wait_seconds=settings.waf_wait_seconds),
    )
    client.warm_up()

    store = RawStore(settings.data_dir)

    for codigo in [c.strip().upper() for c in args.codes.split(",") if c.strip()]:
        try:
            config = get_competition(codigo)
        except KeyError:
            # Un código mal escrito no debe tirar abajo todo el lote.
            print(f"[{codigo}] no está en el catálogo; se omite.")
            continue
        vistos: set[tuple[int, ...]] = set()
        ediciones = 0
        for saison_id in range(args.desde, args.hasta + 1):
            url = url_fixture(codigo, config.slug, config.path, saison_id)
            try:
                html = client.get(url, referer=f"https://{settings.transfermarkt_domain}/")
            except Exception as error:  # noqa: BLE001
                print(f"{_hora()} [{codigo}] saison_id={saison_id}: error {error}")
                continue
            fixtures = parse_schedule(html, codigo, saison_id)
            if not fixtures:
                continue
            clave = tuple(sorted(f.match_id for f in fixtures))
            if clave in vistos:
                continue
            vistos.add(clave)

            fechas = sorted(f.date for f in fixtures if f.date)
            if not fechas:
                continue
            anio = int(fechas[0][:4])
            store.write_fixtures(codigo, anio, [asdict(f) for f in fixtures])
            ediciones += 1
            print(f"{_hora()} [{codigo}] saison_id={saison_id} -> edición {anio}: {len(fixtures)} partidos")

            if args.sin_reportes:
                continue
            for posicion, fixture in enumerate(fixtures, start=1):
                if store.has_match(codigo, anio, fixture.match_id):
                    continue
                try:
                    reporte = parse_match_report(
                        client.get(build_match_url(fixture.match_id), referer=url),
                        fixture.match_id,
                    )
                except Exception as error:  # noqa: BLE001
                    print(f"  {_hora()} [{codigo}] partido {fixture.match_id}: error {error}")
                    continue
                store.write_match(codigo, anio, fixture.match_id, asdict(reporte))
                if posicion % 20 == 0:
                    print(f"  {_hora()} [{codigo} {anio}] {posicion}/{len(fixtures)} reportes")
        print(f"{_hora()} [{codigo}] ediciones cacheadas: {ediciones}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
