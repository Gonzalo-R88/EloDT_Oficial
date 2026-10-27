"""Renderizado de infografías (matplotlib) para redes sociales.

Genera los PNG del "Power Ranking de la Fecha" y del "Duelo de Pizarras" a
partir de los datos ya resueltos en `ranking.py` / `duel.py`. Sin dependencias
de la base de datos: recibe datos para poder testearse y reutilizarse.

Marca: violeta/lila + celeste + blanco, con tipografía Poppins (cuerpo) y
Anton (títulos y cifras). Las fuentes se cargan desde `assets/fonts/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from duel import Duel  # noqa: E402
from ranking import PowerRanking, RankingEntry  # noqa: E402

BG = "#FFFFFF"
PANEL = "#F5F2FE"
ROW = "#FFFFFF"
BORDE = "#E6E0FB"
CELESTE = "#22B8F0"
CELESTE_CLARO = "#7DD3FC"
VIOLETA = "#8B5CF6"
LILA = "#C4B5FD"
TEXTO = "#241C4A"
MUTED = "#6B7280"

_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
for _font_path in sorted(_FONT_DIR.glob("*.ttf")):
    try:
        font_manager.fontManager.addfont(str(_font_path))
    except Exception:  # pragma: no cover - fuente corrupta o ilegible
        pass

_FAMILIAS = {font.name for font in font_manager.fontManager.ttflist}
FUENTE = "Poppins" if "Poppins" in _FAMILIAS else "DejaVu Sans"
FUENTE_DISPLAY = "Anton" if "Anton" in _FAMILIAS else FUENTE

plt.rcParams["font.family"] = FUENTE
plt.rcParams["font.weight"] = "medium"

MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def format_date_es(value) -> str:
    """Formatea una fecha como `10 de mayo de 2026`."""
    return f"{value.day} de {MESES_ES[value.month - 1]} de {value.year}"


def format_range_es(desde, hasta) -> str:
    """Formatea un rango legible, compactando el mes/año si coinciden."""
    if desde == hasta:
        return format_date_es(desde)
    if (desde.year, desde.month) == (hasta.year, hasta.month):
        return f"{desde.day} al {hasta.day} de {MESES_ES[hasta.month - 1]} de {hasta.year}"
    return f"{format_date_es(desde)} al {format_date_es(hasta)}"


def _round_rect(
    ax, x, y, w, h, *, facecolor, edgecolor=None, lw=0.0, alpha=1.0, zorder=1
):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.004,rounding_size=0.014",
        linewidth=lw,
        edgecolor=edgecolor or "none",
        facecolor=facecolor,
        alpha=alpha,
        zorder=zorder,
    )
    ax.add_patch(patch)
    return patch


def _top_accent(ax) -> None:
    """Barra fina superior en dos tonos (celeste / violeta)."""
    ax.add_patch(
        plt.Rectangle((0.0, 0.988), 0.5, 0.012, facecolor=CELESTE, zorder=5)
    )
    ax.add_patch(
        plt.Rectangle((0.5, 0.988), 0.5, 0.012, facecolor=VIOLETA, zorder=5)
    )


def _chip(ax, x, y, size, label, color):
    """Dibuja una ficha cuadrada con una letra (forma reciente)."""
    _round_rect(ax, x, y, size, size, facecolor=color, zorder=3)
    ax.text(
        x + size / 2, y + size / 2, label,
        ha="center", va="center", color=BG, fontsize=11,
        fontfamily=FUENTE, fontweight="bold", zorder=4,
    )


# --------------------------------------------------------------------------- #
# Power Ranking de la Fecha
# --------------------------------------------------------------------------- #


def _draw_ranking_panel(
    ax,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    titulo: str,
    color: str,
    entries: Sequence[RankingEntry],
    top: int,
) -> None:
    _round_rect(ax, x, y, w, h, facecolor=PANEL, zorder=1)

    cabecera = FancyBboxPatch(
        (x, y + h - 0.062), w, 0.062,
        boxstyle="round,pad=0.004,rounding_size=0.014",
        linewidth=0, facecolor=color, alpha=0.16, zorder=2,
    )
    ax.add_patch(cabecera)
    ax.text(
        x + w / 2, y + h - 0.031, titulo,
        ha="center", va="center", color=color, fontsize=17,
        fontfamily=FUENTE_DISPLAY, zorder=3,
    )

    if not entries:
        ax.text(
            x + w / 2, y + h / 2, "Sin movimientos en la fecha",
            ha="center", va="center", color=MUTED, fontsize=12,
            style="italic", fontfamily=FUENTE, zorder=3,
        )
        return

    n = max(top, 1)
    hueco = 0.014
    area_top = y + h - 0.062
    alto_fila = (area_top - y - hueco * (n + 1)) / n

    for index, entry in enumerate(entries):
        fila_y = area_top - hueco - (index + 1) * (alto_fila + hueco) + hueco
        _round_rect(
            ax, x + hueco, fila_y, w - 2 * hueco, alto_fila,
            facecolor=ROW, edgecolor=BORDE, lw=0.8, zorder=2,
        )

        cy = fila_y + alto_fila / 2
        badge_x = x + hueco + 0.028
        ax.add_patch(
            plt.Circle((badge_x, cy), 0.018, color=color, transform=ax.transData, zorder=3)
        )
        ax.text(
            badge_x, cy, str(index + 1),
            ha="center", va="center", color=BG, fontsize=13,
            fontfamily=FUENTE_DISPLAY, zorder=4,
        )

        nombre_x = x + hueco + 0.058
        ax.text(
            nombre_x, cy + 0.018, entry.nombre,
            ha="left", va="center", color=TEXTO, fontsize=13,
            fontfamily=FUENTE, fontweight="bold", zorder=3,
        )
        detalle = entry.club or ""
        if entry.partidos > 1:
            detalle = f"{detalle} · {entry.partidos} PJ" if detalle else f"{entry.partidos} PJ"
        ax.text(
            nombre_x, cy - 0.024, detalle,
            ha="left", va="center", color=MUTED, fontsize=9.5,
            fontfamily=FUENTE, zorder=3,
        )

        delta_x = x + w - hueco - 0.02
        ax.text(
            delta_x, cy + 0.013, f"{entry.delta:+.2f}",
            ha="right", va="center", color=color, fontsize=18,
            fontfamily=FUENTE_DISPLAY, zorder=3,
        )
        ax.text(
            delta_x, cy - 0.027, f"ELO {entry.elo_actual:.0f}",
            ha="right", va="center", color=MUTED, fontsize=9.5,
            fontfamily=FUENTE, zorder=3,
        )


def render_power_ranking(
    ranking: PowerRanking,
    output_path: Path,
    *,
    title: str = "POWER RANKING DE LA FECHA",
    subtitle: Optional[str] = None,
    handle: str = "@AEP_Analitica",
    top: int = 5,
    figsize: tuple[float, float] = (16.0, 9.0),
    dpi: int = 100,
) -> Path:
    """Renderiza el ranking y guarda un PNG listo para publicar en X."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if subtitle is None:
        subtitle = format_range_es(ranking.desde, ranking.hasta)

    fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _top_accent(ax)

    ax.text(
        0.5, 0.918, title,
        ha="center", va="center", color=TEXTO, fontsize=40, fontfamily=FUENTE_DISPLAY,
    )
    ax.add_patch(
        plt.Rectangle((0.40, 0.872), 0.20, 0.006, facecolor=VIOLETA, zorder=4)
    )
    ax.text(
        0.5, 0.845, subtitle,
        ha="center", va="center", color=VIOLETA, fontsize=15,
        fontfamily=FUENTE, fontweight="semibold",
    )

    _draw_ranking_panel(
        ax, x=0.035, y=0.125, w=0.44, h=0.685,
        titulo="SUBIERON", color=CELESTE, entries=ranking.subidas, top=top,
    )
    _draw_ranking_panel(
        ax, x=0.525, y=0.125, w=0.44, h=0.685,
        titulo="CAYERON", color=VIOLETA, entries=ranking.bajadas, top=top,
    )

    ax.text(
        0.5, 0.062, f"{ranking.total_partidos} partidos analizados",
        ha="center", va="center", color=MUTED, fontsize=11, fontfamily=FUENTE,
    )
    ax.text(
        0.5, 0.026, f"AEP · Analítica de Entrenadores & Performance   |   {handle}",
        ha="center", va="center", color=MUTED, fontsize=10.5, fontfamily=FUENTE,
    )

    fig.savefig(output_path, facecolor=BG)
    plt.close(fig)
    return output_path


