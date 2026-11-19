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
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Collection, Optional, Sequence

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
    textos_movimientos_selecciones,
    textos_revelacion,
    textos_sin_club,
    textos_top10,
)
from config import settings  # noqa: E402
from content import (  # noqa: E402
    MIN_MOVERS,
    MIN_PJ_REVELACION,
    duelo_de_la_semana,
    movers,
    polilinea,
    revelacion,
    serie_elo,
    top_n,
    top_sin_club,
)
from db import create_session  # noqa: E402
from elo import MODELO_VERSION  # noqa: E402
from render_html import TEMPLATES_DIR, render_png  # noqa: E402
from selecciones import (  # noqa: E402
    VentanaFifa,
    movers_selecciones,
    partidos_en_ventana,
    ventana_cerrada,
    ventana_fifa,
)
from snapshots import semana_fin, take_snapshot  # noqa: E402

logger = logging.getLogger(__name__)

HANDLE = "@EloDT_oficial"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
VARIANTES = ("portrait", "landscape", "square")

# Rotación del formato sugerido por semana ISO (el resto se genera igual).
ROTACION = ("top10_argentina", "movers_argentina", "duelo", "top10_global")

# Semanas que tienen que pasar antes de volver a publicar al mismo DT revelación.
SEMANAS_SIN_REPETIR = 8

# Nombre con el que se identifica cada post en el aviso por Telegram.
ETIQUETAS = {
    "top10_argentina": "Top 10 Argentina",
    "top10_global": "Top 10 mundial",
    "movers_argentina": "Subieron y cayeron",
    "duelo": "Duelo de pizarras",
    "revelacion": "DT revelación",
}


def texto_semana(desde: date, hasta: date) -> str:
    if desde.month == hasta.month:
        return f"{desde.day} al {hasta.day} de {MESES[hasta.month - 1]} de {hasta.year}"
    return (
        f"{desde.day} de {MESES[desde.month - 1]} al {hasta.day} de "
        f"{MESES[hasta.month - 1]} de {hasta.year}"
    )


def texto_fecha(dia: date) -> str:
    """Una sola fecha en texto: '19 de noviembre de 2026'."""
    return f"{dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def _formato_sugerido(cierre: date, disponibles: Optional[Sequence[str]] = None) -> Optional[str]:
    """El formato que toca por semana ISO; si se omitió, el siguiente de la rotación."""
    inicio = cierre.isocalendar().week % len(ROTACION)
    for paso in range(len(ROTACION)):
        formato = ROTACION[(inicio + paso) % len(ROTACION)]
        if disponibles is None or formato in disponibles:
            return formato
    return None


def _revelados_recientes(raiz: Path, cierre: date, semanas: int = SEMANAS_SIN_REPETIR) -> set[int]:
    """`dt_id` de las revelaciones publicadas en las `semanas` anteriores a `cierre`.

    Lee el `summary.json` de cada paquete. La semana en curso no cuenta: re-renderizarla
    no debe excluir a quien ya había elegido.
    """
    ids: set[int] = set()
    for atras in range(1, semanas + 1):
        anio, semana, _ = (cierre - timedelta(weeks=atras)).isocalendar()
        ruta = raiz / f"{anio}-W{semana:02d}" / "summary.json"
        try:
            elegido = json.loads(ruta.read_text(encoding="utf-8")).get("elegidos", {})
        except (OSError, ValueError):
            continue
        if isinstance(elegido, dict) and elegido.get("revelacion") is not None:
            ids.add(int(elegido["revelacion"]))
    return ids


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


def _etiqueta_delta(valor: float) -> str:
    """'+43,3' / '-18,6' / '0,0' para la escala del gráfico del duelo."""
    if abs(valor) < 0.05:
        return "0,0"
    return f"{valor:+.1f}".replace(".", ",")


