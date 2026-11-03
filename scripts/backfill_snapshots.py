"""Reconstruye los snapshots semanales del ranking.

Cada snapshot es "cómo estaba el ELO el domingo de esa semana", con el puesto de cada
DT. Se usan para las flechas ▲▼ del Top 10 y para la suba a 90 días del "DT
revelación". Los snapshots son inmutables por versión del modelo.

Uso:
    python3 scripts/backfill_snapshots.py                    # últimas 52 semanas
    python3 scripts/backfill_snapshots.py --semanas 156      # ~3 años
    python3 scripts/backfill_snapshots.py --hasta 2026-11-01 --semanas 4
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import create_session  # noqa: E402
from elo import MODELO_VERSION  # noqa: E402
from snapshots import semana_fin, take_snapshot  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill de snapshots semanales.")
    parser.add_argument("--semanas", type=int, default=52, help="Cuántas semanas hacia atrás.")
    parser.add_argument("--hasta", type=date.fromisoformat, default=date.today(),
                        help="Fecha de referencia (default: hoy).")
    parser.add_argument("--modelo-version", default=MODELO_VERSION)
    args = parser.parse_args(argv)

    cierre = semana_fin(args.hasta)
    session = create_session()
    try:
        total = 0
        for atras in range(args.semanas - 1, -1, -1):
            domingo = cierre - timedelta(weeks=atras)
            resultado = take_snapshot(
                session, hasta=domingo, modelo_version=args.modelo_version
            )
            total += resultado.filas
            if atras % 13 == 0 or atras == 0:
                print(
                    f"  {resultado.semana_fin}  filas={resultado.filas:5}  "
                    f"publicables={resultado.publicables:4}"
                )
        session.commit()
    finally:
        session.close()

    print(f"listo: {args.semanas} snapshots, {total} filas en total ({args.modelo_version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
