"""Catálogo de competencias candidatas para el scraping total (2000-2026).

Es la lista de universo del backfill: incluye las competencias ya cargadas más
las principales ligas de UEFA/CONMEBOL/CONCACAF. Cada entrada fue verificada
contra Transfermarkt parseando el fixture de una temporada de muestra (ver
`scripts/verify_competitions.py`); `est_matches` es el promedio de partidos por
temporada observado.

Este módulo es solo datos de planificación. Las competencias que se dan de alta
en la base siguen viviendo en `scraping/competitions.py` (`COMPETITIONS`).
"""

from __future__ import annotations

from dataclasses import dataclass

BACKFILL_FIRST_SEASON = 2000
BACKFILL_LAST_SEASON = 2026


@dataclass(frozen=True)
class LeagueCandidate:
    code: str
    name: str
    country: str
    confederation: str  # UEFA / CONMEBOL / CONCACAF
    kind: str  # liga / copa / internacional
    saison_offset: int
    est_matches: int  # partidos por temporada (promedio observado)
    tier: str  # S / A / B / C (provisional para el ELO)
    coefficient: float
    path: str = "wettbewerb"  # wettbewerb | pokalwettbewerb
    first_season: int = BACKFILL_FIRST_SEASON
    # Última temporada que existe en TM. `None` = sigue vigente. Sirve para no
    # reportar como "hueco" los años posteriores al cierre de una competencia y
    # para que el pipeline semanal no pida temporadas que ya no existen.
    last_season: int | None = None
    verified: bool = True
    note: str = ""


