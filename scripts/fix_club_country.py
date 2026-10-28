"""Corrige el país de los clubes creados desde competencias internacionales.

Problema: `pipeline.ensure_club` guardaba el país de la **competencia**. Para
Libertadores/Sudamericana/Recopa el país configurado es "Conmebol", así que un club
que aparece por primera vez en un torneo internacional quedaba con `pais="Conmebol"`
aunque juegue la liga argentina. Eso rompe cualquier filtro por país (por ejemplo
"DTs de Argentina").

Regla: el país del club es el de la **liga doméstica donde más partidos juega** (si no
tiene liga, el de la copa doméstica donde más juega). Los que solo aparecen en torneos
internacionales quedan como "desconocido" y se listan en el informe.

Es idempotente: al volver a correrlo no encuentra clubes para corregir (salvo nuevos
"desconocido" que hayan empezado a jugar una liga).

Uso:
    python3 scripts/fix_club_country.py            # dry-run: muestra qué cambiaría
    python3 scripts/fix_club_country.py --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, union_all  # noqa: E402

from db import create_session  # noqa: E402
from models import Club, Competition, MatchCoach  # noqa: E402
from scraping.pipeline import PAIS_DESCONOCIDO  # noqa: E402

logger = logging.getLogger("fix_club_country")

# Países a revisar: los que puso el pipeline desde una competencia internacional.
PAISES_A_REVISAR = ("Conmebol", PAIS_DESCONOCIDO)


def elegir_pais(por_liga: Counter[str], por_copa: Counter[str]) -> str:
    """País del club: la liga doméstica con más partidos; si no hay, la copa; si no, desconocido.

    En un empate gana el país alfabéticamente menor, para que el resultado sea estable.
    """
    for conteos in (por_liga, por_copa):
        if conteos:
            return sorted(conteos.items(), key=lambda par: (-par[1], par[0]))[0][0]
    return PAIS_DESCONOCIDO


def contar_partidos_por_pais(session) -> dict[int, tuple[Counter[str], Counter[str]]]:
    """`club_id -> (partidos por país en ligas, partidos por país en copas)` domésticas."""
    objetivos = select(Club.club_id).where(Club.pais.in_(PAISES_A_REVISAR)).subquery()
    local = select(
        MatchCoach.club_local_id.label("club_id"),
        MatchCoach.competencia_id.label("competencia_id"),
    ).join(objetivos, objetivos.c.club_id == MatchCoach.club_local_id)
    visita = select(
        MatchCoach.club_visita_id.label("club_id"),
        MatchCoach.competencia_id.label("competencia_id"),
    ).join(objetivos, objetivos.c.club_id == MatchCoach.club_visita_id)
    partidos = union_all(local, visita).subquery()

    filas = session.execute(
        select(partidos.c.club_id, Competition.pais, Competition.tipo, func.count())
        .join(Competition, Competition.competencia_id == partidos.c.competencia_id)
        .where(Competition.tipo.in_(("liga", "copa")))
        .where(Competition.pais.is_not(None))
        .group_by(partidos.c.club_id, Competition.pais, Competition.tipo)
    ).all()

    acumulado: dict[int, tuple[Counter[str], Counter[str]]] = defaultdict(
        lambda: (Counter(), Counter())
    )
    for club_id, pais, tipo, cantidad in filas:
        ligas, copas = acumulado[club_id]
        (ligas if tipo == "liga" else copas)[pais] += cantidad
    return dict(acumulado)


def plan_de_cambios(session) -> list[tuple[int, str, str | None, str, int]]:
    """`[(club_id, nombre, país_actual, país_nuevo, partidos_de_evidencia)]`."""
    actuales = {
        club_id: pais
        for club_id, pais in session.execute(
            select(Club.club_id, Club.pais).where(Club.pais.in_(PAISES_A_REVISAR))
        ).all()
    }
    conteos = contar_partidos_por_pais(session)
    cambios = []
    for club_id, pais_actual in sorted(actuales.items()):
        ligas, copas = conteos.get(club_id, (Counter(), Counter()))
        nuevo = elegir_pais(ligas, copas)
        if nuevo == pais_actual:
            continue
        nombre = session.execute(
            select(Club.nombre).where(Club.club_id == club_id)
        ).scalar_one()
        evidencia = (ligas + copas).most_common(1)[0][1] if (ligas or copas) else 0
        cambios.append((club_id, nombre, pais_actual, nuevo, evidencia))
    return cambios


def aplicar(session, cambios) -> int:
    """Escribe el país nuevo de cada club. Devuelve cuántos se actualizaron."""
    for club_id, _, _, nuevo, _ in cambios:
        session.execute(Club.__table__.update().where(Club.club_id == club_id).values(pais=nuevo))
    session.commit()
    return len(cambios)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Corrige el país de los clubes.")
    parser.add_argument("--apply", action="store_true", help="Escribir los cambios en la base.")
    parser.add_argument("--top", type=int, default=10, help="Cuántos ejemplos mostrar (default 10).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    session = create_session()
    try:
        cambios = plan_de_cambios(session)
        print(f"clubes a corregir: {len(cambios)}")
        por_pais = Counter(nuevo for *_, nuevo, _ in cambios)
        for pais, cantidad in por_pais.most_common():
            print(f"  -> {pais:12} {cantidad}")
        for club_id, nombre, actual, nuevo, evidencia in cambios[: args.top]:
            print(f"  {nombre[:34]:34} {actual} -> {nuevo} ({evidencia} partidos)")

        if args.apply:
            print(f"aplicados: {aplicar(session, cambios)}")

        sin_pais = session.execute(
            select(Club.nombre)
            .where(Club.pais == PAIS_DESCONOCIDO)
            .order_by(Club.nombre)
        ).scalars().all()
        print(f"clubes que quedan en '{PAIS_DESCONOCIDO}': {len(sin_pais)}")
        for nombre in sin_pais[: args.top]:
            print(f"  {nombre}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
