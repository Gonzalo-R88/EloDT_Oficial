from dataclasses import asdict

from scraping.competitions import get_competition
from scraping.dto import Fixture, MatchReport
from scraping.pipeline import build_schedule_url, load_normalized, season_is_aligned
from scraping.storage import RawStore


def _fixture(fecha):
    return Fixture(
        match_id=1, competition_code="GB1", season=2024, date=fecha, matchday="1",
        home_club_tm_id=1, home_club_name="A", away_club_tm_id=2, away_club_name="B",
        home_goals=0, away_goals=0,
    )


def _cache_temporada(tmp_path, fecha_reporte):
    """Arma un caché mínimo: un fixture con fecha heredada y su reporte."""
    store = RawStore(tmp_path)
    store.write_fixtures(
        "AR1N",
        2005,
        [
            asdict(
                Fixture(
                    match_id=1, competition_code="AR1N", season=2005,
                    date="2005-05-03", matchday="4.Matchday",
                    home_club_tm_id=1, home_club_name="A",
                    away_club_tm_id=2, away_club_name="B",
                    home_goals=1, away_goals=0,
                )
            )
        ],
    )
    store.write_match(
        "AR1N",
        2005,
        1,
        asdict(
            MatchReport(
                match_id=1, final_home_goals=1, final_away_goals=0,
                home_coach_tm_id=10, home_coach_name="DT A",
                away_coach_tm_id=20, away_coach_name="DT B",
                fecha=fecha_reporte,
            )
        ),
    )
    return store


def test_load_normalized_prefiere_la_fecha_del_reporte(tmp_path):
    """El fixture hereda la fecha del bloque; el reporte trae la fecha real."""
    store = _cache_temporada(tmp_path, fecha_reporte="2005-05-16")

    partidos = load_normalized(get_competition("AR1N"), 2005, store)

    assert partidos[0].date == "2005-05-16"


def test_load_normalized_usa_la_fecha_del_fixture_si_el_reporte_no_la_tiene(tmp_path):
    store = _cache_temporada(tmp_path, fecha_reporte=None)

    partidos = load_normalized(get_competition("AR1N"), 2005, store)

    assert partidos[0].date == "2005-05-03"


def test_season_alignment_accepts_european_and_calendar_years():
    assert season_is_aligned([_fixture("2024-08-11"), _fixture("2025-05-20")], 2024)
    assert season_is_aligned([_fixture("2024-02-10"), _fixture("2024-11-30")], 2024)


def test_season_alignment_accepts_split_season_requested_by_start_year():
    """Temporada agosto-junio pedida por el año de arranque (caso Argentina 2017)."""
    fixture = [_fixture("2016-08-26"), _fixture("2017-05-28")]
    assert season_is_aligned(fixture, 2016)
    assert season_is_aligned(fixture, 2017)


def test_season_alignment_accepts_split_season_requested_by_end_year():
    """Temporada agosto-junio pedida por el año en que termina (caso Europa 2024/25)."""
    fixture = [_fixture("2024-08-11"), _fixture("2025-05-20")]
    assert season_is_aligned(fixture, 2024)
    assert season_is_aligned(fixture, 2025)


def test_season_alignment_rejects_wrong_season():
    assert not season_is_aligned([_fixture("2026-02-21")], 2024)
    assert not season_is_aligned([], 2024)
    # Pedir 2000 y recibir la temporada actual sigue siendo un error.
    assert not season_is_aligned([_fixture("2026-08-01"), _fixture("2027-05-20")], 2000)


def test_get_competition_is_case_insensitive():
    assert get_competition("tdea").code == "TDeA"
    assert get_competition("gb1").code == "GB1"


def test_build_schedule_url_applies_saison_offset():
    url = build_schedule_url(get_competition("AR1N"), 2024)
    assert "saison_id=2023" in url
    assert "spieltagVon=1" in url
    assert "spieltagBis=99" in url


def test_build_schedule_url_uses_query_string():
    url = build_schedule_url(get_competition("CLI"), 2021)
    assert url.startswith("https://")
    assert "copa-libertadores/gesamtspielplan/pokalwettbewerb/CLI?" in url
    assert "saison_id=2020" in url
