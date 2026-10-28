from scraping.parser import parse_match_report, parse_report_date, parse_schedule
from scraping.pipeline import infer_factor_k
from scraping.competitions import get_competition

SCHEDULE_HTML = """
<html><body>
<div class="content-box-headline">1.Matchday</div>
<table><tbody>
<tr>
  <td class="hide-for-small">Sat <a href="/aktuell/waspassiertheute/aktuell/new/datum/2024-05-11">11/05/24</a></td>
  <td class="zentriert hide-for-small">12:00 AM</td>
  <td class="text-right no-border-rechts hauptlink"><a title="CA Sarmiento (Junin)" href="/club-atletico-sarmiento-junin-/spielplan/verein/12454/saison_id/2023">Sarmiento Junin</a></td>
  <td class="zentriert no-border-links"><a title="CA Sarmiento (Junin)" href="/club-atletico-sarmiento-junin-/spielplan/verein/12454/saison_id/2023"><img class="tiny_wappen" /></a></td>
  <td class="zentriert hauptlink">&nbsp;<a class="ergebnis-link" id="4283434" href="/ca-sarmiento-junin-_instituto-acc/index/spielbericht/4283434">1:2</a>&nbsp;</td>
  <td class="zentriert no-border-rechts"><a title="Instituto ACC" href="/instituto-ac-cordoba/spielplan/verein/1829/saison_id/2023"><img class="tiny_wappen" /></a></td>
  <td class="no-border-links hauptlink"><a title="Instituto ACC" href="/instituto-ac-cordoba/spielplan/verein/1829/saison_id/2023">Instituto ACC</a></td>
</tr>
<tr>
  <td class="hide-for-small"></td>
  <td class="zentriert hide-for-small">2:15 AM</td>
  <td class="text-right no-border-rechts hauptlink"><a title="AA Argentinos Juniors" href="/argentinos-juniors/spielplan/verein/1030/saison_id/2023">Argentinos Jrs.</a></td>
  <td class="zentriert no-border-links"><a title="AA Argentinos Juniors" href="/argentinos-juniors/spielplan/verein/1030/saison_id/2023"><img class="tiny_wappen" /></a></td>
  <td class="zentriert hauptlink">&nbsp;<a class="ergebnis-link" id="4283429" href="/aa-argentinos-juniors_ca-rosario-central/index/spielbericht/4283429">3:2</a>&nbsp;</td>
  <td class="zentriert no-border-rechts"><a title="CA Rosario Central" href="/club-atletico-rosario-central/spielplan/verein/1418/saison_id/2023"><img class="tiny_wappen" /></a></td>
  <td class="no-border-links hauptlink"><a title="CA Rosario Central" href="/club-atletico-rosario-central/spielplan/verein/1418/saison_id/2023">Rosario Central</a></td>
</tr>
</tbody></table>
</body></html>
"""

MATCH_HTML = """
<html><body>
<div class="sb-spieldaten">
  <p class="sb-datum hide-for-small">
    <a href="/jumplist/spieltag/wettbewerb/AR1N/saison_id/2023/spieltag/1">1. Matchday</a>
    |
    <a href="/aktuell/waspassiertheute/aktuell/new/datum/2024-05-11">Sat, 11/05/24</a>
  </p>
</div>
<div class="sb-endstand">2:1<div class="sb-halbzeit">(<span>1:</span>0)</div></div>
<table>
<tr class="bench-table__tr">
  <td><div>Manager:</div></td>
  <td class="bench-table__td"><a title="Israel Damonte" id="75966" href="/israel-damonte/profil/trainer/75966">Israel Damonte</a></td>
  <td>&nbsp;</td>
</tr>
<tr class="bench-table__tr">
  <td><div>Manager:</div></td>
  <td class="bench-table__td"><a title="Diego Dabove" id="22168" href="/diego-dabove/profil/trainer/22168">Diego Dabove</a></td>
  <td>&nbsp;</td>
</tr>
</table>
<div class="sb-zeitleiste-ereignisse sb-90-minuten">
  <div class="sb-leiste-heim" style="background-color: #1B6345;">
    <div class="sb-leiste-ereignis" style="left: 10%;"><span class="sb-sprite sb-tor">&nbsp;</span></div>
    <div class="sb-leiste-ereignis" style="left: 50%;"><span class="sb-sprite sb-wechsel">&nbsp;</span></div>
    <div class="sb-leiste-ereignis" style="left: 80%;"><span class="sb-sprite sb-tor">&nbsp;</span></div>
  </div>
  <div class="sb-leiste-gast" style="background-color: #ff2424;">
    <div class="sb-leiste-ereignis" style="left: 20%;"><span class="sb-sprite sb-tor">&nbsp;</span></div>
    <div class="sb-leiste-ereignis" style="left: 60%;"><span class="sb-sprite sb-wechsel">&nbsp;</span></div>
  </div>
</div>
</body></html>
"""


