from dataclasses import asdict

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Base, Club
from scraping.competitions import get_competition
from scraping.dto import Fixture, MatchReport, NormalizedMatch
from scraping.pipeline import (
    PAIS_DESCONOCIDO,
    build_schedule_url,
    load_normalized,
    persist_matches,
    season_is_aligned,
)
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


def _partido_normalizado(competicion, fecha, local_tm, visita_tm, match_id):
    return NormalizedMatch(
        tm_match_id=match_id, competition_code=competicion, date=fecha, factor_k=20,
        home_club_tm_id=local_tm, home_club_name=f"Club {local_tm}",
        away_club_tm_id=visita_tm, away_club_name=f"Club {visita_tm}",
        home_goals=1, away_goals=0,
        home_coach_tm_id=100 + match_id, home_coach_name=f"DT {100 + match_id}",
        away_coach_tm_id=200 + match_id, away_coach_name=f"DT {200 + match_id}",
        marcador_pre_cambios_local=None, marcador_pre_cambios_visita=None,
        impacto_banco_local=0, impacto_banco_visita=0,
    )


def test_persist_matches_no_usa_conmebol_como_pais_de_club():
    """Un club que aparece primero en la Libertadores no queda con país "Conmebol"."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    persist_matches([_partido_normalizado("CLI", "2024-04-04", 9001, 9002, 1)], session=session)

    paises = {
        club.transfermarkt_id: club.pais
        for club in session.execute(select(Club)).scalars()
    }
    assert paises == {9001: PAIS_DESCONOCIDO, 9002: PAIS_DESCONOCIDO}
    session.close()


def test_persist_matches_corrige_el_pais_cuando_juega_una_liga():
    """Cuando ese club juega después una liga doméstica, se le pone el país de la liga."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    persist_matches([_partido_normalizado("CLI", "2024-04-04", 9101, 9102, 2)], session=session)
    persist_matches([_partido_normalizado("AR1N", "2024-05-11", 9101, 9102, 3)], session=session)

    paises = {
        club.transfermarkt_id: club.pais
        for club in session.execute(select(Club)).scalars()
    }
    assert paises == {9101: "Argentina", 9102: "Argentina"}
    session.close()


def test_season_alignment_accepts_european_and_calendar_years():
    assert season_is_aligned([_fixture("2024-08-11"), _fixture("2025-05-20")], 2024)
    assert season_is_aligned([_fixture("2024-02-10"), _fixture("2024-11-30")], 2024)


def test_ensure_competition_sincroniza_metadatos_del_catalogo():
    """Si el catálogo cambia nombre/país/tipo, la carga lo refleja (sin tocar el ELO)."""
    from decimal import Decimal

    from models import Competition
    from scraping.pipeline import ensure_competition

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        Competition(
            codigo="RESU", nombre="Recopa Sudamericana", pais="Conmebol",
            tipo="internacional", nivel="B", coeficiente=Decimal("0.80"),
        )
    )
    session.commit()

    competition = ensure_competition(session, get_competition("RESU"))

    assert competition.nombre == "Relegation Superettan (playoffs)"
    assert competition.pais == "Suecia"
    assert competition.tipo == "copa"
    assert competition.coeficiente == Decimal("0.80")  # el ELO no se toca
    session.close()


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


# ---------------------------------------------------------------------------
# Actualización incremental (T2.3)
# ---------------------------------------------------------------------------
from datetime import date  # noqa: E402

from scraping.competitions import CompetitionConfig  # noqa: E402
from scraping.pipeline import (  # noqa: E402
    scrape_incremental,
    temporada_cerrada,
    temporadas_en_curso,
)


def _config(kind="liga", offset=1, last_season=None):
    return CompetitionConfig(
        code="AR1N", slug="liga", name="Liga", country="Argentina",
        tier="A", coefficient=1.0, kind=kind, saison_offset=offset,
        last_season=last_season,
    )


def _html_fixture(partidos):
    filas = []
    for match_id, fecha, local, visita in partidos:
        filas.append(
            f'<tr><td class="hide-for-small">Sat <a href="/datum/{fecha}">{fecha}</a></td>'
            f'<td class="text-right no-border-rechts hauptlink">'
            f'<a title="{local}" href="/x/spielplan/verein/{match_id}">{local}</a></td>'
            f'<td class="zentriert hauptlink"><a class="ergebnis-link" id="{match_id}" '
            f'href="/spielbericht/index/spielbericht/{match_id}">1:0</a></td>'
            f'<td class="no-border-links hauptlink">'
            f'<a title="{visita}" href="/y/spielplan/verein/9">{visita}</a></td></tr>'
        )
    return f"<html><body><table><tbody>{''.join(filas)}</tbody></table></body></html>"


