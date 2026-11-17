#!/usr/bin/env bash
# Puerta de entrada desde Windows (Programador de tareas y n8n).
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

# En la corrida completa también se publica la fecha FIFA si hay una ventana cerrada
# pendiente. El comando decide solo: fuera de una fecha FIFA sale en segundos sin tocar
# la red (`weekly_run.publicar_selecciones`).
if [ "${1:-}" = "all" ]; then
    shift
    set -- all --selecciones "$@"
fi

# `winhost` (el Postgres de Windows) vive en /etc/hosts, pero WSL regenera ese archivo
# cada vez que arranca la VM y se pierde la línea. El `update_winhost` de ~/.bashrc lo
# arregla sólo en terminales interactivas, y estas corridas no lo son: sin esto, la
# tarea falla con "could not translate host name". En WSL2 el gateway por defecto ES la
# IP del host de Windows, así que sirve de respaldo sin necesitar permisos.
if ! getent hosts winhost >/dev/null 2>&1; then
    gateway="$(ip route show default 2>/dev/null | awk '{print $3; exit}')"
    if [ -n "${gateway:-}" ]; then
        echo "aviso: winhost no resuelve; se usa $gateway (host de Windows) como DB_HOST" >&2
        export DB_HOST="$gateway"
    else
        echo "error: no se pudo resolver winhost ni obtener el gateway" >&2
        exit 1
    fi
fi

exec python3 -u scripts/weekly_run.py "$@"
