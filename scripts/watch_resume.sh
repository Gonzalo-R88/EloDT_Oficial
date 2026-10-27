#!/usr/bin/env bash
# Avisa cuando el scraping del "resto" se reanuda de verdad: espera el primer
# partido cacheado NUEVO (ignora lo ya existente con `tail -n0`) y dispara una
# notificación de Windows + deja una marca con la hora en data/logs/resume.txt.
#
# Uso:
#   tmux new -d -s aep-monitor 'bash scripts/watch_resume.sh'
set -u
cd "$(dirname "$0")/.." || exit 1

LOGS="data/logs/resto_w1.log data/logs/resto_w2.log data/logs/resto_w3.log"
MARK="data/logs/resume.txt"

tail -n0 -F $LOGS 2>/dev/null \
  | grep --line-buffered -m1 -E "partido [0-9]+ cacheado" > "$MARK"

{
  echo "Reanudado: $(date '+%Y-%m-%d %H:%M:%S')"
  cat "$MARK"
} > "$MARK.tmp" && mv "$MARK.tmp" "$MARK"

PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
if [ -x "$PS" ]; then
  "$PS" -NoProfile -Command \
    "[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; \
     [reflection.assembly]::loadwithpartialname('System.Drawing') | Out-Null; \
     \$n=New-Object System.Windows.Forms.NotifyIcon; \
     \$n.Icon=[System.Drawing.SystemIcons]::Information; \$n.Visible=\$true; \
     \$n.ShowBalloonTip(15000,'AEP - scraping','Transfermarkt desbloqueado: el backfill del resto se reanudo.','Info'); \
     Start-Sleep -Seconds 16; \$n.Dispose()" >/dev/null 2>&1
fi

echo "[watch] Reanudado $(date '+%Y-%m-%d %H:%M:%S')."
