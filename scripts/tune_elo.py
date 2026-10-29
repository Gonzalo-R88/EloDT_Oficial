"""Búsqueda de parámetros del modelo ELO (T1.5).

Entrena con 2016-2022 y valida con 2023-2026, en tres etapas para no barrer una grilla
combinatoria grande:

  A) ventaja de local × ajuste por goleada            (8 combinaciones)
  B) el mejor de A × calibración × escala de K        (6 combinaciones)
  C) el mejor de B × año de inicio del cómputo        (2 combinaciones)

Además corre el experimento de sensibilidad: cuánto cambian los ratings actuales si el
histórico se calcula desde 2000 o desde 2015 (correlación de rangos de Spearman y las
mayores diferencias).

No escribe en la base. Salida: `data/audit/tune_elo.csv` y un resumen por consola.

Uso:
    python3 scripts/tune_elo.py
    python3 scripts/tune_elo.py --min-pj 20 --csv data/audit/tune_elo.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from backtest_elo import cargar_partidos  # noqa: E402
from backtest import PartidoBacktest, evaluar  # noqa: E402
from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from elo import EloParams  # noqa: E402
from models import Coach  # noqa: E402

ENTRENAMIENTO = (date(2016, 1, 1), date(2022, 12, 31))
VALIDACION = (date(2023, 1, 1), date(2026, 12, 31))


@dataclass(frozen=True)
class Combinacion:
    """Una configuración de la grilla."""

    etapa: str
    hfa: float = 30.0
    mov: str = "actual"
    cap: float | None = None
    calibracion: bool = False
    k_escala: float = 1.0
    inicio: int = 2000
    brier_entrenamiento: float = float("nan")
    logloss_entrenamiento: float = float("nan")
    brier_validacion: float = float("nan")
    logloss_validacion: float = float("nan")
    partidos_validacion: int = 0


def _evaluar(
    partidos: list[PartidoBacktest], combo: Combinacion, ventana: tuple[date, date], min_pj: int
) -> tuple[float, float, int]:
    """`(brier, logloss, partidos)` de una configuración en una ventana."""
    params = EloParams(
        hfa=combo.hfa,
        mov_mode=combo.mov,
        mov_cap=combo.cap,
        calibracion_n=30 if combo.calibracion else 0,
        k_escala=combo.k_escala,
    )
    desde_inicio = [p for p in partidos if p.fecha.year >= combo.inicio]
    metricas = evaluar(
        desde_inicio, params=params, desde=ventana[0], hasta=ventana[1],
        min_pj_previos=min_pj, aplicar_calibracion=combo.calibracion,
    )
    return metricas.brier, metricas.logloss, metricas.partidos


def _probar(
    partidos: list[PartidoBacktest], combo: Combinacion, min_pj: int
) -> Combinacion:
    brier_ent, logloss_ent, _ = _evaluar(partidos, combo, ENTRENAMIENTO, min_pj)
    brier_val, logloss_val, n_val = _evaluar(partidos, combo, VALIDACION, min_pj)
    print(
        f"  {combo.etapa:22} hfa={combo.hfa:<5} mov={combo.mov:<12} "
        f"calib={'sí' if combo.calibracion else 'no':<2} k={combo.k_escala:<5} "
        f"inicio={combo.inicio}  train={logloss_ent:.4f}  valid={logloss_val:.4f} "
        f"(brier {brier_val:.4f})"
    )
    return replace(
        combo,
        brier_entrenamiento=brier_ent,
        logloss_entrenamiento=logloss_ent,
        brier_validacion=brier_val,
        logloss_validacion=logloss_val,
        partidos_validacion=n_val,
    )


def _mejor(combos: list[Combinacion]) -> Combinacion:
    """El de menor log-loss de validación (desempate: menor Brier de validación)."""
    return min(combos, key=lambda c: (c.logloss_validacion, c.brier_validacion))


def spearman(a: list[float], b: list[float]) -> float:
    """Correlación de rangos (sin dependencias externas)."""
    if len(a) < 2:
        return float("nan")

    def rangos(valores: list[float]) -> list[float]:
        orden = sorted(range(len(valores)), key=lambda i: valores[i])
        salida = [0.0] * len(valores)
        for posicion, indice in enumerate(orden):
            salida[indice] = float(posicion)
        return salida

    ra, rb = rangos(a), rangos(b)
    media_a = sum(ra) / len(ra)
    media_b = sum(rb) / len(rb)
    covarianza = sum((x - media_a) * (y - media_b) for x, y in zip(ra, rb))
    var_a = sum((x - media_a) ** 2 for x in ra) ** 0.5
    var_b = sum((y - media_b) ** 2 for y in rb) ** 0.5
    return covarianza / (var_a * var_b) if var_a and var_b else float("nan")


def sensibilidad_inicio(
    partidos: list[PartidoBacktest], combo: Combinacion, min_pj: int
) -> tuple[float, list[tuple[int, float, float]]]:
    """Compara los ratings finales calculando desde 2000 y desde 2015."""
    params = EloParams(
        hfa=combo.hfa, mov_mode=combo.mov, mov_cap=combo.cap,
        calibracion_n=30 if combo.calibracion else 0, k_escala=combo.k_escala,
    )
    desde_2000 = evaluar(
        [p for p in partidos if p.fecha.year >= 2000], params=params,
        min_pj_previos=min_pj, aplicar_calibracion=combo.calibracion,
    ).elo_final
    desde_2015 = evaluar(
        [p for p in partidos if p.fecha.year >= 2015], params=params,
        min_pj_previos=min_pj, aplicar_calibracion=combo.calibracion,
    ).elo_final

    comunes = sorted(set(desde_2000) & set(desde_2015))
    correlacion = spearman(
        [desde_2000[dt] for dt in comunes], [desde_2015[dt] for dt in comunes]
    )
    diferencias = sorted(
        ((dt, desde_2000[dt], desde_2015[dt]) for dt in comunes),
        key=lambda fila: -abs(fila[1] - fila[2]),
    )
    return correlacion, diferencias[:20]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Búsqueda de parámetros del ELO.")
    parser.add_argument("--min-pj", type=int, default=30, help="PJ previos mínimos (default 30).")
    parser.add_argument("--csv", type=Path, default=settings.data_dir / "audit" / "tune_elo.csv")
    args = parser.parse_args(argv)

    session = create_session()
    try:
        partidos = cargar_partidos(session)
        nombres = {
            coach.dt_id: f"{coach.nombre} {coach.apellido}".strip()
            for coach in session.execute(select(Coach)).scalars()
        }
    finally:
        session.close()

    print(f"partidos cargados: {len(partidos):,}".replace(",", "."))
    print("\nEtapa A — ventaja de local × ajuste por goleada")
    etapa_a = [
        _probar(partidos, Combinacion("A: hfa/mov", hfa=hfa, mov=mov), args.min_pj)
        for hfa in (30.0, 45.0, 55.0, 65.0)
        for mov in ("actual", "amortiguado")
    ]
    mejor_a = _mejor(etapa_a)

    print("\nEtapa B — calibración × escala de K")
    etapa_b = [
        _probar(
            partidos,
            Combinacion(
                "B: calib/k", hfa=mejor_a.hfa, mov=mejor_a.mov,
                cap=mejor_a.cap, calibracion=calibracion, k_escala=k_escala,
            ),
            args.min_pj,
        )
        for calibracion in (False, True)
        for k_escala in (0.75, 1.0, 1.25)
    ]
    mejor_b = _mejor(etapa_b)

    print("\nEtapa C — año de inicio del cómputo")
    etapa_c = [
        _probar(
            partidos,
            Combinacion(
                "C: inicio", hfa=mejor_b.hfa, mov=mejor_b.mov, cap=mejor_b.cap,
                calibracion=mejor_b.calibracion, k_escala=mejor_b.k_escala, inicio=inicio,
            ),
            args.min_pj,
        )
        for inicio in (2000, 2015)
    ]
    mejor_c = _mejor(etapa_c)

    combos = etapa_a + etapa_b + etapa_c
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(asdict(combos[0]).keys()))
        escritor.writeheader()
        for combo in combos:
            escritor.writerow(asdict(combo))
    print(f"\nresultados: {args.csv}")

    print("\n=== Configuración elegida ===")
    print(
        f"  hfa={mejor_c.hfa}  mov={mejor_c.mov}  calibración={'sí' if mejor_c.calibracion else 'no'}  "
        f"k_escala={mejor_c.k_escala}  inicio={mejor_c.inicio}"
    )
    print(f"  validación: log-loss {mejor_c.logloss_validacion:.4f} · Brier {mejor_c.brier_validacion:.4f}")

    base = next(c for c in etapa_a if c.hfa == 30.0 and c.mov == "actual")
    print(
        f"  actual:     log-loss {base.logloss_validacion:.4f} · Brier {base.brier_validacion:.4f}"
    )
    print(f"  mejora:     {base.logloss_validacion - mejor_c.logloss_validacion:+.4f} de log-loss")

    correlacion, diferencias = sensibilidad_inicio(partidos, mejor_c, args.min_pj)
    print(f"\n=== Sensibilidad al año de inicio (2000 vs 2015) ===")
    print(f"  correlación de rangos (Spearman): {correlacion:.4f}")
    print("  mayores diferencias:")
    for dt_id, elo_2000, elo_2015 in diferencias[:10]:
        print(
            f"    {nombres.get(dt_id, dt_id)[:28]:28} 2000={elo_2000:7.1f}  "
            f"2015={elo_2015:7.1f}  Δ={elo_2015 - elo_2000:+7.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
