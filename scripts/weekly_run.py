"""Orquestador del pipeline semanal (una sola puerta de entrada para n8n).

Subcomandos:
    render    genera el paquete de imágenes + textos de la semana en data/output/YYYY-Www/
    preflight, update, notify, all    (fases 2 y 4; por ahora avisan que faltan)

Todo imprime JSON por stdout con `--json` y devuelve un código de salida:
    0 ok · 10 bloqueo/VPN (reintentable) · 20 validación fallida · 30 otro error

Uso:
    python3 scripts/weekly_run.py render
    python3 scripts/weekly_run.py render --semana-fin 2026-11-01 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from captions import (  # noqa: E402
    textos_duelo,
    textos_movimientos,
    textos_revelacion,
    textos_top10,
)
from config import settings  # noqa: E402
from content import duelo_de_la_semana, movers, polilinea, revelacion, serie_elo, top_n  # noqa: E402
from db import create_session  # noqa: E402
from elo import MODELO_VERSION  # noqa: E402
from render_html import TEMPLATES_DIR, render_png  # noqa: E402
from snapshots import semana_fin, take_snapshot  # noqa: E402

HANDLE = "@AEP_Analitica"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
VARIANTES = ("portrait", "landscape", "square")

# Rotación del formato sugerido por semana ISO (el resto se genera igual).
ROTACION = ("top10_argentina", "movers_argentina", "duelo", "top10_global")


def texto_semana(desde: date, hasta: date) -> str:
    if desde.month == hasta.month:
        return f"{desde.day} al {hasta.day} de {MESES[hasta.month - 1]} de {hasta.year}"
    return (
        f"{desde.day} de {MESES[desde.month - 1]} al {hasta.day} de "
        f"{MESES[hasta.month - 1]} de {hasta.year}"
    )


def _formato_sugerido(cierre: date) -> str:
    return ROTACION[cierre.isocalendar().week % len(ROTACION)]


# ---------------------------------------------------------------------------
# Contextos por formato
# ---------------------------------------------------------------------------
def _contexto_top(session, cierre: date, pais: Optional[str], partidos: int):
    entradas = top_n(session, semana_fin=cierre, n=10, pais=pais)
    if len(entradas) < 3:
        return None, "no hay suficientes DTs publicables"
    desde = cierre.fromordinal(cierre.toordinal() - 6)
    return {
        "titulo": f"TOP 10 DTs DE {pais.upper()}" if pais else "TOP 10 DTs DEL MUNDO",
        "subtitulo": f"Semana del {texto_semana(desde, cierre)}",
        "entradas": entradas,
        "partidos": partidos,
        "modelo": MODELO_VERSION,
        "handle": HANDLE,
    }, None


def _contexto_duelo(session, cierre: date, semana_texto: str):
    duelo = duelo_de_la_semana(session, semana_fin=cierre)
    if duelo is None:
        return None, "no hubo partidos entre DTs publicables en la semana"

    series = serie_elo(session, [duelo.dt_a_id, duelo.dt_b_id], semanas=12, hasta=cierre)
    valores_a = [elo for _, elo in series.get(duelo.dt_a_id, [])]
    valores_b = [elo for _, elo in series.get(duelo.dt_b_id, [])]
    todos = valores_a + valores_b
    ancho, alto = 1000, 220
    grafico = {
        "ancho": ancho,
        "alto": alto,
        "semanas": 12,
        "puntos_a": polilinea(valores_a, ancho, alto, min(todos), max(todos)) if valores_a else "",
        "puntos_b": polilinea(valores_b, ancho, alto, min(todos), max(todos)) if valores_b else "",
    }
    contexto = {
        "titulo": "DUELO DE PIZARRAS",
        "subtitulo": f"Semana {semana_texto}",
        "duelo": duelo,
        "grafico": grafico,
        "handle": HANDLE,
    }
    return contexto, None


def _contexto_revelacion(session, cierre: date, semana_texto: str):
    entrada = revelacion(session, semana_fin=cierre)
    if entrada is None:
        return None, "nadie con menos de 2 años de carrera y 15+ partidos publicables"
    contexto = {
        "titulo": "DT REVELACIÓN",
        "subtitulo": f"Semana {semana_texto}",
        "entrada": entrada,
        "handle": HANDLE,
    }
    return contexto, None


def _contexto_movimientos(session, cierre: date, pais: Optional[str]):
    mov = movers(session, semana_fin=cierre, dias=7, pais=pais)
    if not mov.subidas and not mov.bajadas:
        return None, "no hubo movimientos en la semana", None
    contexto = {
        "titulo": "SUBIERON Y CAYERON",
        "subtitulo": f"Semana del {texto_semana(mov.desde, mov.hasta)}",
        "subidas": mov.subidas,
        "bajadas": mov.bajadas,
        "partidos": mov.total_partidos,
        "modelo": MODELO_VERSION,
        "handle": HANDLE,
    }
    return contexto, None, mov


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def render(
    cierre: Optional[date] = None,
    out_dir: Optional[Path] = None,
    variantes: tuple[str, ...] = VARIANTES,
) -> dict:
    """Genera el paquete de la semana y devuelve el resumen."""
    session = create_session()
    try:
        cierre = semana_fin(cierre or date.today())
        snapshot = take_snapshot(session, hasta=cierre)
        session.commit()

        mov_ar = movers(session, semana_fin=cierre, dias=7, pais="Argentina")
        partidos = mov_ar.total_partidos
        semana_texto = f"del {texto_semana(mov_ar.desde, mov_ar.hasta)}"
        destino = Path(out_dir or settings.data_dir / "output" / f"{cierre.isocalendar().year}-W{cierre.isocalendar().week:02d}")
        destino.mkdir(parents=True, exist_ok=True)

        formatos: list[dict] = []
        omitidos: list[dict] = []
        textos: dict = {}

        # Top 10 Argentina
        contexto, motivo = _contexto_top(session, cierre, "Argentina", partidos)
        if motivo:
            omitidos.append({"formato": "top10_argentina", "motivo": motivo})
        else:
            archivos = _renderizar_variantes("top10.html", contexto, destino, "top10_argentina", variantes, omitidos)
            if archivos:
                formatos.append({"formato": "top10_argentina", "archivos": archivos})
                textos["top10_argentina"] = textos_top10(
                    contexto["entradas"], semana_texto, partidos=partidos, pais="Argentina"
                )

        # Top 10 global
        contexto, motivo = _contexto_top(session, cierre, None, partidos)
        if motivo:
            omitidos.append({"formato": "top10_global", "motivo": motivo})
        else:
            archivos = _renderizar_variantes("top10.html", contexto, destino, "top10_global", variantes, omitidos)
            if archivos:
                formatos.append({"formato": "top10_global", "archivos": archivos})
                textos["top10_global"] = textos_top10(
                    contexto["entradas"], semana_texto, partidos=partidos, pais="Argentina"
                )

        # Subidas y bajadas (Argentina)
        contexto, motivo, mov = _contexto_movimientos(session, cierre, "Argentina")
        if motivo:
            omitidos.append({"formato": "movers_argentina", "motivo": motivo})
        elif not (TEMPLATES_DIR / "movers.html").exists():
            omitidos.append({"formato": "movers_argentina", "motivo": "plantilla pendiente (T3.4)"})
        else:
            archivos = _renderizar_variantes("movers.html", contexto, destino, "movers_argentina", variantes, omitidos)
            if archivos:
                formatos.append({"formato": "movers_argentina", "archivos": archivos})
                textos["movers_argentina"] = textos_movimientos(
                    contexto["subidas"], contexto["bajadas"], semana_texto, partidos=partidos
                )

        # Duelo de la semana
        contexto, motivo = _contexto_duelo(session, cierre, semana_texto)
        if motivo:
            omitidos.append({"formato": "duelo", "motivo": motivo})
        elif not (TEMPLATES_DIR / "duelo.html").exists():
            omitidos.append({"formato": "duelo", "motivo": "plantilla pendiente (T3.5)"})
        else:
            archivos = _renderizar_variantes("duelo.html", contexto, destino, "duelo", variantes, omitidos)
            if archivos:
                formatos.append({"formato": "duelo", "archivos": archivos})
                textos["duelo"] = textos_duelo(contexto["duelo"], semana_texto)

        # DT revelación
        contexto, motivo = _contexto_revelacion(session, cierre, semana_texto)
        if motivo:
            omitidos.append({"formato": "revelacion", "motivo": motivo})
        elif not (TEMPLATES_DIR / "revelacion.html").exists():
            omitidos.append({"formato": "revelacion", "motivo": "plantilla pendiente (T3.6)"})
        else:
            archivos = _renderizar_variantes("revelacion.html", contexto, destino, "revelacion", variantes, omitidos)
            if archivos:
                formatos.append({"formato": "revelacion", "archivos": archivos})
                textos["revelacion"] = textos_revelacion(contexto["entrada"], semana_texto)

        sugerido = _formato_sugerido(cierre)
        if sugerido not in textos:
            sugerido = next(iter(textos), None)

        resumen = {
            "semana_fin": cierre.isoformat(),
            "semana_iso": f"{cierre.isocalendar().year}-W{cierre.isocalendar().week:02d}",
            "modelo": MODELO_VERSION,
            "partidos": partidos,
            "snapshot": {"filas": snapshot.filas, "publicables": snapshot.publicables},
            "generados": formatos,
            "omitidos": omitidos,
            "sugerido": sugerido,
            "carpeta": str(destino),
        }
        _escribir_paquete(destino, resumen, textos, sugerido, semana_texto)
        return resumen
    finally:
        session.close()


def _renderizar_variantes(
    plantilla: str,
    contexto: dict,
    destino: Path,
    prefijo: str,
    variantes: tuple[str, ...],
    omitidos: list[dict],
) -> list[str]:
    """Renderiza las variantes que entren; las que fallan quedan registradas."""
    archivos: list[str] = []
    for nombre in variantes:
        salida = destino / f"{prefijo}_{nombre}.png"
        try:
            render_png(plantilla, contexto, salida, nombre)
            archivos.append(salida.name)
        except Exception as error:  # noqa: BLE001 - una variante no debe romper el lote
            omitidos.append({"formato": f"{prefijo}_{nombre}", "motivo": str(error)[:200]})
    return archivos


def _escribir_paquete(
    destino: Path,
    resumen: dict,
    textos: dict,
    sugerido: Optional[str],
    semana_texto: str,
) -> None:
    (destino / "summary.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lineas = [f"# Paquete semanal — {semana_texto}", ""]
    lineas.append(f"Modelo `{resumen['modelo']}` · {resumen['partidos']} partidos en la ventana.")
    lineas.append("")
    if sugerido and sugerido in textos:
        elegido = textos[sugerido]
        lineas += [f"## Formato sugerido: {sugerido}", "", "### LinkedIn", "", elegido.linkedin, ""]
        lineas += ["### X", "", elegido.x, ""]
        lineas += ["### Instagram", "", elegido.instagram, ""]
        lineas += ["### Texto alternativo de la imagen", "", elegido.alt, ""]
    for formato, contenido in textos.items():
        if formato == sugerido:
            continue
        lineas += [f"## {formato}", "", "### LinkedIn", "", contenido.linkedin, "",
                   "### X", "", contenido.x, "", "### Instagram", "", contenido.instagram,
                   "", "### Alt", "", contenido.alt, ""]
    if resumen["omitidos"]:
        lineas += ["## Formatos omitidos", ""]
        lineas += [f"- **{o['formato']}**: {o['motivo']}" for o in resumen["omitidos"]]
        lineas.append("")
    lineas += ["## Archivos generados", ""]
    for formato in resumen["generados"]:
        lineas.append(f"- {formato['formato']}: " + ", ".join(formato["archivos"]))
    (destino / "post.md").write_text("\n".join(lineas), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _pendiente(nombre: str) -> int:
    print(json.dumps({"ok": False, "subcomando": nombre,
                      "motivo": "pendiente (fase 2/4)"}, ensure_ascii=False))
    return 30


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline semanal AEP.")
    sub = parser.add_subparsers(dest="comando", required=True)

    render_parser = sub.add_parser("render", help="Genera imágenes y textos de la semana.")
    render_parser.add_argument("--semana-fin", type=date.fromisoformat, default=None)
    render_parser.add_argument("--salida", type=Path, default=None)
    render_parser.add_argument("--json", action="store_true")

    for nombre in ("preflight", "update", "notify", "all"):
        p = sub.add_parser(nombre)
        p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.comando == "render":
        try:
            resumen = render(cierre=args.semana_fin, out_dir=args.salida)
        except Exception as error:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
            return 30
        if args.json:
            print(json.dumps({"ok": True, **resumen}, ensure_ascii=False))
        else:
            print(f"semana {resumen['semana_iso']} · {resumen['partidos']} partidos")
            for formato in resumen["generados"]:
                print(f"  ✓ {formato['formato']}: {', '.join(formato['archivos'])}")
            for omitido in resumen["omitidos"]:
                print(f"  – {omitido['formato']}: {omitido['motivo']}")
            print(f"  sugerido: {resumen['sugerido']}")
            print(f"  carpeta: {resumen['carpeta']}")
        return 0

    return _pendiente(args.comando)


if __name__ == "__main__":
    raise SystemExit(main())