def _contexto_duelo(session, cierre: date, semana_texto: str):
    duelo = duelo_de_la_semana(session, semana_fin=cierre)
    if duelo is None:
        return None, "no hubo partidos entre DTs publicables en la semana"

    series = serie_elo(session, [duelo.dt_a_id, duelo.dt_b_id], semanas=12, hasta=cierre)
    valores_a = [elo for _, elo in series.get(duelo.dt_a_id, [])]
    valores_b = [elo for _, elo in series.get(duelo.dt_b_id, [])]

    # El gráfico muestra **variación desde cero**, no nivel: las dos series arrancan en 0 y
    # se ve cuánto ganó o perdió cada uno en la ventana. Con los niveles, el que está más
    # arriba aplasta al otro y no se entiende quién mejoró.
    delta_a = [valor - valores_a[0] for valor in valores_a] if valores_a else []
    delta_b = [valor - valores_b[0] for valor in valores_b] if valores_b else []
    todos = delta_a + delta_b
    # La escala siempre incluye el cero: es la referencia del gráfico.
    minimo = min([0.0, *todos])
    maximo = max([0.0, *todos])
    if maximo <= minimo:
        maximo = minimo + 1.0

    ancho, alto = 1000, 220
    margen = 10
    util_alto = alto - 2 * margen
    y_cero = alto - margen - ((0.0 - minimo) / (maximo - minimo)) * util_alto

    # Barra de nivel: escala fija 1000-1500 (el ELO arranca en 1000), estirada si algún
    # DT queda fuera para no mostrar una barra vacía.
    elos = [v for v in (valores_a[-1:] + valores_b[-1:]) if v]
    base = min([1000, *(int(v // 50 * 50) for v in elos)]) if elos else 1000
    tope = max([1500, *(int(v // 50 * 50 + 50) for v in elos)]) if elos else 1500
    rango = max(tope - base, 1)

    def _lado(lado, valores, deltas, puntos):
        """Lo que necesita cada fila de la comparación."""
        elo = valores[-1] if valores else getattr(lado, "elo_actual", 0.0)
        delta = deltas[-1] if deltas else 0.0
        return {
            "apellido": getattr(lado, "apellido", "") or getattr(lado, "nombre", ""),
            "elo": elo,
            "delta": delta,
            "delta_texto": _etiqueta_delta(delta),
            "barra": round(min(100.0, max(0.0, (elo - base) / rango * 100)), 1),
            "puntos": puntos,
        }

    grafico = {
        "ancho": ancho,
        "alto": alto,
        "semanas": 12,
        "y_cero": round(y_cero, 1),
        "base": base,
        "tope": tope,
        "serie_a": _lado(
            duelo.duelo.a, valores_a, delta_a,
            polilinea(delta_a, ancho, alto, minimo, maximo) if delta_a else "",
        ),
        "serie_b": _lado(
            duelo.duelo.b, valores_b, delta_b,
            polilinea(delta_b, ancho, alto, minimo, maximo) if delta_b else "",
        ),
    }
    contexto = {
        "titulo": "DUELO DE PIZARRAS",
        "subtitulo": f"Semana {semana_texto}",
        "duelo": duelo,
        "grafico": grafico,
        "handle": HANDLE,
    }
    return contexto, None


def _contexto_revelacion(
    session, cierre: date, semana_texto: str, excluir_dt_ids: Collection[int] = ()
):
    entrada = revelacion(session, semana_fin=cierre, excluir_dt_ids=excluir_dt_ids)
    if entrada is None:
        return None, (
            f"nadie con menos de 2 años de carrera, {MIN_PJ_REVELACION}+ partidos, "
            "liga elegible y sin haber salido en las últimas semanas"
        )
    contexto = {
        "titulo": "DT REVELACIÓN",
        "subtitulo": f"Semana {semana_texto}",
        "entrada": entrada,
        "handle": HANDLE,
    }
    return contexto, None


def _contexto_movimientos(session, cierre: date, pais: Optional[str]):
    mov = movers(session, semana_fin=cierre, dias=7, pais=pais)
    if len(mov.subidas) < MIN_MOVERS or len(mov.bajadas) < MIN_MOVERS:
        return None, (
            f"muy pocos movimientos en la semana ({len(mov.subidas)} subidas y "
            f"{len(mov.bajadas)} bajadas; mínimo {MIN_MOVERS} de cada una)"
        ), None
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
        cierre = semana_fin(cierre)
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
        elegidos: dict = {}

        # Top 10 Argentina
        contexto, motivo = _contexto_top(session, cierre, "Argentina", partidos)
        if motivo:
            omitidos.append({"formato": "top10_argentina", "motivo": motivo})
        else:
            archivos = _renderizar_variantes("top10.html", contexto, destino, "top10_argentina", variantes, omitidos)
            if archivos:
                formatos.append({"formato": "top10_argentina",
                                 "titulo": ETIQUETAS["top10_argentina"], "archivos": archivos})
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
                formatos.append({"formato": "top10_global",
                                 "titulo": ETIQUETAS["top10_global"], "archivos": archivos})
                textos["top10_global"] = textos_top10(
                    contexto["entradas"], semana_texto, partidos=partidos, pais=None
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
                formatos.append({"formato": "movers_argentina",
                                 "titulo": ETIQUETAS["movers_argentina"], "archivos": archivos})
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
                formatos.append({"formato": "duelo",
                                 "titulo": ETIQUETAS["duelo"], "archivos": archivos})
                textos["duelo"] = textos_duelo(contexto["duelo"], semana_texto)

        # DT revelación
        ya_salieron = _revelados_recientes(Path(settings.data_dir) / "output", cierre)
        contexto, motivo = _contexto_revelacion(session, cierre, semana_texto, ya_salieron)
        if motivo:
            omitidos.append({"formato": "revelacion", "motivo": motivo})
        elif not (TEMPLATES_DIR / "revelacion.html").exists():
            omitidos.append({"formato": "revelacion", "motivo": "plantilla pendiente (T3.6)"})
        else:
            archivos = _renderizar_variantes("revelacion.html", contexto, destino, "revelacion", variantes, omitidos)
            if archivos:
                formatos.append({"formato": "revelacion",
                                 "titulo": ETIQUETAS["revelacion"], "archivos": archivos})
                textos["revelacion"] = textos_revelacion(contexto["entrada"], semana_texto)
                elegidos["revelacion"] = contexto["entrada"].dt_id

        sugerido = _formato_sugerido(cierre, list(textos))
        if sugerido is None:
            sugerido = next(iter(textos), None)


        resumen = {
            "semana_fin": cierre.isoformat(),
            "semana_iso": f"{cierre.isocalendar().year}-W{cierre.isocalendar().week:02d}",
            "modelo": MODELO_VERSION,
            "partidos": partidos,
            "snapshot": {"filas": snapshot.filas, "publicables": snapshot.publicables},
            "generados": formatos,
            "textos": {formato: {"texto": t.texto, "alt": t.alt} for formato, t in textos.items()},
            "omitidos": omitidos,
            "sugerido": sugerido,
            "elegidos": elegidos,
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

    titulo = resumen.get("titulo_paquete") or "Paquete semanal"
    lineas = [f"# {titulo} — {semana_texto}", ""]
    detalle = resumen.get("detalle") or f"{resumen.get('partidos', 0)} partidos en la ventana"
    lineas.append(f"Modelo `{resumen['modelo']}` · {detalle}.")
    lineas.append("")
    titulos = {f["formato"]: f.get("titulo", f["formato"]) for f in resumen["generados"]}
    if sugerido and sugerido in textos:
        elegido = textos[sugerido]
        lineas += [f"## Formato sugerido: {titulos.get(sugerido, sugerido)}", ""]
        lineas += ["### Texto (X y LinkedIn)", "", elegido.texto, ""]
        lineas += ["### Alt de la imagen", "", elegido.alt, ""]
    for formato, contenido in textos.items():
        if formato == sugerido:
            continue
        lineas += [f"## {titulos.get(formato, formato)}", ""]
        lineas += ["### Texto (X y LinkedIn)", "", contenido.texto, ""]
        lineas += ["### Alt de la imagen", "", contenido.alt, ""]
    if resumen["omitidos"]:
        lineas += ["## Formatos omitidos", ""]
        lineas += [f"- **{o['formato']}**: {o['motivo']}" for o in resumen["omitidos"]]
        lineas.append("")
    lineas += ["## Archivos generados", ""]
    for formato in resumen["generados"]:
        lineas.append(f"- {formato['formato']}: " + ", ".join(formato["archivos"]))
    (destino / "post.md").write_text("\n".join(lineas), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fecha FIFA (selecciones)
# ---------------------------------------------------------------------------
# Días que se esperan desde el último partido antes de publicar: TM tarda en cargar
# resultados y la ventana no puede cerrarse con partidos pendientes.
DIAS_GRACIA_FIFA = 2


def _marcador_fifa(hasta: date) -> Path:
    """Archivo que marca que esa fecha FIFA ya se publicó."""
    return Path(settings.data_dir) / "output" / f"fifa-{hasta.isoformat()}" / "summary.json"


def _ventana_a_publicar(
    session, hoy: Optional[date] = None
) -> tuple[Optional[VentanaFifa], str]:
    """La ventana FIFA pendiente de publicar, o `None` con el motivo."""
    ventana = ventana_fifa(session, hoy=hoy)
    if ventana is None:
        return None, "no hubo partidos de selecciones en el último mes y medio"

    referencia = hoy or date.today()
    if not ventana_cerrada(ventana, referencia):
        return None, f"la fecha FIFA sigue en juego (último día con partidos: {ventana.hasta})"
    if (referencia - ventana.hasta).days < DIAS_GRACIA_FIFA:
        return None, (
            f"se publica {DIAS_GRACIA_FIFA} días después del último partido "
            f"({ventana.hasta}) para que estén todos los resultados"
        )
    if _marcador_fifa(ventana.hasta).exists():
        return None, f"la fecha FIFA que cerró el {ventana.hasta} ya se publicó"
    return ventana, "ok"


def _rango_fifa(ventana: VentanaFifa, hoy: date) -> tuple[date, date]:
    """Rango de días a bajar y cargar: más ancho que la ventana detectada.

    La detección sale de la base; si todavía no se cargaron los últimos días, se quedaría
    corta justo cuando importa. Se mira un poco antes y hasta una semana después.
    """
    return ventana.desde - timedelta(days=3), min(hoy, ventana.hasta + timedelta(days=7))


def _scrape_selecciones_fifa(rango: tuple[date, date], hoy: date, limit: Optional[int] = None) -> dict:
    """Baja los partidos de selecciones del rango (amistosos y torneos oficiales)."""
    from scraper_transfermarkt import build_client
    from scraping.competitions import COMPETITIONS
    from scraping.pipeline import scrape_incremental
    from scraping.storage import RawStore

    cliente = build_client()
    cliente.warm_up()
    store = RawStore(settings.data_dir)

    totales = {"fixtures": 0, "reportes": 0, "omitidos_fecha": 0, "errores": 0}
    for config in COMPETITIONS.values():
        if config.kind != "selecciones":
            continue
        # Los amistosos siguen la temporada regular julio-junio (`saison_offset=0`); los
        # torneos prueban el año en curso, porque su `saison_id` no sigue una regla fija.
        if config.code == "FS":
            temporadas = [hoy.year if hoy.month >= 7 else hoy.year - 1]
            anios = None
        else:
            temporadas = None
            anios = [hoy.year]
        stats = scrape_incremental(
            config, cliente, store,
            hoy=hoy,
            ventana=rango,
            temporadas=temporadas,
            anios=anios,
            limit=limit,
        )
        for clave in totales:
            totales[clave] += stats.get(clave, 0)
    return totales


def _cargar_selecciones_fifa(session, rango: tuple[date, date]) -> dict:
    """Carga los reportes cacheados que caen dentro del rango."""
    from scraping.competitions import COMPETITIONS
    from scraping.pipeline import load_normalized, persist_matches
    from scraping.storage import RawStore

    store = RawStore(settings.data_dir)
    stats = {"procesados": 0, "duplicados": 0, "sin_dt": 0, "sin_fecha": 0}
    desde, hasta = rango[0].isoformat(), rango[1].isoformat()

    for config in COMPETITIONS.values():
        if config.kind != "selecciones":
            continue
        # Las ediciones de julio a junio se cachean bajo el año de su primer partido, así
        # que la ventana puede vivir en el directorio del año anterior.
        temporadas = [rango[1].year, rango[1].year - 1]
        for season in dict.fromkeys(temporadas):
            if not store.has_fixtures(config.code, season):
                continue
            partidos = [
                partido for partido in load_normalized(config, season, store)
                if partido.date and desde <= partido.date <= hasta
            ]
            if not partidos:
                continue
            resultado = persist_matches(partidos, session=session)
            for clave in stats:
                stats[clave] += resultado.get(clave, 0)

    session.commit()
    return stats


def render_selecciones(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    out_dir: Optional[Path] = None,
    variantes: tuple[str, ...] = VARIANTES,
    n: int = 5,
) -> dict:
    """Genera el paquete de una fecha FIFA (subieron y cayeron de seleccionadores)."""
    session = create_session()
    try:
        if desde is None or hasta is None:
            ventana = ventana_fifa(session)
            if ventana is None:
                raise ValueError("no hay partidos de selecciones para armar la ventana")
            desde, hasta = ventana.desde, ventana.hasta

        mov = movers_selecciones(session, desde=desde, hasta=hasta, n=n)
        if not mov.subidas and not mov.bajadas:
            raise ValueError("no hubo movimientos de seleccionadores en la ventana")

        ventana_texto = f"del {texto_semana(desde, hasta)}"
        destino = Path(out_dir or settings.data_dir / "output" / f"fifa-{hasta.isoformat()}")
        destino.mkdir(parents=True, exist_ok=True)

        contexto = {
            "titulo": "SUBIERON Y CAYERON",
            "subtitulo": f"Fecha FIFA · {ventana_texto}",
            "subidas": mov.subidas,
            "bajadas": mov.bajadas,
            "partidos": mov.total_partidos,
            "modelo": MODELO_VERSION,
            "handle": HANDLE,
        }
        omitidos: list[dict] = []
        archivos = _renderizar_variantes(
            "movers.html", contexto, destino, "movers_selecciones", variantes, omitidos
        )

        textos = {}
        if archivos:
            textos["movers_selecciones"] = textos_movimientos_selecciones(
                mov.subidas, mov.bajadas, ventana_texto, partidos=mov.total_partidos
            )

        resumen = {
            "titulo_paquete": "Paquete de fecha FIFA",
            "semana_iso": f"fecha FIFA {desde.isoformat()} a {hasta.isoformat()}",
            "ventana": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
            "modelo": MODELO_VERSION,
            "partidos": mov.total_partidos,
            "generados": (
                [{"formato": "movers_selecciones",
                  "titulo": "Subieron y cayeron · selecciones",
                  "archivos": archivos}] if archivos else []
            ),
            "textos": {clave: {"texto": t.texto, "alt": t.alt} for clave, t in textos.items()},
            "omitidos": omitidos,
            "sugerido": "movers_selecciones" if textos else None,
            "carpeta": str(destino),
        }
        _escribir_paquete(destino, resumen, textos, resumen["sugerido"], ventana_texto)
        return resumen
    finally:
        session.close()


def publicar_selecciones(
    hoy: Optional[date] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    dry_run: bool = False,
    max_minutos: Optional[int] = None,
    notificar: bool = True,
) -> tuple[int, dict]:
    """Publica la fecha FIFA si corresponde. Devuelve `(codigo_salida, resumen)`.

    Sale sin hacer nada (código 0) cuando no hay ventana, sigue en juego, todavía no
    pasaron los días de gracia o ya se publicó: así puede correr cada 4 horas.
    """
    session = create_session()
    try:
        manual = desde is not None and hasta is not None
        hoy = hoy or date.today()

        if manual:
            ventana = VentanaFifa(desde=desde, hasta=hasta, partidos=0)
            motivo = "manual"
        else:
            ventana, motivo = _ventana_a_publicar(session, hoy)
            if ventana is None:
                return 0, {"skip": True, "motivo": motivo}

        if dry_run:
            return 0, {
                "dry_run": True,
                "ventana": {"desde": ventana.desde.isoformat(), "hasta": ventana.hasta.isoformat()},
                "motivo": motivo,
            }

        # 1) Scraping. El rango es más ancho que la ventana detectada para descubrir los
        # días que todavía no están en la base.
        rango = _rango_fifa(ventana, hoy)
        try:
            scrapeo = _scrape_selecciones_fifa(rango, hoy)
        except Exception as error:  # noqa: BLE001 - bloqueo de VPN: reintentable
            return 10, {"error": f"no se pudieron bajar los partidos: {error}",
                        "reintentable": True}

        # 2) Carga y recálculo
        carga = _cargar_selecciones_fifa(session, rango)
        segundos = None
        if carga["procesados"]:
            segundos = recomputar_con_tiempo(session)

        # 3) Con los datos frescos, la ventana puede haberse estirado o cambiado.
        if not manual:
            ventana_nueva, motivo = _ventana_a_publicar(session, hoy)
            if ventana_nueva is None:
                return 0, {"skip": True, "motivo": motivo, "carga": carga}
            ventana = ventana_nueva

        if ventana.partidos == 0:
            ventana = VentanaFifa(
                desde=ventana.desde, hasta=ventana.hasta,
                partidos=partidos_en_ventana(session, ventana.desde, ventana.hasta),
            )
        if ventana.partidos == 0:
            return 0, {"skip": True, "motivo": "la ventana no tiene partidos cargados"}

        # 4) Imágenes y textos
        paquete = render_selecciones(
            desde=ventana.desde, hasta=ventana.hasta, n=5
        )

        envio = {"ok": False, "error": "no se pidió el envío"}
        if notificar:
            try:
                import notify as _notify

                envio = _notify.enviar_paquete(paquete["carpeta"])
            except Exception as error:  # noqa: BLE001 - el paquete ya está generado
                envio = {"ok": False, "error": str(error)}

        resumen = {
            "tipo": "selecciones",
            "ventana": {"desde": ventana.desde.isoformat(), "hasta": ventana.hasta.isoformat()},
            "partidos": ventana.partidos,
            "nuevos": carga["procesados"],
            "descartados_sin_dt": carga["sin_dt"],
            "scrapeo": scrapeo,
            "tiempo_recompute_s": segundos,
            "carpeta": paquete["carpeta"],
            "telegram": envio.get("ok"),
        }
        if not envio.get("ok"):
            resumen["telegram_error"] = envio.get("error")
        return (0 if envio.get("ok") or not notificar else 30), resumen
    except Exception as error:  # noqa: BLE001
        return 30, {"error": str(error)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Técnicos sin club (bajo demanda)
# ---------------------------------------------------------------------------
def render_sin_club(
    pais: str = "Argentina",
    n: int = 10,
    hasta: Optional[date] = None,
    dias: int = 365,
    excluir: Sequence[int] = (),
    out_dir: Optional[Path] = None,
    variantes: tuple[str, ...] = VARIANTES,
) -> dict:
    """Genera el paquete de "técnicos sin club" sin tocar la red.

    Lee la base como está: el `update` semanal ya la mantiene al día. El último club
    se usa sólo para filtrar por país; en la imagen van el nombre y los partidos.
    """
    session = create_session()
    try:
        referencia = hasta or date.today()
        entradas = top_sin_club(
            session,
            hasta=referencia,
            pais=pais,
            n=n,
            dias=dias,
            excluir_dt_ids=excluir,
        )
        fecha_texto = texto_fecha(referencia)
        destino = Path(
            out_dir or settings.data_dir / "output" / f"sin-club-{referencia.isoformat()}"
        )
        destino.mkdir(parents=True, exist_ok=True)

        omitidos: list[dict] = []
        archivos: list[str] = []
        textos: dict = {}
        if len(entradas) < min(3, n):
            omitidos.append({
                "formato": "sin_club",
                "motivo": f"sólo hay {len(entradas)} técnicos libres con último club en {pais}",
            })
        else:
            contexto = {
                "titulo": "LOS MEJORES DTs SIN CLUB",
                "subtitulo": f"Técnicos libres · {pais} · {fecha_texto}",
                "entradas": entradas,
                "handle": HANDLE,
            }
            archivos = _renderizar_variantes(
                "sin_club.html", contexto, destino, "sin_club", variantes, omitidos
            )
            if archivos:
                textos["sin_club"] = textos_sin_club(entradas, fecha_texto, pais=pais)

        resumen = {
            "titulo_paquete": "Técnicos sin club",
            "semana_iso": fecha_texto,
            "detalle": f"{len(entradas)} técnicos libres · último club en {pais}",
            "modelo": MODELO_VERSION,
            "pais": pais,
            "dias": dias,
            "generados": (
                [{"formato": "sin_club", "titulo": "Técnicos sin club",
                  "archivos": archivos}] if archivos else []
            ),
            "textos": {clave: {"texto": t.texto, "alt": t.alt} for clave, t in textos.items()},
            "omitidos": omitidos,
            "sugerido": "sin_club" if textos else None,
            "carpeta": str(destino),
        }
        _escribir_paquete(destino, resumen, textos, resumen["sugerido"], fecha_texto)
        return resumen
    finally:
        session.close()


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
    from scraping.competitions import COMPETITIONS

    cerradas = {
        codigo for codigo, config in COMPETITIONS.items()
        if getattr(config, "last_season", None) is not None
    }
    return [fila[0] for fila in filas if fila[0] and fila[0] not in cerradas]


def update(
    cierre: Optional[date] = None,
    dry_run: bool = False,
    skip_if_done: bool = False,
    limit: Optional[int] = None,
    max_minutos: Optional[int] = None,
) -> tuple[int, dict]:
    """Actualización semanal completa. Devuelve `(codigo_salida, resumen)`."""
    cierre = semana_fin(cierre)

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

        # Corridas anteriores que quedaron en 'corriendo' (corte de luz, kill) se marcan
        # como interrumpidas: si no, el registro miente sobre lo que está pasando.
        session.execute(
            text("update ejecuciones_pipeline set estado = 'interrumpida', "
                 "terminado_en = now() where estado = 'corriendo'")
        )
        session.commit()

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
        presupuesto = max_minutos or 0
        inicio_scrapeo = time.monotonic()
        cortado_por_tiempo = False

        for config in COMPETITIONS.values():
            if presupuesto and (time.monotonic() - inicio_scrapeo) / 60 >= presupuesto:
                cortado_por_tiempo = True
                logger.warning(
                    "Corte por tiempo tras %.0f min; se sigue con la carga de lo bajado.",
                    (time.monotonic() - inicio_scrapeo) / 60,
                )
                break
            stats = scrape_incremental(
                config, cliente, store, semana_fin=cierre, limit=limit
            )
            for clave in scrapeo:
                scrapeo[clave] += stats.get(clave, 0)
            if stats["reportes"] or stats["errores"]:
                print(f"  {config.code}: {stats}", flush=True)

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
            "cortado_por_tiempo": cortado_por_tiempo,
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


def _selecciones_opcional(args) -> Optional[tuple[int, dict]]:
    """Publica la fecha FIFA si hay una pendiente. Nunca rompe el paquete de clubes."""
    try:
        return publicar_selecciones(max_minutos=args.max_minutos)
    except Exception as error:  # noqa: BLE001 - el paquete de clubes ya se mandó
        logger.warning("fecha FIFA: no se pudo publicar: %s", error)
        return 30, {"error": str(error)}


def _imprimir_selecciones(codigo: int, resumen: dict) -> None:
    if resumen.get("skip"):
        print(f"fecha FIFA: nada que publicar ({resumen['motivo']})")
    elif codigo == 0:
        print(f"fecha FIFA {resumen['ventana']['desde']} a {resumen['ventana']['hasta']}: "
              f"{resumen['partidos']} partidos, {resumen['nuevos']} nuevos")
        print("  telegram: enviado" if resumen.get("telegram")
              else f"  telegram: no se pudo enviar ({resumen.get('telegram_error')})")
    else:
        print(f"fecha FIFA: error (código {codigo}): {resumen.get('error')}")


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
    update_parser.add_argument("--max-minutos", type=int,
                               default=int(os.getenv("TM_UPDATE_MAX_MINUTOS", "150")),
                               help="Corta el scraping pasados N minutos y sigue con lo bajado "
                                    "(default 150 o $TM_UPDATE_MAX_MINUTOS; 0 = sin límite).")
    update_parser.add_argument("--json", action="store_true")

    notify_parser = sub.add_parser("notify", help="Envía el paquete de la semana por Telegram.")
    notify_parser.add_argument("--semana-fin", type=date.fromisoformat, default=None)
    notify_parser.add_argument("--carpeta", type=Path, default=None,
                               help="Carpeta del paquete (default: la de la semana).")
    notify_parser.add_argument("--test", action="store_true", help="Manda sólo un mensaje de prueba.")
    notify_parser.add_argument("--json", action="store_true")

    all_parser = sub.add_parser("all", help="update + render + notify.")
    all_parser.add_argument("--semana-fin", type=date.fromisoformat, default=None)
    all_parser.add_argument("--skip-if-done-this-week", action="store_true")
    all_parser.add_argument("--selecciones", action="store_true",
                            help="Además del paquete de clubes, publica la fecha FIFA si "
                                 "hay una ventana cerrada pendiente.")
    all_parser.add_argument("--max-minutos", type=int,
                            default=int(os.getenv("TM_UPDATE_MAX_MINUTOS", "150")))
    all_parser.add_argument("--json", action="store_true")

    selecciones_parser = sub.add_parser(
        "selecciones",
        help='Publica el "subieron y cayeron" de una fecha FIFA.',
    )
    selecciones_parser.add_argument("--desde", type=date.fromisoformat, default=None,
                                    help="Primer día de la ventana (por defecto, se detecta).")
    selecciones_parser.add_argument("--hasta", type=date.fromisoformat, default=None,
                                    help="Último día de la ventana (por defecto, se detecta).")
    selecciones_parser.add_argument("--sin-envio", action="store_true",
                                    help="Genera el paquete pero no lo manda por Telegram.")
    selecciones_parser.add_argument("--dry-run", action="store_true",
                                    help="Sólo dice si corresponde publicar.")
    selecciones_parser.add_argument("--max-minutos", type=int,
                                    default=int(os.getenv("TM_UPDATE_MAX_MINUTOS", "150")))
    selecciones_parser.add_argument("--json", action="store_true")

    sin_club_parser = sub.add_parser(
        "sin_club",
        help="Ranking de técnicos sin club (bajo demanda, sin tocar la red).",
    )
    sin_club_parser.add_argument("--pais", default="Argentina",
                                 help="País del último club (default: Argentina).")
    sin_club_parser.add_argument("--top", type=int, default=10)
    sin_club_parser.add_argument("--hasta", type=date.fromisoformat, default=None,
                                 help="Fecha de referencia (default: hoy).")
    sin_club_parser.add_argument("--dias", type=int, default=365,
                                 help="Recorta la ventana de actividad (365 por defecto; no la "
                                      "amplía más allá de un año).")
    sin_club_parser.add_argument("--excluir", default="",
                                 help="dt_id separados por coma para dejar afuera.")
    sin_club_parser.add_argument("--salida", type=Path, default=None)
    sin_club_parser.add_argument("--sin-envio", action="store_true",
                                 help="Genera el paquete pero no lo manda por Telegram.")
    sin_club_parser.add_argument("--json", action="store_true")

    preflight_parser = sub.add_parser("preflight", help="Verifica base y Transfermarkt.")
    preflight_parser.add_argument("--json", action="store_true")

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

    if args.comando == "preflight":
        ok, motivo = _preflight()
        if args.json:
            print(json.dumps({"ok": ok, "motivo": motivo}, ensure_ascii=False))
        else:
            print(f"preflight: {motivo}")
        return 0 if ok else 10

    if args.comando == "notify":
        try:
            import notify as _notify

            if args.test:
                _notify.enviar_texto(
                    "<b>AEP</b> — prueba del pipeline: si ves esto, el bot funciona."
                )
                resultado = {"test": True, "ok": True}
            else:
                carpeta = args.carpeta or (
                    Path(settings.data_dir) / "output"
                    / f"{semana_fin(args.semana_fin).isocalendar().year}-W{semana_fin(args.semana_fin).isocalendar().week:02d}"
                )
                resultado = {"test": False, "ok": True, **_notify.enviar_paquete(carpeta)}
        except Exception as error:  # noqa: BLE001
            if args.json:
                print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
            else:
                print(f"error al notificar: {error}")
            return 30
        if args.json:
            print(json.dumps(resultado, ensure_ascii=False))
        else:
            if resultado.get("test"):
                print("mensaje de prueba enviado")
            else:
                print(f"enviado: {resultado['posts']} posts "
                      f"({resultado['documentos']} imágenes + {resultado['mensajes']} mensajes) · "
                      f"sugerido: {resultado['sugerido']}")
        return 0

    if args.comando == "selecciones":
        codigo, resumen = publicar_selecciones(
            desde=args.desde,
            hasta=args.hasta,
            dry_run=args.dry_run,
            max_minutos=args.max_minutos,
            notificar=not args.sin_envio,
        )
        if args.json:
            print(json.dumps({"ok": codigo == 0, "codigo": codigo, **resumen},
                             ensure_ascii=False))
        else:
            if resumen.get("skip"):
                print(f"nada que publicar: {resumen['motivo']}")
            elif resumen.get("dry_run"):
                print(f"hay fecha FIFA para publicar: {resumen['ventana']}")
            elif codigo == 0:
                print(f"fecha FIFA {resumen['ventana']['desde']} a "
                      f"{resumen['ventana']['hasta']}: {resumen['partidos']} partidos, "
                      f"{resumen['nuevos']} nuevos")
                print(f"  paquete: {resumen['carpeta']}")
                print("  telegram: enviado" if resumen.get("telegram")
                      else f"  telegram: no se pudo enviar ({resumen.get('telegram_error')})")
            else:
                print(f"error (código {codigo}): {resumen.get('error')}")
        return codigo

    if args.comando == "sin_club":
        excluir = [int(valor) for valor in args.excluir.split(",") if valor.strip()]
        try:
            resumen = render_sin_club(
                pais=args.pais,
                n=args.top,
                hasta=args.hasta,
                dias=args.dias,
                excluir=excluir,
                out_dir=args.salida,
            )
        except Exception as error:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
            return 30

        envio = {"ok": True, "omitido": True}
        if resumen["generados"] and not args.sin_envio:
            try:
                import notify as _notify

                envio = _notify.enviar_paquete(resumen["carpeta"])
            except Exception as error:  # noqa: BLE001 - el paquete ya está generado
                envio = {"ok": False, "error": str(error)}

        if args.json:
            telegram = None if envio.get("omitido") else envio.get("ok")
            print(json.dumps({"ok": True, **resumen, "telegram": telegram},
                             ensure_ascii=False))
        else:
            if resumen["generados"]:
                print(f"técnicos sin club · {resumen['semana_iso']} · "
                      f"{resumen['detalle']}")
                for formato in resumen["generados"]:
                    print(f"  ✓ {formato['formato']}: {', '.join(formato['archivos'])}")
                print(f"  carpeta: {resumen['carpeta']}")
                if not args.sin_envio:
                    print("  telegram: enviado" if envio.get("ok")
                          else f"  telegram: no se pudo enviar ({envio.get('error')})")
            else:
                for omitido in resumen["omitidos"]:
                    print(f"nada que generar: {omitido['motivo']}")
        return 0 if envio.get("ok") or args.sin_envio or not resumen["generados"] else 30

    if args.comando == "all":
        codigo, resumen_update = update(
            cierre=args.semana_fin,
            skip_if_done=args.skip_if_done_this_week,
            max_minutos=args.max_minutos,
        )
        if codigo != 0:
            if args.json:
                print(json.dumps({"ok": False, "etapa": "update", "codigo": codigo,
                                  **resumen_update}, ensure_ascii=False))
            else:
                print(f"update falló (código {codigo}): {resumen_update.get('error')}")
            return codigo

        if resumen_update.get("skip"):
            # La semana ya se procesó: no se re-renderiza ni se vuelve a mandar nada.
            # La fecha FIFA es un paquete aparte y puede estar pendiente igual.
            extra = _selecciones_opcional(args) if args.selecciones else None
            if args.json:
                salida = {"ok": True, "skip": True, **resumen_update}
                if extra is not None:
                    salida["selecciones"] = extra
                print(json.dumps(salida, ensure_ascii=False))
            else:
                print(f"nada que hacer: {resumen_update['motivo']}")
                if extra is not None:
                    _imprimir_selecciones(extra[0], extra[1])
            return 0

        try:
            paquete = render(cierre=args.semana_fin)
        except Exception as error:  # noqa: BLE001
            if args.json:
                print(json.dumps({"ok": False, "etapa": "render", "error": str(error)},
                                 ensure_ascii=False))
            else:
                print(f"render falló: {error}")
            return 30

        try:
            import notify as _notify

            envio = _notify.enviar_paquete(paquete["carpeta"])
        except Exception as error:  # noqa: BLE001 - el paquete ya está generado
            envio = {"ok": False, "error": str(error)}

        extra = _selecciones_opcional(args) if args.selecciones else None
        if args.json:
            salida = {"ok": bool(envio.get("ok")), "update": resumen_update,
                      "render": paquete, "notify": envio}
            if extra is not None:
                salida["selecciones"] = extra
            print(json.dumps(salida, ensure_ascii=False))
        else:
            print(f"semana {paquete['semana_iso']}: {paquete['partidos']} partidos, "
                  f"{len(paquete['generados'])} formatos")
            if envio.get("ok"):
                print(f"telegram: {envio['posts']} posts enviados "
                      f"({envio['documentos']} imágenes + {envio['mensajes']} mensajes)")
            else:
                print(f"telegram: no se pudo enviar ({envio.get('error')}) — "
                      f"el paquete está en {paquete['carpeta']}")
            if extra is not None:
                _imprimir_selecciones(extra[0], extra[1])
        return 0 if envio.get("ok") else 30

    if args.comando == "update":
        codigo, resumen = update(
            cierre=args.semana_fin,
            dry_run=args.dry_run,
            skip_if_done=args.skip_if_done_this_week,
            limit=args.limit,
            max_minutos=args.max_minutos,
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
