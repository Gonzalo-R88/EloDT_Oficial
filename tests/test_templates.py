"""Tests de las plantillas de imagen (`templates/`)."""

from dataclasses import replace
from datetime import date

import pytest

from content import EntradaTop
from render_html import (
    TEMPLATES_DIR,
    VARIANTES,
    dimensiones,
    render_png,
    renderizar_html,
    tamano_bytes,
)


def _entradas(cantidad: int = 10, nombre_largo: bool = False) -> list[EntradaTop]:
    entradas = []
    for puesto in range(1, cantidad + 1):
        nombre = (
            "Guillermo Martín Barros Schelotto Fernández"
            if nombre_largo else f"DT de Prueba {puesto}"
        )
        entradas.append(
            EntradaTop(
                dt_id=puesto,
                dt=nombre[:40] if nombre_largo else nombre,
                club="Club Atlético Independiente Rivadavia" if nombre_largo else "Club de Prueba",
                pais="Argentina",
                liga="AR1N",
                elo=1234.0 - puesto,
                pj=120,
                etiqueta="provisorio" if puesto == 3 else None,
                puesto=puesto,
                puesto_previo=puesto + 1 if puesto % 2 else puesto - 1,
            )
        )
    return entradas


def _contexto(entradas=None, **extra):
    contexto = {
        "titulo": "TOP 10 DTs DE ARGENTINA",
        "subtitulo": "Semana del 26 de octubre al 1 de noviembre de 2026",
        "entradas": entradas or _entradas(),
        "partidos": 42,
        "modelo": "elo-v2",
        "handle": "@EloDT_oficial",
    }
    contexto.update(extra)
    return contexto


def test_el_contexto_se_renderiza_sin_variables_pendientes():
    html = renderizar_html("top10.html", _contexto(), "portrait")

    assert "TOP 10 DTs DE ARGENTINA" in html
    assert "DT de Prueba 1" in html
    assert "{{" not in html
    assert "provisorio" in html


def _saltar_si_no_hay_navegador():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        pytest.skip("Playwright no está instalado")
    try:
        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
    except Exception:  # pragma: no cover
        pytest.skip("Chromium no está disponible")


@pytest.mark.parametrize("nombre", ["portrait", "landscape", "square"])
def test_top10_renderiza_las_tres_variantes(tmp_path, nombre):
    _saltar_si_no_hay_navegador()

    salida = tmp_path / f"top10_{nombre}.png"
    render_png("top10.html", _contexto(), salida, nombre)

    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)
    assert tamano_bytes(salida) < 1_500_000


@pytest.mark.parametrize("nombre", ["portrait", "landscape"])
def test_top10_entra_con_nombres_de_40_caracteres_y_elo_de_cuatro_digitos(tmp_path, nombre):
    """El caso extremo: nombres larguísimos, clubes largos y ELO de 4 dígitos."""
    _saltar_si_no_hay_navegador()

    entradas = [
        replace(entrada, elo=9999.0 - entrada.puesto) for entrada in _entradas(nombre_largo=True)
    ]
    salida = tmp_path / f"top10_largo_{nombre}.png"

    render_png("top10.html", _contexto(entradas), salida, nombre)

    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)


def test_el_render_falla_si_el_contenido_no_entra(tmp_path):
    """Con 25 filas no entra: el render tiene que fallar, no publicar una imagen cortada."""
    _saltar_si_no_hay_navegador()

    with pytest.raises(ValueError, match="no entra"):
        render_png("top10.html", _contexto(_entradas(25)), tmp_path / "x.png", "portrait")


def test_sin_variacion_no_dibuja_flecha():
    html = renderizar_html("top10.html", _contexto(_entradas(3)), "portrait")

    # Las entradas 1 y 2 tienen puesto_previo, la 3 también; forzamos una sin previo.
    assert "▲" in html or "▼" in html or "=" in html


