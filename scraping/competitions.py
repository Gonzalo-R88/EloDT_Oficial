"""Registro de competencias soportadas.

Agregar una nueva liga/competencia (España, Inglaterra, Brasil, etc.) es tan
simple como sumar una entrada a `COMPETITIONS`. El motor de ELO y el scraper
son genéricos.

Notas de Transfermarkt:
- El slug de la URL se ignora; la competencia se resuelve por `code`.
- Las ligas usan el path `wettbewerb`; las copas usan `pokalwettbewerb`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CompetitionConfig:
    code: str
    slug: str
    name: str
    country: str
    tier: str  # S / A / B / C
    coefficient: float
    kind: str  # liga / copa / internacional
    path: str = "wettbewerb"  # wettbewerb | pokalwettbewerb
    transfermarkt_id: Optional[int] = None
    # Transfermarkt agrupa las temporadas sudamericanas de año calendario bajo
    # el `saison_id` del año anterior (ej. la temporada 2024 usa saison_id 2023).
    # El offset convierte el año real de temporada al `saison_id` de la URL.
    saison_offset: int = 0
    # Última temporada que existe en TM (None = sigue vigente). Sirve para que la
    # actualización semanal no pida competencias que ya cerraron (AR1N, CDLP).
    last_season: Optional[int] = None
    # Descarta los partidos de categorías juveniles por nombre de equipo (sub-15 a
    # sub-23). Los amistosos (`FS`) mezclan mayores y juveniles bajo el mismo código.
    filtrar_juveniles: bool = False
    # Las eliminatorias y los torneos de selecciones no tienen un `saison_id` fijo y
    # hay que probar varios años (`_scrape_selecciones`). Los amistosos sí siguen la
    # temporada regular julio-junio.
    ediciones_irregulares: bool = True
    # Competencia de carga única desde fuentes externas (no existe en TM). El scraper
    # y la actualización semanal la ignoran: `historico.py` la carga una vez.
    historico: bool = False


# Niveles y coeficientes según el documento maestro v1.
COMPETITIONS: dict[str, CompetitionConfig] = {
    # Argentina
    "AR1N": CompetitionConfig(
        code="AR1N", slug="primera-division", name="Liga Profesional",
        country="Argentina", tier="A", coefficient=1.00, kind="liga",
        path="wettbewerb", saison_offset=1, last_season=2024,
    ),
    "ARG2": CompetitionConfig(
        code="ARG2", slug="primera-nacional", name="Primera Nacional",
        country="Argentina", tier="C", coefficient=0.60, kind="liga",
        path="wettbewerb", saison_offset=1,
    ),
    "CDLP": CompetitionConfig(
        code="CDLP", slug="copa-de-la-liga-profesional-de-futbol",
        name="Copa de la Liga Profesional", country="Argentina", tier="B",
        coefficient=0.80, kind="copa", path="wettbewerb", saison_offset=1,
        last_season=2024,
    ),
    "CDCA": CompetitionConfig(
        code="CDCA", slug="copa-diego-armando-maradona-fase-campeon",
        name="Copa de la Liga Profesional - Playoffs", country="Argentina",
        tier="B", coefficient=0.80, kind="copa", path="wettbewerb", saison_offset=1,
    ),
    "ARCA": CompetitionConfig(
        code="ARCA", slug="copa-argentina", name="Copa Argentina",
        country="Argentina", tier="B", coefficient=0.80, kind="copa",
        path="pokalwettbewerb", saison_offset=1,
    ),
    # Histórico argentino (carga única desde fuentes externas, no existe en TM)
    "ARGH": CompetitionConfig(
        code="ARGH", slug="argentina-historico", name="Primera División (histórico)",
        country="Argentina", tier="A", coefficient=1.00, kind="liga",
        saison_offset=1, last_season=2014, historico=True,
    ),
    "ARG2H": CompetitionConfig(
        code="ARG2H", slug="primera-nacional-historico",
        name="Primera B Nacional (histórico)", country="Argentina", tier="C",
        coefficient=0.60, kind="liga", saison_offset=1, last_season=2014,
        historico=True,
    ),
    # Conmebol (competencias puente entre ligas sudamericanas)
    "CLI": CompetitionConfig(
        code="CLI", slug="copa-libertadores", name="Copa Libertadores",
        country="Conmebol", tier="S", coefficient=1.30, kind="internacional",
        path="pokalwettbewerb", saison_offset=1,
    ),
    "CS": CompetitionConfig(
        code="CS", slug="copa-sudamericana", name="Copa Sudamericana",
        country="Conmebol", tier="A", coefficient=1.00, kind="internacional",
        path="pokalwettbewerb", saison_offset=1,
    ),
}


# Competencias de selecciones que sí siguen la temporada regular de TM (julio-junio);
# el resto se baja probando varios `saison_id` (`_scrape_selecciones`).
_TEMPORADA_REGULAR = frozenset({"FS"})

# Competencias donde hay que descartar los partidos de categorías juveniles.
_FILTRAR_JUVENILES = frozenset({"FS"})


def get_competition(code: str) -> CompetitionConfig:
    """Devuelve la configuración de una competencia por su código (sin distinguir mayúsculas)."""
    if code in COMPETITIONS:
        return COMPETITIONS[code]
    lowered = {key.lower(): key for key in COMPETITIONS}
    key = lowered.get(str(code).strip().lower())
    if key is None:
        raise KeyError(
            f"Competencia '{code}' no registrada. "
            f"Disponibles: {', '.join(sorted(COMPETITIONS))}"
        )
    return COMPETITIONS[key]


def _slugify(name: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower() or "competition"


def _register_catalog() -> None:
    """Da de alta en `COMPETITIONS` las ligas verificadas del catálogo global.

    Las competencias ya definidas a mano (Argentina + Conmebol) tienen prioridad
    y no se sobreescriben. El slug es irrelevante para Transfermarkt (la URL se
    resuelve por `code`), pero se genera legible.
    """
    from scraping.leagues_catalog import CATALOG

    for candidate in CATALOG:
        if candidate.code in COMPETITIONS:
            continue
        COMPETITIONS[candidate.code] = CompetitionConfig(
            code=candidate.code,
            slug=_slugify(candidate.name),
            name=candidate.name,
            country=candidate.country,
            tier=candidate.tier,
            coefficient=candidate.coefficient,
            kind=candidate.kind,
            path=candidate.path,
            saison_offset=candidate.saison_offset,
            last_season=candidate.last_season,
            filtrar_juveniles=candidate.code in _FILTRAR_JUVENILES,
            ediciones_irregulares=candidate.code not in _TEMPORADA_REGULAR,
        )


_register_catalog()
