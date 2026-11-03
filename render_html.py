"""Render de plantillas HTML a PNG con Jinja2 + Chromium (Playwright).

Se eligió HTML/CSS en lugar de matplotlib porque el control tipográfico y de
maquetación es mucho mejor para las imágenes de redes, y las plantillas se editan sin
tocar Python.

Chromium ya es dependencia del proyecto (el solver del WAF de Transfermarkt usa
Playwright), así que no suma infraestructura. Playwright se importa de forma perezosa:
los tests que no renderizan no lo necesitan.

Uso desde código:
    from render_html import render_png
    render_png("top10.html", contexto, variante="portrait", salida="salida.png")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
ASSETS_DIR = BASE_DIR / "assets"


@dataclass(frozen=True)
class Variante:
    """Tamaño del lienzo. Los nombres coinciden con las redes donde se publica."""

    nombre: str
    ancho: int
    alto: int


VARIANTES: dict[str, Variante] = {
    "portrait": Variante("portrait", 1080, 1350),    # LinkedIn / Instagram feed
    "landscape": Variante("landscape", 1600, 900),   # X / LinkedIn apaisado
    "square": Variante("square", 1080, 1080),        # respaldo
    "story": Variante("story", 1080, 1920),          # stories
}


def variante(nombre: str) -> Variante:
    if nombre not in VARIANTES:
        raise ValueError(f"Variante desconocida: {nombre}. Opciones: {sorted(VARIANTES)}")
    return VARIANTES[nombre]


def renderizar_html(
    plantilla: str,
    contexto: dict[str, Any],
    variante_nombre: str = "portrait",
    base_dir: Optional[Path] = None,
) -> str:
    """Renderiza la plantilla a HTML (sin navegador). Útil para testear el contexto."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    raiz = Path(base_dir or BASE_DIR)
    entorno = Environment(
        loader=FileSystemLoader(str(raiz / "templates")),
        autoescape=select_autoescape(["html"]),
    )
    entorno.filters["miles"] = lambda valor: f"{int(valor):,}".replace(",", ".")
    variable = variante(variante_nombre)
    return entorno.get_template(plantilla).render(
        variante=variable, ancho=variable.ancho, alto=variable.alto, **contexto
    )


def render_png(
    plantilla: str,
    contexto: dict[str, Any],
    salida: Path | str,
    variante_nombre: str = "portrait",
    base_dir: Optional[Path] = None,
    escala: float = 1.0,
) -> Path:
    """Renderiza la plantilla y guarda un PNG del tamaño exacto de la variante."""
    from playwright.sync_api import sync_playwright

    tamaño = variante(variante_nombre)
    raiz = Path(base_dir or BASE_DIR)
    html = renderizar_html(plantilla, contexto, variante_nombre, base_dir=raiz)

    # Se escribe el HTML al lado de las plantillas para que los `url(../assets/...)`
    # del CSS resuelvan igual que en el navegador.
    temporal = raiz / "templates" / f".render_{tamaño.nombre}.html"
    temporal.write_text(html, encoding="utf-8")

    destino = Path(salida)
    destino.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch()
            pagina = navegador.new_page(
                viewport={"width": tamaño.ancho, "height": tamaño.alto},
                device_scale_factor=escala,
            )
            pagina.goto(temporal.resolve().as_uri(), wait_until="load")
            # Sin esto la captura puede salir con la tipografía de reemplazo.
            pagina.evaluate("document.fonts.ready.then(() => true)")
            pagina.wait_for_timeout(150)
            pagina.screenshot(path=str(destino), full_page=False)
            navegador.close()
    finally:
        temporal.unlink(missing_ok=True)

    return destino


def dimensiones(ruta: Path | str) -> tuple[int, int]:
    """`(ancho, alto)` del PNG (para verificar en tests y en el pipeline)."""
    from PIL import Image

    with Image.open(ruta) as imagen:
        return imagen.size


def tamano_bytes(ruta: Path | str) -> int:
    return Path(ruta).stat().st_size
