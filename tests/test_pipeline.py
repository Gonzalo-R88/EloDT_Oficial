from scraping.competitions import get_competition
from scraping.dto import Fixture
from scraping.pipeline import build_schedule_url, season_is_aligned


def _fixture(fecha):
    return Fixture(
        match_id=1, competition_code="GB1", season=2024, date=fecha, matchday="1",
        home_club_tm_id=1, home_club_name="A", away_club_tm_id=2, away_club_name="B",
        home_goals=0, away_goals=0,
    )


def test_season_alignment_accepts_european_and_calendar_years():
    assert season_is_aligned([_fixture("2024-08-11"), _fixture("2025-05-20")], 2024)
    assert season_is_aligned([_fixture("2024-02-10"), _fixture("2024-11-30")], 2024)


def test_season_alignment_rejects_wrong_season():
    assert not season_is_aligned([_fixture("2026-02-21")], 2024)
    assert not season_is_aligned([], 2024)


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
