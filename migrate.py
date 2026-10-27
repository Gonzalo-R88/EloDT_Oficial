"""Aplica las migraciones SQL de `migrations/` en orden (000 → 001 → 002).

Las migraciones son idempotentes, por lo que este runner puede ejecutarse
varias veces sin efectos colaterales. No usa Alembic a propósito: los archivos
`.sql` son la fuente de verdad del esquema de la base.

Ejemplos:
    python migrate.py
    python migrate.py --create-db
    python migrate.py --reset          # borra tablas y recrea (solo dev)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlalchemy import create_engine, text

from db import build_database_url, engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Orden de borrado respetando dependencias (hijas primero).
RESET_TABLES = ("partidos_dt", "clubes", "competencias", "entrenadores")


def migration_files() -> list[Path]:
    """Devuelve los archivos .sql ordenados por nombre (000, 001, ...)."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def reset_schema() -> None:
    """Elimina las tablas del proyecto para recrearlas desde cero.

    Destructivo: pensado para entornos de desarrollo/backtesting. NO usar en
    producción con datos cargados.
    """
    with engine.begin() as conn:
        for table in RESET_TABLES:
            conn.execute(text(f'DROP TABLE IF EXISTS {table} CASCADE'))
    logger.warning("Esquema reseteado: %s eliminadas.", ", ".join(RESET_TABLES))


def create_database_if_missing() -> None:
    """Crea la base de datos objetivo si no existe (conecta a `postgres`)."""
    url = build_database_url()
    target = url.database
    admin_url = url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target}
            ).scalar()
            if exists:
                logger.info("La base '%s' ya existe.", target)
                return
            conn.execute(text(f'CREATE DATABASE "{target}"'))
            logger.info("Base '%s' creada.", target)
    finally:
        admin_engine.dispose()


def apply_migrations() -> list[str]:
    """Ejecuta cada migración dentro de una transacción. Devuelve los nombres."""
    files = migration_files()
    if not files:
        raise SystemExit("No se encontraron migraciones en migrations/.")

    with engine.begin() as conn:
        for path in files:
            logger.info("Aplicando %s ...", path.name)
            conn.execute(text(path.read_text(encoding="utf-8")))

    applied = [path.name for path in files]
    logger.info("Migraciones aplicadas: %s", ", ".join(applied))
    return applied


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Aplica las migraciones SQL del proyecto AEP.")
    parser.add_argument(
        "--create-db",
        action="store_true",
        help="Crea la base de datos objetivo si no existe antes de migrar.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Elimina las tablas del proyecto antes de migrar (destructivo, solo dev).",
    )
    args = parser.parse_args()

    if args.create_db:
        create_database_if_missing()

    if args.reset:
        reset_schema()

    applied = apply_migrations()
    print(f"[migrate] {len(applied)} migraciones aplicadas: {', '.join(applied)}")


if __name__ == "__main__":
    main()
