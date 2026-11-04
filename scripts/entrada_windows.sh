#!/usr/bin/env bash
# Puerta de entrada desde Windows (Programador de tareas).
#
# El .bat de la tarea ejecuta:
#   wsl.exe -d Ubuntu-24.04 -u gonzalo bash /mnt/f/ProyectoDT/scripts/entrada_windows.sh all --skip-if-done-this-week --json
#
# Se usa un wrapper en vez de `bash -lc "cd ... && python3 ..."` porque cmd.exe
# destroza las comillas anidadas al pasar de Windows a WSL.
set -u
cd "$(dirname "$0")/.." || exit 1

if [ "$#" -eq 0 ]; then
    echo "uso: entrada_windows.sh <subcomando> [opciones] (se pasan a scripts/weekly_run.py)" >&2
    exit 2
fi

exec python3 -u scripts/weekly_run.py "$@"
