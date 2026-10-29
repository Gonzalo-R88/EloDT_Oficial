#!/usr/bin/env bash
# Backfill de selecciones nacionales (torneos): Mundial, Copa América, Eurocopa,
# Copa Africana, Copa Asiática y Copa Oro.
#
# El `saison_id` de estas competencias en TM no sigue una regla fija, así que se
# recorren todos y se cachea cada edición distinta bajo el año de su primer partido
# (`scripts/scrape_ediciones.py`). Después: load -> recompute -> validate -> audit.
#
# Uso:
#   tmux new -d -s aep-sel 'bash scripts/backfill_selecciones.sh'
set -u
cd "$(dirname "$0")/.." || exit 1

export TM_DELAY_MIN="${TM_DELAY_MIN:-8}"
export TM_DELAY_MAX="${TM_DELAY_MAX:-18}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"
LOG_DIR="$DATA_DIR/logs"
mkdir -p "$LOG_DIR"

CODES="${CODES:-FIWC,COPA,EURO,AFCN,AFAC,GOCU}"

echo "[fase] scraping ediciones en 3 workers ($CODES)"
python3 -u scripts/scrape_ediciones.py --codes FIWC,COPA --from 2000 --to 2026 \
    > "$LOG_DIR"/sel_w1.log 2>&1 & P1=$!
python3 -u scripts/scrape_ediciones.py --codes EURO,AFCN --from 2000 --to 2026 \
    > "$LOG_DIR"/sel_w2.log 2>&1 & P2=$!
python3 -u scripts/scrape_ediciones.py --codes AFAC,GOCU --from 2000 --to 2026 \
    > "$LOG_DIR"/sel_w3.log 2>&1 & P3=$!
wait $P1 $P2 $P3
cat "$LOG_DIR"/sel_w1.log "$LOG_DIR"/sel_w2.log "$LOG_DIR"/sel_w3.log > "$LOG_DIR"/sel_scrape.log

echo "[fase] load"
python3 scraper_transfermarkt.py load --leagues "$CODES" --from 2000 --to 2026 \
    > "$LOG_DIR"/sel_load.log 2>&1

echo "[fase] recompute"
python3 scraper_transfermarkt.py recompute > "$LOG_DIR"/sel_recompute.log 2>&1

echo "[fase] validate"
python3 scripts/validate_elo.py --min-partidos 20 --top 20 > "$LOG_DIR"/sel_validate.log 2>&1

echo "[fase] audit"
python3 scripts/audit_data.py > "$LOG_DIR"/sel_audit.log 2>&1

echo "[fase] DONE"
