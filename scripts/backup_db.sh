#!/usr/bin/env bash
# Respaldo de la base AEP en formato custom (restaurable con pg_restore).
#
# Uso:
#   bash scripts/backup_db.sh                # crea data/backups/aep_YYYYmmdd_HHMMSS.dump
#   bash scripts/backup_db.sh --verify       # además restaura en una base temporal y compara
#   BACKUP_DIR=/otra/ruta bash scripts/backup_db.sh
#
# Las credenciales salen de `.env` y nunca se imprimen.
#
# Nota de versiones: `pg_dump` no puede dumpear un servidor más nuevo que él. Si el
# Postgres del servidor corre en Windows (DB_HOST=winhost), el cliente nativo de WSL
# puede quedar viejo; en ese caso se usa el pg_dump.exe de Windows, que sí es de la
# misma versión del servidor. Ese ejecutable corre en Windows, así que se conecta a
# 127.0.0.1 (el servidor vive en esa misma máquina).

set -euo pipefail
umask 077

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

VERIFICAR=0
for arg in "$@"; do
    case "$arg" in
        --verify) VERIFICAR=1 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "Argumento desconocido: $arg" >&2; exit 2 ;;
    esac
done

if [[ ! -f .env ]]; then
    echo "No hay .env en $RAIZ" >&2
    exit 1
fi

# Carga las variables de conexión sin volcarlas por pantalla.
set -a
# shellcheck disable=SC1091
. ./.env
set +a

: "${DB_USER:?falta DB_USER}"
: "${DB_PASS:?falta DB_PASS}"
: "${DB_HOST:?falta DB_HOST}"
: "${DB_PORT:?falta DB_PORT}"
: "${DB_NAME:?falta DB_NAME}"

DESTINO="${BACKUP_DIR:-$RAIZ/data/backups}"
mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/aep_$(date +%Y%m%d_%H%M%S).dump"

export PGPASSWORD="$DB_PASS"

mayor_de() {
    # Extrae la versión mayor de la salida de `<pg_dump> --version`.
    "$1" --version 2>/dev/null | sed -nE 's/.* ([0-9]+)(\.[0-9]+)*.*/\1/p' | head -1
}

mayor_servidor="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -tAc 'show server_version_num' 2>/dev/null | cut -c1-2 | sed -E 's/^0*//')"
if [[ -z "$mayor_servidor" ]]; then
    echo "No se pudo consultar la versión del servidor (¿Postgres levantado en $DB_HOST?)." >&2
    exit 1
fi

# 1) pg_dump nativo, si es igual o más nuevo que el servidor.
DUMP_BIN=""
DUMP_HOST_ARGS=(-h "$DB_HOST" -p "$DB_PORT")
if command -v pg_dump >/dev/null 2>&1; then
    mayor_nativo="$(mayor_de pg_dump)"
    if [[ -n "$mayor_nativo" && "$mayor_nativo" -ge "$mayor_servidor" ]]; then
        DUMP_BIN="$(command -v pg_dump)"
    fi
fi

