"""Pipeline de ingesta: scraping, normalización y persistencia con ELO."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from db import create_session
from models import Club, Coach, Competition
from services import STATUS_DUPLICATE, STATUS_PROCESSED, process_match_elo
from scraping.client import TransfermarktClient
from scraping.competitions import CompetitionConfig, get_competition
from scraping.dto import Fixture, MatchReport, NormalizedMatch
from scraping.parser import parse_match_report, parse_schedule
from scraping.storage import RawStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
def build_schedule_url(config: CompetitionConfig, season: int) -> str:
    # `season` es el año real de la temporada; Transfermarkt usa su propio
    # `saison_id` (offset por competencia). El rango `spieltagVon`/`spieltagBis`
    # fuerza el fixture completo: la temporada más reciente sólo muestra la
    # fecha actual por defecto. El límite superior es holgado (TM lo recorta).
    saison_id = season - config.saison_offset
    return (
        f"https://{settings.transfermarkt_domain}/{config.slug}/gesamtspielplan/"
        f"{config.path}/{config.code}?saison_id={saison_id}&spieltagVon=1&spieltagBis=99"
    )


def build_match_url(match_id: int) -> str:
    return f"https://{settings.transfermarkt_domain}/spielbericht/index/spielbericht/{match_id}"


def season_is_aligned(fixtures: list[Fixture], season: int) -> bool:
    """Verifica que el fixture descargado corresponda a la temporada pedida.

    Cuando Transfermarkt no tiene el `saison_id` solicitado devuelve el fixture
    de la temporada actual; eso cachearía partidos de otro año bajo el directorio
    equivocado. Se considera alineado si el año pedido cae **dentro** del rango de
    fechas del fixture.

    Antes se exigía que la temporada arrancara exactamente en `season`, lo que
    descartaba las temporadas partidas (agosto-junio): al pedir 2017, TM devolvía
    la 2016/17 (fechas de 2016) y se tiraba el fixture completo. Eso dejó a
    Argentina sin 2017-2020 en la base.
    """
    years = [int(f.date[:4]) for f in fixtures if f.date]
    if not years:
        return False
    return min(years) <= season <= max(years)


# ---------------------------------------------------------------------------
# Scraping (con caché reanudable)
# ---------------------------------------------------------------------------
def scrape_season(
    config: CompetitionConfig,
    season: int,
    client: TransfermarktClient,
    store: RawStore,
    refresh: bool = False,
    limit: Optional[int] = None,
) -> list[Fixture]:
    """Descarga y cachea el fixture y los reportes de una temporada.

    `limit` permite descargar sólo los primeros N reportes (útil para pruebas).
    Si Transfermarkt devuelve una temporada distinta a la pedida, se omite (no se
    cachea) para no contaminar la base con partidos de otro año.
    """
    schedule_url = build_schedule_url(config, season)
    if store.has_fixtures(config.code, season) and not refresh:
        logger.info("Fixture %s %s en caché; no se descarga.", config.code, season)
        fixtures = [Fixture(**item) for item in store.read_fixtures(config.code, season)]
        if fixtures and not season_is_aligned(fixtures, season):
            logger.warning(
                "Fixture %s %s desalineado (no arranca en %s); se omite.",
                config.code, season, season,
            )
            return []
    else:
        logger.info("Descargando fixture %s %s...", config.code, season)
        html = client.get(
            schedule_url,
            referer=f"https://{settings.transfermarkt_domain}/",
        )
        fixtures = parse_schedule(html, config.code, season)
        if fixtures and not season_is_aligned(fixtures, season):
            logger.warning(
                "Fixture %s %s desalineado (TM devolvió otra temporada); no se cachea.",
                config.code, season,
            )
            return []
        store.write_fixtures(config.code, season, [asdict(f) for f in fixtures])
        logger.info("Fixture %s %s: %s partidos.", config.code, season, len(fixtures))

    pending = [f for f in fixtures if refresh or not store.has_match(config.code, season, f.match_id)]
    if limit is not None:
        pending = pending[:limit]
    logger.info(
        "Reportes %s %s: %s pendientes de %s.",
        config.code, season, len(pending), len(fixtures),
    )
    for index, fixture in enumerate(pending, start=1):
        html = client.get(build_match_url(fixture.match_id), referer=schedule_url)
        report = parse_match_report(html, fixture.match_id)
        store.write_match(config.code, season, fixture.match_id, asdict(report))
        logger.info(
            "  [%s/%s] partido %s cacheado.", index, len(pending), fixture.match_id
        )

    return fixtures


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------
def infer_factor_k(config: CompetitionConfig, matchday: Optional[str]) -> int:
    """Infiere el factor K según la instancia (final, eliminación o regular)."""
    if config.kind == "liga":
        return 20
    text = (matchday or "").lower()
    if not text or text == "schedule":
        return 20
    # Final (excluyendo semifinal/quarterfinal)
    if "final" in text and "semi" not in text and "quarter" not in text and "cuarto" not in text:
        return 40
    if any(k in text for k in ("last 16", "round of 16", "quarter", "cuarto", "semi", "knockout", "octavo")):
        return 30
    return 20


def load_normalized(
    config: CompetitionConfig,
    season: int,
    store: RawStore,
) -> list[NormalizedMatch]:
    """Combina fixture + reportes cacheados en partidos normalizados."""
    if not store.has_fixtures(config.code, season):
        raise FileNotFoundError(
            f"No hay fixture cacheado para {config.code} {season}. Ejecutá el scrape primero."
        )

    normalized: list[NormalizedMatch] = []
    for raw in store.read_fixtures(config.code, season):
        fixture = Fixture(**raw)
        if not store.has_match(config.code, season, fixture.match_id):
            continue
        report = MatchReport(**store.read_match(config.code, season, fixture.match_id))

        normalized.append(
            NormalizedMatch(
                tm_match_id=fixture.match_id,
                competition_code=config.code,
                # La fecha del fixture no es confiable (TM la imprime una vez por
                # bloque y las filas siguientes la heredan); la del reporte sí.
                date=report.fecha or fixture.date or "",
                factor_k=infer_factor_k(config, fixture.matchday),
                home_club_tm_id=fixture.home_club_tm_id,
                home_club_name=fixture.home_club_name,
                away_club_tm_id=fixture.away_club_tm_id,
                away_club_name=fixture.away_club_name,
                home_goals=fixture.home_goals,
                away_goals=fixture.away_goals,
                home_coach_tm_id=report.home_coach_tm_id,
                home_coach_name=report.home_coach_name,
                away_coach_tm_id=report.away_coach_tm_id,
                away_coach_name=report.away_coach_name,
                marcador_pre_cambios_local=report.marcador_pre_cambios_local,
                marcador_pre_cambios_visita=report.marcador_pre_cambios_visita,
                impacto_banco_local=report.impacto_banco_local,
                impacto_banco_visita=report.impacto_banco_visita,
            )
        )

    normalized.sort(key=lambda m: (m.date or "9999-99-99", m.tm_match_id))
    return normalized


# ---------------------------------------------------------------------------
# Resolución de entidades
# ---------------------------------------------------------------------------
def split_name(full_name: str) -> tuple[str, str]:
    """Divide un nombre completo en (nombre, apellido)."""
    parts = (full_name or "").split()
    if not parts:
        return "Desconocido", "-"
    if len(parts) == 1:
        return parts[0], "-"
    return " ".join(parts[:-1]), parts[-1]


def ensure_competition(session: Session, config: CompetitionConfig) -> Competition:
    competition = session.execute(
        select(Competition).where(Competition.codigo == config.code)
    ).scalar_one_or_none()
    if competition is None:
        competition = Competition(
            codigo=config.code,
            transfermarkt_id=config.transfermarkt_id,
            nombre=config.name,
            pais=config.country,
            tipo=config.kind,
            nivel=config.tier,
            coeficiente=config.coefficient,
        )
        session.add(competition)
        session.flush()
    return competition


def ensure_club(session: Session, tm_id: int, name: str, country: str) -> Club:
    club = session.execute(
        select(Club).where(Club.transfermarkt_id == tm_id)
    ).scalar_one_or_none()
    if club is None:
        club = Club(transfermarkt_id=tm_id, nombre=name, pais=country)
        session.add(club)
        session.flush()
    return club


def ensure_coach(session: Session, tm_id: int, full_name: str) -> Coach:
    coach = session.execute(
        select(Coach).where(Coach.transfermarkt_id == tm_id)
    ).scalar_one_or_none()
    if coach is None:
        nombre, apellido = split_name(full_name)
        coach = Coach(
            transfermarkt_id=tm_id,
            nombre=nombre,
            apellido=apellido,
        )
        session.add(coach)
        session.flush()
    return coach


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def persist_matches(
    matches: list[NormalizedMatch],
    session: Optional[Session] = None,
) -> dict[str, int]:
    """Inserta entidades y procesa el ELO en orden cronológico."""
    own_session = session is None
    db_session = session or create_session()

    stats = {"procesados": 0, "duplicados": 0, "sin_dt": 0, "sin_fecha": 0}
    competition_cache: dict[str, Competition] = {}

    try:
        for match in matches:
            if match.home_coach_tm_id is None or match.away_coach_tm_id is None:
                stats["sin_dt"] += 1
                logger.warning("Partido %s sin DT (interino/ausente); se omite.", match.tm_match_id)
                continue
            if not match.date:
                stats["sin_fecha"] += 1
                logger.warning("Partido %s sin fecha; se omite.", match.tm_match_id)
                continue

            config = get_competition(match.competition_code)
            competition = competition_cache.get(config.code)
            if competition is None:
                competition = ensure_competition(db_session, config)
                competition_cache[config.code] = competition

            home_club = ensure_club(
                db_session, match.home_club_tm_id, match.home_club_name, config.country
            )
            away_club = ensure_club(
                db_session, match.away_club_tm_id, match.away_club_name, config.country
            )
            home_coach = ensure_coach(
                db_session, match.home_coach_tm_id, match.home_coach_name or ""
            )
            away_coach = ensure_coach(
                db_session, match.away_coach_tm_id, match.away_coach_name or ""
            )

            status = process_match_elo(
                dt_local_id=home_coach.dt_id,
                dt_visita_id=away_coach.dt_id,
                goles_local=match.home_goals,
                goles_visita=match.away_goals,
                competencia_id=competition.competencia_id,
                club_local_id=home_club.club_id,
                club_visita_id=away_club.club_id,
                factor_k=match.factor_k,
                marcador_pre_cambios_local=match.marcador_pre_cambios_local,
                marcador_pre_cambios_visita=match.marcador_pre_cambios_visita,
                impacto_banco_local=match.impacto_banco_local,
                impacto_banco_visita=match.impacto_banco_visita,
                fecha=match.date,
                transfermarkt_match_id=match.tm_match_id,
                session=db_session,
            )
            if status == STATUS_PROCESSED:
                stats["procesados"] += 1
            elif status == STATUS_DUPLICATE:
                stats["duplicados"] += 1

        if own_session:
            db_session.commit()
        else:
            db_session.flush()

        logger.info("Persistencia finalizada: %s", stats)
        return stats

    except Exception:
        if own_session:
            db_session.rollback()
        raise
    finally:
        if own_session:
            db_session.close()


# ---------------------------------------------------------------------------
# Reporte de cobertura
# ---------------------------------------------------------------------------
def coverage_report(config: CompetitionConfig, season: int, store: RawStore) -> dict[str, int]:
    """Resume la calidad de la ingesta cacheada de una temporada."""
    if not store.has_fixtures(config.code, season):
        raise FileNotFoundError(f"No hay fixture cacheado para {config.code} {season}.")

    report = {
        "partidos": 0,
        "con_reporte": 0,
        "sin_fecha": 0,
        "sin_dt_local": 0,
        "sin_dt_visita": 0,
        "marcador_discrepante": 0,
        "con_impacto_banco": 0,
    }

    for raw in store.read_fixtures(config.code, season):
        fixture = Fixture(**raw)
        report["partidos"] += 1
        if not fixture.date:
            report["sin_fecha"] += 1
        if not store.has_match(config.code, season, fixture.match_id):
            continue
        report["con_reporte"] += 1
        match = MatchReport(**store.read_match(config.code, season, fixture.match_id))
        if match.home_coach_tm_id is None:
            report["sin_dt_local"] += 1
        if match.away_coach_tm_id is None:
            report["sin_dt_visita"] += 1
        if (match.final_home_goals, match.final_away_goals) != (fixture.home_goals, fixture.away_goals):
            report["marcador_discrepante"] += 1
        if match.marcador_pre_cambios_local or match.marcador_pre_cambios_visita:
            report["con_impacto_banco"] += 1

    return report
