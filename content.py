"""Capa de datos de contenido: los rankings que van a las imágenes.

Cada función devuelve dataclasses con todo lo que necesita una plantilla (nombre, club,
ELO, puesto, variación, etiqueta). Sin matplotlib ni Playwright: se puede testear con
SQLite y el render (T3.2) las consume tal cual.

Reglas de publicación: todo pasa por `publicacion.py` (el ranking es por club y con su
DT actual; los interinos sólo aparecen en "subidas y bajadas").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Collection, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from duel import Duel, compute_duel
from models import Club, Coach, MatchCoach
from publicacion import (
    ETIQUETA_INTERINO,
    ETIQUETA_PROVISORIO,
    Elegibilidad,
    dt_actual_por_club,
    estado_publicacion,
    ranking_por_club,
)
from ranking import compute_power_ranking
from snapshots import semana_fin as _semana_fin
from snapshots import snapshot_hace, snapshot_previo

DIAS_VENTANA_MOVERS = 7
DIAS_REVELACION = 90
# El ranking de movers se corta DESPUÉS de filtrar por país y publicación, así que hay que
# pedirle material de sobra: con un corte global chico (40) no quedaba ningún argentino
# entre los que bajaron y la columna "cayeron" salía vacía.
SIN_CORTE = 5000
ANIOS_REVELACION = 2

# Mínimo de nombres por columna para que "subieron y cayeron" valga la pena: en una fecha
# FIFA hay un solo partido argentino y el ELO es suma cero, así que sale un +x y un -x.
MIN_MOVERS = 3

# La revelación sólo se elige entre DTs de ligas que la audiencia reconoce: el ELO no se
# compara entre ligas, y ordenando por suba bruta ganaban las ligas de más oscilación.
# `AR1N` queda porque la liga doméstica de un club se mide con los últimos 3 años.
LIGAS_REVELACION = frozenset({
    "ARG1", "ARGC", "AR1N", "BRA1",
    "GB1", "ES1", "IT1", "L1", "FR1", "NL1", "PO1",
})
MIN_PJ_REVELACION = 30


@dataclass(frozen=True)
class EntradaTop:
    """Un puesto del Top N."""

    dt_id: int
    dt: str
    club: str
    pais: Optional[str]
    liga: Optional[str]
    elo: float
    pj: int
    etiqueta: Optional[str]
    puesto: int
    puesto_previo: Optional[int] = None

    @property
    def variacion(self) -> Optional[int]:
        """Puestos ganados (+) o perdidos (−) respecto del snapshot anterior."""
        if self.puesto_previo is None:
            return None
        return self.puesto_previo - self.puesto


@dataclass(frozen=True)
class EntradaMovimiento:
    """Una subida o una bajada de la semana."""

    dt_id: int
    dt: str
    club: Optional[str]
    pais: Optional[str]
    elo: float
    delta: float
    partidos: int
    etiqueta: Optional[str]


@dataclass(frozen=True)
class Movimientos:
    desde: date
    hasta: date
    subidas: list[EntradaMovimiento] = field(default_factory=list)
    bajadas: list[EntradaMovimiento] = field(default_factory=list)
    total_partidos: int = 0


@dataclass(frozen=True)
class DueloSemana:
    """El partido de la semana con más ELO en juego."""

    fecha: date
    competencia: str
    dt_a_id: int
    dt_b_id: int
    club_a: str
    club_b: str
    elo_a: float
    elo_b: float
    resultado: str
    duelo: Duel

    @property
    def elo_combinado(self) -> float:
        return self.elo_a + self.elo_b


@dataclass(frozen=True)
class Revelacion:
    """El DT con menos de dos años de carrera que más creció."""

    dt_id: int
    dt: str
    club: Optional[str]
    pais: Optional[str]
    elo: float
    pj: int
    desde_primera_fecha: date
    variacion: float
    etiqueta: Optional[str]


@dataclass(frozen=True)
class EntradaSinClub:
    """Un técnico libre (sin club) listo para el ranking.

    No lleva el último club: se usa sólo para filtrar por país. En la imagen van el
    nombre y los partidos dirigidos.
    """

    dt_id: int
    dt: str
    elo: float
    pj: int
    ultima_fecha: Optional[date]
    etiqueta: Optional[str]
    puesto: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cierre(semana_fin: Optional[date]) -> date:
    return _semana_fin(semana_fin)


def _pais_por_dt(session: Session) -> dict[int, Optional[str]]:
    """`dt_id -> país` del club del que es técnico actual."""
    vigentes = dt_actual_por_club(session)
    paises = {
        club_id: pais for club_id, pais in session.execute(select(Club.club_id, Club.pais))
    }
    return {
        info["dt_id"]: paises.get(club_id)
        for club_id, info in vigentes.items()
    }


def _nombre(session: Session, dt_id: int) -> str:
    from models import Coach

    coach = session.get(Coach, dt_id)
    return f"{coach.nombre} {coach.apellido}".strip() if coach else str(dt_id)


# ---------------------------------------------------------------------------
# Top N
# ---------------------------------------------------------------------------
def top_n(
    session: Session,
    semana_fin: Optional[date] = None,
    n: int = 10,
    pais: Optional[str] = None,
    ruta_cobertura: Optional[Path] = None,
) -> list[EntradaTop]:
    """Los mejores `n` DTs (uno por club, con su técnico actual).

    El ▲▼ compara la posición con el snapshot de la semana anterior calculando el
    orden de **los mismos clubes** con los ELOs previos (no el puesto global, que
    mezclaría países).
    """
    cierre = _cierre(semana_fin)
    clubes = ranking_por_club(
        session, hasta=cierre, pais=pais, ruta_cobertura=ruta_cobertura
    )
    if not clubes:
        return []

    previo = snapshot_previo(session, hasta=cierre)
    orden_previo: dict[int, int] = {}
    if previo:
        # El puesto anterior se calcula ordenando **los mismos clubes** por el ELO que
        # tenían en el snapshot previo: así la flecha mide este ranking y no el global.
        candidatos = [
            (entrada.dt_id, previo[entrada.dt_id]["elo"])
            for entrada in clubes
            if entrada.dt_id in previo
        ]
        candidatos.sort(key=lambda par: (-par[1], par[0]))
        orden_previo = {
            dt_id: puesto for puesto, (dt_id, _) in enumerate(candidatos, start=1)
        }

    entradas: list[EntradaTop] = []
    for puesto, club in enumerate(clubes[:n], start=1):
        entradas.append(
            EntradaTop(
                dt_id=club.dt_id,
                dt=club.dt or _nombre(session, club.dt_id),
                club=club.club or "",
                pais=club.pais,
                liga=club.liga,
                elo=club.elo or 0.0,
                pj=club.pj,
                etiqueta=club.etiqueta,
                puesto=puesto,
                puesto_previo=orden_previo.get(club.dt_id),
            )
        )
    return entradas


def top_por_pais(
    session: Session,
    pais: str,
    semana_fin: Optional[date] = None,
    n: int = 10,
    ruta_cobertura: Optional[Path] = None,
) -> list[EntradaTop]:
    """Top N de un país (el ranking de las imágenes de Argentina, por ejemplo)."""
    return top_n(
        session, semana_fin=semana_fin, n=n, pais=pais, ruta_cobertura=ruta_cobertura
    )


# ---------------------------------------------------------------------------
# Técnicos sin club
# ---------------------------------------------------------------------------
def top_sin_club(
    session: Session,
    hasta: Optional[date] = None,
    pais: Optional[str] = "Argentina",
    n: int = 10,
    dias: int = settings.activo_dias,
    excluir_dt_ids: Collection[int] = (),
    ruta_cobertura: Optional[Path] = None,
) -> list[EntradaSinClub]:
    """Los mejores técnicos libres cuyo último club fue de `pais`.

    "Libre" es la regla de `publicacion.py`: dirigió en los últimos `dias` días y hoy
    no es el DT de ningún club. Sólo entran los que tienen `pj_total >= RANKING_MIN_PJ`
    (entre 15 y 29 llevan la etiqueta "provisorio"). El último club se usa para filtrar
    por país y no se devuelve: no se muestra en la imagen.
    """
    referencia = hasta or date.today()
    estados = estado_publicacion(session, hasta=referencia, ruta_cobertura=ruta_cobertura)
    paises = {
        club_id: pais_club
        for club_id, pais_club in session.execute(select(Club.club_id, Club.pais))
    }
    entrenadores = {
        coach.dt_id: coach for coach in session.execute(select(Coach)).scalars()
    }

    candidatos: list[tuple[float, Coach, Elegibilidad]] = []
    for dt_id, estado in estados.items():
        if not estado.sin_trabajo or dt_id in excluir_dt_ids:
            continue
        if estado.pj_total < settings.ranking_min_pj or estado.ultima_fecha is None:
            continue
        if (referencia - estado.ultima_fecha).days > dias:
            continue
        if pais and paises.get(estado.ultimo_club_id) != pais:
            continue
        coach = entrenadores.get(dt_id)
        if coach is None:
            continue
        candidatos.append((float(coach.elo_actual), coach, estado))

    candidatos.sort(key=lambda fila: (-fila[0], f"{fila[1].nombre} {fila[1].apellido}"))

    entradas: list[EntradaSinClub] = []
    for puesto, (elo, coach, estado) in enumerate(candidatos[:n], start=1):
        entradas.append(
            EntradaSinClub(
                dt_id=coach.dt_id,
                dt=f"{coach.nombre} {coach.apellido}".strip(),
                elo=elo,
                pj=estado.pj_total,
                ultima_fecha=estado.ultima_fecha,
                etiqueta=(
                    ETIQUETA_PROVISORIO
                    if estado.pj_total < settings.provisorio_pj
                    else None
                ),
                puesto=puesto,
            )
        )
    return entradas


# ---------------------------------------------------------------------------
# Subidas y bajadas
# ---------------------------------------------------------------------------
def movers(
    session: Session,
    semana_fin: Optional[date] = None,
    dias: int = DIAS_VENTANA_MOVERS,
    pais: Optional[str] = None,
    n: int = 5,
    ruta_cobertura: Optional[Path] = None,
) -> Movimientos:
    """Mayores subidas y bajadas de ELO en la ventana (por defecto, la última semana).

    Incluye a los interinos (5-14 partidos) con su etiqueta; excluye a los DTs que no
    pasan las reglas de publicación (inactivos, ligas sin datos, selecciones).

    El ranking se pide sin corte global: el filtro por país se aplica después, y si el
    corte viniera antes los que bajaron en ese país podían quedar afuera (columna vacía).
    """
    cierre = _cierre(semana_fin)
    desde = cierre - timedelta(days=dias - 1)
    ranking = compute_power_ranking(
        session, desde=desde, hasta=cierre, dias=dias, top=SIN_CORTE
    )

    estados = estado_publicacion(session, hasta=cierre, ruta_cobertura=ruta_cobertura)
    paises = _pais_por_dt(session)

    def _filtrar(entradas):
        resultado = []
        for entrada in entradas:
            estado = estados.get(entrada.dt_id)
            if estado is None or not estado.en_movimientos:
                continue
            if pais and paises.get(entrada.dt_id) != pais:
                continue
            resultado.append(
                EntradaMovimiento(
                    dt_id=entrada.dt_id,
                    dt=entrada.nombre,
                    club=entrada.club,
                    pais=paises.get(entrada.dt_id),
                    elo=entrada.elo_actual,
                    delta=entrada.delta,
                    partidos=entrada.partidos,
                    etiqueta=estado.etiqueta,
                )
            )
        return resultado

    return Movimientos(
        desde=desde,
        hasta=cierre,
        subidas=_filtrar(ranking.subidas)[:n],
        bajadas=_filtrar(ranking.bajadas)[:n],
        total_partidos=ranking.total_partidos,
    )


def polilinea(
    valores: Sequence[float],
    ancho: float = 1000,
    alto: float = 220,
    minimo: Optional[float] = None,
    maximo: Optional[float] = None,
    margen: float = 10,
) -> str:
    """Convierte una serie de ELO en los puntos de un `<polyline>` SVG.

    Normaliza al rango `[minimo, maximo]` (por defecto, el de la propia serie) y deja
    margen para que el trazo no se corte. Devuelve `"x1,y1 x2,y2 ..."`.
    """
    if not valores:
        return ""
    minimo = min(valores) if minimo is None else minimo
    maximo = max(valores) if maximo is None else maximo
    if maximo <= minimo:
        maximo = minimo + 1.0

    util_alto = alto - 2 * margen
    util_ancho = ancho - 2 * margen
    paso = util_ancho / (len(valores) - 1) if len(valores) > 1 else 0.0

    puntos = []
    for indice, valor in enumerate(valores):
        x = margen + indice * paso
        proporcion = (valor - minimo) / (maximo - minimo)
        y = alto - margen - proporcion * util_alto
        puntos.append(f"{x:.1f},{y:.1f}")
    return " ".join(puntos)


def serie_elo(
    session: Session,
    dt_ids: Sequence[int],
    semanas: int = 12,
    hasta: Optional[date] = None,
) -> dict[int, list[tuple[date, float]]]:
    """Serie semanal de ELO de uno o más DTs (para el gráfico del duelo).

    Sale de `snapshots_elo`; si un DT no tiene snapshot en una semana, se saltea ese
    punto. Devuelve `{dt_id: [(semana, elo), ...]}` ordenado por fecha.
    """
    from models import SnapshotElo

    cierre = _cierre(hasta)
    desde = cierre - timedelta(weeks=semanas - 1)
    filas = session.execute(
        select(SnapshotElo.dt_id, SnapshotElo.semana_fin, SnapshotElo.elo)
        .where(
            SnapshotElo.dt_id.in_(list(dt_ids)),
            SnapshotElo.semana_fin >= desde,
            SnapshotElo.semana_fin <= cierre,
        )
        .order_by(SnapshotElo.dt_id, SnapshotElo.semana_fin)
    ).all()

    series: dict[int, list[tuple[date, float]]] = {dt: [] for dt in dt_ids}
    for dt_id, fecha, elo in filas:
        series.setdefault(dt_id, []).append((fecha, float(elo)))
    return series


# ---------------------------------------------------------------------------
# Duelo de la semana
# ---------------------------------------------------------------------------
def duelo_de_la_semana(
    session: Session,
    semana_fin: Optional[date] = None,
    dias: int = DIAS_VENTANA_MOVERS,
    ruta_cobertura: Optional[Path] = None,
) -> Optional[DueloSemana]:
    """El partido de la ventana con más ELO combinado entre dos DTs publicables.

    Devuelve `None` si no hubo partidos o si ninguno de los dos técnicos pasa las
    reglas de publicación.
    """
    from models import Competition

    cierre = _cierre(semana_fin)
    desde = cierre - timedelta(days=dias - 1)

    filas = session.execute(
        select(
            MatchCoach.fecha, MatchCoach.dt_local_id, MatchCoach.dt_visita_id,
            MatchCoach.goles_local, MatchCoach.goles_visita, Competition.codigo,
            MatchCoach.transfermarkt_match_id,
        )
        .join(Competition, Competition.competencia_id == MatchCoach.competencia_id)
        .where(MatchCoach.fecha >= desde, MatchCoach.fecha <= cierre)
    ).all()
    if not filas:
        return None

    estados = estado_publicacion(session, hasta=cierre, ruta_cobertura=ruta_cobertura)
    vigentes = dt_actual_por_club(session)
    clubes = {
        club_id: (nombre, pais)
        for club_id, nombre, pais in session.execute(
            select(Club.club_id, Club.nombre, Club.pais)
        )
    }

    from models import Coach

    elos = {c.dt_id: float(c.elo_actual) for c in session.execute(select(Coach)).scalars()}

    mejor = None
    for fecha, local, visita, gl, gv, codigo, tm_id in filas:
        for dt_id in (local, visita):
            estado = estados.get(dt_id)
            if estado is None or not estado.publicable:
                break
        else:
            combinado = elos.get(local, 0.0) + elos.get(visita, 0.0)
            if mejor is None or combinado > mejor[0]:
                mejor = (combinado, fecha, local, visita, gl, gv, codigo, tm_id)
    if mejor is None:
        return None

    _, fecha, local, visita, gl, gv, codigo, _ = mejor
    club_local = clubes.get(vigentes.get(local, {}).get("club_id"), ("", None))[0]
    club_visita = clubes.get(vigentes.get(visita, {}).get("club_id"), ("", None))[0]
    duelo = compute_duel(session, local, visita)

    return DueloSemana(
        fecha=fecha,
        competencia=codigo,
        dt_a_id=local,
        dt_b_id=visita,
        club_a=club_local or "",
        club_b=club_visita or "",
        elo_a=elos.get(local, 0.0),
        elo_b=elos.get(visita, 0.0),
        resultado=f"{gl}-{gv}",
        duelo=duelo,
    )


# ---------------------------------------------------------------------------
# DT revelación
# ---------------------------------------------------------------------------
def revelacion(
    session: Session,
    semana_fin: Optional[date] = None,
    ruta_cobertura: Optional[Path] = None,
    anios: int = ANIOS_REVELACION,
    ligas: Optional[Collection[str]] = LIGAS_REVELACION,
    excluir_dt_ids: Collection[int] = (),
    min_pj: int = MIN_PJ_REVELACION,
) -> Optional[Revelacion]:
    """El DT con menos de `anios` de carrera que más creció en los últimos 90 días.

    "Carrera" se mide desde su primer partido en la base. El crecimiento se calcula
    contra el snapshot de hace 90 días; si no hay snapshot, se usa el ELO actual (y la
    variación queda en 0).

    Sólo compiten los DTs de `ligas` (`None` desactiva el filtro), con al menos `min_pj`
    partidos y que no estén en `excluir_dt_ids` (los que ya salieron hace poco).
    """
    cierre = _cierre(semana_fin)
    desde_carrera = cierre - timedelta(days=365 * anios)

    clubes = ranking_por_club(session, hasta=cierre, ruta_cobertura=ruta_cobertura)
    if not clubes:
        return None

    from sqlalchemy import func

    local = select(MatchCoach.dt_local_id.label("dt"), MatchCoach.fecha.label("fecha"))
    visita = select(MatchCoach.dt_visita_id, MatchCoach.fecha)
    partidos = local.union_all(visita).subquery()
    primeras = dict(
        session.execute(
            select(partidos.c.dt, func.min(partidos.c.fecha)).group_by(partidos.c.dt)
        ).all()
    )

    hace_90 = snapshot_hace(session, dias=DIAS_REVELACION, hasta=cierre)

    candidatos = []
    for club in clubes:
        primera_fecha = primeras.get(club.dt_id)
        if primera_fecha is None or primera_fecha < desde_carrera:
            continue
        if club.pj < min_pj:
            continue
        if club.dt_id in excluir_dt_ids:
            continue
        if ligas is not None and club.liga not in ligas:
            continue
        elo_previo = hace_90.get(club.dt_id, {}).get("elo")
        variacion = (club.elo or 0.0) - elo_previo if elo_previo is not None else 0.0
        candidatos.append((variacion, club, primera_fecha))

    if not candidatos:
        return None
    candidatos.sort(key=lambda fila: (-fila[0], -(fila[1].elo or 0)))
    variacion, club, primera_fecha = candidatos[0]

    return Revelacion(
        dt_id=club.dt_id,
        dt=club.dt or _nombre(session, club.dt_id),
        club=club.club,
        pais=club.pais,
        elo=club.elo or 0.0,
        pj=club.pj,
        desde_primera_fecha=primera_fecha,
        variacion=round(variacion, 2),
        etiqueta=club.etiqueta,
    )