# 2) pg_dump.exe de Windows (misma máquina que el servidor), si hace falta.
WIN_ENV=()
WIN_PATH_PREFIX=""
if [[ -z "$DUMP_BIN" ]]; then
    while IFS= read -r candidato; do
        mayor="$(mayor_de "$candidato")"
        if [[ -n "$mayor" && "$mayor" -ge "$mayor_servidor" ]]; then
            DUMP_BIN="$candidato"
            WIN_PATH_PREFIX="$(dirname "$candidato")"
            break
        fi
    done < <(ls -1d /mnt/c/Program\ Files/PostgreSQL/*/bin/pg_dump.exe 2>/dev/null | sort -V -r)
    DUMP_HOST_ARGS=(-h 127.0.0.1 -p "$DB_PORT")
fi

if [[ -z "$DUMP_BIN" ]]; then
    echo "No hay un pg_dump >= $mayor_servidor (servidor $mayor_servidor)." >&2
    echo "Opciones: instalar postgresql-client-$mayor_servidor o usar el pg_dump.exe de Windows." >&2
    exit 1
fi

echo "Respaldo de $DB_NAME (versión de servidor $mayor_servidor) con $DUMP_BIN"

# Los .exe de Windows no entienden rutas /mnt/...: hay que pasarlas como F:\...
ruta_para_cliente() {
    local bin="$1" ruta="$2"
    if [[ "$bin" == *.exe ]]; then
        wslpath -w "$ruta"
    else
        printf '%s' "$ruta"
    fi
}

if [[ -n "$WIN_PATH_PREFIX" ]]; then
    # WSL no propaga variables de entorno a los .exe sin WSLENV; `/p` traduce el PATH
    # para que pg_dump.exe se encuentre a sí mismo (si no, avisa "could not find a pg_dump.exe").
    PATH="$WIN_PATH_PREFIX:$PATH" WSLENV="PATH/p:PGPASSWORD" \
        "$DUMP_BIN" "${DUMP_HOST_ARGS[@]}" -U "$DB_USER" -d "$DB_NAME" \
        --format=custom --compress=6 --no-password \
        --file="$(ruta_para_cliente "$DUMP_BIN" "$ARCHIVO")"
else
    "$DUMP_BIN" "${DUMP_HOST_ARGS[@]}" -U "$DB_USER" -d "$DB_NAME" \
        --format=custom --compress=6 --no-password --file="$ARCHIVO"
fi

if [[ ! -s "$ARCHIVO" ]]; then
    echo "El respaldo quedó vacío: $ARCHIVO" >&2
    exit 1
fi
if [[ "$(head -c 5 "$ARCHIVO")" != "PGDMP" ]]; then
    echo "El archivo no tiene cabecera de formato custom de PostgreSQL: $ARCHIVO" >&2
    exit 1
fi

echo "OK: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"

if [[ "$VERIFICAR" -eq 1 ]]; then
    TEMPORAL="${DB_NAME}_verif_$(date +%Y%m%d_%H%M%S)"
    RESTORE_BIN="$DUMP_BIN"
    # pg_restore debe ser igual o más nuevo que el dump.
    if [[ "$(mayor_de pg_restore 2>/dev/null || echo 0)" -ge "$mayor_servidor" ]]; then
        RESTORE_BIN="$(command -v pg_restore)"
    else
        RESTORE_BIN="$(dirname "$DUMP_BIN")/pg_restore.exe"
    fi

    echo "Verificando en la base temporal $TEMPORAL..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -q \
        -c "CREATE DATABASE \"$TEMPORAL\"" >/dev/null

    restaurar() {
        if [[ "$RESTORE_BIN" == *.exe ]]; then
            PATH="$(dirname "$RESTORE_BIN"):$PATH" WSLENV="PATH/p:PGPASSWORD" \
                "$RESTORE_BIN" -h 127.0.0.1 -p "$DB_PORT" -U "$DB_USER" -d "$TEMPORAL" \
                --no-password --no-owner "$(ruta_para_cliente "$RESTORE_BIN" "$ARCHIVO")"
        else
            "$RESTORE_BIN" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEMPORAL" \
                --no-password --no-owner "$ARCHIVO"
        fi
    }

    if ! restaurar >/dev/null 2>&1; then
        echo "Falló la restauración; se deja la base $TEMPORAL para inspección." >&2
        exit 1
    fi

    ORIGEN="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc 'select count(*) from partidos_dt')"
    COPIA="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEMPORAL" -tAc 'select count(*) from partidos_dt')"
    echo "partidos_dt -> original: $ORIGEN | restaurado: $COPIA"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -q \
        -c "DROP DATABASE \"$TEMPORAL\"" >/dev/null

    if [[ "$ORIGEN" != "$COPIA" ]]; then
        echo "El conteo no coincide: respaldo inconsistente." >&2
        exit 1
    fi
    echo "Verificación OK: el respaldo se restaura y conserva $COPIA partidos."
fi
