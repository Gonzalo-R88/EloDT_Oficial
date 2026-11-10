"""Tests del orquestador (`scripts/weekly_run.py`), sin base ni red.

Se carga por ruta porque vive en `scripts/`, que no es un paquete.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def weekly_run():
    ruta = RAIZ / "scripts" / "weekly_run.py"
    spec = importlib.util.spec_from_file_location("weekly_run_test", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_all_no_renderiza_si_la_semana_ya_esta(weekly_run, monkeypatch):
    """Si el update se saltea, no se vuelve a renderizar ni a mandar el paquete."""
    monkeypatch.setattr(weekly_run, "update", lambda **_: (0, {"skip": True, "semana": "2026-W44"}))
    llamado = {"render": False}

    def _render(**kwargs):
        llamado["render"] = True
        return {}

    monkeypatch.setattr(weekly_run, "render", _render)

    monkeypatch.setattr(
        sys, "argv",
        ["weekly_run.py", "all", "--skip-if-done-this-week", "--json"],
    )
    codigo = weekly_run.main()

    assert codigo == 0
    assert llamado["render"] is False


def test_all_corta_si_el_update_falla(weekly_run, monkeypatch):
    monkeypatch.setattr(weekly_run, "update", lambda **_: (10, {"error": "sin VPN"}))
    monkeypatch.setattr(
        sys, "argv", ["weekly_run.py", "all", "--json"]
    )

    assert weekly_run.main() == 10


# ---------------------------------------------------------------------------
# render: el paquete que se manda por Telegram
# ---------------------------------------------------------------------------
def _paquete_sin_base(weekly_run, monkeypatch, tmp_path) -> dict:
    """Renderiza con la base simulada: nada de Postgres ni de Chromium."""
    from datetime import date
    from types import SimpleNamespace

    from content import EntradaTop

    def entradas(pais):
        return [
            EntradaTop(
                dt_id=puesto, dt=f"DT de Prueba {puesto}", club="Club de Prueba",
                pais=pais or "Inglaterra", liga="AR1N", elo=1300.0 - puesto, pj=40,
                etiqueta=None, puesto=puesto, puesto_previo=None,
            )
            for puesto in range(1, 11)
        ]

    sesion = SimpleNamespace(close=lambda: None, commit=lambda: None)
    monkeypatch.setattr(weekly_run, "create_session", lambda: sesion)
    monkeypatch.setattr(
        weekly_run, "take_snapshot",
        lambda *_, **__: SimpleNamespace(filas=100, publicables=50),
    )
    monkeypatch.setattr(
        weekly_run, "movers",
        lambda *_, **__: SimpleNamespace(
            desde=date(2026, 10, 26), hasta=date(2026, 11, 1), total_partidos=42,
            subidas=[SimpleNamespace(dt="Federico Medina", delta=14.2)],
            bajadas=[SimpleNamespace(dt="Marcelo Gallardo", delta=-11.8)],
        ),
    )
    monkeypatch.setattr(weekly_run, "top_n", lambda *_, pais=None, **__: entradas(pais))
    monkeypatch.setattr(weekly_run, "duelo_de_la_semana", lambda *_, **__: None)
    monkeypatch.setattr(weekly_run, "revelacion", lambda *_, **__: None)

    def png_falso(plantilla, contexto, salida, variante, **__):
        Path(salida).write_bytes(b"png")
        return salida

    monkeypatch.setattr(weekly_run, "render_png", png_falso)

    return weekly_run.render(cierre=date(2026, 11, 1), out_dir=tmp_path)


def test_render_deja_los_textos_en_el_resumen(weekly_run, monkeypatch, tmp_path):
    """notify.py se alimenta de summary.json: sin textos ahí, no hay nada que mandar."""
    import json

    resumen = _paquete_sin_base(weekly_run, monkeypatch, tmp_path)

    generados = {formato["formato"] for formato in resumen["generados"]}
    assert {"top10_argentina", "top10_global", "movers_argentina"} <= generados
    assert set(resumen["textos"]) == set(resumen["textos"]) & generados

    guardado = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert guardado["textos"]["top10_argentina"]["texto"]
    assert guardado["textos"]["top10_argentina"]["alt"]


def test_el_post_global_no_se_anuncia_como_argentina(weekly_run, monkeypatch, tmp_path):
    """El Top 10 mundial salía con el título de Argentina."""
    resumen = _paquete_sin_base(weekly_run, monkeypatch, tmp_path)

    global_ = resumen["textos"]["top10_global"]["texto"]
    argentina = resumen["textos"]["top10_argentina"]["texto"]

    assert "del mundo" in global_
    assert "Argentina" not in global_
    assert "de Argentina" in argentina


def test_cada_post_generado_lleva_etiqueta(weekly_run, monkeypatch, tmp_path):
    """La etiqueta es lo que identifica al post en el mensaje de Telegram."""
    resumen = _paquete_sin_base(weekly_run, monkeypatch, tmp_path)

    for formato in resumen["generados"]:
        assert formato["titulo"] == weekly_run.ETIQUETAS[formato["formato"]]
