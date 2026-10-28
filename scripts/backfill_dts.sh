#!/usr/bin/env bash
# Recupera partidos descartados por falta de DT (T0.9 parcial, versión sin imputar).
#
# Muchas páginas viejas SÍ tienen los entrenadores, pero en otro layout HTML; el
# parser arreglado el 2026-10-28 los lee (89 % de acierto en la muestra). Este script
# re-descarga los reportes de los fixtures cacheados que no están en la base y luego
# recarga sólo los nuevos (el fast-path de `persist_matches` saltea los ya cargados).
#
# 3 workers al ritmo anti-WAF (~14 req/min). Reanudable: los reportes que ya tienen
# los dos DTs dejan de ser "faltantes" en la próxima corrida.
#
# Uso:
#   tmux new -d -s aep-dts 'bash scripts/backfill_dts.sh'
#   bash scripts/backfill_dts.sh 2015 2026        # otro rango
set -u
cd "$(dirname "$0")/.." || exit 1

DESDE="${1:-2012}"
HASTA="${2:-2026}"

export TM_DELAY_MIN="${TM_DELAY_MIN:-8}"
export TM_DELAY_MAX="${TM_DELAY_MAX:-18}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"
LOG_DIR="$DATA_DIR/logs"
WORK_DIR="$DATA_DIR/work"
mkdir -p "$LOG_DIR" "$WORK_DIR"

LISTA="$WORK_DIR/refetch_${DESDE}_${HASTA}.json"

echo "[fase] listar faltantes $DESDE-$HASTA"
python3 -u scripts/refetch_reportes.py --listar-faltantes "$LISTA" \
    --desde "$DESDE" --hasta "$HASTA" > "$LOG_DIR"/dts_list.log 2>&1
cat "$LOG_DIR"/dts_list.log

echo "[fase] re-descarga con 3 workers"
for i in 1 2 3; do
    python3 -u scripts/refetch_reportes.py --ids-file "$LISTA" --shard "$i/3" --apply \
        > "$LOG_DIR"/dts_w"$i".log 2>&1 &
done
wait

echo "[fase] load $DESDE-$HASTA"
python3 scraper_transfermarkt.py load --all-competitions --from "$DESDE" --to "$HASTA" \
    > "$LOG_DIR"/dts_load.log 2>&1

echo "[fase] recompute"
python3 scraper_transfermarkt.py recompute > "$LOG_DIR"/dts_recompute.log 2>&1

echo "[fase] validate"
python3 scripts/validate_elo.py --min-partidos 20 --top 20 > "$LOG_DIR"/dts_validate.log 2>&1

echo "[fase] audit"
python3 scripts/audit_data.py > "$LOG_DIR"/dts_audit.log 2>&1

echo "[fase] DONE"
