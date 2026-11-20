"""Tests del comparativo de los cinco grandes entre GTA V y GTA VI.

Sin ELO en ninguna de las dos columnas: en 2013 la base no tiene la liga argentina, así
que comparar números entre épocas mostraría datos incompletos como si fueran mérito.
"""

import importlib.util
import json
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from captions import LIMITE_POST, _apellido_de, textos_gta
from content import GRANDES, FilaGrande, tecnicos_grandes
from models import Base, Club, Coach, Competition
from render_html import TEMPLATES_DIR, VARIANTES, dimensiones, render_png, renderizar_html
from services import process_match_elo

RAIZ = Path(__file__).resolve().parents[1]


def _filas() -> list[FilaGrande]:
    return [
        FilaGrande("Boca", "Carlos Bianchi", "Rodolfo Arruabarrena", date(2026, 11, 14)),
        FilaGrande("River", "Ramón Díaz", "Leonardo Ponzio", date(2026, 11, 5)),
        FilaGrande("Independiente", "Omar De Felippe", "Jádson Viera", date(2026, 11, 6)),
        FilaGrande("Racing", "Reinaldo Merlo", "Sebastián Romero", date(2026, 11, 6)),
        FilaGrande("San Lorenzo", "Juan Antonio Pizzi", "Rubén Insúa", date(2026, 11, 6)),
    ]


def _contexto(filas=None):
    return {
        "titulo": "LOS 5 GRANDES Y SUS DTs",
        "subtitulo": "Cuando salió cada GTA",
        "filas": filas or _filas(),
        "fecha_a": "17/09/2013",
        "fecha_b": "19/11/2026",
        "handle": "@EloDT_oficial",
    }


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    liga = Competition(codigo="ARG1", nombre="Liga", pais="Argentina", tipo="liga",
                       nivel="A", coeficiente=Decimal("1"))
    session.add(liga)
    session.commit()

    def club(tm_id, nombre):
        cada = Club(transfermarkt_id=tm_id, nombre=nombre, pais="Argentina")
        session.add(cada)
        session.commit()
        return cada

    def dt(tm_id, nombre, apellido):
        cada = Coach(transfermarkt_id=tm_id, nombre=nombre, apellido=apellido)
        session.add(cada)
        session.commit()
        return cada

    club_a, club_b, rival = club(9001, "Club A"), club(9002, "Club B"), club(9003, "Rival")
    viejo, actual, otro, rival_dt = (
        dt(1, "Viejo", "Técnico"), dt(2, "Actual", "Técnico"), dt(3, "Otro", "Técnico"),
        dt(4, "Rival", "Técnico"),
    )

    partido = {"id": 100}

    def jugar(dt_local, club_local, fecha):
        partido["id"] += 1
        process_match_elo(
            dt_local_id=dt_local.dt_id, dt_visita_id=rival_dt.dt_id, goles_local=1,
            goles_visita=0, competencia_id=liga.competencia_id,
            club_local_id=club_local.club_id, club_visita_id=rival.club_id,
            fecha=fecha, transfermarkt_match_id=partido["id"], session=session,
        )

    hoy = date(2026, 11, 19)
    # El Club A cambió de técnico: manda el que dirigió el último partido.
    jugar(viejo, club_a, hoy - timedelta(days=60))
    jugar(actual, club_a, hoy - timedelta(days=5))
    jugar(otro, club_b, hoy - timedelta(days=7))
    session.commit()

    yield session
    session.close()


def test_el_tecnico_de_hoy_es_el_del_ultimo_partido(db):
    grandes = [
        {"club": "A", "tm_id": 9001, "dt_2013": "Viejo Fijo"},
        {"club": "B", "tm_id": 9002, "dt_2013": "Otro Fijo"},
    ]

    filas = tecnicos_grandes(db, grandes)

    assert [(f.club, f.dt_2013, f.dt_hoy) for f in filas] == [
        ("A", "Viejo Fijo", "Actual Técnico"),
        ("B", "Otro Fijo", "Otro Técnico"),
    ]
    assert filas[0].ultimo_partido == date(2026, 11, 14)


def test_un_club_que_no_esta_en_la_base_corta_en_vez_de_publicar_a_medias(db):
    grandes = [{"club": "Fantasma", "tm_id": 424242, "dt_2013": "Nadie"}]

    with pytest.raises(ValueError, match="Fantasma"):
        tecnicos_grandes(db, grandes)


def test_la_tabla_fija_tiene_los_cinco_grandes_sin_repetir():
    assert [g["club"] for g in GRANDES] == [
        "Boca", "River", "Independiente", "Racing", "San Lorenzo",
    ]
    assert len({g["tm_id"] for g in GRANDES}) == 5
    assert all(g["dt_2013"].strip() for g in GRANDES)


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def test_el_texto_entra_en_x_y_trae_los_cinco_cruces():
    textos = textos_gta(_filas(), "17/09/2013", "19/11/2026")

    assert len(textos.texto) <= LIMITE_POST
    for cruce in (
        "Boca: Bianchi → Arruabarrena",
        "River: Díaz → Ponzio",
        "Independiente: De Felippe → Viera",
        "Racing: Merlo → Romero",
        "San Lorenzo: Pizzi → Insúa",
    ):
        assert cruce in textos.texto
    assert "GTA V" in textos.texto and "GTA VI" in textos.texto
    assert textos.alt.strip()


