#!/usr/bin/env bash
# Backfill de Argentina (T0.4): huecos de 2017-2020 y la Primera desde 2025.
#
#   AR1N  2017-2020  Ligas 2016/17 a 2019/20 (temporadas agosto-junio)
#   ARG2  2017-2020  Primera Nacional
#   ARG1  2025-2026  Torneo Apertura (la Primera desde 2025; TM cierra AR1N en 23/24)
#   ARGC  2025-2026  Torneo Clausura
#
# 3 workers con el ritmo anti-WAF documentado (~14 req/min). Es reanudable: si se
# corta, relanzar el mismo comando saltea lo ya cacheado. Al terminar corre
# load -> recompute -> validate.
#
# Uso:
#   tmux new -d -s aep-arg 'bash scripts/backfill_argentina.sh'
#   tmux capture-pane -t aep-arg -p | tail -20
set -u
cd "$(dirname "$0")/.." || exit 1

# No subir el ritmo: a ~0,9 req/s la IP terminó baneada (ver AGENTS.md).
export TM_DELAY_MIN="${TM_DELAY_MIN:-8}"
export TM_DELAY_MAX="${TM_DELAY_MAX:-18}"

export DATA_DIR="${DATA_DIR:-$PWD/data}"
LOG_DIR="$DATA_DIR/logs"
mkdir -p "$LOG_DIR"

echo "[fase] scraping AR1N 2017-2020"
python3 scraper_transfermarkt.py scrape --competition AR1N --from 2017 --to 2020 \
    > "$LOG_DIR"/arg_w1.log 2>&1 & P1=$!

echo "[fase] scraping ARG2 2017-2020"
python3 scraper_transfermarkt.py scrape --competition ARG2 --from 2017 --to 2020 \
    > "$LOG_DIR"/arg_w2.log 2>&1 & P2=$!

echo "[fase] scraping ARG1/ARGC 2025-2026"
python3 scraper_transfermarkt.py scrape --leagues ARG1,ARGC --from 2025 --to 2026 \
    > "$LOG_DIR"/arg_w3.log 2>&1 & P3=$!

wait $P1 $P2 $P3

echo "[fase] load AR1N/ARG2 2017-2020"
python3 scraper_transfermarkt.py load --leagues AR1N,ARG2 --from 2017 --to 2020 \
    > "$LOG_DIR"/arg_load1.log 2>&1

echo "[fase] load ARG1/ARGC 2025-2026"
python3 scraper_transfermarkt.py load --leagues ARG1,ARGC --from 2025 --to 2026 \
    > "$LOG_DIR"/arg_load2.log 2>&1

echo "[fase] recompute"
python3 scraper_transfermarkt.py recompute > "$LOG_DIR"/arg_recompute.log 2>&1

echo "[fase] validate"
python3 scripts/validate_elo.py --min-partidos 20 --top 20 > "$LOG_DIR"/arg_validate.log 2>&1

echo "[fase] audit"
python3 scripts/audit_data.py > "$LOG_DIR"/arg_audit.log 2>&1

echo "[fase] DONE"
