"""Envío de avisos por Telegram.

El pipeline semanal manda el paquete a un chat privado para que el usuario revise y
publique a mano. Los PNG viajan como **documento** (no como foto) para que Telegram no
los recomprima y pierdan calidad.

Credenciales en `.env`: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. Nunca se imprimen.
Sin credenciales, `enviar_*` levanta `FaltaConfiguracion` y el pipeline lo reporta.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Optional, Sequence

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


def enviar_paquete(carpeta: Path | str, variante: str = "landscape") -> dict:
    """Manda el paquete de la semana: una imagen y un texto por post, más la cabecera.

    Cada post llega identificado (número, nombre y red) y después su texto, en un bloque
    monoespaciado para copiarlo de una pieza. Se envía la variante apaisada porque es la
    que X y LinkedIn muestran completa; los otros tamaños quedan en la carpeta.
    """
    raiz = Path(carpeta)
    resumen = json.loads((raiz / "summary.json").read_text(encoding="utf-8"))
    generados = list(resumen.get("generados", []))
    textos = resumen.get("textos", {})
    sugerido = resumen.get("sugerido")

    # El sugerido primero; el resto conserva el orden de generación.
    orden = sorted(generados, key=lambda formato: formato["formato"] != sugerido)

    enviar_texto(_cabecera(resumen, orden, sugerido))

    documentos = 0
    mensajes = 0
    for indice, formato in enumerate(orden, 1):
        nombre = formato["formato"]
        etiqueta = formato.get("titulo", nombre)
        archivo = _elegir_archivo(raiz, formato.get("archivos", []), variante)
        if archivo:
            enviar_documento(archivo, caption=_caption_post(indice, len(orden), etiqueta, nombre == sugerido))
            documentos += 1
        enviar_texto(_texto_del_post(etiqueta, textos.get(nombre, {})))
        mensajes += 1

    return {
        "ok": True,
        "posts": len(orden),
        "documentos": documentos,
        "mensajes": mensajes + 1,  # + la cabecera
        "sugerido": sugerido,
    }


def _elegir_archivo(raiz: Path, archivos: Sequence[str], variante: str) -> Optional[Path]:
    """El archivo de la variante pedida; si no está, el primero que haya."""
    for nombre in archivos:
        if f"_{variante}." in nombre:
            return raiz / nombre
    return raiz / archivos[0] if archivos else None


def _caption_post(indice: int, total: int, etiqueta: str, sugerido: bool) -> str:
    """Leyenda de la imagen: qué post es, para qué red y si es el sugerido."""
    estrellas = " ⭐ sugerido" if sugerido else ""
    return f"POST {indice} de {total} · {etiqueta}{estrellas} · X + LinkedIn"


def _texto_del_post(etiqueta: str, contenido: dict) -> str:
    """El texto para copiar, en bloque monoespaciado, más el alt de la imagen."""
    lineas = [f"<b>Texto del post — {_escapar(etiqueta)}</b> (X y LinkedIn)"]
    texto = contenido.get("texto")
    if texto:
        lineas += ["<code>" + _escapar(texto) + "</code>"]
    alt = contenido.get("alt")
    if alt:
        lineas += ["<i>Alt de la imagen:</i>", "<code>" + _escapar(alt) + "</code>"]
    return "\n".join(lineas)


def _cabecera(resumen: dict, orden: list, sugerido: Optional[str]) -> str:
    """Encabezado del paquete: qué semana es y qué trae."""
    etiquetas = {formato["formato"]: formato.get("titulo", formato["formato"]) for formato in orden}
    titulo = resumen.get("titulo_paquete") or "Paquete semanal ELO DT"
    lineas = [f"<b>{titulo}</b> — {resumen.get('semana_iso')}"]
    # El paquete de fecha FIFA no lleva snapshot semanal: su línea de publicables no aplica.
    snapshot = resumen.get("snapshot") or {}
    detalle = f"{resumen.get('partidos')} partidos"
    if snapshot.get("publicables"):
        detalle += f" · {snapshot['publicables']} DTs publicables"
    lineas.append(detalle)
    lineas.append(
        f"{len(orden)} posts · sugerido: <b>{_escapar(str(etiquetas.get(sugerido, sugerido)))}</b>"
    )
    if resumen.get("omitidos"):
        omitidos = ", ".join(o["formato"] for o in resumen["omitidos"])
        lineas.append(f"<i>Sin generar:</i> {_escapar(omitidos)}")
    lineas.append("Cada post va con su imagen y su texto.")
    return "\n".join(lineas)


def _escapar(texto: str) -> str:
    """Telegram parsea HTML: los nombres con `&`, `<` o `>` romperían el mensaje."""
    return html.escape(texto, quote=False)
