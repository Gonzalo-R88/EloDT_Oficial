"""Textos sugeridos para publicar cada imagen.

Son plantillas deterministas (sin LLM): el mismo dato produce el mismo texto, así el
pipeline semanal no depende de servicios externos ni gasta tokens.

Sale **un solo texto** por pieza, pensado para entrar en el límite de X (280 caracteres) y
servir tal cual en LinkedIn. Sin hashtags, sin nombrar la fuente de los datos y sin el
handle (la cuenta no se menciona a sí misma; el handle va en la imagen).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

LIMITE_POST = 280
CIERRE = "Ranking ELO propio, actualizado cada semana."
# Las ventanas FIFA no cierran con la semana: el cierre no puede decir "cada semana".
CIERRE_SELECCIONES = "Ranking ELO propio de los seleccionadores."


@dataclass(frozen=True)
class Textos:
    """El texto que acompaña a la imagen, con su descripción accesible."""

    texto: str
    alt: str


def _nombre(entrada) -> str:
    return getattr(entrada, "dt", "") or ""


def _apellido(entrada) -> str:
    """En un ranking manda el apellido: es como se reconoce a un DT."""
    return _nombre(entrada).split()[-1] if _nombre(entrada) else ""


def _elo(entrada) -> int:
    return int(round(getattr(entrada, "elo", 0)))


def _decimal(valor: float, decimales: int = 1, signo: bool = False) -> str:
    """Número con coma decimal, como se escribe en español."""
    formato = f"+.{decimales}f" if signo else f".{decimales}f"
    return f"{valor:{formato}}".replace(".", ",")


def _podio(entradas: Sequence, n: int = 3) -> str:
    """El podio en tres líneas: '1. Arruabarrena 1217'."""
    return "\n".join(
        f"{puesto}. {_apellido(entrada)} {_elo(entrada)}"
        for puesto, entrada in enumerate(list(entradas)[:n], 1)
    )


def _recortar(texto: str, limite: int = LIMITE_POST) -> str:
    """Recorta en el último espacio antes del límite y agrega puntos suspensivos."""
    if len(texto) <= limite:
        return texto
    recorte = texto[: limite - 1]
    corte = recorte.rfind(" ")
    return (recorte[:corte] if corte > 0 else recorte).rstrip(" ,;·") + "…"


def textos_top10(
    entradas: Sequence,
    semana_texto: str,
    titulo: Optional[str] = None,
    partidos: Optional[int] = None,
    handle: str = "",
    pais: Optional[str] = None,
) -> Textos:
    """Texto del ranking semanal (Top 10)."""
    if not entradas:
        raise ValueError("No hay entradas para generar los textos.")

    lider = entradas[0]
    titulo = titulo or (f"Top 10 DTs de {pais}" if pais else "Top 10 DTs del mundo")
    gancho = "¿Quién está más alto de lo que debería?"

    texto = _recortar(
        f"🏆 {titulo} · {semana_texto}\n"
        f"{_podio(entradas)}\n"
        f"{CIERRE} {gancho}"
    )

    if len(entradas) >= 3:
        alt = (
            f"{titulo}: {semana_texto}. Primero {_nombre(lider)} con {_elo(lider)} "
            f"puntos de ELO, segundo {_nombre(entradas[1])} y tercero "
            f"{_nombre(entradas[2])}."
        )
    else:
        alt = f"{titulo}: {semana_texto}."

    return Textos(texto=texto, alt=alt)


def textos_movimientos(
    subidas: Sequence,
    bajadas: Sequence,
    semana_texto: str,
    partidos: Optional[int] = None,
    handle: str = "",
) -> Textos:
    """Texto de "subieron / cayeron"."""
    if not subidas and not bajadas:
        raise ValueError("No hay movimientos para generar los textos.")

    arriba = subidas[0] if subidas else None
    abajo = bajadas[0] if bajadas else None

    gancho = ""
    if arriba:
        gancho += f"Subió más: {_nombre(arriba)} (+{_decimal(getattr(arriba, 'delta', 0))}). "
    if abajo:
        gancho += f"Bajó más: {_nombre(abajo)} ({_decimal(getattr(abajo, 'delta', 0))})."

    texto = _recortar(
        f"📈 Subieron y cayeron · {semana_texto}\n"
        f"{gancho.strip()}\n"
        f"{CIERRE} ¿A quién le tenés fe para la próxima fecha?"
    )
    alt = f"Gráfico de subidas y bajadas de ELO de la semana {semana_texto}. {gancho}"

    return Textos(texto=texto, alt=alt)


def textos_movimientos_selecciones(
    subidas: Sequence,
    bajadas: Sequence,
    ventana_texto: str,
    partidos: Optional[int] = None,
) -> Textos:
    """Texto del "subieron y cayeron" de una fecha FIFA (sólo seleccionadores)."""
    if not subidas and not bajadas:
        raise ValueError("No hay movimientos para generar los textos.")

    arriba = subidas[0] if subidas else None
    abajo = bajadas[0] if bajadas else None

    def _linea(etiqueta: str, entrada, signo: bool) -> str:
        if entrada is None:
            return ""
        seleccion = getattr(entrada, "club", "") or ""
        nombre = f"{_nombre(entrada)} ({seleccion})" if seleccion else _nombre(entrada)
        return f"{etiqueta}: {nombre} {_decimal(getattr(entrada, 'delta', 0), signo=True)}."

    gancho = " ".join(
        linea for linea in (
            _linea("Subió más", arriba, True),
            _linea("Bajó más", abajo, False),
        ) if linea
    )

    texto = _recortar(
        f"🌍 Subieron y cayeron en selecciones · fecha FIFA {ventana_texto}\n"
        f"{gancho}\n"
        f"{CIERRE_SELECCIONES}"
    )
    alt = (
        f"Gráfico de subidas y bajadas de ELO de los seleccionadores en la fecha FIFA "
        f"{ventana_texto}. {gancho}"
    )
    return Textos(texto=texto, alt=alt)


def textos_duelo(
    duelo,
    semana_texto: str,
    handle: str = "",
) -> Textos:
    """Texto del duelo de la semana entre dos DTs.

    `duelo` es el `DueloSemana` del partido (dt_a_id/club_a/elo_a + el `Duel` interno,
    que es donde están los nombres y los clubes).
    """
    interno = getattr(duelo, "duelo", None)
    lado_a = getattr(interno, "a", None)
    lado_b = getattr(interno, "b", None)

    nombre_a = getattr(lado_a, "nombre", None) or f"DT {getattr(duelo, 'dt_a_id', 'A')}"
    nombre_b = getattr(lado_b, "nombre", None) or f"DT {getattr(duelo, 'dt_b_id', 'B')}"
    club_a = getattr(lado_a, "club", None) or getattr(duelo, "club_a", "") or ""
    club_b = getattr(lado_b, "club", None) or getattr(duelo, "club_b", "") or ""
    combinado = getattr(duelo, "elo_combinado", 0.0)

    texto = _recortar(
        f"⚔️ Duelo de pizarras · {semana_texto}\n"
        f"{nombre_a} ({club_a}) vs {nombre_b} ({club_b}): "
        f"{combinado:.0f} de ELO combinado.\n"
        f"{CIERRE} ¿Quién gana este duelo para vos?"
    )
    alt = (
        f"Gráfico comparando a {nombre_a} y {nombre_b}, con sus ELO y su historial "
        f"de enfrentamientos."
    )
    return Textos(texto=texto, alt=alt)


def textos_revelacion(entrada, semana_texto: str, handle: str = "") -> Textos:
    """Texto del "DT revelación"."""
    nombre = getattr(entrada, "dt", "DT")
    club = getattr(entrada, "club", "") or ""
    elo = getattr(entrada, "elo", 0.0)
    pj = getattr(entrada, "pj", 0)
    variacion = getattr(entrada, "variacion", 0.0)
    desde = getattr(entrada, "desde_primera_fecha", None)
    desde_texto = desde.strftime("%d/%m/%Y") if desde else "hace poco"

    detalle = f"{int(round(elo))} de ELO en {pj} partidos desde el {desde_texto}"
    texto = _recortar(
        f"🔎 DT revelación · {semana_texto}\n"
        f"{nombre} ({club}): {detalle}."
        + (f" {_decimal(variacion, signo=True)} en los últimos 90 días." if variacion else "")
        + f"\n{CIERRE}"
    )
    alt = (
        f"Gráfico del DT revelación: {nombre}, de {club}, con {int(round(elo))} puntos "
        f"de ELO en {pj} partidos."
    )
    return Textos(texto=texto, alt=alt)
