"""Genera el "Duelo de Pizarras": infografía cara a cara entre dos DTs.

Uso:
    python scripts/duelo_pizarras.py --dt-a 12 --dt-b 34
    python scripts/duelo_pizarras.py --dt-a "Gallardo" --dt-b "Costas"
    python scripts/duelo_pizarras.py --dt-a 12 --dt-b 34 --output duelo.png
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from duel import compute_duel, resolve_coach  # noqa: E402
from visualization import render_duel  # noqa: E402

logger = logging.getLogger(__name__)


def _slug(text: str) -> str:
    return (
        text.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
        .replace(" ", "_")
    )


def _print_duel(duel) -> None:
    print("=" * 60)
    print("DUELO DE PIZARRAS")
    print("=" * 60)
    for etiqueta, side in (("A", duel.a), ("B", duel.b)):
        print(
            f"  [{etiqueta}] {side.nombre:<28} {side.club or '':<28}\n"
            f"      ELO {side.elo_actual:.0f} | PJ {side.partidos} "
            f"| {side.victorias}-{side.empates}-{side.derrotas} "
            f"| GF {side.goles_favor} GC {side.goles_contra} "
            f"| PPP {side.puntos_por_partido} | forma {'-'.join(side.forma)}"
        )
    print("-" * 60)
    print(
        f"Enfrentamientos directos: {duel.enfrentamientos} "
        f"({duel.a.apellido} {duel.victorias_a} - "
        f"{duel.empates} - {duel.victorias_b} {duel.b.apellido})"
    )
    print("=" * 60)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Genera el Duelo de Pizarras (PNG).")
    parser.add_argument("--dt-a", required=True, help="DT A: id numérico o parte del nombre.")
    parser.add_argument("--dt-b", required=True, help="DT B: id numérico o parte del nombre.")
    parser.add_argument("--forma", type=int, default=5, help="Partidos de forma reciente (default 5).")
    parser.add_argument("--output", help="Ruta del PNG. Por defecto data/output/duelo_<a>_<b>.png.")
    parser.add_argument("--title", default="DUELO DE PIZARRAS", help="Título de la infografía.")
    parser.add_argument("--subtitle", default=None, help="Subtítulo (por defecto, historial hasta la fecha).")
    parser.add_argument("--handle", default="@AEP_Analitica", help="Usuario/marca en el pie.")
    args = parser.parse_args(argv)

    session = create_session()
    try:
        coach_a = resolve_coach(session, args.dt_a)
        coach_b = resolve_coach(session, args.dt_b)
        duel = compute_duel(session, coach_a.dt_id, coach_b.dt_id, n_forma=args.forma)
    finally:
        session.close()

    _print_duel(duel)

    output = (
        Path(args.output)
        if args.output
        else settings.data_dir / "output"
        / f"duelo_{_slug(duel.a.nombre)}_{_slug(duel.b.nombre)}.png"
    )
    path = render_duel(
        duel,
        output,
        title=args.title,
        subtitle=args.subtitle,
        handle=args.handle,
        n_forma=args.forma,
    )
    print(f"[duelo_pizarras] Infografía guardada en: {path}")


if __name__ == "__main__":
    main()