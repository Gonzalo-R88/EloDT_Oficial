"""Snapshots semanales del ranking: "cómo estaba el ELO el domingo pasado".

`partidos_dt` permite reconstruir el ELO en cualquier fecha, pero las imágenes y el
texto necesitan además el **puesto** de cada DT y sus marcas de publicación en ese
momento. Eso es un snapshot: una foto inmutable por semana y versión del modelo, de
modo que lo que se publicó no cambia aunque después se recalcule el ELO.

La elegibilidad (`publicable`, `etiqueta`) se evalúa con las reglas vigentes
(`publicacion.estado_publicacion`); para snapshots históricos es una aproximación: lo
que se reconstruye con precisión es el ELO y los partidos jugados a esa fecha.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, func, select, union_all
from sqlalchemy.orm import Session

from elo import MODELO_VERSION
from models import MatchCoach, SnapshotElo
from publicacion import estado_publicacion

logger = logging.getLogger(__name__)

DIAS_ACTIVO = 365


def semana_fin(fecha: Optional[date] = None) -> date:
    """Domingo de la semana a la que pertenece `fecha` (o el anterior a hoy).

    Es la fecha con la que se publica: el lunes se publica la semana que cerró el
    domingo anterior.
    """
    referencia = fecha or date.today()
    return referencia - timedelta(days=(referencia.weekday() + 1) % 7)


def _participaciones():
    """(dt, elo_nuevo, fecha) de local y visitante."""
    local = select(
        MatchCoach.dt_local_id.label("dt_id"),
        MatchCoach.elo_local_nuevo.label("elo"),
        MatchCoach.fecha.label("fecha"),
    )
    visita = select(
        MatchCoach.dt_visita_id.label("dt_id"),
        MatchCoach.elo_visita_nuevo.label("elo"),
        MatchCoach.fecha.label("fecha"),
    )
    return union_all(local, visita).subquery()


def elo_al_cierre(session: Session, hasta: date) -> dict[int, dict]:
    """`dt_id -> {elo, pj_total, ultima_fecha}` con los partidos hasta `hasta`."""
    partidos = _participaciones()

    filas = session.execute(
        select(partidos.c.dt_id, partidos.c.elo, partidos.c.fecha)
        .where(partidos.c.fecha <= hasta)
        .order_by(partidos.c.dt_id, partidos.c.fecha.asc())
    ).all()

    acumulado: dict[int, dict] = {}
    for dt_id, elo, fecha in filas:
        estado = acumulado.get(dt_id)
        if estado is None:
            acumulado[dt_id] = {"elo": float(elo), "pj_total": 1, "ultima_fecha": fecha}
        else:
            estado["elo"] = float(elo)
            estado["pj_total"] += 1
            estado["ultima_fecha"] = fecha
    return acumulado


@dataclass(frozen=True)
class SnapshotSemanal:
    semana_fin: date
    modelo_version: str
    filas: int
    publicables: int


def take_snapshot(
    session: Session,
    hasta: Optional[date] = None,
    modelo_version: str = MODELO_VERSION,
    ventana_activo_dias: int = DIAS_ACTIVO,
    ruta_cobertura: Optional[Path] = None,
) -> SnapshotSemanal:
    """Guarda (o reemplaza) el snapshot de la semana que cierra en `hasta`.

    Es idempotente: borra las filas de esa semana y versión antes de insertar. Sólo
    guarda DTs con actividad en la ventana (para que la tabla no crezca sin sentido).
    """
    cierre = semana_fin(hasta)
    datos = elo_al_cierre(session, cierre)
    estados = estado_publicacion(session, hasta=cierre, ruta_cobertura=ruta_cobertura)

    desde_activo = cierre - timedelta(days=ventana_activo_dias)
    elegibles = {
        dt_id: info
        for dt_id, info in datos.items()
        if info["ultima_fecha"] is not None and info["ultima_fecha"] >= desde_activo
    }

    publicables = sorted(
        (
            (dt_id, info["elo"])
            for dt_id, info in elegibles.items()
            if estados.get(dt_id) is not None and estados[dt_id].publicable
        ),
        key=lambda par: (-par[1], par[0]),
    )
    puestos = {dt_id: puesto for puesto, (dt_id, _) in enumerate(publicables, start=1)}

    session.execute(
        delete(SnapshotElo).where(
            SnapshotElo.semana_fin == cierre,
            SnapshotElo.modelo_version == modelo_version,
        )
    )
    for dt_id, info in elegibles.items():
        estado = estados.get(dt_id)
        session.add(
            SnapshotElo(
                semana_fin=cierre,
                dt_id=dt_id,
                modelo_version=modelo_version,
                elo=info["elo"],
                rank_global=puestos.get(dt_id),
                pj_total=info["pj_total"],
                activo=True,
                publicable=bool(estado.publicable) if estado else False,
                etiqueta=estado.etiqueta if estado else None,
            )
        )
    session.flush()

    logger.info(
        "Snapshot %s (%s): %s filas, %s publicables",
        cierre, modelo_version, len(elegibles), len(publicables),
    )
    return SnapshotSemanal(
        semana_fin=cierre,
        modelo_version=modelo_version,
        filas=len(elegibles),
        publicables=len(publicables),
    )


def snapshot_previo(
    session: Session,
    hasta: Optional[date] = None,
    modelo_version: str = MODELO_VERSION,
    semanas_atras: int = 1,
) -> dict[int, dict]:
    """`dt_id -> {elo, rank_global}` del snapshot anterior disponible (o vacío)."""
    cierre = semana_fin(hasta)
    filas = session.execute(
        select(
            SnapshotElo.semana_fin,
            SnapshotElo.dt_id,
            SnapshotElo.elo,
            SnapshotElo.rank_global,
        )
        .where(
            SnapshotElo.semana_fin < cierre,
            SnapshotElo.modelo_version == modelo_version,
        )
        .order_by(SnapshotElo.semana_fin.desc())
    ).all()
    if not filas:
        return {}

    # La más reciente que tenga alguna fila.
    ultima = filas[0][0]
    return {
        dt_id: {"elo": float(elo), "rank_global": rank, "semana_fin": fecha}
        for fecha, dt_id, elo, rank in filas
        if fecha == ultima
    }


def snapshot_hace(
    session: Session,
    dias: int,
    hasta: Optional[date] = None,
    modelo_version: str = MODELO_VERSION,
) -> dict[int, dict]:
    """`dt_id -> {elo, rank_global}` del snapshot más cercano a `dias` atrás."""
    cierre = semana_fin(hasta)
    objetivo = cierre - timedelta(days=dias)
    fila = session.execute(
        select(SnapshotElo.semana_fin)
        .where(
            SnapshotElo.semana_fin <= objetivo,
            SnapshotElo.modelo_version == modelo_version,
        )
        .order_by(SnapshotElo.semana_fin.desc())
        .limit(1)
    ).first()
    if fila is None:
        return {}
    filas = session.execute(
        select(SnapshotElo.dt_id, SnapshotElo.elo, SnapshotElo.rank_global).where(
            SnapshotElo.semana_fin == fila[0],
            SnapshotElo.modelo_version == modelo_version,
        )
    ).all()
    return {
        dt_id: {"elo": float(elo), "rank_global": rank, "semana_fin": fila[0]}
        for dt_id, elo, rank in filas
    }