# --------------------------------------------------------------------------- #
# Duelo de Pizarras
# --------------------------------------------------------------------------- #


def _initials(nombre: str, apellido: str) -> str:
    return f"{(nombre or ' ')[0]}{(apellido or ' ')[0]}".upper()


def _draw_duel_identity(
    ax, *, x, y, w, h, side, color: str, etiqueta: str, n_forma: int
) -> None:
    _round_rect(ax, x, y, w, h, facecolor=PANEL, zorder=1)
    band_y = y + h - 0.082
    _round_rect(ax, x, band_y, w, 0.082, facecolor=color, zorder=2)

    # Badge de iniciales dentro de la banda.
    badge_x = x + 0.052
    ax.add_patch(
        plt.Circle(
            (badge_x, band_y + 0.041), 0.03, color=BG, alpha=0.28,
            transform=ax.transData, zorder=3,
        )
    )
    ax.text(
        badge_x, band_y + 0.041, _initials(side.nombre, side.apellido),
        ha="center", va="center", color=BG, fontsize=14,
        fontfamily=FUENTE, fontweight="bold", zorder=4,
    )
    ax.text(
        x + w / 2 + 0.022, band_y + 0.041, side.nombre,
        ha="center", va="center", color=BG, fontsize=16,
        fontfamily=FUENTE, fontweight="bold", zorder=3,
    )

    ax.text(
        x + w / 2, y + h - 0.120, side.club or "Sin club",
        ha="center", va="center", color=MUTED, fontsize=11,
        fontfamily=FUENTE, zorder=3,
    )
    ax.text(
        x + w / 2, y + h - 0.168, etiqueta,
        ha="center", va="center", color=color, fontsize=10,
        fontfamily=FUENTE_DISPLAY, zorder=3,
    )
    ax.text(
        x + w / 2, y + h - 0.215, f"{side.elo_actual:.0f}",
        ha="center", va="center", color=TEXTO, fontsize=30,
        fontfamily=FUENTE_DISPLAY, zorder=3,
    )

    ax.text(
        x + w / 2, y + 0.052, f"FORMA (últimos {n_forma})",
        ha="center", va="center", color=MUTED, fontsize=9,
        fontfamily=FUENTE, zorder=3,
    )
    forma = list(side.forma)[-n_forma:]
    if not forma:
        return
    size = 0.026
    gap = 0.010
    total = len(forma) * size + (len(forma) - 1) * gap
    start = x + (w - total) / 2
    colores = {"V": CELESTE, "E": LILA, "D": VIOLETA}
    for index, letra in enumerate(forma):
        _chip(ax, start + index * (size + gap), y + 0.014, size, letra, colores.get(letra, LILA))


