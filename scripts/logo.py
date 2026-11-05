"""Genera las imágenes de marca: foto de perfil y banner de X.

El diseño vive en `templates/brand/marcador.html` y resuelve las dos medidas con la
variable `formato` ('perfil' o 'banner'), así que se edita en un solo archivo.

    python3 scripts/logo.py [--handle @EloDt_Oficial] [--salida assets/brand]

El perfil se renderiza al doble (800×800) porque X lo muestra a 400 y así queda nítido en
pantallas retina; el banner sale a 1500×500, que es la medida que recomienda X.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from render_html import dimensiones, render_png  # noqa: E402

PLANTILLA = "brand/marcador.html"
HANDLE = "@EloDt_Oficial"
FORMATOS = (("perfil", 2.0), ("banner", 1.0))


def generar(handle: str, salida: Path) -> list[Path]:
    salida.mkdir(parents=True, exist_ok=True)
    generados: list[Path] = []

    for formato, escala in FORMATOS:
        destino = salida / f"{formato}.png"
        render_png(
            PLANTILLA,
            {"handle": handle, "formato": formato},
            destino,
            variante_nombre=formato,
            escala=escala,
        )
        generados.append(destino)

    return generados


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el logo (perfil y banner) de la marca.")
    parser.add_argument("--handle", default=HANDLE, help="Usuario de X que va en el banner.")
    parser.add_argument(
        "--salida",
        type=Path,
        default=RAIZ / "assets" / "brand",
        help="Carpeta destino (default: assets/brand).",
    )
    args = parser.parse_args()

    for ruta in generar(args.handle, args.salida):
        ancho, alto = dimensiones(ruta)
        print(f"  {ruta.relative_to(RAIZ)}  {ancho}×{alto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
