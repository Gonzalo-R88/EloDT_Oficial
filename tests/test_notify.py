"""Tests del envío por Telegram (`notify.py`), sin red."""

import json
from pathlib import Path

import pytest

import notify


class _RespuestaFalsa:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"ok": True, "result": {}}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


@pytest.fixture
def credenciales(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCdef")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")


def test_sin_credenciales_falla(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(notify.FaltaConfiguracion):
        notify.credenciales()


def test_enviar_texto_llama_a_la_api(monkeypatch, credenciales):
    llamadas = []

    def post_falso(url, data=None, files=None, timeout=None):
        llamadas.append((url, data))
        return _RespuestaFalsa()

    monkeypatch.setattr(notify.requests, "post", post_falso)

    notify.enviar_texto("hola")

    assert len(llamadas) == 1
    url, datos = llamadas[0]
    assert url.endswith("/sendMessage")
    assert datos["chat_id"] == "999"
    assert datos["text"] == "hola"
    # El token no debe quedar en los datos que se envían al chat.
    assert "123456:ABCdef" not in json.dumps(datos)


def test_enviar_texto_largo_se_parte(monkeypatch, credenciales):
    enviados = []

    def post_falso(url, data=None, files=None, timeout=None):
        enviados.append(data["text"])
        return _RespuestaFalsa()

    monkeypatch.setattr(notify.requests, "post", post_falso)

    notify.enviar_texto("línea\n" * 2000)

    assert len(enviados) > 1
    assert all(len(trozo) <= notify.LIMITE_TEXTO for trozo in enviados)


def test_error_de_telegram_se_propaga(monkeypatch, credenciales):
    monkeypatch.setattr(
        notify.requests, "post",
        lambda *a, **k: _RespuestaFalsa(401, {"ok": False, "description": "Unauthorized"}),
    )

    with pytest.raises(RuntimeError, match="401"):
        notify.enviar_texto("hola")


def test_enviar_documento_adjunta_el_archivo(monkeypatch, credenciales, tmp_path):
    archivo = tmp_path / "imagen.png"
    archivo.write_bytes(b"\x89PNG")
    capturado = {}

    def post_falso(url, data=None, files=None, timeout=None):
        capturado["datos"] = data
        capturado["archivo"] = files["document"][0]
        return _RespuestaFalsa()

    monkeypatch.setattr(notify.requests, "post", post_falso)

    notify.enviar_documento(archivo, caption="Top 10")

    assert capturado["archivo"] == "imagen.png"
    assert capturado["datos"]["caption"] == "Top 10"


def _paquete_de_prueba(tmp_path, sugerido="movers_argentina"):
    for nombre in (
        "top10_argentina_landscape.png", "top10_argentina_portrait.png",
        "movers_argentina_landscape.png", "movers_argentina_portrait.png",
    ):
        (tmp_path / nombre).write_bytes(b"png")
    (tmp_path / "summary.json").write_text(json.dumps({
        "semana_iso": "2026-W44", "partidos": 373, "sugerido": sugerido,
        "carpeta": str(tmp_path), "snapshot": {"publicables": 748},
        "generados": [
            {"formato": "top10_argentina", "titulo": "Top 10 Argentina",
             "archivos": ["top10_argentina_portrait.png", "top10_argentina_landscape.png"]},
            {"formato": "movers_argentina", "titulo": "Subieron y cayeron",
             "archivos": ["movers_argentina_portrait.png", "movers_argentina_landscape.png"]},
        ],
        "textos": {
            "top10_argentina": {"texto": "Texto del top 10", "alt": "Alt del top 10"},
            "movers_argentina": {"texto": "Texto de movers", "alt": "Alt de movers"},
        },
        "omitidos": [],
    }), encoding="utf-8")


def _capturar(monkeypatch):
    enviados = {"documentos": [], "mensajes": []}

    def post_falso(url, data=None, files=None, timeout=None):
        if files:
            enviados["documentos"].append((files["document"][0], data.get("caption")))
        else:
            enviados["mensajes"].append(data["text"])
        return _RespuestaFalsa()

    monkeypatch.setattr(notify.requests, "post", post_falso)
    return enviados


def test_enviar_paquete_manda_todos_los_posts_identificados(monkeypatch, credenciales, tmp_path):
    _paquete_de_prueba(tmp_path, sugerido="movers_argentina")
    enviados = _capturar(monkeypatch)

    resultado = notify.enviar_paquete(tmp_path)

    # El sugerido va primero y se manda una imagen por post, la apaisada.
    assert enviados["documentos"] == [
        ("movers_argentina_landscape.png", "POST 1 de 2 · Subieron y cayeron ⭐ sugerido · X + LinkedIn"),
        ("top10_argentina_landscape.png", "POST 2 de 2 · Top 10 Argentina · X + LinkedIn"),
    ]
    assert resultado["ok"] is True
    assert resultado["posts"] == 2
    assert resultado["sugerido"] == "movers_argentina"


def test_enviar_paquete_manda_el_texto_de_cada_post(monkeypatch, credenciales, tmp_path):
    _paquete_de_prueba(tmp_path)
    enviados = _capturar(monkeypatch)

    notify.enviar_paquete(tmp_path)

    # Cabecera con la semana y el total de posts.
    assert any("2026-W44" in m and "2 posts" in m for m in enviados["mensajes"])
    # Un mensaje por post, con su texto y su alt en bloque para copiar.
    assert any("Texto de movers" in m and "Alt de movers" in m for m in enviados["mensajes"])
    assert any("Texto del top 10" in m and "Alt del top 10" in m for m in enviados["mensajes"])
    assert all("####" not in m for m in enviados["mensajes"])


def test_el_texto_se_escapa_para_html(monkeypatch, credenciales, tmp_path):
    """Un nombre con & o < rompería el HTML de Telegram."""
    _paquete_de_prueba(tmp_path)
    resumen = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    resumen["textos"]["movers_argentina"]["texto"] = "Racing & <Independiente>"
    (tmp_path / "summary.json").write_text(json.dumps(resumen), encoding="utf-8")
    enviados = _capturar(monkeypatch)

    notify.enviar_paquete(tmp_path)

    mensaje = next(m for m in enviados["mensajes"] if "Racing" in m)
    assert "Racing &amp; &lt;Independiente&gt;" in mensaje
