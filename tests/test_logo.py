"""Tests de las imágenes de marca (`scripts/logo.py` y `templates/brand/marcador.html`)."""

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def logo():
    spec = importlib.util.spec_from_file_location("logo_test", RAIZ / "scripts" / "logo.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_el_banner_muestra_el_handle(logo):
    from render_html import renderizar_html

    html = renderizar_html(logo.PLANTILLA, {"handle": "@EloDt_Oficial", "formato": "banner"}, "banner")

    assert "@EloDt_Oficial" in html
    assert "Analítica de entrenadores" in html


def test_el_perfil_no_lleva_texto_chico(logo):
    """Un perfil se ve a 48 px: el handle y la bajada sólo van en el banner."""
    from render_html import renderizar_html

    html = renderizar_html(logo.PLANTILLA, {"handle": "@EloDt_Oficial", "formato": "perfil"}, "perfil")

    assert "@EloDt_Oficial" not in html
    assert "Analítica de entrenadores" not in html


def test_genera_el_perfil_y_el_banner_con_su_tamano(logo, tmp_path):
    from render_html import dimensiones

    generados = logo.generar("@EloDt_Oficial", tmp_path)

    assert [p.name for p in generados] == ["perfil.png", "banner.png"]
    # El perfil sale al doble (X lo muestra a 400 y así queda nítido).
    assert dimensiones(generados[0]) == (800, 800)
    assert dimensiones(generados[1]) == (1500, 500)
