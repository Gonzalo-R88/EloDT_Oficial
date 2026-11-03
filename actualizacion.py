"""Correcciones de resultados y política de recálculo del pipeline semanal.

Transfermarkt corrige marcadores con cierta frecuencia (partidos que terminan 3-2 y
figuran 2-2 hasta que se carga el acta). El pipeline compara lo que dice el caché con
lo que hay en la base para los partidos recientes y, si difieren, corrige los goles y
dispara un `recompute` completo.

La fuente de verdad del marcador es el **reporte** (`final_home_goals`), no el fixture:
el fixture se usa sólo si el reporte no lo trae.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from models import MatchCoach
from scraping.storage import RawStore

logger = logging.getLogger(__name__)

DIAS_REVISION = 21


@dataclass(frozen=True)
class Correccion:
    """Un partido cuya carga en la base no coincide con el caché."""

    tm_match_id: int
    fecha: date
    goles_db: tuple[int, int]
    goles_cache: tuple[int, int]
    origen: str  # "reporte" | "fixture"


def detectar_correcciones(
    session: Session,
    data_dir: Path,
    desde: date,
) -> list[Correccion]:
    """Compara los partidos cargados desde `desde` contra el caché."""
    from auditoria import rutas_fixtures

    filas = {
        int(tm_id): (fecha, int(gl), int(gv))
        for tm_id, fecha, gl, gv in session.execute(
            MatchCoach.__table__.select().with_only_columns(
                MatchCoach.transfermarkt_match_id,
                MatchCoach.fecha,
                MatchCoach.goles_local,
                MatchCoach.goles_visita,
            ).where(MatchCoach.fecha >= desde)
        ).all()
        if tm_id is not None
    }
    if not filas:
        return []

    store = RawStore(data_dir)
    correcciones: list[Correccion] = []

    for codigo, temporada, ruta in rutas_fixtures(data_dir):
        import json

        with open(ruta, encoding="utf-8") as archivo:
            fixtures = json.load(archivo)
        for fixture in fixtures:
            tm_id = fixture.get("match_id")
            if tm_id is None or int(tm_id) not in filas:
                continue
            fecha_db, gl_db, gv_db = filas[int(tm_id)]

            goles_cache: tuple[int, int] | None = None
            origen = "fixture"
            if store.has_match(codigo, temporada, int(tm_id)):
                reporte = store.read_match(codigo, temporada, int(tm_id))
                if reporte.get("final_home_goals") is not None and reporte.get(
                    "final_away_goals"
                ) is not None:
                    goles_cache = (
                        int(reporte["final_home_goals"]),
                        int(reporte["final_away_goals"]),
                    )
                    origen = "reporte"
            if goles_cache is None:
                if fixture.get("home_goals") is None or fixture.get("away_goals") is None:
                    continue
                goles_cache = (int(fixture["home_goals"]), int(fixture["away_goals"]))

            if goles_cache != (gl_db, gv_db):
                correcciones.append(
                    Correccion(
                        tm_match_id=int(tm_id),
                        fecha=fecha_db,
                        goles_db=(gl_db, gv_db),
                        goles_cache=goles_cache,
                        origen=origen,
                    )
                )

    return correcciones


def aplicar_correcciones(session: Session, correcciones: list[Correccion]) -> int:
    """Actualiza los goles en la base. Devuelve cuántos partidos corrigió."""
    aplicadas = 0
    for correccion in correcciones:
        session.execute(
            update(MatchCoach)
            .where(MatchCoach.transfermarkt_match_id == correccion.tm_match_id)
            .values(
                goles_local=correccion.goles_cache[0],
                goles_visita=correccion.goles_cache[1],
            )
        )
        aplicadas += 1
        logger.info(
            "Corregido %s: %s-%s -> %s-%s (%s)",
            correccion.tm_match_id, correccion.goles_db[0], correccion.goles_db[1],
            correccion.goles_cache[0], correccion.goles_cache[1], correccion.origen,
        )
    session.commit()
    return aplicadas


def recomputar_con_tiempo(session: Session) -> float:
    """Corre `recompute_all_elo` y devuelve cuántos segundos tardó."""
    from services import recompute_all_elo

    inicio = time.perf_counter()
    recompute_all_elo(session=session)
    session.commit()
    return round(time.perf_counter() - inicio, 2)


def validar_invariantes(session: Session) -> tuple[bool, dict]:
    """Invariantes del ELO: duplicados, suma cero y masa."""
    duplicados = session.execute(
        text(
            "select count(*) from (select transfermarkt_match_id from partidos_dt "
            "where transfermarkt_match_id is not null group by 1 having count(*) > 1) x"
        )
    ).scalar()
    desbalanceados = session.execute(
        text(
            "select count(*) from partidos_dt where abs((elo_local_nuevo - elo_local_previo) "
            "+ (elo_visita_nuevo - elo_visita_previo)) > 0.02"
        )
    ).scalar()
    masa = float(session.execute(text("select coalesce(sum(elo_actual), 0) from entrenadores")).scalar())
    coaches = session.execute(text("select count(*) from entrenadores")).scalar()
    esperada = 1000.0 * coaches
    ok = duplicados == 0 and desbalanceados == 0 and abs(masa - esperada) < 0.01
    return ok, {
        "duplicados": int(duplicados or 0),
        "desbalanceados": int(desbalanceados or 0),
        "masa": round(masa, 2),
        "masa_esperada": round(esperada, 2),
    }


