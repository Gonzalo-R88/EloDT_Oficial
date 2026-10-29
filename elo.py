"""Matemática pura del sistema ELO para Directores Técnicos.

Fórmula central (documento maestro v1):

    ΔELO = K · C · G · (R − E)

donde K es el factor de volatilidad, C el coeficiente de competencia, G el
multiplicador por margen de victoria (MOV), R el resultado real y E la
expectativa. La localía se modela como una ventaja virtual de +30 puntos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

HOME_ADVANTAGE: float = 30.0
ELO_SCALE: float = 400.0
INITIAL_ELO: float = 1000.0

VALID_FACTOR_K = (20, 30, 40)
VALID_BENCH_IMPACT = (-1, 0, 1)

MOV_ACTUAL = "actual"
MOV_TOPE = "cap"
MOV_AMORTIGUADO = "amortiguado"
VALID_MOV_MODES = (MOV_ACTUAL, MOV_TOPE, MOV_AMORTIGUADO)

# Constante del multiplicador amortiguado (estilo FiveThirtyEight).
AMORTIGUADO_K = 2.2


@dataclass(frozen=True)
class EloParams:
    """Parámetros del modelo. Los valores por defecto reproducen el modelo original.

    Se mantiene así a propósito: `compute_elo_delta(..., params=None)` da exactamente
    el mismo número que antes de existir esta clase, y cada cambio se adopta sólo si
    mejora el backtest (`scripts/tune_elo.py`).

    - `hfa`: ventaja de localía en puntos de ELO.
    - `mov_mode`: `actual` (1,0 / 1,5 / (1,75+d)/3), `cap` (igual pero con tope) o
      `amortiguado` (crece con el logaritmo del margen y se atenúa si el ganador era
      muy favorito).
    - `mov_cap`: tope del multiplicador (sólo con `mov_mode="cap"`).
    - `calibracion_n` / `calibracion_mult`: período de calibración de los DTs nuevos.
      Un DT con `n < calibracion_n` partidos juega con K multiplicado por
      `1 + (calibracion_n - n)/calibracion_n * (calibracion_mult - 1)`; con
      `calibracion_n=0` la calibración está desactivada (comportamiento original).
    - `inactividad_dias` / `inactividad_partidos`: al volver tras `inactividad_dias`
      días sin dirigir, el DT se trata como si tuviera `inactividad_partidos`
      partidos previos (acelera su puesta al día). `None` lo desactiva.
    """

    hfa: float = HOME_ADVANTAGE
    mov_mode: str = MOV_ACTUAL
    mov_cap: Optional[float] = None
    calibracion_n: int = 0
    calibracion_mult: float = 2.0
    inactividad_dias: Optional[int] = None
    inactividad_partidos: int = 15
    # Escala global del K (1,0 = el K guardado en cada partido). Sirve para cambiar la
    # volatilidad del sistema sin tocar la base: `k_escala=1.25` equivale a pasar de
    # un K base de 20 a 25.
    k_escala: float = 1.0

    def __post_init__(self) -> None:
        if self.mov_mode not in VALID_MOV_MODES:
            raise ValueError(
                f"mov_mode inválido: {self.mov_mode}. Permitidos: {VALID_MOV_MODES}"
            )
        if self.mov_mode == MOV_TOPE and self.mov_cap is None:
            raise ValueError("mov_mode='cap' requiere mov_cap")
        if self.calibracion_n < 0:
            raise ValueError("calibracion_n no puede ser negativo")
        if self.calibracion_mult < 1:
            raise ValueError("calibracion_mult no puede ser menor que 1")


def match_calibracion(
    partidos_previos: int,
    params: Optional[EloParams] = None,
    dias_desde_ultimo: Optional[int] = None,
) -> float:
    """Multiplicador de K por experiencia del DT (1,0 = sin calibración).

    Un DT nuevo arranca con K más alto (`calibracion_mult`) y baja hasta 1,0 al llegar
    a `calibracion_n` partidos. Si vuelve tras `inactividad_dias` sin dirigir, se lo
    trata como si tuviera `inactividad_partidos` partidos previos.
    """
    parametros = params or EloParams()
    if parametros.calibracion_n <= 0:
        return 1.0

    previos = max(0, partidos_previos)
    if (
        parametros.inactividad_dias is not None
        and dias_desde_ultimo is not None
        and dias_desde_ultimo >= parametros.inactividad_dias
    ):
        previos = max(previos, parametros.inactividad_partidos)

    if previos >= parametros.calibracion_n:
        return 1.0
    proporcion = (parametros.calibracion_n - previos) / parametros.calibracion_n
    return 1.0 + proporcion * (parametros.calibracion_mult - 1.0)


def calculate_expectation(elo_a: float, elo_b: float) -> float:
    """Probabilidad esperada de victoria de A frente a B (logística de 400 pts)."""
    return 1.0 / (1.0 + math.pow(10, (elo_b - elo_a) / ELO_SCALE))


def expected_result_local(
    elo_local: float,
    elo_visita: float,
    params: Optional[EloParams] = None,
) -> float:
    """Expectativa del local incorporando la ventaja de localía."""
    ventaja = params.hfa if params is not None else HOME_ADVANTAGE
    return calculate_expectation(elo_local + ventaja, elo_visita)


def calculate_margin_of_victory_multiplier(goals_a: int, goals_b: int) -> float:
    """Multiplicador por margen de victoria (MOV).

    - Empate o diferencia de 1 gol: 1.0
    - Diferencia de 2 goles: 1.5
    - Diferencia de 3 o más goles: (1.75 + |diff|) / 3
    """
    goal_diff: int = abs(goals_a - goals_b)
    if goal_diff <= 1:
        return 1.0
    if goal_diff == 2:
        return 1.5
    return (1.75 + goal_diff) / 3.0


def mov_multiplier(
    goles_a: int,
    goles_b: int,
    elo_a: float,
    elo_b: float,
    params: Optional[EloParams] = None,
) -> float:
    """Multiplicador por margen de victoria según `mov_mode`.

    - `actual`: no depende de la diferencia previa de ELO.
    - `cap`: igual, con un tope (evita que una goleada al débil mueva demasiado).
    - `amortiguado`: `ln(|d|+1) · 2,2 / (ventaja_del_ganador·0,001 + 2,2)`. La misma
      goleada mueve menos si el ganador era muy favorito, y más si era el débil.
    """
    parametros = params or EloParams()
    if parametros.mov_mode == MOV_ACTUAL:
        return calculate_margin_of_victory_multiplier(goles_a, goles_b)
    if parametros.mov_mode == MOV_TOPE:
        base = calculate_margin_of_victory_multiplier(goles_a, goles_b)
        return min(base, parametros.mov_cap)

    diferencia = abs(goles_a - goles_b)
    if diferencia == 0:
        return 1.0
    if goles_a > goles_b:
        elo_ganador, elo_perdedor = elo_a, elo_b
    else:
        elo_ganador, elo_perdedor = elo_b, elo_a
    ventaja = elo_ganador - elo_perdedor
    return (
        math.log(diferencia + 1)
        * AMORTIGUADO_K
        / (ventaja * 0.001 + AMORTIGUADO_K)
    )


def result_from_goals(goles_local: int, goles_visita: int) -> tuple[float, float]:
    """Devuelve (R_local, R_visita): 1.0 victoria, 0.5 empate, 0.0 derrota."""
    if goles_local > goles_visita:
        return 1.0, 0.0
    if goles_local < goles_visita:
        return 0.0, 1.0
    return 0.5, 0.5


def compute_elo_delta(
    elo_local: float,
    elo_visita: float,
    goles_local: int,
    goles_visita: int,
    factor_k: int,
    coeficiente: float,
    apply_mov: bool = True,
    params: Optional[EloParams] = None,
    mult_local: float = 1.0,
    mult_visita: float = 1.0,
) -> tuple[float, float, float]:
    """Calcula (delta_local, delta_visita, mov).

    El intercambio es de suma cero: delta_visita = -delta_local.

    `mult_local`/`mult_visita` son los multiplicadores de calibración de cada DT
    (ver `match_calibracion`); el K efectivo del partido es `factor_k` por el promedio
    de los dos, así el intercambio sigue siendo de suma cero.
    """
    if factor_k not in VALID_FACTOR_K:
        raise ValueError(f"factor_k inválido: {factor_k}. Valores permitidos: {VALID_FACTOR_K}")

    e_local = expected_result_local(elo_local, elo_visita, params)
    r_local, r_visita = result_from_goals(goles_local, goles_visita)
    mov = (
        mov_multiplier(goles_local, goles_visita, elo_local, elo_visita, params)
        if apply_mov
        else 1.0
    )
    parametros = params or EloParams()
    k_efectivo = factor_k * parametros.k_escala * (mult_local + mult_visita) / 2.0

    delta_local = k_efectivo * coeficiente * mov * (r_local - e_local)
    delta_visita = k_efectivo * coeficiente * mov * (r_visita - (1.0 - e_local))
    return delta_local, delta_visita, mov


def classify_bench_impact(
    team_goals_before: int,
    opp_goals_before: int,
    team_goals_final: int,
    opp_goals_final: int,
) -> int:
    """Clasifica el impacto del banco de suplentes.

    +1: el equipo mejoró su diferencia tras los cambios.
     0: mantuvo la misma diferencia.
    -1: empeoró su diferencia.
    """
    before = team_goals_before - opp_goals_before
    after = team_goals_final - opp_goals_final
    if after > before:
        return 1
    if after < before:
        return -1
    return 0