# Nota: `saison_offset=1` en ligas sudamericanas de año calendario (Transfermarkt
# agrupa la temporada real bajo el saison_id del año anterior).
CATALOG: tuple[LeagueCandidate, ...] = (
    # --- Argentina (ya cargadas) -----------------------------------------
    LeagueCandidate("AR1N", "Liga Profesional", "Argentina", "CONMEBOL", "liga", 1, 378, "A", 1.00,
                    last_season=2024,
                    note="TM la da por terminada en 23/24: desde 2025 la Primera va en ARG1/ARGC"),
    LeagueCandidate("ARG2", "Primera Nacional", "Argentina", "CONMEBOL", "liga", 1, 660, "C", 0.60),
    # Desde 2025 la Primera División se juega como Torneo Apertura + Torneo Clausura,
    # cada uno en su propia competencia de TM (30 equipos, 240 partidos por torneo).
    LeagueCandidate("ARG1", "Torneo Apertura (Primera División)", "Argentina", "CONMEBOL", "liga", 1, 240, "A", 1.00,
                    first_season=2025, note="temporada de año calendario: saison_id = año - 1"),
    LeagueCandidate("ARGC", "Torneo Clausura (Primera División)", "Argentina", "CONMEBOL", "liga", 1, 240, "A", 1.00,
                    first_season=2025, note="temporada de año calendario: saison_id = año - 1"),
    LeagueCandidate("CDLP", "Copa de la Liga Profesional", "Argentina", "CONMEBOL", "copa", 1, 196, "B", 0.80,
                    last_season=2024,
                    note="dejó de jugarse en 2024; desde 2025 la Primera va en ARG1/ARGC"),
    LeagueCandidate("CDCA", "Copa de la Liga - Playoffs", "Argentina", "CONMEBOL", "copa", 1, 4, "B", 0.80),
    LeagueCandidate("ARCA", "Copa Argentina", "Argentina", "CONMEBOL", "copa", 1, 63, "B", 0.80, "pokalwettbewerb"),
    # --- Conmebol ---------------------------------------------------------
    LeagueCandidate("CLI", "Copa Libertadores", "Conmebol", "CONMEBOL", "internacional", 1, 155, "S", 1.30, "pokalwettbewerb"),
    LeagueCandidate("CS", "Copa Sudamericana", "Conmebol", "CONMEBOL", "internacional", 1, 157, "A", 1.00, "pokalwettbewerb"),
    # OJO: `RESU` NO es la Recopa Sudamericana. En TM es "Relegation Superettan"
    # (playoffs de ascenso/descenso del fútbol sueco, noviembre, series de ida y
    # vuelta). Estuvo mal clasificado como competencia internacional de Conmebol
    # hasta 2026-10-28, lo que además etiquetaba clubes suecos como "Conmebol".
    LeagueCandidate("RESU", "Relegation Superettan (playoffs)", "Suecia", "UEFA", "copa", 1, 4, "B", 0.80,
                    "pokalwettbewerb", note="playoffs de ascenso/descenso suecos; NO es la Recopa"),
    # --- Sudamérica -------------------------------------------------------
    LeagueCandidate("BRA1", "Brasileirão Série A", "Brasil", "CONMEBOL", "liga", 1, 380, "A", 1.00),
    LeagueCandidate("BRA2", "Brasileirão Série B", "Brasil", "CONMEBOL", "liga", 1, 380, "B", 0.80),
    LeagueCandidate("URU1", "Primera División", "Uruguay", "CONMEBOL", "liga", 1, 120, "B", 0.80),
    LeagueCandidate("CLPD", "Liga de Primera", "Chile", "CONMEBOL", "liga", 1, 240, "B", 0.80),
    LeagueCandidate("COL1", "Primera A", "Colombia", "CONMEBOL", "liga", 1, 195, "B", 0.80),
    LeagueCandidate("EC1N", "LigaPro Serie A", "Ecuador", "CONMEBOL", "liga", 1, 240, "B", 0.80,
                    first_season=2025, note="TM sólo expone temporadas recientes (histórico incompleto)"),
    LeagueCandidate("TDeA", "Liga 1 Apertura", "Perú", "CONMEBOL", "liga", 1, 160, "B", 0.80),
    LeagueCandidate("TDeC", "Liga 1 Clausura", "Perú", "CONMEBOL", "liga", 1, 155, "B", 0.80),
    LeagueCandidate("PR1A", "Primera División Apertura", "Paraguay", "CONMEBOL", "liga", 1, 132, "B", 0.80),
    LeagueCandidate("PR1C", "Primera División Clausura", "Paraguay", "CONMEBOL", "liga", 1, 132, "B", 0.80),
    LeagueCandidate("BO1A", "División Profesional Apertura", "Bolivia", "CONMEBOL", "liga", 1, 200, "B", 0.80,
                    note="cobertura con huecos; el guard de temporada saltea los saison_id inválidos"),
    LeagueCandidate("BO1C", "División Profesional Clausura", "Bolivia", "CONMEBOL", "liga", 1, 240, "B", 0.80),
    LeagueCandidate("VZ1A", "Primera División Apertura", "Venezuela", "CONMEBOL", "liga", 1, 91, "B", 0.80),
    LeagueCandidate("VZ1C", "Primera División Clausura", "Venezuela", "CONMEBOL", "liga", 1, 91, "B", 0.80),
    # --- Concacaf ---------------------------------------------------------
    LeagueCandidate("MEX1", "Liga MX", "México", "CONCACAF", "liga", 1, 153, "A", 1.00),
    LeagueCandidate("MLS1", "Major League Soccer", "Estados Unidos", "CONCACAF", "liga", 1, 500, "A", 1.00),
    # --- UEFA: top 5 + segundas ------------------------------------------
    LeagueCandidate("GB1", "Premier League", "Inglaterra", "UEFA", "liga", 0, 380, "S", 1.30),
    LeagueCandidate("GB2", "Championship", "Inglaterra", "UEFA", "liga", 0, 552, "A", 1.00),
    LeagueCandidate("ES1", "LaLiga", "España", "UEFA", "liga", 0, 380, "S", 1.30),
    LeagueCandidate("ES2", "LaLiga 2", "España", "UEFA", "liga", 0, 462, "A", 1.00),
    LeagueCandidate("IT1", "Serie A", "Italia", "UEFA", "liga", 0, 380, "S", 1.30),
    LeagueCandidate("IT2", "Serie B", "Italia", "UEFA", "liga", 0, 380, "A", 1.00),
    LeagueCandidate("L1", "Bundesliga", "Alemania", "UEFA", "liga", 0, 306, "S", 1.30),
    LeagueCandidate("L2", "2. Bundesliga", "Alemania", "UEFA", "liga", 0, 306, "A", 1.00),
    LeagueCandidate("FR1", "Ligue 1", "Francia", "UEFA", "liga", 0, 306, "S", 1.30),
    LeagueCandidate("FR2", "Ligue 2", "Francia", "UEFA", "liga", 0, 340, "A", 1.00),
    # --- UEFA: resto de primeras -----------------------------------------
    LeagueCandidate("PO1", "Primeira Liga", "Portugal", "UEFA", "liga", 0, 306, "A", 1.00),
    LeagueCandidate("NL1", "Eredivisie", "Países Bajos", "UEFA", "liga", 0, 306, "A", 1.00),
    LeagueCandidate("BE1", "Pro League", "Bélgica", "UEFA", "liga", 0, 240, "A", 1.00),
    LeagueCandidate("TR1", "Süper Lig", "Turquía", "UEFA", "liga", 0, 360, "A", 1.00),
    LeagueCandidate("GR1", "Super League", "Grecia", "UEFA", "liga", 0, 182, "B", 0.80),
    LeagueCandidate("RU1", "Premier Liga", "Rusia", "UEFA", "liga", 0, 240, "A", 1.00),
    LeagueCandidate("UKR1", "Premier Liha", "Ucrania", "UEFA", "liga", 0, 240, "B", 0.80),
    LeagueCandidate("SC1", "Scottish Premiership", "Escocia", "UEFA", "liga", 0, 198, "B", 0.80),
    LeagueCandidate("A1", "Bundesliga", "Austria", "UEFA", "liga", 0, 192, "B", 0.80),
    LeagueCandidate("C1", "Super League", "Suiza", "UEFA", "liga", 0, 228, "B", 0.80),
    LeagueCandidate("DK1", "Superliga", "Dinamarca", "UEFA", "liga", 0, 132, "B", 0.80),
    LeagueCandidate("SE1", "Allsvenskan", "Suecia", "UEFA", "liga", 1, 240, "B", 0.80),
    LeagueCandidate("NO1", "Eliteserien", "Noruega", "UEFA", "liga", 1, 240, "B", 0.80),
    LeagueCandidate("PL1", "Ekstraklasa", "Polonia", "UEFA", "liga", 0, 306, "B", 0.80),
    LeagueCandidate("TS1", "Chance Liga", "Chequia", "UEFA", "liga", 0, 240, "B", 0.80),
    # --- Otras ligas fuertes ---------------------------------------------
    LeagueCandidate("JAP1", "J1 League", "Japón", "AFC", "liga", 1, 380, "B", 0.80),
    LeagueCandidate("SA1", "Saudi Pro League", "Arabia Saudita", "AFC", "liga", 0, 306, "B", 0.80),
)


def total_seasons(candidate: LeagueCandidate, first: int, last: int) -> int:
    """Cantidad de temporadas a scrapear para una competencia en el rango dado."""
    inicio = max(first, candidate.first_season)
    return max(0, last - inicio + 1)


def total_requests(candidate: LeagueCandidate, first: int, last: int) -> int:
    """Requests estimados = fixture (1) + un reporte por partido, por temporada."""
    return total_seasons(candidate, first, last) * (1 + candidate.est_matches)