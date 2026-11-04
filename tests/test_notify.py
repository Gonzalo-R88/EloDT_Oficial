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


def test_enviar_paquete_manda_el_formato_sugerido(monkeypatch, credenciales, tmp_path):
    (tmp_path / "top10_argentina_portrait.png").write_bytes(b"png")
    (tmp_path / "movers_argentina_portrait.png").write_bytes(b"png")
    (tmp_path / "summary.json").write_text(json.dumps({
        "semana_iso": "2026-W44", "partidos": 373, "sugerido": "top10_argentina",
        "carpeta": str(tmp_path),
        "snapshot": {"publicables": 748},
        "generados": [
            {"formato": "top10_argentina", "archivos": ["top10_argentina_portrait.png"]},
            {"formato": "movers_argentina", "archivos": ["movers_argentina_portrait.png"]},
        ],
        "omitidos": [],
    }), encoding="utf-8")
    (tmp_path / "post.md").write_text("## Formato sugerido\n\n### X\n\nTexto para X.\n\n### Instagram\n",
                                      encoding="utf-8")

    documentos = []
    mensajes = []

    def post_falso(url, data=None, files=None, timeout=None):
        if files:
            documentos.append(files["document"][0])
        else:
            mensajes.append(data["text"])
        return _RespuestaFalsa()

    monkeypatch.setattr(notify.requests, "post", post_falso)

    resultado = notify.enviar_paquete(tmp_path)

    assert documentos == ["top10_argentina_portrait.png"]  # sólo el sugerido
    assert resultado["documentos"] == 1
    assert any("Texto para X" in m for m in mensajes)
    assert any("2026-W44" in m for m in mensajes)