CUP_SCHEDULE_HTML = """
<html><body>
<table><tbody>
<tr class="bg_blau_20">
  <td class="show-for-small" colspan="7">Thu <a href="/aktuell/waspassiertheute/aktuell/new/datum/2024-04-04">04/04/2024</a></td>
</tr>
<tr>
  <td class="hide-for-small">04/04/2024</td>
  <td class="text-right no-border-rechts hauptlink"><a title="CSD Colo-Colo" href="/csd-colo-colo/startseite/verein/2433/saison_id/2023">Colo-Colo</a></td>
  <td class="zentriert no-border-links"><a title="CSD Colo-Colo" href="/csd-colo-colo/startseite/verein/2433/saison_id/2023"><img /></a></td>
  <td class="zentriert hauptlink"><a title="Match report" class="ergebnis-link" id="4314431" href="/spielbericht/index/spielbericht/4314431">1:0</a></td>
  <td class="zentriert no-border-rechts"><a title="Club Cerro Porteño" href="/club-cerro-porteno/startseite/verein/1214/saison_id/2023"><img /></a></td>
  <td class="no-border-links hauptlink"><a title="Club Cerro Porteño" href="/club-cerro-porteno/startseite/verein/1214/saison_id/2023">Cerro Porteño</a></td>
</tr>
<tr>
  <td class="hide-for-small"></td>
  <td class="text-right no-border-rechts hauptlink"><a title="Club Alianza Lima" href="/alianza-lima/startseite/verein/1234/saison_id/2023">Alianza Lima</a></td>
  <td class="zentriert no-border-links"><a title="Club Alianza Lima" href="/alianza-lima/startseite/verein/1234/saison_id/2023"><img /></a></td>
  <td class="zentriert hauptlink"><a title="Match report" class="ergebnis-link" id="4314432" href="/spielbericht/index/spielbericht/4314432">1:1</a></td>
  <td class="zentriert no-border-rechts"><a title="Fluminense" href="/fluminense/startseite/verein/999/saison_id/2023"><img /></a></td>
  <td class="no-border-links hauptlink"><a title="Fluminense" href="/fluminense/startseite/verein/999/saison_id/2023">Fluminense</a></td>
</tr>
</tbody></table>
</body></html>
"""


def test_parse_schedule_extracts_fixture():
    fixtures = parse_schedule(SCHEDULE_HTML, "AR1N", 2023)
    assert len(fixtures) == 2
    fixture = fixtures[0]
    assert fixture.match_id == 4283434
    assert fixture.date == "2024-05-11"
    assert fixture.home_club_tm_id == 12454
    assert fixture.away_club_tm_id == 1829
    assert fixture.home_goals == 1
    assert fixture.away_goals == 2
    assert fixture.matchday == "1.Matchday"


def test_parse_schedule_propagates_date_to_rows_without_date():
    fixtures = parse_schedule(SCHEDULE_HTML, "AR1N", 2023)
    second = fixtures[1]
    assert second.match_id == 4283429
    assert second.date == "2024-05-11"


def test_parse_schedule_cup_plain_text_dates():
    fixtures = parse_schedule(CUP_SCHEDULE_HTML, "CLI", 2023)
    assert len(fixtures) == 2
    assert fixtures[0].date == "2024-04-04"
    assert fixtures[1].date == "2024-04-04"  # forward-fill
    assert fixtures[0].home_club_name == "CSD Colo-Colo"
    assert fixtures[0].away_club_name == "Club Cerro Porteño"


def test_parse_match_report_extracts_coaches_and_bench_metrics():
    report = parse_match_report(MATCH_HTML, 4283434)
    assert report.final_home_goals == 2
    assert report.final_away_goals == 1
    assert report.home_coach_tm_id == 75966
    assert report.away_coach_tm_id == 22168
    # Local: primer cambio en 50 con 1:1 -> terminó 2:1 => +1
    assert report.marcador_pre_cambios_local == "1:1"
    assert report.impacto_banco_local == 1
    # Visita: primer cambio en 60 con 1:1 -> terminó 1:2 => -1
    assert report.marcador_pre_cambios_visita == "1:1"
    assert report.impacto_banco_visita == -1


