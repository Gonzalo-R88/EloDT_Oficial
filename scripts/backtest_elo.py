"""Backtest del ELO contra la base real (no escribe nada).

Carga los partidos en el mismo orden que `recompute_all_elo` y evalúa la capacidad
predictiva con distintos parámetros.

Uso:
    python3 scripts/backtest_elo.py                       # desde 2021, DTs con >=30 PJ
    python3 scripts/backtest_elo.py --desde 2016
    python3 scripts/backtest_elo.py --hfa 55 --min-pj 30
    python3 scripts/backtest_elo.py --mov amortiguado --calibracion
    python3 scripts/backtest_elo.py --sin-filtro           # todos los partidos
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backtest import PartidoBacktest, brier_constante, evaluar  # noqa: E402
from db import create_session  # noqa: E402
from elo import EloParams  # noqa: E402
from models import Competition, MatchCoach  # noqa: E402


def cargar_partidos(session) -> list[PartidoBacktest]:
    """Partidos ordenados como en `recompute_all_elo` (fecha, tm_id, partido_id)."""
    filas = session.execute(
        select(
            MatchCoach.transfermarkt_match_id,
            MatchCoach.fecha,
            MatchCoach.dt_local_id,
            MatchCoach.dt_visita_id,
            MatchCoach.goles_local,
            MatchCoach.goles_visita,
            MatchCoach.factor_k,
            Competition.coeficiente,
            Competition.nivel,
            Competition.codigo,
        )
        .join(Competition, Competition.competencia_id == MatchCoach.competencia_id)
        .order_by(
            MatchCoach.fecha.asc(),
            MatchCoach.transfermarkt_match_id.asc().nulls_first(),
            MatchCoach.partido_id.asc(),
        )
    ).all()
    return [
        PartidoBacktest(
            tm_match_id=tm_id, fecha=fecha, dt_local=local, dt_visita=visita,
            goles_local=goles_local, goles_visita=goles_visita,
            factor_k=factor_k, coeficiente=float(coeficiente),
            nivel=nivel or "", competencia=codigo or "",
        )
        for tm_id, fecha, local, visita, goles_local, goles_visita, factor_k, coeficiente, nivel, codigo in filas
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest del ELO.")
    parser.add_argument("--desde", type=int, default=2021, help="Año inicial (default 2021).")
    parser.add_argument("--hasta", type=int, default=None, help="Año final (default: último).")
    parser.add_argument("--min-pj", type=int, default=30,
                        help="Partidos previos mínimos de ambos DTs (default 30).")
    parser.add_argument("--sin-filtro", action="store_true", help="Evaluar todos los partidos.")
    parser.add_argument("--hfa", type=float, default=30.0, help="Ventaja de localía (default 30).")
    parser.add_argument("--mov", default="actual", choices=["actual", "cap", "amortiguado"])
    parser.add_argument("--cap", type=float, default=None, help="Tope del MOV (con --mov cap).")
    parser.add_argument("--calibracion", action="store_true",
                        help="Activar el período de calibración de los DTs nuevos.")
    parser.add_argument("--calibracion-mult", type=float, default=2.0)
    parser.add_argument("--tasa-empate", type=float, default=0.27,
                        help="Tasa de empates en E=0,5 para el log-loss (default 0.27).")
    args = parser.parse_args(argv)

    session = create_session()
    try:
        partidos = cargar_partidos(session)
    finally:
        session.close()

    if not partidos:
        print("No hay partidos cargados.")
        return 1

    params = EloParams(
        hfa=args.hfa,
        mov_mode=args.mov,
        mov_cap=args.cap,
        calibracion_n=30 if args.calibracion else 0,
        calibracion_mult=args.calibracion_mult,
    )
    desde = date(args.desde, 1, 1)
    hasta = date(args.hasta, 12, 31) if args.hasta else None
    min_pj = 0 if args.sin_filtro else args.min_pj

    metricas = evaluar(
        partidos, params=params, desde=desde, hasta=hasta,
        min_pj_previos=min_pj, aplicar_calibracion=args.calibracion,
        tasa_empate=args.tasa_empate,
    )
    if metricas.partidos == 0:
        print("Ningún partido cumple el filtro.")
        return 1

    print(f"Partidos evaluados: {metricas.partidos}")
    print(f"  período: {args.desde}-{args.hasta or 'fin'} | min PJ previos: {min_pj}")
    print(f"  parámetros: hfa={args.hfa} mov={args.mov} calibración={'sí' if args.calibracion else 'no'}")
    print()
    print(f"Brier del resultado esperado: {metricas.brier:.4f}   (constante: {brier_constante(partidos, desde):.4f})")
    print(f"Brier 1X2:                    {metricas.brier_1x2_medio:.4f}")
    print(f"Log-loss 1X2:                 {metricas.logloss:.4f}")
    print(f"Acierto del signo (mayor p):  {100 * metricas.exactitud_signo:.1f} %")
    print()
    print("Brier por año:", metricas.brier_por_anio())
    print("Brier por nivel:", {
        nivel: round(sum(v) / len(v), 4) for nivel, v in sorted(metricas.por_nivel.items()) if v
    })
    print()
    print("Calibración (E medio, tramo, n):")
    for esperado, limite, cantidad in metricas.resumen_calibracion():
        print(f"  E≈{esperado:.3f}  (tramo hasta {limite:.1f})  n={cantidad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
