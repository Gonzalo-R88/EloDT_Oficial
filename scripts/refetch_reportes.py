"""Re-descarga reportes cacheados para corregir datos que el parser no pudo extraer.

Uso principal: partidos descartados por `sin_dt` (falta el DT de algún lado). Muchas
de esas páginas viejas sí tienen los entrenadores, pero en otro layout (`div.box` con
la etiqueta "Manager"); `scraping.parser._parse_coaches` ya lo contempla, así que basta
con volver a pedir la página para que el dato quede en el caché.

Después de correrlo hay que recargar y recalcular:
    python3 scraper_transfermarkt.py load --from AAAA --to AAAA ...
    python3 scraper_transfermarkt.py recompute
    python3 scripts/validate_elo.py

Uso:
    python3 scripts/refetch_reportes.py --sin-dt                    # sólo cuenta
    python3 scripts/refetch_reportes.py --sin-dt --desde 2015 --hasta 2026 --limit 20 --apply
    python3 scripts/refetch_reportes.py --sin-dt --desde 2015 --hasta 2026 --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from auditoria import rutas_fixtures  # noqa: E402
from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from models import MatchCoach  # noqa: E402
from scraping.parser import parse_match_report  # noqa: E402
from scraping.pipeline import build_match_url  # noqa: E402
from scraping.storage import RawStore  # noqa: E402

logger = logging.getLogger("refetch_reportes")


def rutas_objetivo(
    data_dir: Path,
    desde: int | None,
    hasta: int | None,
    solo_sin_dt: bool,
    solo_sin_fecha: bool,
    codigos: set[str] | None = None,
) -> list[tuple[str, int, int]]:
    """`(codigo, temporada, match_id)` de los reportes a re-descargar."""
    objetivos: list[tuple[str, int, int]] = []
    for ruta in sorted(Path(data_dir).glob("raw/*/*/matches/*.json")):
        codigo = ruta.parent.parent.parent.name
        try:
            temporada = int(ruta.parent.parent.name)
            match_id = int(ruta.stem)
        except ValueError:
            continue
        if codigos is not None and codigo.upper() not in codigos:
            continue
        if desde is not None and temporada < desde:
            continue
        if hasta is not None and temporada > hasta:
            continue
        try:
            with open(ruta, encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except (OSError, json.JSONDecodeError):
            continue
        if solo_sin_dt and datos.get("home_coach_tm_id") and datos.get("away_coach_tm_id"):
            continue
        if solo_sin_fecha and datos.get("fecha"):
            continue
        objetivos.append((codigo, temporada, match_id))
    return objetivos


def listar_faltantes(data_dir: Path, desde: int, hasta: int, destino: Path) -> int:
    """Escribe los fixtures cacheados que NO están en la base (candidatos a rescrape)."""
    desde_db = create_session()
    try:
        en_db = {
            int(valor)
            for valor in desde_db.execute(
                select(MatchCoach.transfermarkt_match_id).where(
                    MatchCoach.transfermarkt_match_id.is_not(None)
                )
            ).scalars()
        }
    finally:
        desde_db.close()

    faltantes: list[list] = []
    for codigo, temporada, ruta in rutas_fixtures(data_dir):
        with open(ruta, encoding="utf-8") as archivo:
            for item in json.load(archivo):
                fecha = (item.get("date") or "")[:4]
                if not fecha.isdigit():
                    continue
                anio = int(fecha)
                if anio < desde or anio > hasta:
                    continue
                if item.get("match_id") is None or int(item["match_id"]) in en_db:
                    continue
                faltantes.append([codigo, temporada, int(item["match_id"])])

    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as archivo:
        json.dump(faltantes, archivo)
    print(f"faltantes {desde}-{hasta}: {len(faltantes)} -> {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-descarga reportes cacheados.")
    parser.add_argument("--desde", type=int, default=None, help="Temporada mínima (año).")
    parser.add_argument("--hasta", type=int, default=None, help="Temporada máxima (año).")
    parser.add_argument("--sin-dt", action="store_true", help="Sólo reportes sin algún DT.")
    parser.add_argument("--sin-fecha", action="store_true", help="Sólo reportes sin fecha.")
    parser.add_argument("--codes", default=None,
                        help="Competencias separadas por coma (default: todas).")
    parser.add_argument("--listar-faltantes", type=Path, default=None,
                        help="Escribe en ese JSON los fixtures cacheados que NO están en la base y sale.")
    parser.add_argument("--ids-file", type=Path, default=None,
                        help="JSON con [[codigo, temporada, match_id], ...] (evita escanear el caché).")
    parser.add_argument("--shard", default=None, metavar="I/N",
                        help="Procesar sólo la parte I de N (para correr varios workers en paralelo).")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de reportes a procesar.")
    parser.add_argument("--apply", action="store_true", help="Escribir el caché.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    data_dir = settings.data_dir
    store = RawStore(data_dir)
    if args.listar_faltantes is not None:
        return listar_faltantes(
            data_dir,
            args.desde if args.desde is not None else 2000,
            args.hasta if args.hasta is not None else 2100,
            args.listar_faltantes,
        )

    if args.ids_file is not None:
        with open(args.ids_file, encoding="utf-8") as archivo:
            objetivos = [tuple(item) for item in json.load(archivo)]
    else:
        codigos = {c.strip().upper() for c in args.codes.split(",")} if args.codes else None
        objetivos = rutas_objetivo(
            data_dir, args.desde, args.hasta, args.sin_dt, args.sin_fecha, codigos
        )

    if args.shard:
        indice, total = (int(parte) for parte in args.shard.split("/"))
        objetivos = objetivos[indice - 1 :: total]

    if args.limit is not None:
        objetivos = objetivos[: args.limit]

    print(f"reportes objetivo: {len(objetivos)}")
    if not args.apply:
        por_anio: dict[int, int] = {}
        for _, temporada, _ in objetivos:
            por_anio[temporada] = por_anio.get(temporada, 0) + 1
        for temporada in sorted(por_anio):
            print(f"  {temporada}: {por_anio[temporada]}")
        print("(dry-run: usar --apply para descargarlos)")
        return 0

    from scraper_transfermarkt import build_client  # import tardío: arma el cliente WAF

    client = build_client()
    client.warm_up()

    recuperados = 0
    for posicion, (codigo, temporada, match_id) in enumerate(objetivos, start=1):
        try:
            report = parse_match_report(client.get(build_match_url(match_id)), match_id)
        except Exception as error:  # noqa: BLE001 - un fallo no corta el lote
            logger.error("Partido %s: %s", match_id, error)
            continue
        store.write_match(codigo, temporada, match_id, asdict(report))
        if report.home_coach_tm_id and report.away_coach_tm_id:
            recuperados += 1
        if posicion % 25 == 0:
            logger.info("[%s/%s] recuperados hasta ahora: %s", posicion, len(objetivos), recuperados)

    print(f"re-descargados: {len(objetivos)} | con ambos DTs: {recuperados}")
    print("Ahora: load de esas temporadas + recompute + validate_elo.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
