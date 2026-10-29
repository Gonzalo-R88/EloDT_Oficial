"""Muestra qué DTs pueden publicarse y por qué el resto no.

Usa `publicacion.estado_publicacion` (mismas reglas que las imágenes y el pipeline).

Uso:
    python3 scripts/publicables.py                      # resumen general
    python3 scripts/publicables.py --pais Argentina     # top de DTs con club argentino
    python3 scripts/publicables.py --pais Argentina --top 10
    python3 scripts/publicables.py --dt 123             # detalle de un DT
    python3 scripts/publicables.py --motivos            # cuántos caen por cada motivo
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from db import create_session  # noqa: E402
from publicacion import estado_publicacion  # noqa: E402

_CONSULTA = """
with part as (
    select dt_local_id dt, club_local_id club, fecha from partidos_dt
    union all
    select dt_visita_id, club_visita_id, fecha from partidos_dt
),
pj as (select dt, count(*) c from part group by 1),
ult as (select distinct on (dt) dt, club from part order by dt, fecha desc)
select e.dt_id, e.nombre || ' ' || e.apellido, round(e.elo_actual, 1), pj.c, cl.nombre, cl.pais
from entrenadores e
join pj on pj.dt = e.dt_id
join ult on ult.dt = e.dt_id
join clubes cl on cl.club_id = ult.club
{where}
order by e.elo_actual desc
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qué DTs son publicables.")
    parser.add_argument("--pais", default=None, help="Filtrar por país del club actual.")
    parser.add_argument("--top", type=int, default=10, help="Cuántos listar (default 10).")
    parser.add_argument("--dt", type=int, default=None, help="Detalle de un DT por dt_id.")
    parser.add_argument("--motivos", action="store_true", help="Resumen de motivos de exclusión.")
    parser.add_argument("--sin-trabajo", action="store_true",
                        help="Listar DTs que dirigieron en el último año pero hoy no tienen club.")
    parser.add_argument("--hoy", type=date.fromisoformat, default=date.today(),
                        help="Fecha de referencia (default: hoy).")
    args = parser.parse_args(argv)

    session = create_session()
    try:
        estados = estado_publicacion(session, hasta=args.hoy)

        if args.dt is not None:
            estado = estados.get(args.dt)
            if estado is None:
                print(f"No hay partidos cargados para dt_id={args.dt}.")
                return 1
            nombre = session.execute(
                text("select nombre || ' ' || apellido from entrenadores where dt_id = :dt"),
                {"dt": args.dt},
            ).scalar_one_or_none()
            print(nombre or f"dt_id={args.dt}")
            print(f"  publicable: {estado.publicable} | etiqueta: {estado.etiqueta} | motivo: {estado.motivo}")
            print(f"  PJ: {estado.pj_total} | último partido: {estado.ultima_fecha}")
            print(f"  liga: {estado.liga} | cobertura: {estado.cobertura}")
            return 0

        publicables = {dt for dt, e in estados.items() if e.publicable}
        print(f"DTs evaluados: {len(estados)}")
        print(f"  publicables (DT actual de un club): {len(publicables)}")
        print(f"  provisorios (15-29 PJ): {sum(1 for e in estados.values() if e.publicable and e.etiqueta)}")
        print(f"  interinos (sólo subidas y bajadas): {sum(1 for e in estados.values() if e.interino)}")
        print(f"  sin trabajo (dirigieron en el último año): {sum(1 for e in estados.values() if e.sin_trabajo)}")

        if args.sin_trabajo:
            candidatos = [dt for dt, e in estados.items() if e.sin_trabajo]
            consulta = _CONSULTA.format(where="where e.dt_id = any(:ids)") + f" limit {args.top}"
            print(f"\nTop {args.top} sin trabajo (por ELO):")
            for _, nombre, elo, pj, club, pais in session.execute(
                text(consulta), {"ids": candidatos}
            ):
                print(f"  {elo:7.1f}  {nombre[:30]:30} {pj:4} PJ  último club: {club[:24]}")
            return 0

        if args.motivos:
            print("\nExcluidos por motivo:")
            for motivo, cantidad in Counter(
                e.motivo for e in estados.values() if e.motivo
            ).most_common():
                print(f"  {motivo:22} {cantidad}")

        if not publicables:
            print("\nNo hay DTs publicables.")
            return 0

        where = "where e.dt_id = any(:ids)"
        parametros: dict = {"ids": list(publicables)}
        if args.pais:
            where += " and cl.pais = :pais"
            parametros["pais"] = args.pais
        consulta = _CONSULTA.format(where=where) + f" limit {args.top}"

        print(f"\nTop {args.top}" + (f" ({args.pais})" if args.pais else "") + ":")
        con_etiqueta = False
        for dt_id, nombre, elo, pj, club, pais in session.execute(text(consulta), parametros):
            etiqueta = estados[dt_id].etiqueta
            con_etiqueta = con_etiqueta or bool(etiqueta)
            marca = " *provisorio" if etiqueta else ""
            print(f"  {elo:7.1f}  {nombre[:30]:30} {pj:4} PJ  {club[:26]:26} {pais or '':12}{marca}")
        if con_etiqueta:
            print("  (*) menos de 30 partidos: aparece con la etiqueta 'provisorio'.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
