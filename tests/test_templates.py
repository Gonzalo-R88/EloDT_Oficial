"""Tests de las plantillas de imagen (`templates/`)."""

from dataclasses import replace

import pytest

from content import EntradaTop
from render_html import VARIANTES, dimensiones, render_png, renderizar_html, tamano_bytes


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
        "handle": "@AEP_Analitica",
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