def _draw_stat_rows(ax, duel: Duel, *, y_top: float, y_bottom: float) -> None:
    a, b = duel.a, duel.b

    def mejor_de(valor_a, valor_b, *, mayor_es_mejor=True):
        if valor_a == valor_b:
            return None
        if mayor_es_mejor:
            return "a" if valor_a > valor_b else "b"
        return "a" if valor_a < valor_b else "b"

    filas = [
        ("Partidos jugados", a.partidos, b.partidos, mejor_de(a.partidos, b.partidos)),
        ("Victorias", a.victorias, b.victorias, mejor_de(a.victorias, b.victorias)),
        ("Empates", a.empates, b.empates, None),
        ("Derrotas", a.derrotas, b.derrotas, mejor_de(a.derrotas, b.derrotas, mayor_es_mejor=False)),
        ("Goles a favor", a.goles_favor, b.goles_favor, mejor_de(a.goles_favor, b.goles_favor)),
        ("Goles en contra", a.goles_contra, b.goles_contra, mejor_de(a.goles_contra, b.goles_contra, mayor_es_mejor=False)),
        ("Diferencia de gol", a.diferencia, b.diferencia, mejor_de(a.diferencia, b.diferencia)),
        ("Puntos por partido", a.puntos_por_partido, b.puntos_por_partido, mejor_de(a.puntos_por_partido, b.puntos_por_partido)),
    ]

    n = len(filas)
    alto = (y_top - y_bottom) / n
    for index, (label, valor_a, valor_b, mejor) in enumerate(filas):
        cy = y_top - (index + 0.5) * alto
        if index % 2 == 0:
            _round_rect(
                ax, 0.05, cy - alto * 0.44, 0.90, alto * 0.88,
                facecolor=PANEL, alpha=0.55, zorder=1,
            )
        color_a = CELESTE if mejor == "a" else (TEXTO if mejor is None else MUTED)
        color_b = VIOLETA if mejor == "b" else (TEXTO if mejor is None else MUTED)
        peso_a = "bold" if mejor == "a" else "medium"
        peso_b = "bold" if mejor == "b" else "medium"

        ax.text(0.42, cy, f"{valor_a}", ha="right", va="center",
                color=color_a, fontsize=15, fontfamily=FUENTE, fontweight=peso_a, zorder=3)
        ax.text(0.50, cy, label, ha="center", va="center",
                color=MUTED, fontsize=10.5, fontfamily=FUENTE, zorder=3)
        ax.text(0.58, cy, f"{valor_b}", ha="left", va="center",
                color=color_b, fontsize=15, fontfamily=FUENTE, fontweight=peso_b, zorder=3)


