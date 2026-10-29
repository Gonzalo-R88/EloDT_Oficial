"""Backtest del modelo ELO: reproduce el histórico en memoria y mide qué tan bien predice.

No escribe en la base ni usa matplotlib: recibe la lista de partidos ya ordenada y
devuelve métricas. Así se pueden probar parámetros (`EloParams`) sin tocar datos.

Métricas:
- **Brier del resultado esperado**: `(E - S)²` con `S ∈ {1, 0,5, 0}`. Es la misma que
  se usó como línea base (0,1783 con una constante, 0,1637 con HFA 30 en 2021+).
- **Brier 1X2**: suma de errores al cuadrado de las tres probabilidades.
- **Log-loss 1X2**: con un modelo de empate simple, `p_empate = d·(1 - |2E - 1|)`, que
  cumple `E = p_local + p_empate/2`. `d` es la tasa de empates en `E = 0,5`.
- **Calibración**: por tramos de `E`, la frecuencia real observada.

Las actualizaciones de ELO se aplican **siempre** (como en el sistema real); los filtros
(`min_pj_previos`, `desde`, `hasta`) sólo deciden qué partidos se evalúan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from elo import (
    INITIAL_ELO,
    EloParams,
    compute_elo_delta,
    expected_result_local,
    match_calibracion,
    result_from_goals,
)

TASA_EMPATE = 0.27
TRAMOS_CALIBRACION = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


@dataclass(frozen=True)
class PartidoBacktest:
    """Un partido tal como lo necesita el backtest (sin ORM)."""

    tm_match_id: Optional[int]
    fecha: date
    dt_local: int
    dt_visita: int
    goles_local: int
    goles_visita: int
    factor_k: int
    coeficiente: float
    nivel: str = ""
    competencia: str = ""


@dataclass
class Metricas:
    """Resultado de evaluar un conjunto de partidos."""

    partidos: int = 0
    brier_resultado: float = 0.0
    brier_1x2: float = 0.0
    log_loss: float = 0.0
    aciertos_signo: int = 0
    por_anio: dict[int, list[float]] = field(default_factory=dict)
    por_nivel: dict[str, list[float]] = field(default_factory=dict)
    calibracion: dict[tuple[float, float], list[float]] = field(default_factory=dict)
    # Rating final de cada DT tras reproducir todo el histórico.
    elo_final: dict[int, float] = field(default_factory=dict)

    @property
    def brier(self) -> float:
        return self.brier_resultado / self.partidos if self.partidos else float("nan")

    @property
    def logloss(self) -> float:
        return self.log_loss / self.partidos if self.partidos else float("nan")

    @property
    def brier_1x2_medio(self) -> float:
        return self.brier_1x2 / self.partidos if self.partidos else float("nan")

    @property
    def exactitud_signo(self) -> float:
        return self.aciertos_signo / self.partidos if self.partidos else float("nan")

    def resumen_calibracion(self) -> list[tuple[float, float, int]]:
        """`[(E medio, frecuencia real, n)]` por tramo, ordenado."""
        filas = []
        for (_, limite), valores in sorted(self.calibracion.items()):
            if not valores:
                continue
            esperado = sum(valores) / len(valores)
            filas.append((round(esperado, 3), round(limite, 2), len(valores)))
        return filas

    def brier_por_anio(self) -> dict[int, float]:
        return {
            anio: round(sum(valores) / len(valores), 4)
            for anio, valores in sorted(self.por_anio.items())
            if valores
        }


def probabilidades_1x2(e_local: float, tasa_empate: float = TASA_EMPATE) -> tuple[float, float, float]:
    """`(p_local, p_empate, p_visita)` a partir de la expectativa de puntos del local.

    `E` es la expectativa de "score" (victoria 1, empate 0,5), así que
    `E = p_local + p_empate/2`. El empate se concentra cerca de `E = 0,5`.
    """
    e = min(max(e_local, 0.0), 1.0)
    p_empate = max(1e-6, tasa_empate * (1 - abs(2 * e - 1)))
    p_local = max(1e-6, e - p_empate / 2)
    p_visita = max(1e-6, 1 - e - p_empate / 2)
    total = p_local + p_empate + p_visita
    return p_local / total, p_empate / total, p_visita / total


def _tramo(e_local: float) -> tuple[float, float]:
    for limite in TRAMOS_CALIBRACION[1:]:
        if e_local <= limite:
            return (round(limite - 0.2, 1), limite)
    return (0.8, 1.0)


def evaluar(
    partidos: Iterable[PartidoBacktest],
    params: Optional[EloParams] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    min_pj_previos: int = 0,
    aplicar_calibracion: bool = False,
    tasa_empate: float = TASA_EMPATE,
) -> Metricas:
    """Reproduce los partidos y mide la capacidad predictiva.

    `min_pj_previos` filtra los partidos evaluados (no las actualizaciones): los que no
    cumplen se juegan igual pero no entran en las métricas. Es lo que se usa para
    evaluar sólo partidos con historial suficiente.
    """
    parametros = params or EloParams()
    elo: dict[int, float] = {}
    partidos_previos: dict[int, int] = {}
    ultima_fecha: dict[int, date] = {}
    metricas = Metricas()

    for partido in partidos:
        elo_local = elo.get(partido.dt_local, INITIAL_ELO)
        elo_visita = elo.get(partido.dt_visita, INITIAL_ELO)

        if aplicar_calibracion and parametros.calibracion_n > 0:
            mult_local = match_calibracion(
                partidos_previos.get(partido.dt_local, 0),
                parametros,
                _dias(partido.fecha, ultima_fecha.get(partido.dt_local)),
            )
            mult_visita = match_calibracion(
                partidos_previos.get(partido.dt_visita, 0),
                parametros,
                _dias(partido.fecha, ultima_fecha.get(partido.dt_visita)),
            )
        else:
            mult_local = mult_visita = 1.0

        evaluar_partido = (
            (desde is None or partido.fecha >= desde)
            and (hasta is None or partido.fecha <= hasta)
            and partidos_previos.get(partido.dt_local, 0) >= min_pj_previos
            and partidos_previos.get(partido.dt_visita, 0) >= min_pj_previos
        )

        if evaluar_partido:
            _acumular(metricas, partido, elo_local, elo_visita, parametros, tasa_empate)

        delta_local, _, _ = compute_elo_delta(
            elo_local, elo_visita, partido.goles_local, partido.goles_visita,
            partido.factor_k, partido.coeficiente, params=parametros,
            mult_local=mult_local, mult_visita=mult_visita,
        )
        elo[partido.dt_local] = elo_local + delta_local
        elo[partido.dt_visita] = elo_visita - delta_local
        partidos_previos[partido.dt_local] = partidos_previos.get(partido.dt_local, 0) + 1
        partidos_previos[partido.dt_visita] = partidos_previos.get(partido.dt_visita, 0) + 1
        ultima_fecha[partido.dt_local] = partido.fecha
        ultima_fecha[partido.dt_visita] = partido.fecha

    metricas.elo_final = dict(elo)
    return metricas


def _dias(fecha: date, anterior: Optional[date]) -> Optional[int]:
    return (fecha - anterior).days if anterior is not None else None


def _acumular(metricas, partido, elo_local, elo_visita, parametros, tasa_empate) -> None:
    e_local = expected_result_local(elo_local, elo_visita, parametros)
    s_local, _ = result_from_goals(partido.goles_local, partido.goles_visita)

    error = (e_local - s_local) ** 2
    metricas.partidos += 1
    metricas.brier_resultado += error
    metricas.por_anio.setdefault(partido.fecha.year, []).append(error)
    metricas.por_nivel.setdefault(partido.nivel, []).append(error)
    metricas.calibracion.setdefault(_tramo(e_local), []).append(e_local)

    p_local, p_empate, p_visita = probabilidades_1x2(e_local, tasa_empate)
    if s_local == 1.0:
        probabilidad = p_local
    elif s_local == 0.5:
        probabilidad = p_empate
    else:
        probabilidad = p_visita
    metricas.log_loss += -math.log(probabilidad)
    metricas.brier_1x2 += sum(
        (probabilidad_modelo - observado) ** 2
        for probabilidad_modelo, observado in (
            (p_local, 1.0 if s_local == 1.0 else 0.0),
            (p_empate, 1.0 if s_local == 0.5 else 0.0),
            (p_visita, 1.0 if s_local == 0.0 else 0.0),
        )
    )
    esperado_signo = max((p_local, "local"), (p_visita, "visita"))
    if (esperado_signo[1] == "local" and s_local == 1.0) or (
        esperado_signo[1] == "visita" and s_local == 0.0
    ):
        metricas.aciertos_signo += 1


def brier_constante(partidos: Iterable[PartidoBacktest], desde: Optional[date] = None) -> float:
    """Línea base: predecir siempre la frecuencia observada de victoria local."""
    resultados = [
        result_from_goals(p.goles_local, p.goles_visita)[0]
        for p in partidos
        if desde is None or p.fecha >= desde
    ]
    if not resultados:
        return float("nan")
    promedio = sum(resultados) / len(resultados)
    return sum((promedio - s) ** 2 for s in resultados) / len(resultados)
