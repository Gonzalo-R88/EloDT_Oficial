"""Capa de datos de las ventanas FIFA (selecciones nacionales).

En una pausa de selecciones los partidos de clubes son casi inexistentes, así que el
paquete semanal de clubes queda flojo (un +x y un -x en "subieron y cayeron"). Esta capa
detecta la ventana por sí sola y arma el ranking de **seleccionadores** con los mismos
campos que la plantilla de movimientos, para reutilizarla.

Sin dibujo ni escritura: se puede testear con SQLite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Club, Coach, Competition, MatchCoach
from ranking import compute_power_ranking

# Un amistoso de sub-15 a sub-23 aparece como "France U21" / "Germany U18". La temporada
# de amistosos de Transfermarkt mezcla todas las categorías bajo el mismo código.
JUVENIL = re.compile(r"\bU\s?\d{2}\b", re.IGNORECASE)

# Debajo de esta cantidad de partidos de carrera el nivel de ELO todavía no dice nada
# (arranca en 1000): se etiqueta al DT como debutante en la imagen.
MIN_PJ_DEBUTANTE = 5

# Un día cuenta como "de fecha FIFA" si tiene al menos esta cantidad de partidos de
# selecciones mayores. En la ventana de noviembre de 2026 hubo 8-22 por día.
MIN_PARTIDOS_DIA = 6

# Días sin partidos que se toleran dentro de una misma ventana (rara vez se juega todos
# los días: la ventana de septiembre-octubre de 2026 tuvo huecos).
HUECO_MAXIMO = 2

# Cuántos días hacia atrás se buscan ventanas.
DIAS_BUSQUEDA = 45

SIN_CORTE = 5000


@dataclass(frozen=True)
class VentanaFifa:
    """Días consecutivos con partidos de selecciones mayores."""

    desde: date
    hasta: date
    partidos: int
    dias: tuple[date, ...] = ()

    @property
    def dias_totales(self) -> int:
        return (self.hasta - self.desde).days + 1


@dataclass(frozen=True)
class EntradaSeleccion:
    """Un seleccionador dentro del ranking de la ventana."""

    dt_id: int
    dt: str
    club: Optional[str]  # nombre de la selección
    elo: float
    delta: float
    partidos: int
    pj_carrera: int = 0
    etiqueta: Optional[str] = None


@dataclass(frozen=True)
class MovimientosSelecciones:
    desde: date
    hasta: date
    subidas: list[EntradaSeleccion] = field(default_factory=list)
    bajadas: list[EntradaSeleccion] = field(default_factory=list)
    total_partidos: int = 0


def es_juvenil(nombre: Optional[str]) -> bool:
    """True si el nombre de equipo corresponde a una categoría juvenil (sub-15 a sub-23)."""
    return bool(JUVENIL.search(nombre or ""))


def _clubes_juveniles(session: Session) -> set[int]:
    return {
        club.club_id
        for club in session.execute(select(Club)).scalars()
        if es_juvenil(club.nombre)
    }


def dias_con_partidos(
    session: Session,
    desde: date,
    hasta: date,
) -> dict[date, int]:
    """Partidos de selecciones mayores por día en `[desde, hasta]`."""
    filas = session.execute(
        select(
            MatchCoach.fecha,
            MatchCoach.club_local_id,
            MatchCoach.club_visita_id,
        )
        .join(Competition, Competition.competencia_id == MatchCoach.competencia_id)
        .where(
            Competition.tipo == "selecciones",
            MatchCoach.fecha >= desde,
            MatchCoach.fecha <= hasta,
        )
    ).all()

    juveniles = _clubes_juveniles(session)
    conteo: dict[date, int] = {}
    for fecha, local, visita in filas:
        if local in juveniles or visita in juveniles:
            continue
        conteo[fecha] = conteo.get(fecha, 0) + 1
    return dict(sorted(conteo.items()))


def _ventanas(dias: list[date], hueco: int) -> list[list[date]]:
    """Agrupa los días con partidos que estén separados por `hueco` días o menos."""
    grupos: list[list[date]] = []
    for dia in dias:
        if grupos and (dia - grupos[-1][-1]).days <= hueco + 1:
            grupos[-1].append(dia)
        else:
            grupos.append([dia])
    return grupos


def ventana_fifa(
    session: Session,
    hoy: Optional[date] = None,
    minimo: int = MIN_PARTIDOS_DIA,
    hueco: int = HUECO_MAXIMO,
    dias: int = DIAS_BUSQUEDA,
) -> Optional[VentanaFifa]:
    """La ventana FIFA más reciente, o `None` si no hubo partidos de selecciones.

    Se arma con los días que superan `minimo` partidos de selecciones mayores, uniendo
    los que estén separados por `hueco` días o menos. El `hasta` es el último día con
    partidos, así que la ventana está cerrada cuando ya pasó ese día.
    """
    hoy = hoy or date.today()
    conteo = dias_con_partidos(session, hoy - timedelta(days=dias), hoy)
    dias_llenos = [dia for dia, total in conteo.items() if total >= minimo]
    if not dias_llenos:
        return None

    grupos = _ventanas(dias_llenos, hueco)
    elegido = grupos[-1]
    return VentanaFifa(
        desde=elegido[0],
        hasta=elegido[-1],
        partidos=sum(conteo[dia] for dia in elegido),
        dias=tuple(elegido),
    )


def ventana_cerrada(ventana: VentanaFifa, hoy: Optional[date] = None) -> bool:
    """True si ya pasó el último día de la ventana (no quedan partidos por jugar)."""
    return (hoy or date.today()) > ventana.hasta


def partidos_en_ventana(session: Session, desde: date, hasta: date) -> int:
    """Partidos de selecciones mayores cargados en el rango."""
    return sum(dias_con_partidos(session, desde, hasta).values())


def _partidos_de_carrera(session: Session, dt_ids: list[int]) -> dict[int, int]:
    """Partidos totales de cada DT en la base (todas las competencias)."""
    if not dt_ids:
        return {}
    local = select(MatchCoach.dt_local_id.label("dt"))
    visita = select(MatchCoach.dt_visita_id.label("dt"))
    todos = local.union_all(visita).subquery()
    filas = session.execute(
        select(todos.c.dt, func.count()).where(todos.c.dt.in_(dt_ids)).group_by(todos.c.dt)
    ).all()
    return {dt_id: total for dt_id, total in filas}


def movers_selecciones(
    session: Session,
    desde: date,
    hasta: date,
    n: int = 5,
) -> MovimientosSelecciones:
    """Mayores subidas y bajadas de ELO entre seleccionadores en la ventana.

    No pide un mínimo de partidos: el primer partido de un DT mueve el ELO lo mismo que
    cualquiera (lo que pesa es el torneo, el margen y la sorpresa). Lo que sí se hace es
    etiquetar como "debutante" a quien tiene menos de `MIN_PJ_DEBUTANTE` partidos, porque
    su nivel de ELO todavía no es informativo.
    """
    ranking = compute_power_ranking(
        session, desde=desde, hasta=hasta, top=SIN_CORTE, tipo="selecciones"
    )

    dt_ids = [entrada.dt_id for entrada in ranking.subidas + ranking.bajadas]
    carrera = _partidos_de_carrera(session, dt_ids)
    clubes = {
        club.club_id: club.nombre
        for club in session.execute(select(Club)).scalars()
    }
    dt_a_club = {}
    for match in session.execute(
        select(MatchCoach).where(MatchCoach.fecha >= desde, MatchCoach.fecha <= hasta)
    ).scalars():
        dt_a_club[match.dt_local_id] = match.club_local_id
        dt_a_club[match.dt_visita_id] = match.club_visita_id

    def _convertir(entradas) -> list[EntradaSeleccion]:
        resultado = []
        for entrada in entradas:
            pj = carrera.get(entrada.dt_id, 0)
            resultado.append(
                EntradaSeleccion(
                    dt_id=entrada.dt_id,
                    dt=entrada.nombre,
                    club=clubes.get(dt_a_club.get(entrada.dt_id)),
                    elo=entrada.elo_actual,
                    delta=entrada.delta,
                    partidos=entrada.partidos,
                    pj_carrera=pj,
                    etiqueta="debutante" if pj < MIN_PJ_DEBUTANTE else None,
                )
            )
        return resultado

    return MovimientosSelecciones(
        desde=desde,
        hasta=hasta,
        subidas=_convertir(ranking.subidas)[:n],
        bajadas=_convertir(ranking.bajadas)[:n],
        total_partidos=ranking.total_partidos,
    )
