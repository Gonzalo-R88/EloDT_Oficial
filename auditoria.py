"""Auditoría de datos: cobertura del caché contra la base, conflictos de fecha y calidad.

Capa de datos sin escritura ni dibujo (misma separación que `ranking.py`/`duel.py`):
las funciones de este módulo reciben datos ya leídos (fixtures del caché, filas de
la DB o rutas de reportes) y devuelven estructuras planas, fáciles de testear con
SQLite. La CLI está en `scripts/audit_data.py`.

Objetivo de la auditoría: saber qué porcentaje de los partidos que Transfermarkt
publica llegó realmente a la base. Un hueco en el caché (por ejemplo Argentina
2025-26, descartada por el guard de temporada) se ve como un año sin fixtures, y
se reporta con `ratio = 0` en lugar de desaparecer del informe.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from models import Coach, Competition, MatchCoach

ANIO_PRIMERA_TEMPORADA_DEFAULT = 2000


# ---------------------------------------------------------------------------
# Lectura del caché
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FixtureCrudo:
    """Un partido tal como está en `fixtures.json` del caché."""

    codigo: str
    temporada: int
    match_id: int
    fecha: Optional[date]


def _parse_fecha(valor: Optional[str]) -> Optional[date]:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def ruta_fixtures(data_dir: Path, codigo: str, temporada: int) -> Path:
    return Path(data_dir) / "raw" / codigo / str(temporada) / "fixtures.json"


def rutas_fixtures(data_dir: Path) -> list[tuple[str, int, Path]]:
    """Rutas de todos los fixtures cacheados como `(codigo, temporada, ruta)`."""
    resultado: list[tuple[str, int, Path]] = []
    for ruta in sorted(Path(data_dir).glob("raw/*/*/fixtures.json")):
        codigo = ruta.parent.parent.name
        try:
            temporada = int(ruta.parent.name)
        except ValueError:
            continue
        resultado.append((codigo, temporada, ruta))
    return resultado


def iter_fixtures(data_dir: Path) -> Iterator[FixtureCrudo]:
    """Itera los fixtures de todo el caché sin cargarlos todos en memoria a la vez."""
    for codigo, temporada, ruta in rutas_fixtures(data_dir):
        try:
            with open(ruta, encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except (OSError, json.JSONDecodeError):
            continue
        for item in datos:
            match_id = item.get("match_id")
            if match_id is None:
                continue
            yield FixtureCrudo(
                codigo=codigo,
                temporada=temporada,
                match_id=int(match_id),
                fecha=_parse_fecha(item.get("date")),
            )


# ---------------------------------------------------------------------------
# Cobertura por competencia y año calendario
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CoberturaCelda:
    """Partidos cachados y cargados de una competencia en un año calendario."""

    fixtures: int
    cargados: int

    @property
    def ratio(self) -> float:
        return round(self.cargados / self.fixtures, 4) if self.fixtures else 0.0


def construir_cobertura(
    fixtures: Iterable[FixtureCrudo],
    ids_en_db: set[int],
    primera_temporada: dict[str, int],
    anio_actual: int,
) -> tuple[dict[str, dict[int, CoberturaCelda]], dict[str, int]]:
    """Cuenta fixtures y cargados por competencia y año calendario.

    Devuelve `(cobertura, sin_fecha)`:
    - `cobertura[codigo][anio] = CoberturaCelda`, con todos los años desde la
      primera temporada de la competencia (o antes, si hay datos) hasta
      `anio_actual`. Los años sin fixtures cacheados quedan en 0 (huecos visibles).
    - `sin_fecha[codigo]`: fixtures cacheados sin fecha usable (no asignables a un año).
    """
    conteo: Counter[tuple[str, int]] = Counter()
    cargados: Counter[tuple[str, int]] = Counter()
    sin_fecha: Counter[str] = Counter()
    anio_min: dict[str, int] = {}

    for fixture in fixtures:
        if fixture.fecha is None:
            sin_fecha[fixture.codigo] += 1
            continue
        clave = (fixture.codigo, fixture.fecha.year)
        conteo[clave] += 1
        if fixture.match_id in ids_en_db:
            cargados[clave] += 1
        actual = anio_min.get(fixture.codigo)
        if actual is None or fixture.fecha.year < actual:
            anio_min[fixture.codigo] = fixture.fecha.year

    cobertura: dict[str, dict[int, CoberturaCelda]] = {}
    for codigo in sorted(set(primera_temporada) | set(anio_min)):
        inicial = primera_temporada.get(codigo, ANIO_PRIMERA_TEMPORADA_DEFAULT)
        if codigo in anio_min:
            inicial = min(inicial, anio_min[codigo])
        inicial = min(inicial, anio_actual)
        por_anio: dict[int, CoberturaCelda] = {}
        for anio in range(inicial, anio_actual + 1):
            por_anio[anio] = CoberturaCelda(
                fixtures=conteo.get((codigo, anio), 0),
                cargados=cargados.get((codigo, anio), 0),
            )
        cobertura[codigo] = por_anio

    return cobertura, dict(sin_fecha)


def cobertura_a_json(cobertura: dict[str, dict[int, CoberturaCelda]]) -> dict:
    """Forma serializable `{codigo: {anio: {"fixtures", "cargados", "ratio"}}}`."""
    return {
        codigo: {
            str(anio): {
                "fixtures": celda.fixtures,
                "cargados": celda.cargados,
                "ratio": celda.ratio,
            }
            for anio, celda in sorted(por_anio.items())
        }
        for codigo, por_anio in sorted(cobertura.items())
    }


def rangos_anios(anios: Sequence[int]) -> str:
    """Colapsa años consecutivos en rangos legibles: `[2017, 2018, 2020]` -> "2017-2018, 2020"."""
    ordenados = sorted(set(anios))
    if not ordenados:
        return ""
    partes: list[str] = []
    inicio = anterior = ordenados[0]
    for anio in ordenados[1:]:
        if anio == anterior + 1:
            anterior = anio
            continue
        partes.append(f"{inicio}-{anterior}" if inicio != anterior else str(inicio))
        inicio = anterior = anio
    partes.append(f"{inicio}-{anterior}" if inicio != anterior else str(inicio))
    return ", ".join(partes)


@dataclass(frozen=True)
class ResumenCompetencia:
    """Agregado por competencia, para el informe y para decidir qué publicar."""

    codigo: str
    fixtures: int
    cargados: int
    anios_hueco: list[int]
    anios_incompletos: list[int]
    ratio: float


def resumir_competencias(
    cobertura: dict[str, dict[int, CoberturaCelda]],
) -> list[ResumenCompetencia]:
    """Agrega la cobertura por competencia y lista los años con huecos.

    `anios_hueco`: años sin ningún fixture cacheado (ratio 0).
    `anios_incompletos`: años con fixtures pero con partidos no cargados.
    """
    resumenes: list[ResumenCompetencia] = []
    for codigo, por_anio in cobertura.items():
        fixtures_total = sum(celda.fixtures for celda in por_anio.values())
        cargados_total = sum(celda.cargados for celda in por_anio.values())
        resumenes.append(
            ResumenCompetencia(
                codigo=codigo,
                fixtures=fixtures_total,
                cargados=cargados_total,
                anios_hueco=[a for a, c in por_anio.items() if c.fixtures == 0],
                anios_incompletos=[
                    a for a, c in por_anio.items() if c.fixtures > 0 and c.cargados < c.fixtures
                ],
                ratio=round(cargados_total / fixtures_total, 4) if fixtures_total else 0.0,
            )
        )
    resumenes.sort(key=lambda r: (r.ratio, -r.fixtures))
    return resumenes


# ---------------------------------------------------------------------------
# Conflictos de fecha (un DT con más de un partido el mismo día)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Conflicto:
    """Un DT con varios partidos en la misma fecha (síntoma de fechas mal parseadas)."""

    dt_id: int
    nombre: str
    fecha: date
    partidos: int
    competencias: list[str]
    match_ids: list[Optional[int]]


def _consulta_participaciones():
    """Vista `UNION ALL` de (DT, fecha, competencia, partido) para local y visitante."""
    local = select(
        MatchCoach.dt_local_id.label("dt_id"),
        Coach.nombre.label("nombre"),
        Coach.apellido.label("apellido"),
        MatchCoach.fecha.label("fecha"),
        Competition.codigo.label("codigo"),
        MatchCoach.transfermarkt_match_id.label("match_id"),
    ).join(Coach, Coach.dt_id == MatchCoach.dt_local_id).join(
        Competition, Competition.competencia_id == MatchCoach.competencia_id
    )
    visita = select(
        MatchCoach.dt_visita_id.label("dt_id"),
        Coach.nombre.label("nombre"),
        Coach.apellido.label("apellido"),
        MatchCoach.fecha.label("fecha"),
        Competition.codigo.label("codigo"),
        MatchCoach.transfermarkt_match_id.label("match_id"),
    ).join(Coach, Coach.dt_id == MatchCoach.dt_visita_id).join(
        Competition, Competition.competencia_id == MatchCoach.competencia_id
    )
    return union_all(local, visita).subquery()


def conflictos_dt_dia(session: Session) -> list[Conflicto]:
    """Detecta DTs con más de un partido el mismo día.

    Cuenta en SQL (agrupa y filtra con `HAVING`), así que solo materializa las
    filas de las claves conflictivas: con 190k partidos las claves son pocas.
    """
    vista = _consulta_participaciones()
    claves = session.execute(
        select(vista.c.dt_id, vista.c.fecha)
        .group_by(vista.c.dt_id, vista.c.fecha)
        .having(func.count() > 1)
    ).all()
    if not claves:
        return []

    conjunto = {(fila[0], fila[1]) for fila in claves}
    dts = {clave[0] for clave in conjunto}
    fechas = {clave[1] for clave in conjunto}
    filas = session.execute(
        select(
            vista.c.dt_id,
            vista.c.nombre,
            vista.c.apellido,
            vista.c.fecha,
            vista.c.codigo,
            vista.c.match_id,
        ).where(vista.c.dt_id.in_(dts), vista.c.fecha.in_(fechas))
    ).all()

    agrupado: dict[tuple[int, date], dict] = defaultdict(
        lambda: {"nombre": "", "codigos": set(), "match_ids": [], "partidos": 0}
    )
    for dt_id, nombre, apellido, fecha, codigo, match_id in filas:
        if (dt_id, fecha) not in conjunto:
            continue
        entrada = agrupado[(dt_id, fecha)]
        entrada["nombre"] = f"{nombre} {apellido}".strip()
        entrada["partidos"] += 1
        if codigo:
            entrada["codigos"].add(codigo)
        if match_id is not None:
            entrada["match_ids"].append(int(match_id))

    conflictos = [
        Conflicto(
            dt_id=dt_id,
            nombre=entrada["nombre"],
            fecha=fecha,
            partidos=entrada["partidos"],
            competencias=sorted(entrada["codigos"]),
            match_ids=sorted(entrada["match_ids"]),
        )
        for (dt_id, fecha), entrada in agrupado.items()
    ]
    conflictos.sort(key=lambda c: (-c.partidos, c.fecha))
    return conflictos


# ---------------------------------------------------------------------------
# Último partido por competencia
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class UltimoPartido:
    codigo: str
    fecha: date
    dias: int
    partidos: int


def ultimos_partidos(session: Session, hoy: date) -> list[UltimoPartido]:
    """Último partido cargado y días transcurridos, por competencia."""
    filas = session.execute(
        select(
            Competition.codigo,
            func.max(MatchCoach.fecha),
            func.count(MatchCoach.partido_id),
        )
        .join(MatchCoach, MatchCoach.competencia_id == Competition.competencia_id)
        .group_by(Competition.codigo)
    ).all()
    resultado = [
        UltimoPartido(codigo=codigo, fecha=fecha, dias=(hoy - fecha).days, partidos=total)
        for codigo, fecha, total in filas
        if codigo and fecha
    ]
    resultado.sort(key=lambda u: u.fecha)
    return resultado


# ---------------------------------------------------------------------------
# Estimación de reportes sin DT (muestra)
# ---------------------------------------------------------------------------
def rutas_reportes(data_dir: Path) -> list[Path]:
    return sorted(Path(data_dir).glob("raw/*/*/matches/*.json"))


def estimar_dt_faltante(
    rutas: Sequence[Path],
    muestra: int,
    semilla: int = 7,
) -> dict[int, dict[str, int]]:
    """Estima el porcentaje de reportes sin algún DT, agrupado por quinquenio.

    `rutas` son los JSON de `raw/{codigo}/{temporada}/matches/{id}.json`; el
    quinquenio sale del directorio de temporada. Es una estimación: leer los
    ~260k reportes en `/mnt/f` tarda demasiado.
    """
    if muestra <= 0 or not rutas:
        return {}
    elegidas = random.Random(semilla).sample(list(rutas), min(muestra, len(rutas)))

    acumulado: dict[int, dict[str, int]] = defaultdict(lambda: {"reportes": 0, "sin_dt": 0})
    for ruta in elegidas:
        try:
            temporada = int(ruta.parent.parent.name)
        except ValueError:
            continue
        quinquenio = (temporada // 5) * 5
        acumulado[quinquenio]["reportes"] += 1
        try:
            with open(ruta, encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except (OSError, json.JSONDecodeError):
            continue
        if datos.get("home_coach_tm_id") is None or datos.get("away_coach_tm_id") is None:
            acumulado[quinquenio]["sin_dt"] += 1

    return {
        quinquenio: {
            **valores,
            "pct_sin_dt": round(100 * valores["sin_dt"] / valores["reportes"], 1)
            if valores["reportes"]
            else 0.0,
        }
        for quinquenio, valores in sorted(acumulado.items())
    }


# ---------------------------------------------------------------------------
# Cobertura del catálogo
# ---------------------------------------------------------------------------
def primera_temporada_por_competencia() -> dict[str, int]:
    """Primera temporada declarada en el catálogo (no consulta Transfermarkt)."""
    from scraping.competitions import COMPETITIONS
    from scraping.leagues_catalog import CATALOG

    primeras = {codigo: ANIO_PRIMERA_TEMPORADA_DEFAULT for codigo in COMPETITIONS}
    for candidato in CATALOG:
        primeras[candidato.code] = candidato.first_season
    return primeras
