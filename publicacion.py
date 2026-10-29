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
MOTIVO_SIN_CLUB = "sin_club_actual"

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
    # DT actual de algún club (ver `dt_actual_por_club`). Los rankings se arman por
    # club, así que sólo entra quien hoy está en un banco.
    es_vigente: bool = False
    club_actual: Optional[int] = None
    # Dirigió en el último año pero hoy no es el DT de ningún club: candidato al
    # ranking de "técnicos sin trabajo".
    sin_trabajo: bool = False

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


def codigos_del_mismo_pais(codigo: str) -> list[str]:
    """El código y todas las ligas del mismo país según el catálogo.

    Muchos países tienen la liga partida en dos competencias (Apertura y Clausura:
    ARG1/ARGC, BO1A/BO1C, TDeA/TDeC, PR1A/PR1C, VZ1A/VZ1C...). Medir la cobertura de
    una sola hace que cada una parezca vacía en los años en que no se jugó, aunque
    los datos del país estén completos.
    """
    try:
        from scraping.competitions import COMPETITIONS
    except ImportError:  # pragma: no cover - sólo si falta el paquete
        return [codigo]

    configuracion = COMPETITIONS.get(codigo)
    if configuracion is None or not configuracion.country:
        return [codigo]
    del_pais = {
        otro
        for otro, datos in COMPETITIONS.items()
        if datos.country == configuracion.country and datos.kind == "liga"
    }
    del_pais.add(codigo)
    return sorted(del_pais)


def cobertura_liga(
    codigo: str,
    hasta: date,
    anios: Optional[int] = None,
    ruta: Optional[Path] = None,
    agrupar_por_pais: bool = True,
) -> Optional[float]:
    """Cobertura del fútbol de liga de un país en los últimos `anios` años.

    Por defecto suma todas las ligas del mismo país (ponderando por cantidad de
    partidos, así una liga de 380 partidos pesa más que una de 240). Con
    `agrupar_por_pais=False` mide sólo esa competencia, útil para diagnosticar.

    Devuelve `None` si no hay ningún partido en la ventana (no se puede afirmar nada).
    Los años fuera de la vida de la competencia (`first_season`/`last_season`) no
    cuentan: `cobertura.json` ya los omite.
    """
    datos = cargar_cobertura(ruta)
    codigos = codigos_del_mismo_pais(codigo) if agrupar_por_pais else [codigo]
    cantidad = anios or settings.cobertura_anios
    ventana = {hasta.year - desplazamiento for desplazamiento in range(cantidad)}

    fixtures = cargados = 0
    anios_en_ventana = 0
    for cada in codigos:
        for anio, valores in (datos.get(cada) or {}).items():
            if int(anio) not in ventana:
                continue
            anios_en_ventana += 1
            fixtures += int(valores.get("fixtures", 0))
            cargados += int(valores.get("cargados", 0))

    if anios_en_ventana == 0:
        # La competencia no tiene ningún año dentro de la ventana: no se puede afirmar nada.
        return None
    if fixtures == 0:
        # Tiene años en la ventana pero ninguno con partidos: cobertura 0.
        return 0.0
    return round(cargados / fixtures, 4)


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
def dt_actual_por_club(session: Session) -> dict[int, dict]:
    """`club_id -> {"dt_id", "fecha"}` del técnico del partido más reciente del club.

    Es la definición operativa de "DT actual": quien dirigió el último partido del
    club. Evita publicar rankings con técnicos que ya no están (el club cambió de DT).
    """
    partidos = _participaciones()
    maxima = (
        select(partidos.c.club_id.label("club_id"), func.max(partidos.c.fecha).label("fecha"))
        .group_by(partidos.c.club_id)
        .subquery()
    )
    filas = session.execute(
        select(partidos.c.club_id, partidos.c.dt_id, partidos.c.fecha).join(
            maxima,
            and_(
                partidos.c.club_id == maxima.c.club_id,
                partidos.c.fecha == maxima.c.fecha,
            ),
        )
    ).all()

    vigentes: dict[int, dict] = {}
    for club_id, dt_id, fecha in filas:
        vigentes.setdefault(club_id, {"dt_id": dt_id, "fecha": fecha})
    return vigentes