REPORTE_LAYOUT_VIEJO = """
<html><body>
<div class="box">
  <div class="large-6 columns aufstellung-box">
    <table><tbody><tr><td>Manager
      <a title="Enrique Meza" href="/enrique-meza/profil/trainer/5101">Enrique Meza</a>
    </td></tr></tbody></table>
  </div>
  <div class="large-6 columns">
    <table><tbody><tr><td>Manager
      <a title="Alexandre Gallo" href="/alexandre-gallo/profil/trainer/4733">Alexandre Gallo</a>
    </td></tr></tbody></table>
  </div>
</div>
<div class="sb-endstand">2:1</div>
</body></html>
"""


def test_parse_match_report_encuentra_dts_en_el_layout_viejo():
    """Las páginas viejas no tienen `tr.bench-table__tr`: los DTs están en `div.box`."""
    report = parse_match_report(REPORTE_LAYOUT_VIEJO, 994417)

    assert report.home_coach_tm_id == 5101
    assert report.home_coach_name == "Enrique Meza"
    assert report.away_coach_tm_id == 4733
    assert report.away_coach_name == "Alexandre Gallo"


def test_parse_match_report_con_un_solo_dt_no_adivina_el_lado():
    """Con un solo entrenador en la página no se puede saber si es local o visitante."""
    html = """
    <html><body>
    <div class="box"><table><tbody><tr><td>Manager
      <a title="Alfio Basile" href="/alfio-basile/profil/trainer/1234">Alfio Basile</a>
    </td></tr></tbody></table></div>
    <div class="sb-endstand">3:2</div>
    </body></html>
    """
    report = parse_match_report(html, 3296964)

    assert report.home_coach_tm_id is None
    assert report.away_coach_tm_id is None


def test_parse_match_report_extrae_la_fecha_del_reporte():
    """La fecha del reporte es la única confiable: el fixture la hereda de la fila previa."""
    report = parse_match_report(MATCH_HTML, 4283434)
    assert report.fecha == "2024-05-11"


def test_parse_report_date_usa_el_link_datum():
    html = """
    <html><body>
      <p class="sb-datum hide-for-small">
        <a href="/jumplist/spieltag/wettbewerb/TDeC/saison_id/2005/spieltag/4">4. Matchday</a>
        |
        <a href="/aktuell/waspassiertheute/aktuell/new/datum/2006-08-05">Sat, 05/08/06</a>
      </p>
    </body></html>
    """
    assert parse_report_date(html) == "2006-08-05"


def test_parse_report_date_cae_al_texto_si_no_hay_link():
    html = """
    <html><body>
      <p class="sb-datum">6. Matchday | Mon, 16/05/05 | 7:00 PM</p>
    </body></html>
    """
    assert parse_report_date(html) == "2005-05-16"


def test_parse_report_date_sin_fecha_devuelve_none():
    assert parse_report_date("<html><body><p>sin datos</p></body></html>") is None


def test_infer_factor_k_by_round():
    cli = get_competition("CLI")
    assert infer_factor_k(cli, "Group stage") == 20
    assert infer_factor_k(cli, "Schedule") == 20
    assert infer_factor_k(cli, "Last 16 1st Leg") == 30
    assert infer_factor_k(cli, "Quarter-Finals 1st Leg") == 30
    assert infer_factor_k(cli, "Semi-Finals 2nd Leg") == 30
    assert infer_factor_k(cli, "Final") == 40
    assert infer_factor_k(get_competition("AR1N"), "1.Matchday") == 20


def test_parse_match_report_without_timeline_defaults_to_zero():
    html = """
    <html><body>
    <div class="sb-endstand">0:0</div>
    <table>
      <tr class="bench-table__tr">
        <td><div>Manager:</div></td>
        <td><a title="Uno" id="1" href="/uno/profil/trainer/1">Uno</a></td>
      </tr>
      <tr class="bench-table__tr">
        <td><div>Manager:</div></td>
        <td>(interino)</td>
      </tr>
    </table>
    </body></html>
    """
    report = parse_match_report(html, 1)
    assert report.marcador_pre_cambios_local is None
    assert report.impacto_banco_local == 0
    assert report.home_coach_tm_id == 1
    assert report.away_coach_tm_id is None
