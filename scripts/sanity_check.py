"""Control de sanidad del ELO con entrenadores conocidos.

Imprime el top de DTs en actividad (jugaron en el último año) con 100+ partidos y
verifica que una lista de referencia esté arriba. Es un control humano contra el
"¿esto tiene sentido?" que ninguna métrica de backtest reemplaza.

La lista de referencia vive en `data/sanity_coaches.json` (apellidos o nombres, se
buscan como subcadena).

Uso:
    python3 scripts/sanity_check.py
    python3 scripts/sanity_check.py --top 25 --min-partidos 100 --maximo 30
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from config import settings  # noqa: E402
from db import create_session  # noqa: E402

LISTA_POR_DEFECTO = [
    "Guardiola", "Ancelotti", "Klopp", "Simeone", "Mourinho",
    "Luis Enrique", "Arteta", "Inzaghi", "Flick", "Gallardo",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanidad del ranking con DTs conocidos.")
    parser.add_argument("--top", type=int, default=25, help="Cuántos listar (default 25).")
    parser.add_argument("--min-partidos", type=int, default=100)
    parser.add_argument("--maximo", type=int, default=30,
                        help="Puesto máximo aceptado para la lista de referencia (default 30).")
    parser.add_argument("--lista", type=Path, default=None,
                        help="JSON con la lista de referencia (default: data/sanity_coaches.json).")
    args = parser.parse_args(argv)

    if args.lista and args.lista.exists():
        lista = json.loads(args.lista.read_text(encoding="utf-8"))
    else:
        lista = LISTA_POR_DEFECTO

    session = create_session()
    try:
        filas = session.execute(
            text("""
                with part as (
                    select dt_local_id dt, fecha from partidos_dt
                    union all
                    select dt_visita_id, fecha from partidos_dt
                ), pj as (select dt, count(*) c, max(fecha) ultimo from part group by dt)
                select e.dt_id, e.nombre || ' ' || e.apellido, round(e.elo_actual, 1), pj.c
                from entrenadores e join pj on pj.dt = e.dt_id
                where pj.c >= :min_pj and pj.ultimo >= :desde
                order by e.elo_actual desc
            """),
            {
                "min_pj": args.min_partidos,
                "desde": date.today() - timedelta(days=365),
            },
        ).all()
    finally:
        session.close()

    if not filas:
        print("No hay DTs que cumplan el filtro.")
        return 1

    print(f"Top {args.top} de DTs en actividad con {args.min_partidos}+ partidos:\n")
    for puesto, (_, nombre, elo, pj) in enumerate(filas[: args.top], start=1):
        print(f"  {puesto:2}. {elo:7.1f}  {nombre[:32]:32} {pj:4} PJ")

    puestos = {nombre: puesto for puesto, (_, nombre, _, _) in enumerate(filas, start=1)}
    encontrados = []
    for referencia in lista:
        candidatos = [
            (puesto, nombre) for nombre, puesto in puestos.items()
            if referencia.lower() in nombre.lower()
        ]
        if candidatos:
            puesto, nombre = min(candidatos)
            encontrados.append((referencia, nombre, puesto))

    print(f"\nLista de referencia ({len(lista)}):")
    for referencia in lista:
        hallado = next((e for e in encontrados if e[0] == referencia), None)
        if hallado is None:
            print(f"  ✗ {referencia:14} no aparece (¿inactivo o sin 100 PJ?)")
        else:
            marca = "✓" if hallado[2] <= args.maximo else "✗"
            print(f"  {marca} {referencia:14} puesto {hallado[2]:3}  ({hallado[1]})")

    dentro = [e for e in encontrados if e[2] <= args.maximo]
    print(f"\n{dentro.__len__()} de {len(lista)} dentro del top {args.maximo} "
          f"(se pide al menos 7 de 10).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
