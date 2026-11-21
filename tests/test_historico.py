"""Tests de la capa de datos del histórico argentino (T0.11, etapa A)."""

from __future__ import annotations

from datetime import date

import pytest

import historico

CSV_MINIMO = """Country,League,Season,Date,Time,Home,Away,HG,AG,Res
Argentina,Liga Profesional,2012/2013,03/08/2012,23:00,Arsenal Sarandi,Union de Santa Fe,1,0,H
Argentina,Liga Profesional,2012/2013,04/08/2012,01:10,Velez Sarsfield,Argentinos Jrs,3,0,H
Argentina,Liga Profesional,2014,08/08/2014,20:30,River Plate,San Lorenzo,2,1,H
Argentina,Liga Profesional,2016/2017,01/01/2017,20:30,Boca Juniors,River Plate,1,0,H
Argentina,Liga Profesional,2014,09/08/2014,20:30,Equipo Inexistente,Boca Juniors,0,0,D
"""

RSSSF_MINIMO = """
<h3><a name="second">Second Level</a></h3><pre>
Final Table:
 1.Banfield                          42  22 12  8  71-40  78

<u>Round 1</u>:
[Aug 3]
Independiente (Avellaneda)         1-2 Brown (Adrogué)
Talleres (Córdoba)                 2-2 Sarmiento (Junín)                  [at Mario Alberto Kempes]
[Aug 4]
Defensa y Justicia                 1-0 Instituto
<u>Round 2</u>:
[Aug 9]
Sarmiento (Junín)                  1-0 Unión (Santa Fe)
</pre>
<h3><a name="third">Third Level</a></h3>
"""


def _etapa(dt, desde, hasta=None, pj=None, interino=False):
    return historico.Etapa(
        club_tm_id=189,
        dt_tm_id=dt,
        dt_nombre=f"DT {dt}",
        desde=desde,
        hasta=hasta,
        pj_tm=pj,
        interino=interino,
    )


# --- football-data ---------------------------------------------------------
def test_parse_football_data_toma_solo_las_temporadas_del_hueco():
    partidos = historico.parse_football_data(CSV_MINIMO.replace("Equipo Inexistente", "Belgrano"))

    assert len(partidos) == 4
    assert {p.competencia for p in partidos} == {historico.ARGH}
    assert date(2012, 8, 3) in {p.fecha for p in partidos}
    # 2016/2017 queda afuera: el histórico sólo cubre 2012-2014.
    assert all(p.fecha.year <= 2014 for p in partidos)


def test_parse_football_data_falla_si_hay_un_club_sin_mapear():
    with pytest.raises(historico.FuenteInvalida):
        historico.parse_football_data(CSV_MINIMO)


def test_parse_football_data_lee_goles_y_equipos():
    partidos = historico.parse_football_data(CSV_MINIMO.replace("Equipo Inexistente", "Belgrano"))
    primero = next(p for p in partidos if p.fecha == date(2012, 8, 3))

    assert (primero.local_tm_id, primero.visita_tm_id) == (4673, 7097)
    assert (primero.goles_local, primero.goles_visita) == (1, 0)


# --- RSSSF ----------------------------------------------------------------
def test_parse_bnacional_lee_rondas_y_limpia_la_sede():
    partidos = historico.parse_bnacional(RSSSF_MINIMO, 2013)

    assert len(partidos) == 4
    assert {p.competencia for p in partidos} == {historico.ARG2H}
    talleres = next(p for p in partidos if p.local_tm_id == 3938)
    assert talleres.visita_tm_id == 12454  # Sarmiento (Junín), sin el "[at ...]"


def test_parse_bnacional_ignora_la_tabla_de_posiciones():
    partidos = historico.parse_bnacional(RSSSF_MINIMO, 2013)

    # La línea "1.Banfield 42 22 12 8 71-40 78" tiene un 71-40 que parece un
    # resultado; no debe entrar como partido.
    assert all(p.local_tm_id != 830 or p.fecha.month == 8 for p in partidos)
    assert len(partidos) == 4


def test_parse_bnacional_asigna_el_anio_segun_el_mes():
    partidos = historico.parse_bnacional(RSSSF_MINIMO, 2013)
    agosto = [p for p in partidos if p.fecha.month == 8]

    assert agosto and all(p.fecha.year == 2013 for p in agosto)


def test_parse_bnacional_corta_si_no_encuentra_la_seccion():
    with pytest.raises(historico.FuenteInvalida):
        historico.parse_bnacional("<html><body>nada</body></html>", 2013)


# --- etapas ---------------------------------------------------------------
def test_etapas_por_club_ordena_por_fecha():
    etapas = [_etapa(2, date(2013, 6, 1)), _etapa(1, date(2011, 2, 13))]
    agrupadas = historico.etapas_por_club(etapas)

    assert [e.dt_tm_id for e in agrupadas[189]] == [1, 2]


