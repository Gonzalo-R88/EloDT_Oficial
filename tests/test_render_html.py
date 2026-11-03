"""Tests del motor de render HTML → PNG (`render_html.py`)."""

import pytest

from render_html import VARIANTES, dimensiones, render_png, renderizar_html, variante


def test_variantes_conocidas():
    assert VARIANTES["portrait"].ancho == 1080
    assert VARIANTES["portrait"].alto == 1350
    assert VARIANTES["landscape"].ancho == 1600
    assert VARIANTES["landscape"].alto == 900


def test_variante_desconocida():
    with pytest.raises(ValueError):
        variante("cuadrada")


def test_renderizar_html_no_necesita_navegador():
    html = renderizar_html("prueba.html", {"titulo": "Hola"}, "portrait")

    assert "Hola" in html
    assert "1080" in html and "1350" in html
    assert "{{" not in html  # no quedaron variables sin resolver


def test_renderizar_html_escapa_el_contenido():
    html = renderizar_html("prueba.html", {"titulo": "<script>x</script>"}, "square")

    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def _saltar_si_no_hay_navegador():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        pytest.skip("Playwright no está instalado")
    try:
        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
    except Exception:  # pragma: no cover
        pytest.skip("Chromium no está disponible para Playwright")


@pytest.mark.parametrize("nombre", ["portrait", "landscape", "square"])
def test_render_png_genera_el_tamano_exacto(tmp_path, nombre):
    _saltar_si_no_hay_navegador()

    salida = tmp_path / f"prueba_{nombre}.png"
    render_png("prueba.html", {"titulo": "Prueba"}, salida, nombre)

    assert salida.exists()
    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)


def test_render_png_no_deja_temporales(tmp_path):
    _saltar_si_no_hay_navegador()

    render_png("prueba.html", {}, tmp_path / "x.png", "square")

    temporales = list((__import__("pathlib").Path(__file__).resolve().parent.parent
                       / "templates").glob(".render_*.html"))
    assert temporales == []