def test_el_texto_no_lleva_elo_ni_fuente_ni_hashtags():
    textos = textos_gta(_filas(), "17/09/2013", "19/11/2026")
    conjunto = f"{textos.texto} {textos.alt}"

    assert "#" not in conjunto
    assert "ELO" not in conjunto
    for fuente in ("Transfermarkt", "Wikipedia"):
        assert fuente not in conjunto
    # Las líneas de los clubes no llevan ninguna cifra.
    for linea in textos.texto.splitlines():
        if "→" in linea:
            assert not re.search(r"\d", linea), linea


def test_el_apellido_conserva_la_particula():
    assert _apellido_de("Omar De Felippe") == "De Felippe"
    assert _apellido_de("Juan Antonio Pizzi") == "Pizzi"
    assert _apellido_de("Ramón Díaz") == "Díaz"
    assert _apellido_de("Cristian Díaz") == "Díaz"
    assert _apellido_de("Pizzi") == "Pizzi"


# ---------------------------------------------------------------------------
# Plantilla
# ---------------------------------------------------------------------------
def test_la_plantilla_lleva_los_dos_logos_y_ningun_elo():
    html = renderizar_html("gta.html", _contexto(), "landscape")

    assert "assets/gta/gta5.png" in html and "assets/gta/gta6.png" in html
    assert "17/09/2013" in html and "19/11/2026" in html
    for nombre in ("Carlos Bianchi", "Rodolfo Arruabarrena", "Omar De Felippe", "Rubén Insúa"):
        assert nombre in html
    assert "ELO" not in html
    assert "Transfermarkt" not in html and "Wikipedia" not in html
    assert "{{" not in html


def test_los_logos_existen_y_tienen_transparencia():
    from PIL import Image

    for nombre in ("gta5.png", "gta6.png"):
        ruta = RAIZ / "assets" / "gta" / nombre
        assert ruta.exists(), nombre
        with Image.open(ruta) as imagen:
            assert imagen.mode == "RGBA"
            assert imagen.split()[-1].getextrema()[0] == 0


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
def test_gta_renderiza_las_tres_variantes(tmp_path, nombre):
    _saltar_si_no_hay_navegador()

    salida = tmp_path / f"gta_{nombre}.png"
    render_png("gta.html", _contexto(), salida, nombre)

    assert dimensiones(salida) == (VARIANTES[nombre].ancho, VARIANTES[nombre].alto)


@pytest.mark.parametrize("nombre", ["portrait", "landscape", "square"])
def test_los_nombres_largos_no_rompen_el_lienzo(tmp_path, nombre):
    """Un nombre largo se parte en dos líneas, pero la imagen tiene que seguir entrando."""
    _saltar_si_no_hay_navegador()

    filas = [
        FilaGrande(f.club, "Guillermo Martín Barros Schelotto", "Juan Sebastián Verón Fernández",
                   None)
        for f in _filas()
    ]
    render_png("gta.html", _contexto(filas), tmp_path / f"largo_{nombre}.png", nombre)


def test_la_plantilla_gta_no_nombra_la_fuente_ni_el_handle_viejo():
    html = (TEMPLATES_DIR / "gta.html").read_text(encoding="utf-8")

    assert "Transfermarkt" not in html
    assert "AEP_Analitica" not in html


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def weekly_run():
    ruta = RAIZ / "scripts" / "weekly_run.py"
    spec = importlib.util.spec_from_file_location("weekly_run_gta_test", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _sesion_falsa(weekly_run, monkeypatch):
    monkeypatch.setattr(
        weekly_run, "create_session", lambda: SimpleNamespace(close=lambda: None)
    )

    def png_falso(plantilla, contexto, salida, variante, **__):
        Path(salida).write_bytes(b"png")
        return salida

    monkeypatch.setattr(weekly_run, "render_png", png_falso)


def test_render_gta_deja_el_paquete_listo_para_telegram(weekly_run, monkeypatch, tmp_path):
    _sesion_falsa(weekly_run, monkeypatch)
    monkeypatch.setattr(weekly_run, "tecnicos_grandes", lambda *_, **__: _filas())

    resumen = weekly_run.render_gta(out_dir=tmp_path)

    assert resumen["sugerido"] == "gta"
    assert resumen["generados"][0]["archivos"] == [
        "gta_portrait.png", "gta_landscape.png", "gta_square.png",
    ]
    assert resumen["semana_iso"] == "17/09/2013 y 19/11/2026"
    assert [t["club"] for t in resumen["tecnicos_hoy"]] == [
        "Boca", "River", "Independiente", "Racing", "San Lorenzo",
    ]

    guardado = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert guardado["textos"]["gta"]["texto"] and guardado["textos"]["gta"]["alt"]
    assert "Los 5 grandes" in (tmp_path / "post.md").read_text(encoding="utf-8")


def test_render_gta_no_publica_si_falta_un_club(weekly_run, monkeypatch, tmp_path):
    _sesion_falsa(weekly_run, monkeypatch)

    def sin_club(*_, **__):
        raise ValueError("Racing: no hay club o partidos en la base.")

    monkeypatch.setattr(weekly_run, "tecnicos_grandes", sin_club)

    with pytest.raises(ValueError, match="Racing"):
        weekly_run.render_gta(out_dir=tmp_path)
    assert not (tmp_path / "summary.json").exists()
