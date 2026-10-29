"""Reglas de publicación: qué DT puede aparecer en una imagen y con qué etiqueta.

Es la única fuente de verdad de "esto se publica / esto no". La usan la capa de
contenido (`content.py`), el pipeline semanal y los snapshots.

Reglas (umbrales configurables en `config.py`):

1. `pj_total >= INTERINO_MIN_PJ` (5). Menos que eso no se muestra nunca.
2. **Activo**: jugó algún partido en los últimos `ACTIVO_DIAS` (365) días.
3. **Liga doméstica verificable**: el país del DT no se publica "de memoria"; se toma
   la liga donde juega su club actual y se exige que sus datos sean confiables
   (`cobertura >= COBERTURA_MIN`, 90 %, promediando los últimos `COBERTURA_ANIOS` años).
   Un DT cuyo club no tiene liga doméstica conocida (sólo jugó copas internacionales)
   no se publica.
4. **Rankings**: con `pj_total >= RANKING_MIN_PJ` (15). Entre 15 y `PROVISORIO_PJ` (30)
   lleva la etiqueta "provisorio".
5. **Interinos**: entre 5 y 14 partidos. No entran a los rankings (Top 10) pero sí a
   "subidas y bajadas", siempre etiquetados.

Los datos de `data/audit/cobertura.json` los regenera la auditoría (T2.5 en el
pipeline semanal); este módulo sólo los lee.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import and_, func, select, union_all
from sqlalchemy.orm import Session

from config import settings
from models import Competition, MatchCoach

logger = logging.getLogger(__name__)

ETIQUETA_PROVISORIO = "provisorio"
ETIQUETA_INTERINO = "interino"

# Motivos por los que un DT no se publica (para logs y diagnóstico).
MOTIVO_POCOS_PARTIDOS = "pocos_partidos"
MOTIVO_INACTIVO = "inactivo"
MOTIVO_SIN_LIGA = "sin_liga_domestica"
MOTIVO_COBERTURA = "cobertura_baja"
MOTIVO_SIN_FECHAS = "sin_partidos"

_cobertura_cache: tuple[float, dict] | None = None


@dataclass(frozen=True)
class Elegibilidad:
    """Resultado de evaluar a un DT contra las reglas de publicación."""

    dt_id: int
    publicable: bool
    etiqueta: Optional[str] = None
    interino: bool = False
    motivo: Optional[str] = None
    pj_total: int = 0
    ultima_fecha: Optional[date] = None
    liga: Optional[str] = None
    cobertura: Optional[float] = None

    @property
    def en_movimientos(self) -> bool:
        """Puede aparecer en "subidas y bajadas" (incluye interinos)."""
        return self.publicable or self.interino


# ---------------------------------------------------------------------------
# Cobertura (data/audit/cobertura.json)
# ---------------------------------------------------------------------------
def cargar_cobertura(ruta: Optional[Path] = None) -> dict:
    """Lee `cobertura.json` cacheando por fecha de modificación del archivo."""
    global _cobertura_cache
    destino = Path(ruta or settings.cobertura_json)
    try:
        marca = destino.stat().st_mtime
    except OSError:
        logger.warning("No existe el archivo de cobertura %s; no se puede publicar.", destino)
        return {}
    if _cobertura_cache is not None and _cobertura_cache[0] == marca:
        return _cobertura_cache[1]
    with open(destino, encoding="utf-8") as archivo:
        datos = json.load(archivo)
    _cobertura_cache = (marca, datos)
    return datos


def cobertura_liga(
    codigo: str,
    hasta: date,
    anios: Optional[int] = None,
    ruta: Optional[Path] = None,
) -> Optional[float]:
    """Cobertura promedio de una competencia en los últimos `anios` años calendario.

    Devuelve `None` si la competencia no tiene ningún año con datos en la ventana
    (no se puede afirmar nada). Los años fuera de la vida de la competencia
    (`first_season`/`last_season`) no cuentan: `cobertura.json` ya los omite.
    """
    datos = cargar_cobertura(ruta)
    por_anio = datos.get(codigo)
    if not por_anio:
        return None
    cantidad = anios or settings.cobertura_anios
    ventana = {hasta.year - desplazamiento for desplazamiento in range(cantidad)}
    ratios = [
        float(valores["ratio"])
        for anio, valores in por_anio.items()
        if int(anio) in ventana
    ]
    if not ratios:
        return None
    return round(sum(ratios) / len(ratios), 4)


# ---------------------------------------------------------------------------
# Ligas domésticas por club
# ---------------------------------------------------------------------------
def _participaciones():
    """Vista `UNION ALL` de (dt, club, competencia, fecha) para local y visitante."""
    local = select(
        MatchCoach.dt_local_id.label("dt_id"),
        MatchCoach.club_local_id.label("club_id"),
        MatchCoach.competencia_id.label("competencia_id"),
        MatchCoach.fecha.label("fecha"),
    )
    visita = select(
        MatchCoach.dt_visita_id.label("dt_id"),
        MatchCoach.club_visita_id.label("club_id"),
        MatchCoach.competencia_id.label("competencia_id"),
        MatchCoach.fecha.label("fecha"),
    )
    return union_all(local, visita).subquery()


def ligas_domesticas(session: Session, desde: date) -> dict[int, str]:
    """`club_id -> código` de la liga doméstica donde más jugó desde `desde`.

    En un empate gana el código alfabéticamente menor (resultado estable).
    """
    partidos = _participaciones()
    filas = session.execute(
        select(partidos.c.club_id, Competition.codigo, func.count())
        .join(Competition, Competition.competencia_id == partidos.c.competencia_id)
        .where(Competition.tipo == "liga")
        .where(partidos.c.fecha >= desde)
        .group_by(partidos.c.club_id, Competition.codigo)
    ).all()

    agrupado: dict[int, list[tuple[str, int]]] = {}
    for club_id, codigo, cantidad in filas:
        agrupado.setdefault(club_id, []).append((codigo, int(cantidad)))
    return {
        club_id: sorted(opciones, key=lambda par: (-par[1], par[0]))[0][0]
        for club_id, opciones in agrupado.items()
    }


# ---------------------------------------------------------------------------
# Estado de publicación
# ---------------------------------------------------------------------------
def _datos_por_dt(session: Session, desde: date) -> dict[int, dict]:
    """`dt_id -> {pj, ultima_fecha, club_id}` a partir de `partidos_dt`."""
    partidos = _participaciones()

    totales = dict(
        session.execute(
            select(partidos.c.dt_id, func.count()).group_by(partidos.c.dt_id)
        ).all()
    )

    maxima = (
        select(partidos.c.dt_id.label("dt_id"), func.max(partidos.c.fecha).label("fecha"))
        .group_by(partidos.c.dt_id)
        .subquery()
    )
    ultimos = session.execute(
        select(partidos.c.dt_id, partidos.c.club_id, partidos.c.fecha).join(
            maxima,
            and_(
                partidos.c.dt_id == maxima.c.dt_id,
                partidos.c.fecha == maxima.c.fecha,
            ),
        )
    ).all()

    datos: dict[int, dict] = {}
    for dt_id, club_id, fecha in ultimos:
        datos.setdefault(
            dt_id,
            {"pj": int(totales.get(dt_id, 0)), "club_id": club_id, "ultima_fecha": fecha},
        )
    return datos


def estado_publicacion(
    session: Session,
    hasta: Optional[date] = None,
    dt_ids: Optional[Iterable[int]] = None,
    ruta_cobertura: Optional[Path] = None,
) -> dict[int, Elegibilidad]:
    """Evalúa las reglas para todos los DTs (o para `dt_ids`) en `hasta`."""
    referencia = hasta or date.today()
    desde_ligas = referencia - timedelta(days=365 * settings.cobertura_anios)
    ligas = ligas_domesticas(session, desde_ligas)
    por_dt = _datos_por_dt(session, desde_ligas)

    objetivo = set(dt_ids) if dt_ids is not None else set(por_dt)
    estados: dict[int, Elegibilidad] = {}

    for dt_id in objetivo:
        datos = por_dt.get(dt_id)
        if datos is None:
            estados[dt_id] = Elegibilidad(dt_id=dt_id, publicable=False, motivo=MOTIVO_SIN_FECHAS)
            continue

        pj_total = datos["pj"]
        ultima = datos["ultima_fecha"]
        club_id = datos["club_id"]
        liga = ligas.get(club_id)
        cobertura = cobertura_liga(liga, referencia, ruta=ruta_cobertura) if liga else None

        base = {
            "dt_id": dt_id,
            "pj_total": pj_total,
            "ultima_fecha": ultima,
            "liga": liga,
            "cobertura": cobertura,
        }

        if pj_total < settings.interino_min_pj:
            estados[dt_id] = Elegibilidad(
                publicable=False, motivo=MOTIVO_POCOS_PARTIDOS, **base
            )
            continue
        if ultima is None or (referencia - ultima).days > settings.activo_dias:
            estados[dt_id] = Elegibilidad(publicable=False, motivo=MOTIVO_INACTIVO, **base)
            continue
        if liga is None:
            estados[dt_id] = Elegibilidad(publicable=False, motivo=MOTIVO_SIN_LIGA, **base)
            continue
        if cobertura is None or cobertura < settings.cobertura_min:
            estados[dt_id] = Elegibilidad(publicable=False, motivo=MOTIVO_COBERTURA, **base)
            continue

        if pj_total >= settings.ranking_min_pj:
            etiqueta = None if pj_total >= settings.provisorio_pj else ETIQUETA_PROVISORIO
            estados[dt_id] = Elegibilidad(
                publicable=True, etiqueta=etiqueta, **base
            )
        else:
            estados[dt_id] = Elegibilidad(
                publicable=False, interino=True, etiqueta=ETIQUETA_INTERINO, **base
            )

    return estados


def es_publicable(
    session: Session,
    dt_id: int,
    hasta: Optional[date] = None,
    ruta_cobertura: Optional[Path] = None,
) -> Elegibilidad:
    """Evalúa a un solo DT (misma lógica que `estado_publicacion`)."""
    return estado_publicacion(
        session, hasta=hasta, dt_ids=[dt_id], ruta_cobertura=ruta_cobertura
    )[dt_id]
