"""Auditoría de cobertura del caché contra la base.

Genera en `data/audit/`:
- `cobertura.json`: `{codigo: {anio: {"fixtures", "cargados", "ratio"}}}` (lo consume
  la regla de publicación y el pipeline semanal).
- `conflictos_fecha.json`: DTs con más de un partido el mismo día.
- `auditoria_<fecha>.md`: informe legible con totales, huecos y peores años.

Uso:
    python3 scripts/audit_data.py
    python3 scripts/audit_data.py --muestra 3000      # estima % de reportes sin DT
    python3 scripts/audit_data.py --hoy 2026-10-27    # fija la fecha de referencia
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from auditoria import (  # noqa: E402
    cobertura_a_json,
    conflictos_dt_dia,
    construir_cobertura,
    estimar_dt_faltante,
    iter_fixtures,
    primera_temporada_por_competencia,
    rangos_anios,
    resumir_competencias,
    rutas_reportes,
    ultima_temporada_por_competencia,
    ultimos_partidos,
)
from config import settings  # noqa: E402
from db import create_session  # noqa: E402
from models import MatchCoach  # noqa: E402


def ids_en_db(session) -> set[int]:
    """IDs de Transfermarkt de los partidos ya cargados."""
    return {
        int(valor)
        for valor in session.execute(
            select(MatchCoach.transfermarkt_match_id).where(
                MatchCoach.transfermarkt_match_id.is_not(None)
            )
        ).scalars()
    }


def total_partidos(session) -> int:
    return int(session.execute(select(func.count(MatchCoach.partido_id))).scalar_one())


def informe_markdown(
    *,
    hoy: date,
    total_fixtures: int,
    total_cargados_cache: int,
    total_db: int,
    sin_fecha: dict[str, int],
    resumenes,
    conflictos,
    ultimos,
    muestra_dt,
    top: int,
) -> str:
    """Arma el informe legible de la auditoría."""
    ratio_global = round(100 * total_cargados_cache / total_fixtures, 2) if total_fixtures else 0.0
    lineas: list[str] = [
        f"# Auditoría de datos — {hoy.isoformat()}",
        "",
        "## Totales",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Fixtures cacheados | {total_fixtures:,} |".replace(",", "."),
        f"| Partidos en la base | {total_db:,} |".replace(",", "."),
        f"| Fixtures cacheados que están en la base | {total_cargados_cache:,} |".replace(",", "."),
        f"| Cobertura global del caché | {ratio_global} % |",
        f"| Conflictos de fecha (DT con >1 partido el mismo día) | {len(conflictos)} |",
        f"| Competencias con datos | "
        f"{sum(1 for r in resumenes if r.fixtures)} de {len(resumenes)} |",
        "",
    ]

    if total_db != total_cargados_cache:
        lineas += [
            f"> **Atención:** hay {total_db - total_cargados_cache} partidos en la base que "
            "no están en el caché actual (o el caché se regeneró). Revisar antes de confiar "
            "en la cobertura por año.",
            "",
        ]

    faltantes = [c for c, n in sorted(sin_fecha.items()) if n]
    if faltantes:
        lineas += [
            "Fixtures cacheados sin fecha usable (no se pueden asignar a un año): "
            + ", ".join(f"`{c}` {n}" for c in faltantes for n in [sin_fecha[c]]),
            "",
        ]

    lineas += [
        "## Cobertura por competencia",
        "",
        "Ordenado por peor ratio. `Huecos` son años sin ningún fixture cacheado; "
        "`Incompletos` son años con fixtures de los que faltan partidos en la base.",
        "",
        "| Competencia | Fixtures | Cargados | Ratio | Huecos | Incompletos |",
        "|---|---:|---:|---:|---|---|",
    ]
    for r in resumenes:
        lineas.append(
            f"| `{r.codigo}` | {r.fixtures} | {r.cargados} | {round(100 * r.ratio, 1)} % | "
            f"{rangos_anios(r.anios_hueco) or '—'} | {rangos_anios(r.anios_incompletos) or '—'} |"
        )

    if conflictos:
        lineas += [
            "",
            f"## Conflictos de fecha ({len(conflictos)})",
            "",
            "Un DT con más de un partido el mismo día suele indicar una fecha mal parseada.",
            "",
            "| DT | Fecha | Partidos | Competencias | Partidos (tm_id) |",
            "|---|---|---:|---|---|",
        ]
        for c in conflictos[:top]:
            lineas.append(
                f"| {c.nombre} | {c.fecha.isoformat()} | {c.partidos} | "
                f"{', '.join(c.competencias)} | {', '.join(str(m) for m in c.match_ids)} |"
            )

    lineas += [
        "",
        "## Último partido cargado por competencia",
        "",
        "| Competencia | Último partido | Días | Partidos |",
        "|---|---|---:|---:|",
    ]
    for u in ultimos:
        lineas.append(f"| `{u.codigo}` | {u.fecha.isoformat()} | {u.dias} | {u.partidos} |")

    if muestra_dt:
        lineas += [
            "",
            "## Reportes sin algún DT (muestra)",
            "",
            "| Quinquenio | Reportes | Sin algún DT | % |",
            "|---|---:|---:|---:|",
        ]
        for quinquenio, valores in muestra_dt.items():
            lineas.append(
                f"| {quinquenio}-{quinquenio + 4} | {valores['reportes']} | "
                f"{valores['sin_dt']} | {valores['pct_sin_dt']} % |"
            )

    lineas.append("")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audita la cobertura del caché contra la base.")
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir,
                        help="Raíz del caché (default: $DATA_DIR).")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Destino de los informes (default: <data-dir>/audit).")
    parser.add_argument("--muestra", type=int, default=0,
                        help="Cantidad de reportes a muestrear para el % sin DT (default: 0).")
    parser.add_argument("--top", type=int, default=15,
                        help="Cuántos conflictos listar en el informe (default: 15).")
    parser.add_argument("--hoy", type=date.fromisoformat, default=date.today(),
                        help="Fecha de referencia (YYYY-MM-DD).")
    args = parser.parse_args(argv)

    data_dir: Path = args.data_dir
    out_dir: Path = args.out_dir or data_dir / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    session = create_session()
    try:
        ids = ids_en_db(session)
        total_db = total_partidos(session)
        conflictos = conflictos_dt_dia(session)
        ultimos = ultimos_partidos(session, args.hoy)
    finally:
        session.close()

    cobertura, sin_fecha = construir_cobertura(
        iter_fixtures(data_dir),
        ids_en_db=ids,
        primera_temporada=primera_temporada_por_competencia(),
        anio_actual=args.hoy.year,
        ultima_temporada=ultima_temporada_por_competencia(),
    )
    resumenes = resumir_competencias(cobertura)

    # Los fixtures sin fecha no se pueden asignar a un año: se suman aparte para que
    # el total del informe reconcilie con el caché real.
    total_fixtures = sum(r.fixtures for r in resumenes) + sum(sin_fecha.values())
    total_cargados = sum(r.cargados for r in resumenes)

    (out_dir / "cobertura.json").write_text(
        json.dumps(cobertura_a_json(cobertura), indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "conflictos_fecha.json").write_text(
        json.dumps(
            [
                {
                    "dt_id": c.dt_id,
                    "nombre": c.nombre,
                    "fecha": c.fecha.isoformat(),
                    "partidos": c.partidos,
                    "competencias": c.competencias,
                    "match_ids": c.match_ids,
                }
                for c in conflictos
            ],
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    muestra_dt = estimar_dt_faltante(rutas_reportes(data_dir), args.muestra) if args.muestra else {}

    informe = informe_markdown(
        hoy=args.hoy,
        total_fixtures=total_fixtures,
        total_cargados_cache=total_cargados,
        total_db=total_db,
        sin_fecha=sin_fecha,
        resumenes=resumenes,
        conflictos=conflictos,
        ultimos=ultimos,
        muestra_dt=muestra_dt,
        top=args.top,
    )
    ruta_informe = out_dir / f"auditoria_{args.hoy.isoformat()}.md"
    ruta_informe.write_text(informe, encoding="utf-8")

    print(f"fixtures cacheados: {total_fixtures}")
    print(f"partidos en la base: {total_db}")
    print(f"fixtures cacheados cargados: {total_cargados}")
    print(f"conflictos de fecha: {len(conflictos)}")
    print(f"competencias con huecos: {sum(1 for r in resumenes if r.anios_hueco)}")
    print(f"informes en: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