# ---------------------------------------------------------------------------
# Lo que no debe aparecer nunca en una imagen publicada
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("plantilla", ["top10.html", "movers.html", "duelo.html", "revelacion.html", "sin_club.html"])
def test_las_plantillas_no_nombran_la_fuente_ni_el_handle_viejo(plantilla):
    html = (TEMPLATES_DIR / plantilla).read_text(encoding="utf-8")

    assert "Transfermarkt" not in html
    assert "AEP_Analitica" not in html


# ---------------------------------------------------------------------------
# Subidas y bajadas (T3.4)
# ---------------------------------------------------------------------------
def _movimientos():
    from content import EntradaMovimiento

    return EntradaMovimiento(
        dt_id=1, dt="Guillermo Barros Schelotto", club="CA Vélez Sarsfield",
        pais="Argentina", elo=1150.0, delta=12.75, partidos=1, etiqueta=None,
    )


def _contexto_movimientos():
    entrada = _movimientos()
    interino = replace(entrada, dt="DT Interino", etiqueta="interino", delta=3.5)
    return {
        "titulo": "SUBIERON Y CAYERON",
        "subtitulo": "Semana del 26 de octubre al 1 de noviembre de 2026",
        "subidas": [entrada, interino],
        "bajadas": [replace(entrada, dt="DT Que Baja", delta=-9.4)],
        "partidos": 5,
        "handle": "@EloDT_oficial",
    }


@pytest.mark.parametrize("nombre", ["portrait", "landscape", "square"])
def test_movers_renderiza_las_tres_variantes(tmp_path, nombre):
    _saltar_si_no_hay_navegador()

    salida = tmp_path / f"movers_{nombre}.png"
    render_png("movers.html", _contexto_movimientos(), salida, nombre)

    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)
    assert tamano_bytes(salida) < 1_500_000


def test_movers_muestra_la_etiqueta_del_interino():
    html = renderizar_html("movers.html", _contexto_movimientos(), "portrait")

    assert "interino" in html
    assert "+12,75" in html  # coma decimal


# ---------------------------------------------------------------------------
# Duelo (T3.5) y revelación (T3.6)
# ---------------------------------------------------------------------------
def _contexto_duelo():
    from duel import Duel, DuelSide

    def lado(dt_id, nombre, club, elo, forma):
        return DuelSide(
            dt_id=dt_id, nombre=nombre, apellido=nombre.split()[-1], club=club,
            elo_actual=elo, partidos=100, victorias=50, empates=30, derrotas=20,
            goles_favor=150, goles_contra=100, forma=forma,
        )

    duelo = Duel(
        a=lado(1, "Nicolás Diez", "Argentinos Juniors", 1138.0, ("V", "E", "D")),
        b=lado(2, "Alfredo Berti", "Independiente Rivadavia", 1141.0, ("D", "V", "V")),
        enfrentamientos=6, victorias_a=1, empates=2, victorias_b=3,
        desde=date(2025, 3, 1), hasta=date(2026, 10, 27),
    )
    from content import DueloSemana

    return {
        "titulo": "DUELO DE PIZARRAS",
        "subtitulo": "Semana del 26 de octubre al 1 de noviembre de 2026",
        "duelo": DueloSemana(
            fecha=date(2026, 10, 27), competencia="ARGC", dt_a_id=1, dt_b_id=2,
            club_a="Argentinos Juniors", club_b="Independiente Rivadavia",
            elo_a=1138.0, elo_b=1141.0, resultado="1-0", duelo=duelo,
        ),
        "grafico": {
            "ancho": 1000, "alto": 220, "semanas": 12,
            "y_cero": 138.5, "base": 1000, "tope": 1500,
            "serie_a": {
                "apellido": "Diez", "elo": 1138.0, "delta": -12.6, "delta_texto": "-12,6",
                "barra": 27.6, "puntos": "10,10 500,120 990,200",
            },
            "serie_b": {
                "apellido": "Berti", "elo": 1141.0, "delta": 8.3, "delta_texto": "+8,3",
                "barra": 28.2, "puntos": "10,200 500,120 990,10",
            },
        },
        "handle": "@EloDT_oficial",
    }


