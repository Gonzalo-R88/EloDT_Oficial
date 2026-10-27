#!/usr/bin/env bash
# Ejecuta el git de Windows sobre este repo.
#
# Motivo: el proyecto vive en `F:` montado en WSL sin soporte de chmod, así que el
# git de Linux no puede escribir `.git` ("chmod en .git/config.lock falló"). El git
# de Windows sí. Este repo tiene `core.autocrlf=false` para no convertir a CRLF.
#
# Uso: bash scripts/gitw.sh status | bash scripts/gitw.sh commit -am "mensaje"

set -euo pipefail

GIT_WIN="${GIT_WIN:-/mnt/c/Program Files/Git/cmd/git.exe}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -x "$GIT_WIN" ]]; then
    echo "No se encontró el git de Windows en: $GIT_WIN" >&2
    exit 1
fi

exec "$GIT_WIN" -C "$(wslpath -w "$PWD")" "$@"
