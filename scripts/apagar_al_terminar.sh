#!/usr/bin/env bash
# Espera a que termine la actualización semanal y APAGA la PC siempre.
#
# Si la corrida falló, deja el motivo escrito en data/logs/shutdown.log antes de
# apagar (así mañana se sabe qué pasó sin tener que buscarlo).
#
# Se lanza con nohup para que sobreviva a la sesión del agente:
#   nohup bash scripts/apagar_al_terminar.sh > /dev/null 2>&1 &
set -u
cd "$(dirname "$0")/.." || exit 1

LOG="data/logs/shutdown.log"
mkdir -p data/logs
echo "$(date '+%F %T') esperando el update..." >> "$LOG"

while pgrep -f "[w]eekly_run.py update" >/dev/null; do
    sleep 60
done
sleep 20  # margen para que termine de escribir el log

codigo=$(grep -o "exit=[0-9]*" data/logs/weekly_update.log 2>/dev/null | tail -1)
codigo=${codigo:-exit=desconocido}
echo "$(date '+%F %T') update terminó: $codigo" >> "$LOG"

if [ "$codigo" != "exit=0" ]; then
    {
        echo "=== FALLÓ: motivo ==="
        grep -E "error \(código|Traceback|Exception|^[A-Za-z]*Error" \
            data/logs/weekly_update.log 2>/dev/null | tail -6
        echo "--- últimas líneas del log (sin avisos de WAF) ---"
        grep -v "Challenge AWS WAF" data/logs/weekly_update.log 2>/dev/null | tail -12
    } >> "$LOG" 2>&1
fi

echo "$(date '+%F %T') apagando en 5 minutos" >> "$LOG"
cmd.exe /c shutdown /s /t 300 >> "$LOG" 2>&1
