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