def _datos_por_dt(session: Session) -> dict[int, dict]:
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
    por_dt = _datos_por_dt(session)

    # dt_id -> club del que es técnico actual (si es el de algún club).
    club_del_dt: dict[int, int] = {}
    for club_id, info in dt_actual_por_club(session).items():
        club_del_dt.setdefault(info["dt_id"], club_id)

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
        es_vigente = dt_id in club_del_dt

        base = {
            "dt_id": dt_id,
            "pj_total": pj_total,
            "ultima_fecha": ultima,
            "liga": liga,
            "cobertura": cobertura,
            "es_vigente": es_vigente,
            "club_actual": club_del_dt.get(dt_id),
        }

        if pj_total < settings.interino_min_pj:
            estados[dt_id] = Elegibilidad(
                publicable=False, motivo=MOTIVO_POCOS_PARTIDOS, **base
            )
            continue

        reciente = ultima is not None and (referencia - ultima).days <= settings.activo_dias
        # "Inactivo" se evalúa antes que la liga: un DT que dejó de dirigir hace años
        # no debe figurar como "sin liga doméstica" (el motivo tiene que ser el real).
        if not reciente:
            estados[dt_id] = Elegibilidad(publicable=False, motivo=MOTIVO_INACTIVO, **base)
            continue

        if liga is None:
            estados[dt_id] = Elegibilidad(publicable=False, motivo=MOTIVO_SIN_LIGA, **base)
            continue
        if cobertura is None or cobertura < settings.cobertura_min:
            estados[dt_id] = Elegibilidad(publicable=False, motivo=MOTIVO_COBERTURA, **base)
            continue

        if not es_vigente:
            # Dirigió hace poco pero hoy no está en ningún banco: no va al ranking de
            # clubes; queda como candidato al ranking de "sin trabajo".
            estados[dt_id] = Elegibilidad(
                publicable=False, sin_trabajo=True, motivo=MOTIVO_SIN_CLUB, **base
            )
            continue

        if pj_total >= settings.ranking_min_pj:
            etiqueta = None if pj_total >= settings.provisorio_pj else ETIQUETA_PROVISORIO
            estados[dt_id] = Elegibilidad(publicable=True, etiqueta=etiqueta, **base)
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


@dataclass(frozen=True)
class EntradaClub:
    """Un club con su técnico actual, listo para un ranking."""

    club_id: int
    club: str
    pais: Optional[str]
    dt_id: int
    dt: str
    elo: float
    pj: int
    etiqueta: Optional[str]
    liga: Optional[str]
    ultima_fecha: Optional[date]


def ranking_por_club(
    session: Session,
    hasta: Optional[date] = None,
    pais: Optional[str] = None,
    ruta_cobertura: Optional[Path] = None,
) -> list[EntradaClub]:
    """Ranking por club: **una fila por club, con su técnico actual**.

    Es la forma correcta de listar "los mejores DTs de un país": si un club cambió de
    entrenador, aparece sólo el actual; el anterior queda afuera (puede ir al ranking
    de técnicos sin trabajo). Ordenado por ELO descendente.
    """
    from models import Club, Coach

    estados = estado_publicacion(session, hasta=hasta, ruta_cobertura=ruta_cobertura)
    vigentes = dt_actual_por_club(session)

    info_clubes = {}
    for club in session.execute(select(Club)).scalars():
        info_clubes[club.club_id] = (club.nombre, club.pais)
    info_dts = {}
    for coach in session.execute(select(Coach)).scalars():
        info_dts[coach.dt_id] = (f"{coach.nombre} {coach.apellido}".strip(), float(coach.elo_actual))

    entradas: list[EntradaClub] = []
    for club_id, info in vigentes.items():
        dt_id = info["dt_id"]
        estado = estados.get(dt_id)
        if estado is None or not estado.publicable:
            continue
        club_nombre, club_pais = info_clubes.get(club_id, (None, None))
        if pais and club_pais != pais:
            continue
        dt_nombre, elo = info_dts.get(dt_id, (None, None))
        entradas.append(
            EntradaClub(
                club_id=club_id,
                club=club_nombre,
                pais=club_pais,
                dt_id=dt_id,
                dt=dt_nombre,
                elo=elo,
                pj=estado.pj_total,
                etiqueta=estado.etiqueta,
                liga=estado.liga,
                ultima_fecha=estado.ultima_fecha,
            )
        )

    entradas.sort(key=lambda entrada: (-(entrada.elo or 0), entrada.dt or ""))
    return entradas
