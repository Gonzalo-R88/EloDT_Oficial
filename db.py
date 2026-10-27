"""Configuración del engine y fábrica de sesiones de SQLAlchemy."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from config import settings


def build_database_url() -> URL:
    """Construye la URL de conexión de forma segura (escapa caracteres especiales)."""
    return URL.create(
        drivername="postgresql",
        username=settings.db_user,
        password=settings.db_pass or None,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )


engine = create_engine(
    build_database_url(),
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
    future=True,
)

SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_session() -> Session:
    """Devuelve una nueva sesión de base de datos."""
    return SessionFactory()
