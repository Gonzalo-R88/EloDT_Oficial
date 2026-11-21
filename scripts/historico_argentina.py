"""Carga el histórico de la liga argentina 2012-2014 (T0.11, etapa A).

Cinco pasos, todos reanudables:

    python3 scripts/historico_argentina.py fetch     # resultados (sin VPN)
    python3 scripts/historico_argentina.py etapas    # técnicos por club (VPN)
    python3 scripts/historico_argentina.py build     # resuelve DT por partido
    python3 scripts/historico_argentina.py load      # carga + recompute
    python3 scripts/historico_argentina.py check     # invariantes y resumen

Las fuentes de resultados son football-data.co.uk (Primera 2012-2014) y RSSSF
(B Nacional 2013/14). El técnico de cada partido sale del historial de etapas de
cada club en Transfermarkt. Nada se inventa: si un partido queda sin técnico, se
informa y no se carga.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import historico  # noqa: E402
from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from models import Coach  # noqa: E402

URL_FOOTBALL_DATA = "https://www.football-data.co.uk/new/ARG.csv"
URL_RSSSF = "https://www.rsssf.org/tablesa/arg2014.html"
URL_ETAPA = "https://www.transfermarkt.com/x/mitarbeiterhistorie/verein/{club}"

CARPETA = settings.data_dir / "historico"


def _ruta(*partes: str) -> Path:
    destino = CARPETA.joinpath(*partes)
    destino.parent.mkdir(parents=True, exist_ok=True)
    return destino


def _escribir_json(ruta: Path, datos) -> None:
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
def cmd_fetch(refresh: bool = False) -> int:
    """Descarga las dos fuentes de resultados. No necesita VPN."""
    from scraping.client import TransfermarktClient

    cliente = TransfermarktClient(delay_min=1.0, delay_max=2.0, waf_solver=None)

    pendientes = [
        (URL_FOOTBALL_DATA, _ruta("ARG.csv")),
        (URL_RSSSF, _ruta("rsssf", "arg2014.html")),
    ]
    for url, destino in pendientes:
        if destino.exists() and not refresh:
            print(f"  ya está: {destino.relative_to(CARPETA)}")
            continue
        print(f"  bajando {url}")
        texto = cliente.get(url, referer="https://www.rsssf.org/" if "rsssf" in url else None)
        destino.write_text(texto, encoding="utf-8")
        print(f"  guardado: {destino.relative_to(CARPETA)} ({len(texto)} bytes)")
    return 0


# ---------------------------------------------------------------------------
# etapas
# ---------------------------------------------------------------------------
def _clubes_necesarios() -> list[int]:
    """Clubes de los que hace falta el historial de técnicos (los de ambas fuentes)."""
    try:
        partidos = _leer_partidos_crudos()
    except FileNotFoundError:
        return sorted(set(historico.CLUBES.values()))
    return sorted(historico.equipos(partidos))


def cmd_etapas(refresh: bool = False, limit: int | None = None) -> int:
    """Baja el historial de entrenadores de cada club (necesita VPN)."""
    from scraper_transfermarkt import build_client

    clubes = _clubes_necesarios()
    if limit:
        clubes = clubes[:limit]
    print(f"clubes a consultar: {len(clubes)}")

    cliente = build_client()
    cliente.warm_up()

    faltan = []
    for numero, club in enumerate(clubes, start=1):
        destino = _ruta("etapas", f"{club}.html")
        if destino.exists() and not refresh:
            continue
        faltan.append((numero, club, destino))

    print(f"por bajar: {len(faltan)} (el resto ya está en caché)")
    for numero, club, destino in faltan:
        html = cliente.get(URL_ETAPA.format(club=club))
        destino.write_text(html, encoding="utf-8")
        print(f"  [{numero}/{len(clubes)}] club {club} -> {len(html)} bytes")
    return 0


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def _leer_partidos_crudos() -> list[historico.PartidoHistorico]:
    """Parsea las fuentes guardadas y devuelve los partidos de liga."""
    ruta_csv = _ruta("ARG.csv")
    ruta_rsssf = _ruta("rsssf", "arg2014.html")
    if not ruta_csv.exists() or not ruta_rsssf.exists():
        raise FileNotFoundError("Faltan las fuentes: corré `fetch` primero.")

    primera = historico.parse_football_data(ruta_csv.read_text(encoding="utf-8"))
    segunda = historico.parse_bnacional(ruta_rsssf.read_text(encoding="utf-8"), 2013)
    return historico.limpiar(primera + segunda)


def _leer_etapas(clubes: list[int], obligatorio: bool = True) -> list[historico.Etapa]:
    etapas: list[historico.Etapa] = []
    faltan: list[int] = []
    for club in clubes:
        ruta = _ruta("etapas", f"{club}.html")
        if not ruta.exists():
            faltan.append(club)
            continue
        etapas.extend(historico.parse_etapas(ruta.read_text(encoding="utf-8"), club))
    if faltan and obligatorio:
        raise FileNotFoundError(
            f"Falta el historial de {len(faltan)} clubes: {faltan[:10]}. Corré `etapas`."
        )
    return etapas


def cmd_build() -> int:
    """Resuelve el DT de cada partido y escribe el plan de carga."""
    partidos = _leer_partidos_crudos()
    problemas = historico.validar_ligas(partidos)
    for problema in problemas:
        print(f"  AVISO: {problema}")

    clubes = sorted(historico.equipos(partidos))
    etapas = historico.etapas_por_club(_leer_etapas(clubes, obligatorio=False))
    asignacion = historico.asignar(partidos, etapas)

    print(f"partidos de liga: {len(partidos)}")
    print(f"con ambos DT:     {len(asignacion.partidos)}")
    print(f"sin DT:           {len(asignacion.sin_dt)}")

    if asignacion.sin_dt:
        por_club = Counter()
        for partido in asignacion.sin_dt:
            por_club[partido.local_tm_id] += 1
            por_club[partido.visita_tm_id] += 1
        print("clubes con partidos sin DT (top 10):")
        for club, cantidad in por_club.most_common(10):
            print(f"  club {club}: {cantidad}")

    plan = {
        "generado": date.today().isoformat(),
        "fuentes": {
            "ARG.csv": URL_FOOTBALL_DATA,
            "rsssf/arg2014.html": URL_RSSSF,
        },
        "liga": len(partidos),
        "con_dt": len(asignacion.partidos),
        "sin_dt": len(asignacion.sin_dt),
        "problemas": problemas + asignacion.problemas,
        "partidos": [
            {
                "fecha": p.fecha.isoformat(),
                "temporada": p.temporada,
                "competencia": p.competencia,
                "local_tm_id": p.local_tm_id,
                "visita_tm_id": p.visita_tm_id,
                "goles_local": p.goles_local,
                "goles_visita": p.goles_visita,
                "factor_k": p.factor_k,
                "dt_local_tm_id": p.dt_local_tm_id,
                "dt_local_nombre": p.dt_local_nombre,
                "dt_visita_tm_id": p.dt_visita_tm_id,
                "dt_visita_nombre": p.dt_visita_nombre,
            }
            for p in asignacion.partidos
        ],
        "sin_dt_detalle": [
            {
                "fecha": p.fecha.isoformat(),
                "temporada": p.temporada,
                "competencia": p.competencia,
                "local_tm_id": p.local_tm_id,
                "visita_tm_id": p.visita_tm_id,
            }
            for p in asignacion.sin_dt
        ],
    }
    ruta = _ruta("plan.json")
    _escribir_json(ruta, plan)
    print(f"plan escrito: {ruta}")

    # Resumen de coherencia por club y por temporada.
    por_temporada = Counter(
        (p.competencia, p.temporada) for p in asignacion.partidos
    )
    print("partidos asignados por temporada:")
    for (competencia, temporada), cantidad in sorted(por_temporada.items()):
        print(f"  {competencia:6} {temporada}/{temporada + 1}: {cantidad}")
    return 1 if asignacion.sin_dt else 0


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------
def cmd_load(aplicar_recompute: bool = True) -> int:
    """Carga los partidos a la base y recalcula el ELO desde cero."""
    ruta = _ruta("plan.json")
    if not ruta.exists():
        raise FileNotFoundError("Falta el plan: corré `build` primero.")
    plan = json.loads(ruta.read_text(encoding="utf-8"))

    from sqlalchemy import select

    from models import Club
    from scraping.competitions import get_competition
    from scraping.pipeline import ensure_club, ensure_coach, ensure_competition
    from services import recompute_all_elo, process_match_elo

    stats = defaultdict(int)
    session = create_session()
    try:
        existentes = {
            club.transfermarkt_id: club.nombre
            for club in session.execute(select(Club)).scalars()
            if club.transfermarkt_id is not None
        }
        # Nombre de respaldo si el club no estuviera en la base (no debería pasar).
        respaldo: dict[int, str] = {}
        for nombre, tm_id in historico.CLUBES.items():
            respaldo.setdefault(tm_id, nombre)

        competencias = {}
        clubes = {}
        entrenadores = {}
        nuevos_clubes = 0
        nuevos_dts = 0

        for fila in plan["partidos"]:
            config = get_competition(fila["competencia"])
            competencia = competencias.get(config.code)
            if competencia is None:
                competencia = ensure_competition(session, config)
                competencias[config.code] = competencia

            for tm_id in (fila["local_tm_id"], fila["visita_tm_id"]):
                if tm_id not in clubes:
                    if tm_id not in existentes:
                        nuevos_clubes += 1
                    clubes[tm_id] = ensure_club(
                        session,
                        tm_id,
                        existentes.get(tm_id) or respaldo.get(tm_id, f"Club {tm_id}"),
                        "Argentina",
                    )

            for clave in ("dt_local", "dt_visita"):
                tm_id = fila[f"{clave}_tm_id"]
                if tm_id not in entrenadores:
                    antes = session.execute(
                        select(Coach).where(Coach.transfermarkt_id == tm_id)
                    ).scalar_one_or_none()
                    if antes is None:
                        nuevos_dts += 1
                    entrenadores[tm_id] = ensure_coach(
                        session, tm_id, fila[f"{clave}_nombre"] or ""
                    )

            estado = process_match_elo(
                dt_local_id=entrenadores[fila["dt_local_tm_id"]].dt_id,
                dt_visita_id=entrenadores[fila["dt_visita_tm_id"]].dt_id,
                goles_local=fila["goles_local"],
                goles_visita=fila["goles_visita"],
                competencia_id=competencia.competencia_id,
                club_local_id=clubes[fila["local_tm_id"]].club_id,
                club_visita_id=clubes[fila["visita_tm_id"]].club_id,
                factor_k=fila["factor_k"],
                fecha=fila["fecha"],
                transfermarkt_match_id=None,
                session=session,
            )
            stats[estado] += 1

        if nuevos_clubes:
            print(f"AVISO: se crearon {nuevos_clubes} clubes que no estaban en la base.")
        print(f"entrenadores nuevos: {nuevos_dts}")
        session.commit()
        print(f"carga: {dict(stats)}")

        if aplicar_recompute:
            print("recalculando ELO desde cero...")
            total = recompute_all_elo(session=session)
            session.commit()
            print(f"partidos reproducidos: {total}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
def cmd_check() -> int:
    """Invariantes de la base: cobertura del hueco y suma cero."""
    from sqlalchemy import text

    session = create_session()
    try:
        print("=== partidos por competencia histórica ===")
        filas = session.execute(
            text(
                "select c.codigo, count(*), min(p.fecha), max(p.fecha), "
                "count(distinct p.dt_local_id) + 0 as dts "
                "from partidos_dt p join competencias c on c.competencia_id = p.competencia_id "
                "where c.codigo in ('ARGH','ARG2H') group by 1 order by 1"
            )
        ).all()
        for fila in filas:
            print(f"  {fila[0]:6} {fila[1]:5} partidos | {fila[2]} .. {fila[3]}")

        print("\n=== partidos argentinos de liga por año (2000-2026) ===")
        filas = session.execute(
            text(
                "select extract(year from p.fecha)::int a, count(*) from partidos_dt p "
                "join competencias c on c.competencia_id = p.competencia_id "
                "where c.pais = 'Argentina' and c.tipo = 'liga' group by 1 order by 1"
            )
        ).all()
        for fila in filas:
            print(f"  {fila[0]}: {fila[1]}")

        print("\n=== suma cero ===")
        malos = session.execute(
            text(
                "select count(*) from partidos_dt "
                "where abs((elo_local_nuevo - elo_local_previo) + (elo_visita_nuevo - elo_visita_previo)) > 0.02"
            )
        ).scalar()
        print(f"  partidos con suma != 0: {malos}")
        return 0 if malos == 0 else 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Histórico argentino 2012-2014.")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_fetch = sub.add_parser("fetch", help="Descarga las fuentes de resultados (sin VPN).")
    p_fetch.add_argument("--refresh", action="store_true")

    p_etapas = sub.add_parser("etapas", help="Baja el historial de DTs por club (VPN).")
    p_etapas.add_argument("--refresh", action="store_true")
    p_etapas.add_argument("--limit", type=int, default=None)

    sub.add_parser("build", help="Resuelve el DT de cada partido.")

    p_load = sub.add_parser("load", help="Carga a la base y recalcula.")
    p_load.add_argument("--sin-recompute", action="store_true")

    sub.add_parser("check", help="Invariantes y cobertura.")

    args = parser.parse_args(argv)
    if args.comando == "fetch":
        return cmd_fetch(refresh=args.refresh)
    if args.comando == "etapas":
        return cmd_etapas(refresh=args.refresh, limit=args.limit)
    if args.comando == "build":
        return cmd_build()
    if args.comando == "load":
        return cmd_load(aplicar_recompute=not args.sin_recompute)
    if args.comando == "check":
        return cmd_check()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())