def _html_reporte(fecha):
    return (
        f'<html><body><div class="sb-endstand">1:0</div>'
        f'<p class="sb-datum"><a href="/datum/{fecha}">Sat, {fecha}</a></p>'
        '<table>'
        '<tr class="bench-table__tr"><td><a title="DT A" href="/a/profil/trainer/11">DT A</a></td></tr>'
        '<tr class="bench-table__tr"><td><a title="DT B" href="/b/profil/trainer/22">DT B</a></td></tr>'
        '</table></body></html>'
    )


class _ClienteFalso:
    """Cliente de prueba: cuenta requests y responde según la URL."""

    def __init__(self, partidos):
        self.partidos = partidos
        self.pedidos: list[str] = []

    def get(self, url, referer=None):
        self.pedidos.append(url)
        if "/spielbericht/index/spielbericht/" in url:
            match_id = int(url.rsplit("/", 1)[-1])
            fecha = next(f for m, f, _, _ in self.partidos if m == match_id)
            return _html_reporte(fecha)
        return _html_fixture(self.partidos)

    @property
    def reportes_pedidos(self):
        return [u for u in self.pedidos if "/spielbericht/index/spielbericht/" in u]


def test_temporadas_en_curso_por_tipo_de_liga():
    europa = _config(offset=0)
    assert temporadas_en_curso(europa, date(2026, 3, 15)) == [2025, 2024]
    assert temporadas_en_curso(europa, date(2026, 8, 15)) == [2026, 2025]

    calendario = _config(offset=1)
    assert temporadas_en_curso(calendario, date(2026, 3, 15)) == [2026, 2025]


def test_temporadas_en_curso_selecciones():
    selecciones = _config(kind="selecciones")
    temporadas = temporadas_en_curso(selecciones, date(2026, 3, 15))

    assert 2026 in temporadas
    assert min(temporadas) <= 2022  # las eliminatorias viven en años anteriores


def test_temporada_cerrada_respeta_last_season():
    assert temporada_cerrada(_config(last_season=2024), date(2026, 3, 1))
    assert not temporada_cerrada(_config(last_season=None), date(2026, 3, 1))


def test_scrape_incremental_solo_baja_lo_que_falta(tmp_path):
    partidos = [
        (101, "2026-10-20", "Club A", "Club B"),
        (102, "2026-10-21", "Club C", "Club D"),
    ]
    cliente = _ClienteFalso(partidos)
    store = RawStore(tmp_path)
    # El 101 ya estaba cacheado: no se debe volver a pedir.
    store.write_match("AR1N", 2026, 101, {"match_id": 101, "fecha": "2026-10-20"})

    stats = scrape_incremental(
        _config(), cliente, store, semana_fin=date(2026, 11, 1), hoy=date(2026, 11, 2)
    )

    assert stats["reportes"] == 1
    assert len(cliente.reportes_pedidos) == 1
    assert cliente.reportes_pedidos[0].endswith("/102")
    assert store.has_match("AR1N", 2026, 102)


def test_scrape_incremental_respeta_la_semana_de_cierre(tmp_path):
    partidos = [
        (201, "2026-10-28", "Club A", "Club B"),
        (202, "2026-11-15", "Club C", "Club D"),  # después del cierre
    ]
    cliente = _ClienteFalso(partidos)
    store = RawStore(tmp_path)

    stats = scrape_incremental(
        _config(), cliente, store, semana_fin=date(2026, 11, 1), hoy=date(2026, 11, 2)
    )

    assert stats["reportes"] == 1
    assert stats["omitidos_fecha"] == 1
    assert store.has_match("AR1N", 2026, 201)
    assert not store.has_match("AR1N", 2026, 202)


def test_scrape_incremental_dry_run_no_pide_reportes(tmp_path):
    cliente = _ClienteFalso([(301, "2026-10-20", "A", "B")])
    store = RawStore(tmp_path)

    stats = scrape_incremental(
        _config(), cliente, store, semana_fin=date(2026, 11, 1),
        hoy=date(2026, 11, 2), dry_run=True,
    )

    assert cliente.pedidos == []
    assert stats["fixtures"] >= 1
    assert stats["reportes"] == 0


def test_scrape_incremental_saltea_competencias_cerradas(tmp_path):
    cliente = _ClienteFalso([(401, "2026-10-20", "A", "B")])
    store = RawStore(tmp_path)

    stats = scrape_incremental(
        _config(last_season=2024), cliente, store, hoy=date(2026, 11, 2)
    )

    assert cliente.pedidos == []
    assert stats["fixtures"] == 0
