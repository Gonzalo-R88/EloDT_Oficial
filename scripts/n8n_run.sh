#!/usr/bin/env bash
# Puerta de entrada para n8n (que corre en Windows).
#
# n8n ejecuta, por ejemplo:
#   wsl.exe -d Ubuntu-24.04 bash /mnt/f/ProyectoDT/scripts/n8n_run.sh all --json
#
# Se usa un wrapper en vez de `bash -lc "cd ... && python3 ..."` porque cmd.exe
# destroza las comillas anidadas al pasar de Windows a WSL.
set -u
cd "$(dirname "$0")/.." || exit 1

if [ "$#" -eq 0 ]; then
    echo "uso: n8n_run.sh <subcomando> [opciones] (se pasan a scripts/weekly_run.py)" >&2
    exit 2
fi

exec python3 -u scripts/weekly_run.py "$@"
