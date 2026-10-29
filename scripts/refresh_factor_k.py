"""Recalcula el `factor_k` de los partidos cargados usando la ronda del fixture.

No hace requests: la ronda (`matchday`) ya está en el caché de fixtures. Sirve después
de corregir `infer_factor_k` (`scraping/pipeline.py`): antes de este script, de 195 mil
partidos sólo ~1.100 tenían K distinto de 20 porque las rondas de copa no se
reconocían ("First Round", "Second Round", "Play Off", "Playoffs"...).

Después de aplicar hay que recalcular el ELO:
    python3 scraper_transfermarkt.py recompute
    python3 scripts/validate_elo.py

Uso:
    python3 scripts/refresh_factor_k.py            # dry-run: muestra qué cambiaría
    python3 scripts/refresh_factor_k.py --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update  # noqa: E402

from auditoria import rutas_fixtures  # noqa: E402
from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from models import MatchCoach  # noqa: E402
from scraping.competitions import get_competition  # noqa: E402
from scraping.pipeline import infer_factor_k  # noqa: E402

logger = logging.getLogger("refresh_factor_k")


def k_por_partido(data_dir: Path) -> dict[int, int]:
    """`match_id -> K` calculado desde la ronda del fixture cacheado."""
    calculado: dict[int, int] = {}
    for codigo, _, ruta in rutas_fixtures(data_dir):
        try:
            config = get_competition(codigo)
        except KeyError:
            continue
        with open(ruta, encoding="utf-8") as archivo:
            for item in json.load(archivo):
                match_id = item.get("match_id")
                if match_id is None:
                    continue
                calculado[int(match_id)] = infer_factor_k(config, item.get("matchday"))
    return calculado


def plan_de_cambios(session, calculado: dict[int, int]) -> list[tuple[int, int, int]]:
    """`[(match_id, k_actual, k_nuevo)]` de los partidos que cambian."""
    filas = session.execute(
        select(MatchCoach.transfermarkt_match_id, MatchCoach.factor_k).where(
            MatchCoach.transfermarkt_match_id.is_not(None)
        )
    ).all()
    cambios = []
    for match_id, actual in filas:
        nuevo = calculado.get(int(match_id))
        if nuevo is None or int(actual) == nuevo:
            continue
        cambios.append((int(match_id), int(actual), nuevo))
    return cambios


def aplicar(session, cambios) -> int:
    for match_id, _, nuevo in cambios:
        session.execute(
            update(MatchCoach)
            .where(MatchCoach.transfermarkt_match_id == match_id)
            .values(factor_k=nuevo)
        )
    session.commit()
    return len(cambios)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recalcula factor_k desde el fixture.")
    parser.add_argument("--apply", action="store_true", help="Escribir los cambios.")
    parser.add_argument("--top", type=int, default=8, help="Ejemplos a mostrar (default 8).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    calculado = k_por_partido(settings.data_dir)
    print(f"partidos con ronda en el caché: {len(calculado)}")

    session = create_session()
    try:
        cambios = plan_de_cambios(session, calculado)
        print(f"partidos a recategorizar: {len(cambios)}")
        transiciones = Counter((actual, nuevo) for _, actual, nuevo in cambios)
        for (actual, nuevo), cantidad in sorted(transiciones.items()):
            print(f"  K {actual} -> {nuevo}: {cantidad}")
        for match_id, actual, nuevo in cambios[: args.top]:
            print(f"  {match_id}: {actual} -> {nuevo}")

        if args.apply:
            print(f"aplicados: {aplicar(session, cambios)}")
            print("Ahora: python3 scraper_transfermarkt.py recompute && python3 scripts/validate_elo.py")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
