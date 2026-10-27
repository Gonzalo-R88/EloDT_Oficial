#!/usr/bin/env bash
# Cierre del backfill: quedan sólo MEX1 + PR1C/VZ1A/EC1N (el resto ya está 100%
# cacheado). Reparte esas 4 ligas en 3 workers y al terminar corre
# load -> recompute -> validate para TODAS las ligas del "resto". Reanudable.
set -u
cd "$(dirname "$0")/.." || exit 1

export TM_DELAY_MIN="${TM_DELAY_MIN:-3}"
export TM_DELAY_MAX="${TM_DELAY_MAX:-6}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"
LOG_DIR="$DATA_DIR/logs"
mkdir -p "$LOG_DIR"

G1="GB2,GB1,IT2,FR2,FR1,PL1,BO1C,RU1,NO1,BO1A,A1,TDeC,PR1A,URU1"
G2="MLS1,BRA2,IT1,TR1,L2,NL1,CLPD,BE1,SE1,C1,COL1,TDeA,DK1,VZ1C"
G3="ES2,BRA1,ES1,JAP1,L1,PO1,SA1,UKR1,TS1,SC1,GR1,MEX1,PR1C,VZ1A,EC1N"
ALL="$G1,$G2,$G3"

F1="MEX1"
F2="PR1C,VZ1A"
F3="EC1N"

echo "[fase] cierre resto 2000-2026 (3 workers)"
python3 scraper_transfermarkt.py scrape --leagues "$F1" --from 2000 --to 2026 > "$LOG_DIR/fin1.log" 2>&1 & P1=$!
python3 scraper_transfermarkt.py scrape --leagues "$F2" --from 2000 --to 2026 > "$LOG_DIR/fin2.log" 2>&1 & P2=$!
python3 scraper_transfermarkt.py scrape --leagues "$F3" --from 2000 --to 2026 > "$LOG_DIR/fin3.log" 2>&1 & P3=$!
wait $P1 $P2 $P3

echo "[fase] load resto"
python3 scraper_transfermarkt.py load --leagues "$ALL" --from 2000 --to 2026 > "$LOG_DIR/resto_load.log" 2>&1

echo "[fase] recompute"
python3 scraper_transfermarkt.py recompute > "$LOG_DIR/resto_recompute.log" 2>&1

echo "[fase] validate"
python3 scripts/validate_elo.py --min-partidos 20 --top 20 > "$LOG_DIR/resto_validate.log" 2>&1

echo "[fase] DONE"
