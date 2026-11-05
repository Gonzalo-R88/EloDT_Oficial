"""Genera el "Power Ranking de la Fecha" (subidas/caídas de ELO) como PNG.

Uso:
    python scripts/power_ranking.py
    python scripts/power_ranking.py --dias 7 --top 5
    python scripts/power_ranking.py --competition AR1N --hasta 2024-12-15
    python scripts/power_ranking.py --desde 2024-12-01 --hasta 2024-12-31 --output ranking.png
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from ranking import compute_power_ranking, resolve_competition_id  # noqa: E402
from visualization import render_power_ranking  # noqa: E402

logger = logging.getLogger(__name__)


def _print_ranking(ranking) -> None:
    print("=" * 60)
    print(f"POWER RANKING  ({ranking.desde} -> {ranking.hasta})")
    print(f"Partidos analizados: {ranking.total_partidos}")
    print("-" * 60)
    print("SUBIERON")
    for i, entry in enumerate(ranking.subidas, 1):
        club = f" · {entry.club}" if entry.club else ""
        print(f"  {i}. {entry.nombre:<30}{club:<22} {entry.delta:+.2f}  (ELO {entry.elo_actual:.0f})")
    print("CAYERON")
    for i, entry in enumerate(ranking.bajadas, 1):
        club = f" · {entry.club}" if entry.club else ""
        print(f"  {i}. {entry.nombre:<30}{club:<22} {entry.delta:+.2f}  (ELO {entry.elo_actual:.0f})")
    print("=" * 60)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Genera el Power Ranking de la Fecha (PNG).")
    parser.add_argument("--desde", help="Fecha inicial (YYYY-MM-DD). Por defecto, retrocede --dias.")
    parser.add_argument("--hasta", help="Fecha final (YYYY-MM-DD). Por defecto, el último partido cargado.")
    parser.add_argument("--dias", type=int, default=7, help="Tamaño de la ventana en días (default 7).")
    parser.add_argument("--top", type=int, default=5, help="Cantidad de DTs por columna (default 5).")
    parser.add_argument("--competition", help="Filtrar por código de competencia (ej. AR1N).")
    parser.add_argument("--output", help="Ruta del PNG. Por defecto data/output/power_ranking_<hasta>.png.")
    parser.add_argument("--title", default="POWER RANKING DE LA FECHA", help="Título de la infografía.")
    parser.add_argument("--handle", default="@EloDT_oficial", help="Usuario/marca en el pie.")
    args = parser.parse_args(argv)

    session = create_session()
    try:
        competencia_id = (
            resolve_competition_id(session, args.competition) if args.competition else None
        )
        ranking = compute_power_ranking(
            session,
            desde=args.desde,
            hasta=args.hasta,
            dias=args.dias,
            top=args.top,
            competencia_id=competencia_id,
        )
    finally:
        session.close()

    _print_ranking(ranking)

    output = (
        Path(args.output)
        if args.output
        else settings.data_dir / "output" / f"power_ranking_{ranking.hasta.isoformat()}.png"
    )
    path = render_power_ranking(
        ranking,
        output,
        title=args.title,
        handle=args.handle,
        top=args.top,
    )
    print(f"[power_ranking] Infografía guardada en: {path}")


if __name__ == "__main__":
    main()