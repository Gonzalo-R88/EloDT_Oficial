"""Textos sugeridos para publicar cada imagen (LinkedIn, X, Instagram y alt text).

Son plantillas deterministas (sin LLM): el mismo dato produce el mismo texto, así el
pipeline semanal no depende de servicios externos ni gasta tokens. Se generan tres
versiones porque el largo y el tono cambian por red.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

HANDLE = "@AEP_Analitica"
HASHTAGS = "#AEP #DTs #ELO #Futbol"
LIMITE_X = 280
FUENTE = "Datos: Transfermarkt · ELO propio (modelo AEP)."


@dataclass(frozen=True)
class Textos:
    """Los cuatro textos que acompañan a una imagen."""

    linkedin: str
    x: str
    instagram: str
    alt: str


def _nombre(entrada) -> str:
    return getattr(entrada, "dt", "") or ""


def _elo(entrada) -> int:
    return int(round(getattr(entrada, "elo", 0)))


def _podio(entradas: Sequence, n: int = 3, formato: str = "largo") -> str:
    partes = []
    for entrada in list(entradas)[:n]:
        if formato == "corto":
            # En X manda el apellido: es como se reconoce a un DT.
            partes.append(f"{_nombre(entrada).split()[-1]} {_elo(entrada)}")
        else:
            partes.append(f"{getattr(entrada, 'puesto', '')}. {_nombre(entrada)} ({_elo(entrada)})")
    return " · ".join(partes) if formato == "corto" else "\n".join(partes)


def _recortar(texto: str, limite: int = LIMITE_X) -> str:
    """Recorta en el último espacio antes del límite y agrega puntos suspensivos."""
    if len(texto) <= limite:
        return texto
    recorte = texto[: limite - 1]
    corte = recorte.rfind(" ")
    return (recorte[:corte] if corte > 0 else recorte).rstrip(" ,;·") + "…"


def textos_top10(
    entradas: Sequence,
    semana_texto: str,
    titulo: str = "Top 10 DTs de Argentina",
    partidos: Optional[int] = None,
    handle: str = HANDLE,
    pais: Optional[str] = None,
) -> Textos:
    """Textos para el ranking semanal (Top 10)."""
    if not entradas:
        raise ValueError("No hay entradas para generar los textos.")

    lider = entradas[0]
    podio_largo = _podio(entradas, 3)
    podio_corto = _podio(entradas, 3, formato="corto")
    etiqueta_pais = f" de {pais}" if pais and pais not in titulo else ""
    detalle_partidos = f" ({partidos} partidos)" if partidos else ""

    linkedin = (
        f"{titulo} — {semana_texto}{detalle_partidos}\n\n"
        f"{podio_largo}\n\n"
        "El ranking se arma con un modelo ELO propio: cada entrenador aparece con su "
        "club actual y sólo si dirigió en el último año. Gana el que acumula mejores "
        "resultados frente a rivales más exigentes, no el que más partidos jugó.\n\n"
        f"¿Quién te parece que está más alto de lo que debería? Te leo.\n\n"
        f"{HASHTAGS}\n{FUENTE}"
    )

    x = (
        f"🏆 {titulo}{etiqueta_pais} ({semana_texto}): "
        f"{podio_corto}. "
        f"Ranking ELO propio, datos Transfermarkt. {handle}"
    )

    instagram = (
        f"🏆 {titulo} — {semana_texto}\n\n"
        f"El N°1: {_nombre(lider)} ({_elo(lider)}).\n"
        f"Podio: {podio_corto}.\n\n"
        f"Ranking ELO propio. {FUENTE}\n"
        f"{HASHTAGS}"
    )

    if len(entradas) >= 3:
        alt = (
            f"{titulo}: {semana_texto}. Primero {_nombre(lider)} con {_elo(lider)} "
            f"puntos de ELO, segundo {_nombre(entradas[1])} y tercero "
            f"{_nombre(entradas[2])}."
        )
    else:
        alt = f"{titulo}: {semana_texto}."

    return Textos(linkedin=linkedin, x=_recortar(x), instagram=instagram, alt=alt)


def textos_movimientos(
    subidas: Sequence,
    bajadas: Sequence,
    semana_texto: str,
    partidos: Optional[int] = None,
    handle: str = HANDLE,
) -> Textos:
    """Textos para "subieron / cayeron"."""
    if not subidas and not bajadas:
        raise ValueError("No hay movimientos para generar los textos.")

    arriba = subidas[0] if subidas else None
    abajo = bajadas[0] if bajadas else None
    detalle = f" ({partidos} partidos)" if partidos else ""

    gancho = ""
    if arriba:
        gancho += f"Subió más: {_nombre(arriba)} (+{getattr(arriba, 'delta', 0):.1f}). "
    if abajo:
        gancho += f"Bajó más: {_nombre(abajo)} ({getattr(abajo, 'delta', 0):.1f})."

    linkedin = (
        f"Subieron y cayeron — {semana_texto}{detalle}\n\n"
        f"{gancho}\n\n"
        "Cada semana el ELO se mueve con los resultados: ganarle a un rival fuerte suma "
        "más que golear a uno débil, y perder de local cuesta más que perder de visitante.\n\n"
        f"¿A quién le tenés fe para la próxima fecha?\n\n{HASHTAGS}\n{FUENTE}"
    )
    x = _recortar(f"📈 {semana_texto}: {gancho} Ranking ELO propio, datos Transfermarkt. {handle}")
    instagram = (
        f"📈 Subieron y cayeron — {semana_texto}\n\n{gancho}\n\n"
        f"ELO propio. {FUENTE}\n{HASHTAGS}"
    )
    alt = f"Gráfico de subidas y bajadas de ELO de la semana {semana_texto}. {gancho}"

    return Textos(linkedin=linkedin, x=x, instagram=instagram, alt=alt)


def textos_duelo(
    duelo,
    semana_texto: str,
    handle: str = HANDLE,
) -> Textos:
    """Textos para el duelo de la semana entre dos DTs."""
    nombre_a = getattr(duelo, "dt_a", None) or "DT A"
    nombre_b = getattr(duelo, "dt_b", None) or "DT B"
    club_a = getattr(duelo, "club_a", "")
    club_b = getattr(duelo, "club_b", "")
    combinado = getattr(duelo, "elo_combinado", 0.0)

    linkedin = (
        f"Duelo de pizarras — {semana_texto}\n\n"
        f"{nombre_a} ({club_a}) contra {nombre_b} ({club_b}): "
        f"{combinado:.0f} puntos de ELO combinados en el banco.\n\n"
        "Los dos técnicos se enfrentaron con planteles distintos y trayectorias "
        "distintas; el ELO mide lo que cada uno sostuvo en el tiempo.\n\n"
        f"¿Quién gana este duelo para vos?\n\n{HASHTAGS}\n{FUENTE}"
    )
    x = _recortar(
        f"⚔️ {nombre_a} vs {nombre_b} ({semana_texto}): {combinado:.0f} de ELO combinado. "
        f"Ranking ELO propio. {handle}"
    )
    instagram = (
        f"⚔️ Duelo de pizarras — {semana_texto}\n\n{nombre_a} vs {nombre_b}\n"
        f"{combinado:.0f} puntos de ELO combinados.\n\n{hashtags_linea()}"
    )
    alt = (
        f"Gráfico comparando a {nombre_a} y {nombre_b}, con sus ELO y su historial "
        f"de enfrentamientos."
    )
    return Textos(linkedin=linkedin, x=x, instagram=instagram, alt=alt)


def hashtags_linea() -> str:
    return f"{HASHTAGS}\n{FUENTE}"


def textos_revelacion(entrada, semana_texto: str, handle: str = HANDLE) -> Textos:
    """Textos para el "DT revelación"."""
    nombre = getattr(entrada, "dt", "DT")
    club = getattr(entrada, "club", "") or ""
    elo = getattr(entrada, "elo", 0.0)
    pj = getattr(entrada, "pj", 0)
    variacion = getattr(entrada, "variacion", 0.0)
    desde = getattr(entrada, "desde_primera_fecha", None)
    desde_texto = desde.strftime("%d/%m/%Y") if desde else "hace poco"

    linkedin = (
        f"DT revelación — {semana_texto}\n\n"
        f"{nombre} ({club}) lleva {pj} partidos desde {desde_texto} y ya suma "
        f"{int(round(elo))} puntos de ELO"
        + (f" (+{variacion:.1f} en los últimos 90 días)." if variacion else ".")
        + "\n\n"
        "El ranking mira resultados y contexto: no premia al que más partidos jugó, sino "
        "al que sostuvo mejores resultados frente a rivales más exigentes.\n\n"
        f"¿Lo tenías en el radar?\n\n{HASHTAGS}\n{FUENTE}"
    )
    x = _recortar(
        f"🔎 DT revelación: {nombre} ({club}) con {int(round(elo))} de ELO tras {pj} "
        f"partidos. ELO propio. {handle}"
    )
    instagram = (
        f"🔎 DT revelación — {semana_texto}\n\n{nombre} ({club})\n"
        f"{int(round(elo))} de ELO · {pj} partidos\n\n{HASHTAGS}\n{FUENTE}"
    )
    alt = (
        f"Gráfico del DT revelación: {nombre}, de {club}, con {int(round(elo))} puntos "
        f"de ELO en {pj} partidos."
    )
    return Textos(linkedin=linkedin, x=x, instagram=instagram, alt=alt)
