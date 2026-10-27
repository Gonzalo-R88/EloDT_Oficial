#!/usr/bin/env bash
# Watchdog del backfill: si la sesión tmux `aep-resto` no está, la relanza.
# Pensado para que lo dispare el Task Scheduler de Windows (al iniciar sesión y
# cada 2 h), de modo que el scraper se recupere solo tras un reinicio de Windows
# (que apaga WSL). Escribe un log en $DATA_DIR/logs/watchdog.log.
set -u
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
cd "$(dirname "$0")/.." || exit 1
export DATA_DIR="${DATA_DIR:-$PWD/data}"
mkdir -p "$DATA_DIR/logs"
WLOG="$DATA_DIR/logs/watchdog.log"
ts="$(date '+%F %T')"

if tmux has-session -t aep-resto 2>/dev/null; then
    echo "$ts - OK: aep-resto corriendo" >> "$WLOG"
else
    echo "$ts - CAIDO: relanzando aep-resto" >> "$WLOG"
    tmux new -d -s aep-resto "bash '$PWD/scripts/backfill_resto.sh'"
fi
