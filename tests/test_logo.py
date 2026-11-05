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


def test_el_banner_dice_que_hace_la_cuenta(logo):
    """El banner no repite el logo (ya está en el avatar) ni el handle (X lo muestra solo)."""
    from render_html import renderizar_html

    html = renderizar_html(logo.PLANTILLA, {"handle": "@EloDT_oficial", "formato": "banner"}, "banner")

    assert "Ranking" in html and "entrenadores" in html
    assert "Nuevo ranking cada lunes" in html
    assert "@EloDT_oficial" not in html


def test_el_perfil_no_lleva_texto_chico(logo):
    """Un perfil se ve a 48 px: el handle y la bajada sólo van en el banner."""
    from render_html import renderizar_html

    html = renderizar_html(logo.PLANTILLA, {"handle": "@EloDT_oficial", "formato": "perfil"}, "perfil")

    assert "@EloDT_oficial" not in html
    assert "Analítica de entrenadores" not in html


def test_el_handle_de_la_marca(logo):
    assert logo.HANDLE == "@EloDT_oficial"


def test_genera_el_perfil_y_el_banner_con_su_tamano(logo, tmp_path):
    from render_html import dimensiones

    generados = logo.generar("@EloDT_oficial", tmp_path)

    assert [p.name for p in generados] == ["perfil.png", "banner.png"]
    assert dimensiones(generados[0]) == (400, 400)
    assert dimensiones(generados[1]) == (1500, 500)