def test_entrenador_en_usa_el_arranque_de_la_siguiente_etapa():
    """Con fechas redondeadas, la etapa siguiente manda sobre el fin declarado."""
    etapas = [
        _etapa(1, date(2011, 1, 1), date(2012, 12, 31)),
        _etapa(2, date(2013, 1, 1), date(2014, 8, 28)),
    ]

    assert historico.entrenador_en(etapas, date(2012, 6, 30)).dt_tm_id == 1
    assert historico.entrenador_en(etapas, date(2013, 3, 1)).dt_tm_id == 2


def test_entrenador_en_resuelve_el_solapamiento_a_favor_del_ultimo():
    etapas = [
        _etapa(1, date(2011, 1, 1), date(2012, 12, 31)),
        _etapa(2, date(2012, 6, 1), None),
    ]

    # El fin declarado de la etapa 1 llega hasta fin de 2012, pero la 2 arrancó antes.
    assert historico.entrenador_en(etapas, date(2012, 7, 1)).dt_tm_id == 2


def test_entrenador_en_no_inventa_si_hay_un_hueco():
    etapas = [
        _etapa(1, date(2011, 1, 1), date(2011, 6, 30)),
        _etapa(2, date(2012, 1, 1), None),
    ]

    assert historico.entrenador_en(etapas, date(2011, 9, 1)) is None


def test_entrenador_en_sin_etapas_devuelve_none():
    assert historico.entrenador_en([], date(2013, 1, 1)) is None


def test_entrenador_en_prefiere_la_etapa_mas_reciente_que_cubre():
    etapas = [_etapa(1, date(2012, 1, 1), None), _etapa(2, date(2013, 1, 1), None)]

    assert historico.entrenador_en(etapas, date(2013, 5, 1)).dt_tm_id == 2


# --- asignación -----------------------------------------------------------
def _partido(fecha, competencia=historico.ARGH, local=189, visita=209, temporada=None):
    return historico.PartidoHistorico(
        fecha=fecha,
        temporada=temporada if temporada is not None else (fecha.year if fecha.month >= 7 else fecha.year - 1),
        competencia=competencia,
        local_tm_id=local,
        visita_tm_id=visita,
        goles_local=1,
        goles_visita=0,
    )


def test_asignar_resuelve_los_dos_lados():
    etapas = {
        189: [_etapa(1, date(2011, 1, 1))],
        209: [_etapa(2, date(2011, 1, 1))],
    }

    resultado = historico.asignar([_partido(date(2013, 8, 4))], etapas)

    assert resultado.completo
    assert resultado.partidos[0].dt_local_tm_id == 1
    assert resultado.partidos[0].dt_visita_tm_id == 2


def test_asignar_deja_fuera_los_partidos_sin_dt():
    etapas = {189: [_etapa(1, date(2011, 1, 1))], 209: []}

    resultado = historico.asignar([_partido(date(2013, 8, 4))], etapas)

    assert not resultado.completo
    assert not resultado.partidos
    assert len(resultado.sin_dt) == 1


# --- limpieza e invariantes -----------------------------------------------
def test_limpiar_quita_los_partidos_que_no_son_de_liga():
    liga = _partido(date(2013, 8, 4))
    copa = _partido(date(2013, 6, 29), local=1029, visita=1286)
    otras = _partido(date(2013, 8, 5), local=1029, visita=1286)

    limpios = historico.limpiar([copa, liga, otras])

    assert copa not in limpios
    assert liga in limpios
    assert otras in limpios


def test_limpiar_no_confunde_un_partido_de_liga_con_un_tercer_cruce():
    """El 3.er cruce Boca-Vélez (29/01/2015) queda afuera; el 2.º de Rafaela-Colón no.

    Boca y Vélez jugaron tres veces en 2013/14: Inicial, Final y un tercer partido que
    no es de liga. Rafaela y Colón también, pero su tercer cruce es el desempate.
    """
    tercero_boca_velez = _partido(date(2015, 1, 29), local=189, visita=1029)
    segundo_rafaela_colon = _partido(date(2014, 4, 26), local=10233, visita=1070)

    limpios = historico.limpiar([tercero_boca_velez, segundo_rafaela_colon])

    assert tercero_boca_velez not in limpios
    assert segundo_rafaela_colon in limpios


def test_limpiar_ordena_cronologicamente():
    tarde = _partido(date(2014, 5, 1))
    temprano = _partido(date(2012, 8, 1))

    assert historico.limpiar([tarde, temprano]) == [temprano, tarde]


