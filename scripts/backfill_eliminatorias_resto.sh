#!/usr/bin/env bash
# Cierra el backfill de eliminatorias: lo que faltó por el corte del 31-oct.
#
# El 30-oct quedaron cacheadas 7.458 reportes de eliminatorias (WMQ1-4, WMQ6, EMQ,
# AFCQ, GCQU). El worker que tenía que seguir con `POWM` se cayó porque ese código no
# estaba en el catálogo, así que nunca se bajaron la Nations League ni las
# eliminatorias de la Copa Asiática. Esto completa esos códigos y después carga TODO
# (lo nuevo y lo ya cacheado), recalcula y valida.
#
# Uso:
#   tmux new -d -s aep-eli2 'bash scripts/backfill_eliminatorias_resto.sh'
set -u
cd "$(dirname "$0")/.." || exit 1

export TM_DELAY_MIN="${TM_DELAY_MIN:-8}"
export TM_DELAY_MAX="${TM_DELAY_MAX:-18}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"
LOG_DIR="$DATA_DIR/logs"
mkdir -p "$LOG_DIR"

PENDIENTES="POWM,ACQU,UNLA,UNLB,UNLC,UNLD,UNFI"
# Todas las de selecciones que hay que cargar (eliminatorias + Nations League).
TODAS="WMQ1,WMQ2,WMQ3,WMQ4,WMQ6,POWM,EMQ,AFCQ,ACQU,GCQU,UNLA,UNLB,UNLC,UNLD,UNFI"

echo "[fase] scraping lo que faltaba ($PENDIENTES)"
python3 -u scripts/scrape_ediciones.py --codes "$PENDIENTES" --from 2000 --to 2026 \
    > "$LOG_DIR"/eli2_scrape.log 2>&1

echo "[fase] load"
python3 scraper_transfermarkt.py load --leagues "$TODAS" --from 2000 --to 2026 \
    > "$LOG_DIR"/eli2_load.log 2>&1

echo "[fase] recompute"
python3 scraper_transfermarkt.py recompute > "$LOG_DIR"/eli2_recompute.log 2>&1

echo "[fase] validate"
python3 scripts/validate_elo.py --min-partidos 20 --top 20 > "$LOG_DIR"/eli2_validate.log 2>&1

echo "[fase] audit"
python3 scripts/audit_data.py > "$LOG_DIR"/eli2_audit.log 2>&1

echo "[fase] DONE"
