"""Envío de avisos por Telegram.

El pipeline semanal manda el paquete a un chat privado para que el usuario revise y
publique a mano. Los PNG viajan como **documento** (no como foto) para que Telegram no
los recomprima y pierdan calidad.

Credenciales en `.env`: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. Nunca se imprimen.
Sin credenciales, `enviar_*` levanta `FaltaConfiguracion` y el pipeline lo reporta.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests

API = "https://api.telegram.org"
LIMITE_TEXTO = 4096


class FaltaConfiguracion(RuntimeError):
    """No hay token o chat id configurados."""


def credenciales() -> tuple[str, str]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise FaltaConfiguracion(
            "Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID en .env "
            "(creá el bot con @BotFather y poné el chat_id)."
        )
    return token, chat


def _post(metodo: str, datos: dict, archivos: Optional[dict] = None, timeout: int = 30) -> dict:
    token, _ = credenciales()
    respuesta = requests.post(
        f"{API}/bot{token}/{metodo}", data=datos, files=archivos, timeout=timeout
    )
    if respuesta.status_code >= 400:
        # El cuerpo no contiene el token, así que se puede mostrar el error real.
        raise RuntimeError(f"Telegram {metodo}: HTTP {respuesta.status_code} {respuesta.text[:300]}")
    return respuesta.json()


def enviar_texto(texto: str, deshabilitar_preview: bool = True) -> list[dict]:
    """Envía un texto, partiéndolo si supera el límite de Telegram."""
    _, chat = credenciales()
    enviados = []
    for trozo in _partir(texto):
        enviados.append(
            _post(
                "sendMessage",
                {
                    "chat_id": chat,
                    "text": trozo,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true" if deshabilitar_preview else "false",
                },
            )
        )
    return enviados


def enviar_documento(ruta: Path | str, caption: Optional[str] = None) -> dict:
    """Envía un archivo (PNG) como documento, sin recomprimir."""
    _, chat = credenciales()
    destino = Path(ruta)
    datos = {"chat_id": chat}
    if caption:
        datos["caption"] = caption[:1024]
    with open(destino, "rb") as archivo:
        return _post("sendDocument", datos, archivos={"document": (destino.name, archivo)})


def _partir(texto: str, limite: int = LIMITE_TEXTO - 100) -> list[str]:
    """Parte un texto largo en trozos, cortando en saltos de línea."""
    if len(texto) <= limite:
        return [texto]
    trozos: list[str] = []
    resto = texto
    while len(resto) > limite:
        corte = resto.rfind("\n", 0, limite)
        if corte <= 0:
            corte = limite
        trozos.append(resto[:corte])
        resto = resto[corte:].lstrip("\n")
    if resto:
        trozos.append(resto)
    return trozos


def enviar_paquete(carpeta: Path | str, solo_sugerido: bool = True) -> dict:
    """Manda el paquete de la semana: imágenes + resumen + textos sugeridos.

    Por defecto envía las imágenes del **formato sugerido** (las tres variantes) para
    no inundar el chat; el resto queda en `post.md` dentro de la carpeta.
    """
    raiz = Path(carpeta)
    resumen = json.loads((raiz / "summary.json").read_text(encoding="utf-8"))
    post = (raiz / "post.md").read_text(encoding="utf-8") if (raiz / "post.md").exists() else ""

    sugerido = resumen.get("sugerido")
    archivos = []
    for formato in resumen.get("generados", []):
        if solo_sugerido and formato["formato"] != sugerido:
            continue
        archivos.extend(raiz / nombre for nombre in formato["archivos"])

    enviados = []
    for archivo in archivos:
        enviados.append(enviar_documento(archivo, caption=archivo.stem.replace("_", " ")))

    mensaje = _armar_mensaje(resumen, post)
    enviados.extend(enviar_texto(mensaje))

    return {
        "documentos": len(archivos),
        "mensajes": len(enviados) - len(archivos),
        "sugerido": sugerido,
    }


def _armar_mensaje(resumen: dict, post: str) -> str:
    """Resumen corto + textos sugeridos, en HTML de Telegram."""
    lineas = [
        f"<b>Paquete semanal AEP</b> — {resumen.get('semana_iso')}",
        f"{resumen.get('partidos')} partidos · {resumen.get('snapshot', {}).get('publicables')} DTs publicables",
        f"Formato sugerido: <b>{resumen.get('sugerido')}</b>",
        "",
    ]
    if resumen.get("omitidos"):
        lineas.append("<i>Omitidos:</i> " + ", ".join(
            f"{o['formato']} ({o['motivo']})" for o in resumen["omitidos"][:4]
        ))
        lineas.append("")

    # Del post.md se toma sólo la sección de X: es la que se usa para publicar rápido.
    bloque_x = ""
    if "### X" in post:
        resto = post.split("### X", 1)[1]
        bloque_x = resto.split("###", 1)[0].strip()
    if bloque_x:
        lineas += ["<b>Texto para X:</b>", bloque_x, ""]

    lineas.append(f"Archivos en <code>{resumen.get('carpeta')}</code>")
    return "\n".join(lineas)
