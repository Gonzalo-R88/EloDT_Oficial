#!/usr/bin/env bash
# Backfill de eliminatorias de selecciones + UEFA Nations League.
#
# Mismo mecanismo que `backfill_selecciones.sh`: `scrape_ediciones.py` recorre los
# `saison_id` (las eliminatorias de un Mundial se juegan en 3-4 años y TM las agrupa
# bajo un sólo `saison_id`, que además no sigue una regla fija entre confederaciones),
# descarta la edición repetida que devuelve TM y cachea cada ciclo bajo el año de su
# primer partido.
#
# Volumen estimado: ~9.300 partidos (~12 h a 13 req/min). Reanudable: si se corta,
# relanzar el mismo comando saltea lo cacheado. Al terminar: load -> recompute ->
# validate -> audit.
#
# Uso:
#   tmux new -d -s aep-eli 'bash scripts/backfill_eliminatorias.sh'
set -u
cd "$(dirname "$0")/.." || exit 1

export TM_DELAY_MIN="${TM_DELAY_MIN:-8}"
export TM_DELAY_MAX="${TM_DELAY_MAX:-18}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"
LOG_DIR="$DATA_DIR/logs"
mkdir -p "$LOG_DIR"

# Reparto por volumen estimado (partidos por ciclo × ciclos).
W1="WMQ4,WMQ6,POWM,ACQU,UNLA,UNLB,UNLC,UNLD,UNFI"
W2="EMQ,WMQ3,GCQU"
W3="WMQ1,WMQ2,AFCQ"
TODOS="$W1,$W2,$W3"

echo "[fase] scraping eliminatorias + Nations League (3 workers)"
python3 -u scripts/scrape_ediciones.py --codes "$W1" --from 2000 --to 2026 \
    > "$LOG_DIR"/eli_w1.log 2>&1 & P1=$!
python3 -u scripts/scrape_ediciones.py --codes "$W2" --from 2000 --to 2026 \
    > "$LOG_DIR"/eli_w2.log 2>&1 & P2=$!
python3 -u scripts/scrape_ediciones.py --codes "$W3" --from 2000 --to 2026 \
    > "$LOG_DIR"/eli_w3.log 2>&1 & P3=$!
wait $P1 $P2 $P3

echo "[fase] load"
python3 scraper_transfermarkt.py load --leagues "$TODOS" --from 2000 --to 2026 \
    > "$LOG_DIR"/eli_load.log 2>&1

echo "[fase] recompute"
python3 scraper_transfermarkt.py recompute > "$LOG_DIR"/eli_recompute.log 2>&1

echo "[fase] validate"
python3 scripts/validate_elo.py --min-partidos 20 --top 20 > "$LOG_DIR"/eli_validate.log 2>&1

echo "[fase] audit"
python3 scripts/audit_data.py > "$LOG_DIR"/eli_audit.log 2>&1

echo "[fase] DONE"
