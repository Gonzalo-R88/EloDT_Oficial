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
def _paquete_sin_base(weekly_run, monkeypatch, tmp_path, subidas=3, bajadas=3) -> dict:
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
            subidas=[SimpleNamespace(dt=f"Subió {i}", delta=14.2 - i) for i in range(subidas)],
            bajadas=[SimpleNamespace(dt=f"Bajó {i}", delta=-11.8 + i) for i in range(bajadas)],
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


def test_semana_con_pocos_movimientos_omite_el_formato(weekly_run, monkeypatch, tmp_path):
    """En una fecha FIFA hay un solo partido argentino: un +x y un -x no es un post."""
    resumen = _paquete_sin_base(weekly_run, monkeypatch, tmp_path, subidas=1, bajadas=1)

    assert "movers_argentina" not in resumen["textos"]
    omitido = next(o for o in resumen["omitidos"] if o["formato"] == "movers_argentina")
    assert "muy pocos movimientos" in omitido["motivo"]


def test_el_sugerido_pasa_al_siguiente_si_el_que_toca_se_omitio(weekly_run):
    from datetime import date

    # Semana ISO 46 -> índice 2 de la rotación (duelo); si falta, sigue top10_global.
    cierre = date(2026, 11, 15)
    assert weekly_run._formato_sugerido(cierre) == "duelo"
    assert weekly_run._formato_sugerido(cierre, ["top10_argentina", "top10_global"]) == "top10_global"
    assert weekly_run._formato_sugerido(cierre, ["movers_argentina"]) == "movers_argentina"
    assert weekly_run._formato_sugerido(cierre, []) is None


def test_revelados_recientes_mira_8_semanas_y_no_la_actual(weekly_run, tmp_path):
    import json
    from datetime import date, timedelta

    cierre = date(2026, 11, 15)

    def paquete(atras, dt_id):
        anio, semana, _ = (cierre - timedelta(weeks=atras)).isocalendar()
        carpeta = tmp_path / f"{anio}-W{semana:02d}"
        carpeta.mkdir()
        (carpeta / "summary.json").write_text(
            json.dumps({"elegidos": {"revelacion": dt_id}}), encoding="utf-8"
        )

    paquete(0, 99)  # la semana en curso: re-renderizar no puede excluir a su propio elegido
    paquete(1, 11)
    paquete(8, 88)
    paquete(9, 77)  # fuera de la ventana
    carpeta_vieja = tmp_path / "2026-W44"  # sin la clave `elegidos`
    carpeta_vieja.mkdir(exist_ok=True)
    (carpeta_vieja / "summary.json").write_text("{}", encoding="utf-8")

    assert weekly_run._revelados_recientes(tmp_path, cierre) == {11, 88}


def test_el_resumen_guarda_a_quien_se_eligio_de_revelacion(weekly_run, monkeypatch, tmp_path):
    import json
    from datetime import date
    from types import SimpleNamespace

    resumen = _paquete_sin_base(weekly_run, monkeypatch, tmp_path)
    assert resumen["elegidos"] == {}

    monkeypatch.setattr(
        weekly_run, "revelacion",
        lambda *_, **__: SimpleNamespace(
            dt_id=321, dt="DT Nuevo", club="Club", pais="Argentina", elo=1100.0, pj=31,
            desde_primera_fecha=date(2025, 3, 1), variacion=20.0, etiqueta=None,
        ),
    )
    resumen = weekly_run.render(cierre=date(2026, 11, 1), out_dir=tmp_path)

    assert resumen["elegidos"] == {"revelacion": 321}
    guardado = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert guardado["elegidos"] == {"revelacion": 321}


# ---------------------------------------------------------------------------
# Fecha FIFA (selecciones)
# ---------------------------------------------------------------------------
def _ventana(desde="2026-11-12", hasta="2026-11-17"):
    from datetime import date

    from selecciones import VentanaFifa

    return VentanaFifa(
        desde=date.fromisoformat(desde), hasta=date.fromisoformat(hasta), partidos=40
    )


def test_fecha_fifa_espera_los_dias_de_gracia(weekly_run, monkeypatch, tmp_path):
    """El último partido fue el 17: el 18 todavía no se publica, el 19 sí."""
    from datetime import date

    monkeypatch.setattr(weekly_run, "ventana_fifa", lambda *_, **__: _ventana())
    monkeypatch.setattr(weekly_run, "_marcador_fifa", lambda hasta: tmp_path / f"fifa-{hasta}.json")

    ventana, motivo = weekly_run._ventana_a_publicar(None, date(2026, 11, 18))
    assert ventana is None
    assert "2 días después" in motivo

    ventana, motivo = weekly_run._ventana_a_publicar(None, date(2026, 11, 19))
    assert ventana is not None
    assert motivo == "ok"


def test_fecha_fifa_no_publica_dos_veces(weekly_run, monkeypatch, tmp_path):
    from datetime import date

    (tmp_path / "fifa-2026-11-17.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(weekly_run, "ventana_fifa", lambda *_, **__: _ventana())
    monkeypatch.setattr(weekly_run, "_marcador_fifa", lambda hasta: tmp_path / f"fifa-{hasta}.json")

    ventana, motivo = weekly_run._ventana_a_publicar(None, date(2026, 11, 20))

    assert ventana is None
    assert "ya se publicó" in motivo


def test_fecha_fifa_no_publica_con_la_ventana_en_juego(weekly_run, monkeypatch, tmp_path):
    from datetime import date

    monkeypatch.setattr(weekly_run, "ventana_fifa", lambda *_, **__: _ventana())
    monkeypatch.setattr(weekly_run, "_marcador_fifa", lambda hasta: tmp_path / f"fifa-{hasta}.json")

    ventana, motivo = weekly_run._ventana_a_publicar(None, date(2026, 11, 17))

    assert ventana is None
    assert "sigue en juego" in motivo


def test_sin_partidos_de_selecciones_no_hay_ventana(weekly_run, monkeypatch):
    monkeypatch.setattr(weekly_run, "ventana_fifa", lambda *_, **__: None)

    ventana, motivo = weekly_run._ventana_a_publicar(None, None)

    assert ventana is None
    assert "no hubo partidos de selecciones" in motivo
