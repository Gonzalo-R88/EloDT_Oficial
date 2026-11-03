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
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from actualizacion import (  # noqa: E402
    DIAS_REVISION,
    aplicar_correcciones,
    detectar_correcciones,
    recomputar_con_tiempo,
    validar_invariantes,
)
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
# Update semanal (T2.4 + T2.5)
# ---------------------------------------------------------------------------
LOCK = "weekly.lock"


def _ruta_lock() -> Path:
    return Path(settings.data_dir) / LOCK


def _tomar_lock() -> bool:
    """Crea el lock; devuelve False si ya hay una corrida en curso viva."""
    ruta = _ruta_lock()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        try:
            pid = int(ruta.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if pid and _proceso_vivo(pid):
            return False
        ruta.unlink(missing_ok=True)
    ruta.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _proceso_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _liberar_lock() -> None:
    _ruta_lock().unlink(missing_ok=True)


def _preflight() -> tuple[bool, str]:
    """Base accesible y Transfermarkt alcanzable. Devuelve `(ok, motivo)`."""
    session = create_session()
    try:
        session.execute(text("select 1 from partidos_dt limit 1")).first()
    except Exception as error:  # noqa: BLE001
        return False, f"base de datos no responde: {error}"
    finally:
        session.close()

    try:
        from scraper_transfermarkt import build_client

        cliente = build_client()
        cliente.get(f"https://{settings.transfermarkt_domain}/")
    except Exception as error:  # noqa: BLE001
        return False, f"Transfermarkt no responde ({error}); revisá la VPN"
    return True, "ok"


def _cargar_nuevos(session, store, cierre: date) -> dict:
    """Carga a la base los reportes cacheados de las temporadas en curso."""
    from scraping.competitions import COMPETITIONS
    from scraping.pipeline import (
        load_normalized,
        persist_matches,
        temporada_cerrada,
        temporadas_en_curso,
    )

    stats = {"procesados": 0, "duplicados": 0, "sin_dt": 0, "sin_fecha": 0}
    for config in COMPETITIONS.values():
        if temporada_cerrada(config, cierre):
            continue
        for season in temporadas_en_curso(config, cierre):
            if not store.has_fixtures(config.code, season):
                continue
            partidos = [
                p for p in load_normalized(config, season, store)
                if not p.date or p.date <= cierre.isoformat()
            ]
            if not partidos:
                continue
            resultado = persist_matches(partidos, session=session)
            for clave in stats:
                stats[clave] += resultado.get(clave, 0)
    session.commit()
    return stats


def _competencias_inactivas(session, cierre: date, dias: int = 14) -> list[str]:
    desde = cierre - timedelta(days=dias)
    filas = session.execute(
        text(
            "select c.codigo from competencias c left join "
            "(select competencia_id, max(fecha) ultimo from partidos_dt group by 1) p "
            "on p.competencia_id = c.competencia_id "
            "where p.ultimo is null or p.ultimo < :desde order by c.codigo"
        ),
        {"desde": desde},
    ).all()
    return [fila[0] for fila in filas if fila[0]]


def update(
    cierre: Optional[date] = None,
    dry_run: bool = False,
    skip_if_done: bool = False,
    limit: Optional[int] = None,
) -> tuple[int, dict]:
    """Actualización semanal completa. Devuelve `(codigo_salida, resumen)`."""
    cierre = semana_fin(cierre or date.today())

    if skip_if_done:
        session = create_session()
        try:
            ya = session.execute(
                text(
                    "select 1 from ejecuciones_pipeline where estado = 'ok' "
                    "and semana_fin = :c limit 1"
                ),
                {"c": cierre},
            ).first()
        finally:
            session.close()
        if ya:
            return 0, {"skip": True, "motivo": "ya corrió esta semana", "semana_fin": cierre.isoformat()}

    if not _tomar_lock():
        return 30, {"error": "otra corrida en curso (weekly.lock)"}

    session = create_session()
    run_id = None
    try:
        from models import EjecucionPipeline

        ejecucion = EjecucionPipeline(semana_fin=cierre, estado="corriendo")
        session.add(ejecucion)
        session.commit()
        run_id = ejecucion.run_id

        ok, motivo = _preflight()
        if dry_run:
            return (0 if ok else 10), {
                "dry_run": True,
                "semana_fin": cierre.isoformat(),
                "preflight": motivo,
            }
        if not ok:
            raise _Bloqueo(motivo)

        # 1) Scraping incremental
        from scraper_transfermarkt import build_client
        from scraping.competitions import COMPETITIONS
        from scraping.pipeline import scrape_incremental
        from scraping.storage import RawStore

        store = RawStore(settings.data_dir)
        cliente = build_client()
        cliente.warm_up()
        scrapeo = {"fixtures": 0, "reportes": 0, "omitidos_fecha": 0, "errores": 0}
        for config in COMPETITIONS.values():
            stats = scrape_incremental(
                config, cliente, store, semana_fin=cierre, limit=limit
            )
            for clave in scrapeo:
                scrapeo[clave] += stats.get(clave, 0)

        # 2) Carga
        carga = _cargar_nuevos(session, store, cierre)

        # 3) Correcciones
        correcciones = detectar_correcciones(
            session, Path(settings.data_dir), cierre - timedelta(days=DIAS_REVISION)
        )
        aplicadas = aplicar_correcciones(session, correcciones) if correcciones else 0

        # 4) Recálculo (si hubo algo nuevo o correcciones)
        segundos = None
        if carga["procesados"] or aplicadas:
            segundos = recomputar_con_tiempo(session)

        # 5) Validación
        valido, detalle = validar_invariantes(session)
        if not valido:
            raise _Validacion(detalle)

        # 6) Cobertura y snapshot
        subprocess.run(
            [sys.executable, "scripts/audit_data.py"],
            capture_output=True, check=False, cwd=str(Path(__file__).resolve().parent.parent),
        )
        snapshot = take_snapshot(session, hasta=cierre)
        session.commit()

        ultimo = session.execute(text("select max(fecha) from partidos_dt")).scalar()
        resumen = {
            "semana_fin": cierre.isoformat(),
            "nuevos": carga["procesados"],
            "descartados_sin_dt": carga["sin_dt"],
            "correcciones": aplicadas,
            "scrapeo": scrapeo,
            "competencias_sin_partidos_14d": _competencias_inactivas(session, cierre),
            "dias_desde_ultimo_partido": (date.today() - ultimo).days if ultimo else None,
            "tiempo_recompute_s": segundos,
            "snapshot_filas": snapshot.filas,
            "snapshot_publicables": snapshot.publicables,
        }
        ejecucion = session.get(EjecucionPipeline, run_id)
        ejecucion.estado = "ok"
        ejecucion.terminado_en = datetime.now(timezone.utc)
        ejecucion.resumen = resumen
        session.commit()
        return 0, resumen

    except _Bloqueo as error:
        _registrar_error(session, run_id, "bloqueo", {"motivo": str(error)})
        return 10, {"error": str(error), "reintentable": True}
    except _Validacion as error:
        _registrar_error(session, run_id, "validacion", error.detalle)
        return 20, {"error": "validación falló", **error.detalle}
    except Exception as error:  # noqa: BLE001
        _registrar_error(session, run_id, "error", {"motivo": str(error)})
        return 30, {"error": str(error)}
    finally:
        session.close()
        _liberar_lock()


class _Bloqueo(Exception):
    """Bloqueo externo (VPN/base): reintentable."""


class _Validacion(Exception):
    """Las invariantes del ELO no se cumplen: no se publica."""

    def __init__(self, detalle: dict):
        super().__init__("validación fallida")
        self.detalle = detalle


def _registrar_error(session, run_id, estado: str, detalle: dict) -> None:
    from models import EjecucionPipeline

    if run_id is None:
        return
    try:
        ejecucion = session.get(EjecucionPipeline, run_id)
        ejecucion.estado = estado
        ejecucion.terminado_en = datetime.now(timezone.utc)
        ejecucion.resumen = detalle
        session.commit()
    except Exception:  # noqa: BLE001 - nunca enmascarar el error original
        session.rollback()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _pendiente(nombre: str) -> int:
    print(json.dumps({"ok": False, "subcomando": nombre,
                      "motivo": "pendiente (fase 2/4)"}, ensure_ascii=False))
    return 30


def _configurar_logging() -> None:
    """Log a archivo además de la salida estándar (n8n sólo ve el stdout)."""
    import logging

    destino = Path(settings.data_dir) / "logs"
    destino.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(destino / "weekly.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    _configurar_logging()
    parser = argparse.ArgumentParser(description="Pipeline semanal AEP.")
    sub = parser.add_subparsers(dest="comando", required=True)

    render_parser = sub.add_parser("render", help="Genera imágenes y textos de la semana.")
    render_parser.add_argument("--semana-fin", type=date.fromisoformat, default=None)
    render_parser.add_argument("--salida", type=Path, default=None)
    render_parser.add_argument("--json", action="store_true")

    update_parser = sub.add_parser("update", help="Scraping incremental + correcciones + recálculo.")
    update_parser.add_argument("--semana-fin", type=date.fromisoformat, default=None)
    update_parser.add_argument("--dry-run", action="store_true",
                               help="No descarga ni escribe: sólo verifica el entorno.")
    update_parser.add_argument("--skip-if-done-this-week", action="store_true",
                               help="Si ya corrió bien para esa semana, no hace nada.")
    update_parser.add_argument("--limit", type=int, default=None,
                               help="Máximo de reportes por competencia (pruebas).")
    update_parser.add_argument("--json", action="store_true")

    for nombre in ("preflight", "notify", "all"):
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

    if args.comando == "update":
        codigo, resumen = update(
            cierre=args.semana_fin,
            dry_run=args.dry_run,
            skip_if_done=args.skip_if_done_this_week,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps({"ok": codigo == 0, "codigo": codigo, **resumen}, ensure_ascii=False))
        else:
            if codigo == 0 and resumen.get("dry_run"):
                print(f"preflight: {resumen['preflight']} (semana {resumen['semana_fin']})")
            elif codigo == 0 and resumen.get("skip"):
                print(f"nada que hacer: {resumen['motivo']}")
            elif codigo == 0:
                print(f"semana {resumen['semana_fin']}: {resumen['nuevos']} partidos nuevos, "
                      f"{resumen['correcciones']} correcciones, "
                      f"recompute {resumen['tiempo_recompute_s']}s")
                print(f"  snapshot: {resumen['snapshot_filas']} filas "
                      f"({resumen['snapshot_publicables']} publicables)")
                inactivas = resumen["competencias_sin_partidos_14d"]
                if inactivas:
                    print(f"  sin partidos hace 14+ días: {', '.join(inactivas[:8])}"
                          + (" ..." if len(inactivas) > 8 else ""))
            else:
                print(f"error (código {codigo}): {resumen.get('error')}")
        return codigo

    return _pendiente(args.comando)


if __name__ == "__main__":
    raise SystemExit(main())