def render_duel(
    duel: Duel,
    output_path: Path,
    *,
    title: str = "DUELO DE PIZARRAS",
    subtitle: Optional[str] = None,
    handle: str = "@AEP_Analitica",
    n_forma: int = 5,
    figsize: tuple[float, float] = (16.0, 9.0),
    dpi: int = 100,
) -> Path:
    """Renderiza el cara a cara de dos DTs y guarda un PNG listo para X."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if subtitle is None:
        if duel.hasta is not None:
            subtitle = f"Historial hasta {format_date_es(duel.hasta)}"
        else:
            subtitle = "Sin partidos registrados"

    fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _top_accent(ax)

    ax.text(0.5, 0.918, title, ha="center", va="center",
            color=TEXTO, fontsize=40, fontfamily=FUENTE_DISPLAY)
    ax.add_patch(
        plt.Rectangle((0.42, 0.872), 0.16, 0.006, facecolor=VIOLETA, zorder=4)
    )
    ax.text(0.5, 0.845, subtitle, ha="center", va="center", color=VIOLETA,
            fontsize=14, fontfamily=FUENTE, fontweight="semibold")

    _draw_duel_identity(
        ax, x=0.04, y=0.49, w=0.38, h=0.325,
        side=duel.a, color=CELESTE, etiqueta="ELO ACTUAL", n_forma=n_forma,
    )
    _draw_duel_identity(
        ax, x=0.58, y=0.49, w=0.38, h=0.325,
        side=duel.b, color=VIOLETA, etiqueta="ELO ACTUAL", n_forma=n_forma,
    )

    ax.add_patch(
        plt.Circle((0.5, 0.6525), 0.037, color=VIOLETA, transform=ax.transData, zorder=4)
    )
    ax.text(0.5, 0.6525, "VS", ha="center", va="center",
            color=BG, fontsize=16, fontfamily=FUENTE_DISPLAY, zorder=5)

    _draw_stat_rows(ax, duel, y_top=0.445, y_bottom=0.165)

    if duel.enfrentamientos:
        h2h = (
            f"Enfrentamientos directos: {duel.enfrentamientos}   ·   "
            f"{duel.a.apellido} {duel.victorias_a} - "
            f"{duel.empates} - {duel.victorias_b} {duel.b.apellido}"
        )
    else:
        h2h = "Sin enfrentamientos directos registrados"
    ax.text(0.5, 0.108, h2h, ha="center", va="center", color=TEXTO,
            fontsize=12, fontfamily=FUENTE, fontweight="semibold", zorder=3)

    ax.text(
        0.5, 0.04, f"AEP · Analítica de Entrenadores & Performance   |   {handle}",
        ha="center", va="center", color=MUTED, fontsize=10.5, fontfamily=FUENTE,
    )

    fig.savefig(output_path, facecolor=BG)
    plt.close(fig)
    return output_path