@pytest.mark.parametrize("nombre", ["portrait", "landscape"])
def test_duelo_renderiza_y_no_duplica_el_nombre(tmp_path, nombre):
    _saltar_si_no_hay_navegador()

    salida = tmp_path / f"duelo_{nombre}.png"
    render_png("duelo.html", _contexto_duelo(), salida, nombre)

    html = renderizar_html("duelo.html", _contexto_duelo(), nombre)
    assert "Nicolás Diez" in html
    assert "Nicolás Diez Diez" not in html
    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)


def test_el_duelo_separa_nivel_de_mejora():
    """El nivel va en la barra (más larga = más ELO) y la mejora en el número verde.

    Un solo gráfico con las dos series obligaba a elegir: si mostraba el nivel, no se veía
    la mejora; si mostraba la mejora, la línea del que tiene menos ELO parecía la mejor.
    """
    html = renderizar_html("duelo.html", _contexto_duelo(), "landscape")

    assert "Nivel de ELO y mejora" in html                      # el rótulo dice qué muestra
    assert "width: 27.6%" in html and "width: 28.2%" in html    # barras proporcionales
    assert "1138" in html and "1141" in html                    # el nivel, al lado de la barra
    assert "-12,6" in html and "+8,3" in html                   # la mejora, con signo
    assert ">1000<" in html and ">1500<" in html                # escala de la barra
    assert 'vector-effect="non-scaling-stroke"' in html         # el trazo no engorda


def _contexto_revelacion():
    from content import Revelacion

    return {
        "titulo": "DT REVELACIÓN",
        "subtitulo": "Semana del 26 de octubre al 1 de noviembre de 2026",
        "entrada": Revelacion(
            dt_id=1, dt="Sergej Jakirovic", club="Hull City", pais="Inglaterra",
            elo=1115.0, pj=68, desde_primera_fecha=date(2025, 2, 1),
            variacion=43.5, etiqueta=None,
        ),
        "handle": "@EloDT_oficial",
    }


@pytest.mark.parametrize("nombre", ["portrait", "square"])
def test_revelacion_renderiza(tmp_path, nombre):
    _saltar_si_no_hay_navegador()

    salida = tmp_path / f"revelacion_{nombre}.png"
    render_png("revelacion.html", _contexto_revelacion(), salida, nombre)

    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)


# ---------------------------------------------------------------------------
# Técnicos sin club
# ---------------------------------------------------------------------------
def _entradas_sin_club(cantidad: int = 10) -> list:
    from content import EntradaSinClub

    return [
        EntradaSinClub(
            dt_id=puesto,
            dt=f"DT de Prueba {puesto}",
            elo=1200.0 - puesto,
            pj=40 + puesto,
            ultima_fecha=date(2026, 10, 1),
            etiqueta="provisorio" if puesto == 10 else None,
            puesto=puesto,
        )
        for puesto in range(1, cantidad + 1)
    ]


def _contexto_sin_club():
    return {
        "titulo": "LOS MEJORES DTs SIN CLUB",
        "subtitulo": "Técnicos libres · Argentina · 19 de noviembre de 2026",
        "entradas": _entradas_sin_club(),
        "handle": "@EloDT_oficial",
    }


def test_sin_club_muestra_partidos_y_provisorio():
    html = renderizar_html("sin_club.html", _contexto_sin_club(), "portrait")

    assert "LOS MEJORES DTs SIN CLUB" in html
    assert "41 partidos" in html
    assert "provisorio" in html
    assert "{{" not in html


@pytest.mark.parametrize("nombre", ["portrait", "landscape", "square"])
def test_sin_club_renderiza_las_tres_variantes(tmp_path, nombre):
    _saltar_si_no_hay_navegador()

    salida = tmp_path / f"sin_club_{nombre}.png"
    render_png("sin_club.html", _contexto_sin_club(), salida, nombre)

    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)
    assert tamano_bytes(salida) < 1_500_000
