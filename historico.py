"""Histórico de la liga argentina 2012-2014 (T0.11, etapa A).

Transfermarkt no tiene las ligas argentinas anteriores a 2015 y pedirlas devuelve la
temporada actual. Este módulo arma ese hueco con dos fuentes externas:

* **Primera 2012/13, 2013/14 y 2014** — `football-data.co.uk` (`/new/ARG.csv`).
* **Primera B Nacional 2013/14** — RSSSF (`rsssf.org/tablesa/arg2014.html`).

Ninguna de las dos dice quién dirigía. Ese dato sale del historial de etapas de cada
club en Transfermarkt (`/{slug}/mitarbeiterhistorie/verein/{id}`), que se asigna por
fecha y se valida contra los partidos que informa Transfermarkt por etapa.

El módulo no toca la red ni la base: parsea texto y resuelve. La descarga y la carga
viven en `scripts/historico_argentina.py`.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

# Códigos de competencia nuevos. No se scrapean: son de carga única.
ARGH = "ARGH"  # Primera División 2012-2014
ARG2H = "ARG2H"  # Primera B Nacional 2013/14

# Temporada real (año de inicio) -> tramo de fechas. Las temporadas argentinas de
# esta época arrancan en agosto y cierran a mitad del año siguiente.
TEMPORADAS = {
    2012: (date(2012, 7, 1), date(2013, 6, 30)),
    2013: (date(2013, 7, 1), date(2014, 6, 30)),
    2014: (date(2014, 7, 1), date(2014, 12, 31)),
}

# Nombres de las fuentes -> `tm_id` del club. Revisado a mano contra `clubes`.
# football-data (Primera) y RSSSF (B Nacional) escriben los nombres distinto, así que
# la tabla incluye las dos formas.
CLUBES: dict[str, int] = {
    # Primera (football-data)
    "All Boys": 12100,
    "Argentinos Jrs": 1030,
    "Arsenal Sarandi": 4673,
    "Atl. Rafaela": 10233,
    "Banfield": 830,
    "Belgrano": 2417,
    "Boca Juniors": 189,
    "Colon Santa FE": 1070,
    "Defensa y Justicia": 2402,
    "Estudiantes L.P.": 288,
    "Gimnasia L.P.": 1106,
    "Godoy Cruz": 12574,
    "Independiente": 1234,
    "Lanus": 333,
    "Newells Old Boys": 1286,
    "Olimpo Bahia Blanca": 7468,
    "Quilmes": 1826,
    "Racing Club": 1444,
    "River Plate": 209,
    "Rosario Central": 1418,
    "San Lorenzo": 1775,
    "San Martin S.J.": 10511,
    "Tigre": 11831,
    "Union de Santa Fe": 7097,
    "Velez Sarsfield": 1029,
    # Primera B Nacional 2013/14 (RSSSF)
    "Atlético Tucumán": 14554,
    "Instituto": 1829,
    "Gimnasia (San Salvador de Jujuy)": 10885,
    "Crucero del Norte": 26157,
    "San Martín (San Juan)": 10511,
    "Unión (Santa Fe)": 7097,
    "Independiente Rivadavia": 12179,
    "Sarmiento (Junín)": 12454,
    "Ferro Carril Oeste (Buenos Aires)": 4557,
    "Boca Unidos": 13549,
    "Sportivo Belgrano": 15414,
    "Aldosivi": 12301,
    "Douglas Haig": 14718,
    "Brown (Adrogué)": 14681,
    "Patronato de la Juventud Católica": 19806,
    "Talleres (Córdoba)": 3938,
    "Almirante Brown": 12672,
    "Villa San Carlos": 19517,
    "Huracán (Buenos Aires)": 2063,
    "Independiente (Avellaneda)": 1234,
}

# Partidos de las fuentes que NO son de liga y quedan afuera para que cada equipo
# cierre con 38 (Primera) o 42 (B Nacional) partidos, una invariante verificable.
# Se identifican por (fecha, local_tm, visitante_tm) y no por regla: el tercer cruce
# entre dos equipos casi siempre es una copa o un desempate, pero hay que mirarlo uno
# por uno para no descartar un partido postergado de liga.
NO_LIGA: dict[tuple[date, int, int], str] = {
    (date(2013, 6, 29), 1029, 1286): "Copa Campeonato 2012/13 (Vélez-Newell's)",
    (date(2014, 5, 25), 1775, 209): "Copa Campeonato 2013/14 (San Lorenzo-River)",
    (date(2014, 5, 24), 1070, 10233): "desempate/playoff Colón-Rafaela",
    # Tercer cruce de la temporada (ya se habían enfrentado en el Inicial y en el
    # Final): no es un partido de liga, aunque el CSV lo etiquete así.
    (date(2015, 1, 29), 189, 1029): "tercer cruce Boca-Vélez",
    (date(2014, 6, 11), 1234, 2063): "playoff de ascenso Independiente-Huracán",
}

RE_RSSSF_FECHA = re.compile(r"^\[([A-Z][a-z]{2})\s+(\d{1,2})\]:?$")
RE_RSSSF_FECHA_EN_LINEA = re.compile(r"\[([A-Z][a-z]{2})\s+(\d{1,2})\]")
RE_RSSSF_PARTIDO = re.compile(
    r"^(?P<local>.+?)\s{2,}(?P<gl>\d+)-(?P<gv>\d+)\s+(?P<resto>.+)$"
)
RE_RSSSF_RONDA = re.compile(r"<u>Round\s+\d+</u>:?")

MESES = {
    nombre: numero
    for numero, nombre in enumerate(
        "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1
    )
}


@dataclass(frozen=True)
class PartidoHistorico:
    """Un partido de liga listo para cargar, sin datos de entrenador todavía."""

    fecha: date
    temporada: int  # año de inicio de la temporada según la fuente (no el de la fecha)
    competencia: str
    local_tm_id: int
    visita_tm_id: int
    goles_local: int
    goles_visita: int
    factor_k: int = 20


@dataclass(frozen=True)
class Etapa:
    """Una etapa de un entrenador en un club según Transfermarkt."""

    club_tm_id: int
    dt_tm_id: int
    dt_nombre: str
    desde: date
    hasta: Optional[date]
    pj_tm: Optional[int]
    interino: bool = False


class FuenteInvalida(ValueError):
    """La fuente no tiene el formato esperado: mejor cortar que cargar mal."""


# ---------------------------------------------------------------------------
# football-data.co.uk
# ---------------------------------------------------------------------------
def parse_football_data(texto: str) -> list[PartidoHistorico]:
    """Primera 2012/13, 2013/14 y 2014 desde el CSV de football-data.

    El CSV trae las cuotas además del resultado; sólo se usan fecha, equipos y goles.
    """
    lector = csv.DictReader(io.StringIO(texto.lstrip("\ufeff")))
    partidos: list[PartidoHistorico] = []
    sin_mapear: set[str] = set()

    for fila in lector:
        temporada = _temporada_football_data(fila.get("Season", ""))
        if temporada is None:
            continue
        dia = _fecha_dmy(fila.get("Date", ""))
        if dia is None:
            continue
        local = fila.get("Home", "").strip()
        visita = fila.get("Away", "").strip()
        if local not in CLUBES or visita not in CLUBES:
            sin_mapear.update({local, visita})
            continue
        partidos.append(
            PartidoHistorico(
                fecha=dia,
                temporada=temporada,
                competencia=ARGH,
                local_tm_id=CLUBES[local],
                visita_tm_id=CLUBES[visita],
                goles_local=int(fila["HG"]),
                goles_visita=int(fila["AG"]),
            )
        )

    if sin_mapear:
        raise FuenteInvalida(f"Clubes sin mapear en football-data: {sorted(sin_mapear)}")
    if not partidos:
        raise FuenteInvalida("football-data no devolvió ningún partido de 2012-2014.")
    return partidos


def _temporada_football_data(texto: str) -> Optional[int]:
    """'2012/2013' -> 2012; '2014' -> 2014; el resto (2015+) -> None."""
    limpio = texto.strip()
    if not limpio:
        return None
    try:
        inicio = int(limpio.split("/")[0])
    except ValueError:
        return None
    return inicio if inicio in TEMPORADAS else None


def _fecha_dmy(texto: str) -> Optional[date]:
    partes = texto.strip().split("/")
    if len(partes) != 3:
        return None
    try:
        return date(int(partes[2]), int(partes[1]), int(partes[0]))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# RSSSF
# ---------------------------------------------------------------------------
def parse_bnacional(html: str, temporada: int = 2013) -> list[PartidoHistorico]:
    """Primera B Nacional 2013/14 desde la página de RSSSF.

    La página trae todas las categorías. Se toma sólo la sección
    `name="second"` (Segunda División) y se parsean las rondas, no las tablas de
    posiciones ni la de promedios: una línea se acepta sólo si los dos equipos
    están en `CLUBES`.
    """
    inicio = html.find('name="second"')
    fin = html.find('name="third"')
    if inicio < 0:
        raise FuenteInvalida("RSSSF: no se encontró la sección de la B Nacional.")
    seccion = html[inicio : fin if fin > inicio else len(html)]

    bloques = RE_RSSSF_RONDA.split(seccion)[1:]
    if not bloques:
        raise FuenteInvalida("RSSSF: la sección de la B Nacional no tiene rondas.")

    partidos: list[PartidoHistorico] = []
    for bloque in bloques:
        dia_actual: Optional[date] = None
        for linea in bloque.split("\n"):
            linea = linea.strip()
            # La fecha abre la mayoría de los bloques, pero también puede venir en la
            # misma línea que un subtítulo ("<u>Playoff</u> [Jun 11]:").
            marca = RE_RSSSF_FECHA_EN_LINEA.search(linea)
            if marca:
                dia_actual = _fecha_rsssf(marca.group(1), int(marca.group(2)), temporada)
                linea = linea[marca.end() :].strip(" :")
                if not linea:
                    continue
            encontrado = RE_RSSSF_PARTIDO.match(linea)
            if not encontrado or dia_actual is None:
                continue
            local = encontrado.group("local").strip()
            visita = re.sub(r"\s*\[.*$", "", encontrado.group("resto")).strip()
            if local not in CLUBES or visita not in CLUBES:
                continue
            partidos.append(
                PartidoHistorico(
                    fecha=dia_actual,
                    temporada=temporada,
                    competencia=ARG2H,
                    local_tm_id=CLUBES[local],
                    visita_tm_id=CLUBES[visita],
                    goles_local=int(encontrado.group("gl")),
                    goles_visita=int(encontrado.group("gv")),
                )
            )

    if not partidos:
        raise FuenteInvalida("RSSSF: no se pudo parsear ningún partido de la B Nacional.")
    return partidos


def _fecha_rsssf(mes: str, dia: int, temporada: int) -> date:
    """'Aug' 3 de la temporada 2013/14 -> 2013-08-03; 'Jun' -> año siguiente."""
    numero = MESES[mes]
    anio = temporada if numero >= 7 else temporada + 1
    return date(anio, numero, dia)


# ---------------------------------------------------------------------------
# Limpieza de partidos
# ---------------------------------------------------------------------------
def limpiar(partidos: Iterable[PartidoHistorico]) -> list[PartidoHistorico]:
    """Quita los partidos que no son de liga y ordena cronológicamente."""
    limpios = [
        partido
        for partido in partidos
        if (partido.fecha, partido.local_tm_id, partido.visita_tm_id) not in NO_LIGA
    ]
    limpios.sort(key=lambda p: (p.fecha, p.local_tm_id, p.visita_tm_id))
    return limpios


def equipos(partidos: Iterable[PartidoHistorico]) -> set[int]:
    return {p.local_tm_id for p in partidos} | {p.visita_tm_id for p in partidos}


# ---------------------------------------------------------------------------
# Etapas de entrenadores (Transfermarkt)
# ---------------------------------------------------------------------------
RE_ETAPA_TM = re.compile(r"/profil/trainer/(\d+)")
RE_FECHA_TM_DMY = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_FECHA_TM_TEXTO = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})")


def parse_etapas(html: str, club_tm_id: int) -> list[Etapa]:
    """Etapas de entrenadores de un club desde `mitarbeiterhistorie`.

    La tabla (`table.items`) tiene una columna por dato:

        Name/Date of birth | Nat. | Appointed | End of time in post | Time in post | Matches | PPG

    Se toman las columnas por su encabezado y no por posición, porque la primera
    celda trae además la fecha de nacimiento del entrenador y confundirla con el
    inicio de la etapa corre todo el historial.
    """
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(html, "lxml")
    tabla = sopa.find("table", class_="items") or sopa
    filas = tabla.find_all("tr")
    columnas = _columnas(filas)
    etapas: list[Etapa] = []

    for fila in filas:
        celdas = fila.find_all("td", recursive=False)
        if len(celdas) <= max(columnas.values(), default=6):
            continue
        enlace = fila.find("a", href=RE_ETAPA_TM)
        if enlace is None:
            continue
        coincidencia = RE_ETAPA_TM.search(enlace.get("href", ""))
        if coincidencia is None:
            continue

        desde = _fecha_celda(celdas[columnas["desde"]])
        if desde is None:
            continue
        etapas.append(
            Etapa(
                club_tm_id=club_tm_id,
                dt_tm_id=int(coincidencia.group(1)),
                dt_nombre=_nombre_enlace(enlace),
                desde=desde,
                hasta=_fecha_celda(celdas[columnas["hasta"]]),
                pj_tm=_entero_celda(celdas[columnas["pj"]]),
            )
        )
    return etapas


def _columnas(filas) -> dict[str, int]:
    """Índice de cada columna según el encabezado; posición conocida como respaldo."""
    por_defecto = {"desde": 2, "hasta": 3, "pj": 5}
    for fila in filas:
        celdas = fila.find_all(["th", "td"], recursive=False)
        textos = [celda.get_text(" ", strip=True).lower() for celda in celdas]
        if not any("appointed" in texto for texto in textos):
            continue
        encontradas = dict(por_defecto)
        for indice, texto in enumerate(textos):
            if "appointed" in texto:
                encontradas["desde"] = indice
            elif "end of time" in texto:
                encontradas["hasta"] = indice
            elif texto.startswith("matches"):
                encontradas["pj"] = indice
        return encontradas
    return por_defecto


def _nombre_enlace(enlace) -> str:
    for candidato in (enlace.get("title"), enlace.get_text(" ", strip=True)):
        if candidato and candidato.strip():
            return candidato.strip()
    imagen = enlace.find("img")
    if imagen is not None and imagen.get("alt"):
        return imagen["alt"].strip()
    return ""


def _fecha_celda(celda) -> Optional[date]:
    """Primera fecha `dd/mm/aaaa` de la celda (vacía si no es una etapa abierta)."""
    for dia, mes, anio in RE_FECHA_TM_DMY.findall(celda.get_text(" ", strip=True)):
        try:
            return date(int(anio), int(mes), int(dia))
        except ValueError:
            continue
    for mes, dia, anio in RE_FECHA_TM_TEXTO.findall(celda.get_text(" ", strip=True)):
        numero = MESES.get(mes)
        if numero:
            return date(int(anio), numero, int(dia))
    return None


def _entero_celda(celda) -> Optional[int]:
    """Entero de la celda (los partidos vienen dentro de un link)."""
    texto = celda.get_text(" ", strip=True)
    return int(texto) if re.fullmatch(r"\d{1,4}", texto) else None


# ---------------------------------------------------------------------------
# Asignación del entrenador por fecha
# ---------------------------------------------------------------------------
def etapas_por_club(etapas: Iterable[Etapa]) -> dict[int, list[Etapa]]:
    """Agrupa y ordena las etapas de cada club por fecha de inicio."""
    agrupadas: dict[int, list[Etapa]] = {}
    for etapa in etapas:
        agrupadas.setdefault(etapa.club_tm_id, []).append(etapa)
    for lista in agrupadas.values():
        lista.sort(key=lambda e: e.desde)
    return agrupadas


def entrenador_en(etapas: list[Etapa], dia: date) -> Optional[Etapa]:
    """Etapa vigente en `dia`, respetando el orden de las etapas.

    La fecha de fin de Transfermarkt viene redondeada (1 de enero o 31 de diciembre),
    así que el arranque de la etapa siguiente manda: si las fechas se solapan, gana la
    etapa posterior; si queda un hueco (interino sin etapa propia), no se inventa nada
    y el partido se descarta.
    """
    if not etapas:
        return None
    ordenadas = sorted(etapas, key=lambda e: e.desde)
    elegida: Optional[Etapa] = None
    for indice, etapa in enumerate(ordenadas):
        siguiente = ordenadas[indice + 1].desde if indice + 1 < len(ordenadas) else None
        fin = _fin_efectiva(etapa.hasta, siguiente)
        if etapa.desde <= dia < fin:
            elegida = etapa
    return elegida


def _fin_efectiva(hasta: Optional[date], siguiente: Optional[date]) -> date:
    """Fin de la etapa: el menor entre el declarado y el arranque de la siguiente."""
    fin = date.max
    if hasta is not None:
        fin = min(fin, hasta + _UN_DIA)
    if siguiente is not None:
        fin = min(fin, siguiente)
    return fin


_UN_DIA = __import__("datetime").timedelta(days=1)


# ---------------------------------------------------------------------------
# Armado final
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PartidoAsignado:
    """Partido con los dos entrenadores resueltos."""

    fecha: date
    temporada: int
    competencia: str
    local_tm_id: int
    visita_tm_id: int
    goles_local: int
    goles_visita: int
    factor_k: int
    dt_local_tm_id: int
    dt_local_nombre: str
    dt_visita_tm_id: int
    dt_visita_nombre: str


@dataclass
class Asignacion:
    """Resultado de asignar entrenadores: partidos listos y problemas detectados."""

    partidos: list[PartidoAsignado]
    sin_dt: list[PartidoHistorico]
    problemas: list[str]

    @property
    def completo(self) -> bool:
        return not self.sin_dt


def asignar(
    partidos: Iterable[PartidoHistorico],
    etapas: dict[int, list[Etapa]],
) -> Asignacion:
    """Resuelve el entrenador de cada club en cada partido."""
    asignados: list[PartidoAsignado] = []
    sin_dt: list[PartidoHistorico] = []
    problemas: list[str] = []

    for partido in partidos:
        local = entrenador_en(etapas.get(partido.local_tm_id, []), partido.fecha)
        visita = entrenador_en(etapas.get(partido.visita_tm_id, []), partido.fecha)
        if local is None or visita is None:
            sin_dt.append(partido)
            continue
        asignados.append(
            PartidoAsignado(
                fecha=partido.fecha,
                temporada=partido.temporada,
                competencia=partido.competencia,
                local_tm_id=partido.local_tm_id,
                visita_tm_id=partido.visita_tm_id,
                goles_local=partido.goles_local,
                goles_visita=partido.goles_visita,
                factor_k=partido.factor_k,
                dt_local_tm_id=local.dt_tm_id,
                dt_local_nombre=local.dt_nombre,
                dt_visita_tm_id=visita.dt_tm_id,
                dt_visita_nombre=visita.dt_nombre,
            )
        )

    if not etapas:
        problemas.append("No hay etapas de entrenadores cargadas.")
    return Asignacion(partidos=asignados, sin_dt=sin_dt, problemas=problemas)


def partidos_por_equipo(
    partidos: Iterable[PartidoHistorico],
    competencia: Optional[str] = None,
    temporada: Optional[int] = None,
) -> dict[int, int]:
    """Cantidad de partidos por club (invariante: 38 en Primera, 42 en la B)."""
    conteo: dict[int, int] = {}
    for partido in partidos:
        if competencia is not None and partido.competencia != competencia:
            continue
        if temporada is not None and partido.temporada != temporada:
            continue
        for club in (partido.local_tm_id, partido.visita_tm_id):
            conteo[club] = conteo.get(club, 0) + 1
    return conteo


def validar_ligas(partidos: list[PartidoHistorico]) -> list[str]:
    """Verifica que cada temporada y competencia cierre con la cantidad esperada.

    La cuenta es por temporada de la fuente, no por año de la fecha: el partido
    postergado Boca-Vélez se jugó el 29/01/2015 y sigue siendo de la temporada
    2013/14.
    """
    problemas: list[str] = []
    esperados = {
        (ARGH, 2012): 38,
        (ARGH, 2013): 38,
        # 2014 fue el torneo de Transición: una sola rueda de 19 fechas.
        (ARGH, 2014): 19,
        (ARG2H, 2013): 42,
    }
    vistos = {(p.competencia, p.temporada) for p in partidos}
    for (competencia, temporada), esperado in esperados.items():
        if (competencia, temporada) not in vistos:
            problemas.append(f"{competencia} {temporada}: no hay partidos.")
            continue
        for club, cantidad in sorted(
            partidos_por_equipo(partidos, competencia, temporada).items()
        ):
            if cantidad != esperado:
                problemas.append(
                    f"{competencia} {temporada}: club {club} tiene {cantidad} "
                    f"partidos (esperado {esperado})."
                )
    for clave in _duplicados(partidos):
        problemas.append(f"partido repetido {clave}.")
    return problemas


def _duplicados(partidos: Iterable[PartidoHistorico]) -> list[tuple[date, int, int]]:
    vistos: set[tuple[date, int, int]] = set()
    repetidos: list[tuple[date, int, int]] = []
    for partido in partidos:
        clave = (partido.fecha, partido.local_tm_id, partido.visita_tm_id)
        if clave in vistos:
            repetidos.append(clave)
        vistos.add(clave)
    return repetidos


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin espacios repetidos (para comparar nombres)."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()