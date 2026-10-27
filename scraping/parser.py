"""Parsers de HTML de Transfermarkt (fixture y reporte de partido)."""

from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from elo import classify_bench_impact
from scraping.dto import Fixture, MatchReport, TimelineEvent

logger = logging.getLogger(__name__)

_CLUB_ID_RE = re.compile(r"/verein/(\d+)")
_MATCH_ID_RE = re.compile(r"/spielbericht/(\d+)")
_TRAINER_ID_RE = re.compile(r"/trainer/(\d+)")
_DATE_RE = re.compile(r"/datum/(\d{4}-\d{2}-\d{2})")
_SCORE_RE = re.compile(r"(\d+)\s*:\s*(\d+)")
_LEFT_RE = re.compile(r"left:\s*([\d.]+)%")
_TEXT_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")


def _text(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(value.replace("\xa0", " ").split())


def _extract_date(row, current: Optional[str]) -> Optional[str]:
    """Extrae la fecha de la fila. Soporta link /datum/ (ligas) y texto (copas).

    La fecha sólo aparece en la primera fila de cada grupo, por lo que se
    propaga el último valor visto (`current`).
    """
    cell = row.select_one("td.hide-for-small")
    if cell is None:
        return current

    anchor = cell.select_one("a[href*='/datum/']")
    if anchor:
        match = _DATE_RE.search(anchor.get("href", ""))
        return match.group(1) if match else current

    text_match = _TEXT_DATE_RE.search(_text(cell.get_text(" ")))
    if text_match:
        day, month, year = text_match.group(1), text_match.group(2), text_match.group(3)
        if len(year) == 2:
            year = f"20{year}"
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return current


def parse_schedule(html: str, competition_code: str, season: int) -> list[Fixture]:
    """Extrae todos los partidos del fixture (`gesamtspielplan`) de una temporada."""
    soup = BeautifulSoup(html, "lxml")
    fixtures: list[Fixture] = []
    current_date: Optional[str] = None

    for anchor in soup.select("a.ergebnis-link"):
        href = anchor.get("href", "")
        match_id_match = _MATCH_ID_RE.search(href)
        if not match_id_match:
            continue

        score_match = _SCORE_RE.search(anchor.get_text(" ", strip=True))
        if not score_match:
            continue

        match_id = int(anchor.get("id") or match_id_match.group(1))
        home_goals, away_goals = int(score_match.group(1)), int(score_match.group(2))

        row = anchor.find_parent("tr")
        if row is None:
            continue

        team_links = row.select("td.hauptlink a[href*='/verein/']")
        if len(team_links) < 2:
            continue
        home_link, away_link = team_links[0], team_links[1]

        home_club_match = _CLUB_ID_RE.search(home_link.get("href", ""))
        away_club_match = _CLUB_ID_RE.search(away_link.get("href", ""))
        if not home_club_match or not away_club_match:
            continue

        # La fecha sólo aparece en la primera fila de cada grupo; se propaga.
        current_date = _extract_date(row, current_date)
        date_iso: Optional[str] = current_date

        # Ronda: en copas aparece en un tr.bg_Sturm previo; en ligas, en el headline.
        matchday: Optional[str] = None
        round_header = row.find_previous("tr", class_="bg_Sturm")
        if round_header is not None:
            round_text = _text(round_header.get_text(" "))
            if round_text and round_text.lower() != "schedule":
                matchday = round_text
        if matchday is None:
            headline = anchor.find_previous("div", class_="content-box-headline")
            matchday = _text(headline.get_text()) if headline else None

        fixtures.append(
            Fixture(
                match_id=match_id,
                competition_code=competition_code,
                season=season,
                date=date_iso,
                matchday=matchday,
                home_club_tm_id=int(home_club_match.group(1)),
                home_club_name=_text(home_link.get("title")) or _text(home_link.get_text()),
                away_club_tm_id=int(away_club_match.group(1)),
                away_club_name=_text(away_link.get("title")) or _text(away_link.get_text()),
                home_goals=home_goals,
                away_goals=away_goals,
            )
        )

    return fixtures


def _parse_coaches(soup: BeautifulSoup) -> tuple[Optional[int], Optional[str], Optional[int], Optional[str]]:
    """Extrae los DTs local y visitante del reporte (orden: home, away)."""
    links = soup.select("tr.bench-table__tr a[href*='/profil/trainer/']")
    home_id = home_name = away_id = away_name = None

    if links:
        first = links[0]
        id_match = _TRAINER_ID_RE.search(first.get("href", ""))
        home_id = int(id_match.group(1)) if id_match else None
        home_name = _text(first.get("title")) or _text(first.get_text())
    if len(links) >= 2:
        second = links[1]
        id_match = _TRAINER_ID_RE.search(second.get("href", ""))
        away_id = int(id_match.group(1)) if id_match else None
        away_name = _text(second.get("title")) or _text(second.get_text())

    return home_id, home_name, away_id, away_name


def _parse_events(soup: BeautifulSoup) -> list[TimelineEvent]:
    """Extrae los eventos de la línea de tiempo, asociando equipo y tipo."""
    events: list[TimelineEvent] = []
    timeline = soup.select_one("div.sb-zeitleiste-ereignisse")
    if timeline is None:
        return events

    for team, bar_class in (("home", "sb-leiste-heim"), ("away", "sb-leiste-gast")):
        bar = timeline.select_one(f"div.{bar_class}")
        if bar is None:
            continue
        for event in bar.select("div.sb-leiste-ereignis"):
            position_match = _LEFT_RE.search(event.get("style", ""))
            position = float(position_match.group(1)) if position_match else 0.0

            sprite = event.select_one("span.sb-sprite")
            classes = sprite.get("class", []) if sprite else []
            if "sb-tor" in classes or "sb-eigentor" in classes:
                event_type = "goal"
            elif "sb-wechsel" in classes:
                event_type = "sub"
            else:
                event_type = "card"

            events.append(TimelineEvent(team=team, type=event_type, position=position))

    return events


def _first_sub_position(events: list[TimelineEvent], team: str) -> Optional[float]:
    positions = [e.position for e in events if e.type == "sub" and e.team == team]
    return min(positions) if positions else None


def _score_at(events: list[TimelineEvent], cutoff: float) -> tuple[int, int]:
    home = sum(1 for e in events if e.type == "goal" and e.team == "home" and e.position <= cutoff)
    away = sum(1 for e in events if e.type == "goal" and e.team == "away" and e.position <= cutoff)
    return home, away


def _compute_bench_metrics(
    events: list[TimelineEvent],
    final_home: int,
    final_away: int,
) -> tuple[Optional[str], Optional[str], int, int]:
    """Calcula marcador previo a los cambios e impacto del banco por equipo."""
    marcador_local: Optional[str] = None
    marcador_visita: Optional[str] = None
    impacto_local = 0
    impacto_visita = 0

    cutoff_home = _first_sub_position(events, "home")
    if cutoff_home is not None:
        home_before, away_before = _score_at(events, cutoff_home)
        marcador_local = f"{home_before}:{away_before}"
        impacto_local = classify_bench_impact(
            home_before, away_before, final_home, final_away
        )

    cutoff_away = _first_sub_position(events, "away")
    if cutoff_away is not None:
        home_before, away_before = _score_at(events, cutoff_away)
        marcador_visita = f"{home_before}:{away_before}"
        impacto_visita = classify_bench_impact(
            away_before, home_before, final_away, final_home
        )

    return marcador_local, marcador_visita, impacto_local, impacto_visita


def parse_match_report(html: str, match_id: int) -> MatchReport:
    """Extrae DTs, resultado final, eventos e impacto del banco de un partido."""
    soup = BeautifulSoup(html, "lxml")

    final_home = final_away = 0
    score_found = False
    # El marcador principal vive en div.sb-endstand; span.matchresult pertenece
    # a la lista de otros partidos de la fecha y daría un resultado equivocado.
    score_element = soup.select_one("div.sb-endstand")
    if score_element:
        score_match = _SCORE_RE.search(score_element.get_text(" ", strip=True))
        if score_match:
            final_home, final_away = int(score_match.group(1)), int(score_match.group(2))
            score_found = True

    home_id, home_name, away_id, away_name = _parse_coaches(soup)
    events = _parse_events(soup)

    # Fallback: si no hubo marcador en el encabezado, reconstruirlo desde eventos.
    if not score_found:
        final_home = sum(1 for e in events if e.type == "goal" and e.team == "home")
        final_away = sum(1 for e in events if e.type == "goal" and e.team == "away")

    marcador_local, marcador_visita, impacto_local, impacto_visita = _compute_bench_metrics(
        events, final_home, final_away
    )

    return MatchReport(
        match_id=match_id,
        final_home_goals=final_home,
        final_away_goals=final_away,
        home_coach_tm_id=home_id,
        home_coach_name=home_name,
        away_coach_tm_id=away_id,
        away_coach_name=away_name,
        events=events,
        marcador_pre_cambios_local=marcador_local,
        marcador_pre_cambios_visita=marcador_visita,
        impacto_banco_local=impacto_local,
        impacto_banco_visita=impacto_visita,
    )
