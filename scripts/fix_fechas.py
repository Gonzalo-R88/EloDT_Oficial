"""Corrige fechas de partidos usando la fecha del reporte en lugar de la del fixture.

Motivo: en el fixture (`gesamtspielplan`) Transfermarkt imprime la fecha **una sola
vez por bloque** y deja vacías las filas siguientes, así que las jornadas de un
mismo bloque heredan la fecha de la primera. Eso produjo 152 casos de un DT con
más de un partido el mismo día (`data/audit/conflictos_fecha.json`) y fechas
corridas hasta semanas.

La página del partido sí trae la fecha exacta (`/datum/AAAA-MM-DD`), y
`scraping.parser.parse_report_date` la extrae. Este script:

1. `--fetch`  re-descarga solo los reportes afectados y les agrega `fecha` al caché.
2. (sin flags) muestra qué fechas cambiaría respecto de la base.
3. `--apply`  actualiza `partidos_dt.fecha`. Después hay que correr `recompute`.

Uso:
    python3 scripts/fix_fechas.py --fetch --limit 5     # prueba
    python3 scripts/fix_fechas.py --fetch --bloques     # re-descarga (VPN, ~1 h)
    python3 scripts/fix_fechas.py                       # dry-run
    python3 scripts/fix_fechas.py --apply
    python3 scraper_transfermarkt.py recompute && python3 scripts/validate_elo.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from models import MatchCoach  # noqa: E402
from scraping.dto import MatchReport  # noqa: E402
from scraping.parser import parse_match_report  # noqa: E402
from scraping.pipeline import build_match_url  # noqa: E402
from scraping.storage import RawStore  # noqa: E402

logger = logging.getLogger("fix_fechas")


def mapa_fixtures(data_dir: Path) -> dict[int, dict]:
    """`match_id -> {codigo, temporada, fecha, matchday}` a partir del caché de fixtures."""
    mapa: dict[int, dict] = {}
    for ruta in sorted(Path(data_dir).glob("raw/*/*/fixtures.json")):
        codigo = ruta.parent.parent.name
        temporada = int(ruta.parent.name)
        with open(ruta, encoding="utf-8") as archivo:
            for item in json.load(archivo):
                if item.get("match_id") is None:
                    continue
                mapa[int(item["match_id"])] = {
                    "codigo": codigo,
                    "temporada": temporada,
                    "fecha": item.get("date"),
                    "matchday": item.get("matchday"),
                }
    return mapa


def ids_objetivo(conflictos: list[dict], mapa: dict[int, dict], bloques: bool) -> list[int]:
    """Partidos a corregir: los de los conflictos o todos los de sus bloques (comp+temporada+fecha)."""
    ids = {m for conflicto in conflictos for m in conflicto["match_ids"]}
    ids = {i for i in ids if i in mapa}
    if not bloques:
        return sorted(ids)
    claves = {(mapa[i]["codigo"], mapa[i]["temporada"], mapa[i]["fecha"]) for i in ids}
    return sorted(
        match_id for match_id, info in mapa.items()
        if (info["codigo"], info["temporada"], info["fecha"]) in claves
    )


def descargar(ids: list[int], mapa: dict[int, dict], store: RawStore, limit: int | None) -> int:
    """Re-descarga los reportes que todavía no tienen la fecha en el caché."""
    from scraper_transfermarkt import build_client  # import tardío: arma el cliente WAF

    pendientes = []
    for match_id in ids:
        info = mapa[match_id]
        if not store.has_match(info["codigo"], info["temporada"], match_id):
            continue
        if store.read_match(info["codigo"], info["temporada"], match_id).get("fecha"):
            continue
        pendientes.append(match_id)
    if limit is not None:
        pendientes = pendientes[:limit]

    logger.info("Reportes a re-descargar: %s de %s", len(pendientes), len(ids))
    if not pendientes:
        return 0

    client = build_client()
    client.warm_up()
    hechos = 0
    for posicion, match_id in enumerate(pendientes, start=1):
        info = mapa[match_id]
        try:
            html = client.get(build_match_url(match_id), referer=f"https://{settings.transfermarkt_domain}/")
            report = parse_match_report(html, match_id)
        except Exception as error:  # noqa: BLE001 - un fallo no debe cortar el lote
            logger.error("Partido %s: %s", match_id, error)
            continue
        if not report.fecha:
            logger.warning("Partido %s sin fecha en el reporte; se deja igual.", match_id)
            continue
        store.write_match(info["codigo"], info["temporada"], match_id, asdict(report))
        hechos += 1
        logger.info("[%s/%s] %s -> %s", posicion, len(pendientes), match_id, report.fecha)
    return hechos


def plan_de_cambios(session, ids: list[int]) -> list[tuple[int, str, str | None, str]]:
    """`[(match_id, competencia, fecha_en_db, fecha_nueva)]` de los que hay que corregir."""
    cambios = []
    for match_id in ids:
        fila = session.execute(
            select(MatchCoach.fecha).where(MatchCoach.transfermarkt_match_id == match_id)
        ).first()
        if fila is None:
            continue
        nueva = _fecha_en_cache(match_id)
        if nueva is None:
            continue
        actual = fila[0].isoformat()
        if nueva != actual:
            cambios.append((match_id, "", actual, nueva))
    return cambios


_CACHE_REPORTES: dict[int, str | None] = {}


def _fecha_en_cache(match_id: int) -> str | None:
    return _CACHE_REPORTES.get(match_id)


def cargar_fechas_de_cache(ids: list[int], mapa: dict[int, dict], store: RawStore) -> None:
    """Completa `_CACHE_REPORTES` leyendo los reportes cacheados."""
    _CACHE_REPORTES.clear()
    for match_id in ids:
        info = mapa.get(match_id)
        if not info or not store.has_match(info["codigo"], info["temporada"], match_id):
            continue
        _CACHE_REPORTES[match_id] = store.read_match(
            info["codigo"], info["temporada"], match_id
        ).get("fecha")


def aplicar(session, cambios: list[tuple[int, str, str | None, str]]) -> tuple[int, int]:
    """Actualiza las fechas. Devuelve `(aplicados, fallidos)`."""
    aplicados = fallidos = 0
    for match_id, _, actual, nueva in cambios:
        try:
            session.execute(
                MatchCoach.__table__.update()
                .where(MatchCoach.transfermarkt_match_id == match_id)
                .values(fecha=date.fromisoformat(nueva))
            )
            session.commit()
            aplicados += 1
        except Exception as error:  # noqa: BLE001 - se informa y se sigue
            session.rollback()
            fallidos += 1
            logger.error("Partido %s (%s -> %s): %s", match_id, actual, nueva, error)
    return aplicados, fallidos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Corrige fechas usando la fecha del reporte.")
    parser.add_argument("--conflictos", type=Path,
                        default=settings.data_dir / "audit" / "conflictos_fecha.json",
                        help="Lista de conflictos (default: data/audit/conflictos_fecha.json).")
    parser.add_argument("--match-ids", default=None,
                        help="IDs separados por coma, en lugar de la lista de conflictos.")
    parser.add_argument("--bloques", action="store_true",
                        help="Incluir todos los partidos del bloque (misma comp/temporada/fecha heredada).")
    parser.add_argument("--fetch", action="store_true", help="Re-descargar los reportes faltantes.")
    parser.add_argument("--apply", action="store_true", help="Escribir los cambios en la base.")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de partidos a procesar.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    data_dir = settings.data_dir
    store = RawStore(data_dir)
    mapa = mapa_fixtures(data_dir)

    if args.match_ids:
        ids = [int(x) for x in args.match_ids.split(",") if x.strip()]
    else:
        with open(args.conflictos, encoding="utf-8") as archivo:
            conflictos = json.load(archivo)
        ids = ids_objetivo(conflictos, mapa, bloques=args.bloques)
    if args.limit is not None:
        ids = ids[: args.limit]

    print(f"partidos objetivo: {len(ids)}")

    if args.fetch:
        hechos = descargar(ids, mapa, store, args.limit)
        print(f"reportes actualizados con fecha: {hechos}")
        return 0

    cargar_fechas_de_cache(ids, mapa, store)
    session = create_session()
    try:
        cambios = plan_de_cambios(session, ids)
        sin_fecha = sum(1 for i in ids if _fecha_en_cache(i) is None)
        print(f"con fecha en caché: {len(ids) - sin_fecha} | sin fecha: {sin_fecha}")
        print(f"fechas a cambiar: {len(cambios)}")
        for match_id, _, actual, nueva in cambios[:20]:
            print(f"  {match_id}: {actual} -> {nueva}")
        if len(cambios) > 20:
            print(f"  ... y {len(cambios) - 20} más")

        if args.apply:
            aplicados, fallidos = aplicar(session, cambios)
            print(f"aplicados: {aplicados} | fallidos: {fallidos}")
            print("Ahora: python3 scraper_transfermarkt.py recompute && python3 scripts/validate_elo.py")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