def test_validar_ligas_detecta_un_equipo_con_partidos_de_mas():
    partidos = []
    for indice in range(39):
        partidos.append(
            historico.PartidoHistorico(
                fecha=date(2013, 8, 1),
                temporada=2013,
                competencia=historico.ARGH,
                local_tm_id=189,
                visita_tm_id=209 + indice,
                goles_local=1,
                goles_visita=0,
            )
        )

    problemas = historico.validar_ligas(partidos)

    assert any("esperado 38" in problema for problema in problemas)


def test_normalizar_saca_acentos_y_mayusculas():
    assert historico.normalizar("  Atlético   Tucumán ") == "atletico tucuman"


# --- parser de etapas de Transfermarkt -----------------------------------
# Recorte de `mitarbeiterhistorie` con la estructura real: la primera celda trae el
# nombre y la fecha de NACIMIENTO (una tabla anidada), y las fechas de la etapa están
# en las columnas "Appointed" y "End of time in post".
HTML_ETAPAS = """
<table class="items">
<thead><tr>
  <th>Name/Date of birth</th><th>Nat.</th><th>Appointed</th>
  <th>End of time in post</th><th>Time in post</th><th>Matches</th><th>PPG</th>
</tr></thead>
<tbody>
<tr class="odd">
  <td><table class="inline-table">
    <tr><td class="hauptlink"><a title="Carlos Bianchi" href="/carlos-bianchi/profil/trainer/1234">Carlos Bianchi</a></td></tr>
    <tr><td>26/04/1949</td></tr>
  </table></td>
  <td class="zentriert"><img alt="Argentina"/></td>
  <td class="zentriert">01/01/2013</td>
  <td class="zentriert">28/08/2014</td>
  <td class="rechts">604 days</td>
  <td class="zentriert"><a href="/trainer/leistungsdatenDetail?id=1234">72</a></td>
  <td class="zentriert">1.62</td>
</tr>
<tr class="even">
  <td><table class="inline-table">
    <tr><td class="hauptlink"><a title="Rodolfo Arruabarrena" href="/rodolfo-arruabarrena/profil/trainer/5678">Rodolfo Arruabarrena</a></td></tr>
    <tr><td>20/07/1975</td></tr>
  </table></td>
  <td class="zentriert"></td>
  <td class="zentriert">29/08/2014</td>
  <td class="zentriert"></td>
  <td class="rechts">100 days</td>
  <td class="zentriert"><a href="/trainer/leistungsdatenDetail?id=5678">12</a></td>
  <td class="zentriert">2.00</td>
</tr>
</tbody></table>
"""


def test_parse_etapas_lee_nombre_fechas_y_partidos():
    etapas = historico.parse_etapas(HTML_ETAPAS, 189)

    assert len(etapas) == 2
    primera = etapas[0]
    assert primera.dt_tm_id == 1234
    assert primera.dt_nombre == "Carlos Bianchi"
    assert primera.desde == date(2013, 1, 1)
    assert primera.hasta == date(2014, 8, 28)
    assert primera.pj_tm == 72
    assert etapas[1].hasta is None  # etapa abierta


def test_parse_etapas_no_confunde_el_nacimiento_con_el_inicio():
    """La fecha de nacimiento vive en la misma celda que el nombre."""
    etapas = historico.parse_etapas(HTML_ETAPAS, 189)

    assert etapas[0].desde.year == 2013
    assert etapas[0].desde != date(1949, 4, 26)


def test_parse_etapas_ignora_las_filas_anidadas_del_nombre():
    """La tabla del nombre tiene sus propios `tr`, sin las columnas de la etapa."""
    etapas = historico.parse_etapas(HTML_ETAPAS, 189)

    assert len(etapas) == 2


def test_parse_etapas_ignora_las_filas_sin_link_de_entrenador():
    html = (
        '<table class="items"><tr><th>Appointed</th><th>End of time in post</th>'
        "<th>Matches</th></tr>"
        "<tr><td>Utillero</td><td>01/01/2013</td><td>01/02/2013</td><td>4</td></tr></table>"
    )

    assert historico.parse_etapas(html, 189) == []


def test_parse_etapas_soporta_fechas_en_texto():
    html = """
    <table class="items">
    <tr><th>Name/Date of birth</th><th>Appointed</th><th>End of time in post</th><th>Matches</th></tr>
    <tr>
      <td><a title="Diego Maradona" href="/diego-maradona/profil/trainer/999">Diego Maradona</a></td>
      <td>Jan 1, 2000</td>
      <td>Dec 31, 2001</td>
      <td>20</td>
    </tr></table>
    """
    etapas = historico.parse_etapas(html, 189)

    assert len(etapas) == 1
    assert etapas[0].desde == date(2000, 1, 1)
    assert etapas[0].hasta == date(2001, 12, 31)
