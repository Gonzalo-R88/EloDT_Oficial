"""Modelos declarativos ORM (SQLAlchemy 2.0) del proyecto AEP.

Esquema preparado para multi-liga/multi-competencia: las entidades guardan su
identificador estable de Transfermarkt (`transfermarkt_id`) y los partidos su
`transfermarkt_match_id`, lo que permite idempotencia robusta y resolución de
entidades sin depender del nombre.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Clase base para todos los modelos ORM."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Coach(Base):
    """Entrenador (Director Técnico)."""

    __tablename__ = "entrenadores"

    dt_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transfermarkt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    nacionalidad: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fecha_nacimiento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    elo_actual: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("1000.00"), nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("transfermarkt_id", name="uq_entrenadores_tm_id"),
    )


class Competition(Base):
    """Competencia con su coeficiente de jerarquía."""

    __tablename__ = "competencias"

    competencia_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    transfermarkt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    pais: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    nivel: Mapped[str] = mapped_column(String(10), nullable=False)
    coeficiente: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("nivel IN ('S', 'A', 'B', 'C')", name="check_nivel_competencia"),
        CheckConstraint(
            "tipo IS NULL OR tipo IN ('liga', 'copa', 'internacional', 'selecciones')",
            name="check_tipo_competencia",
        ),
        UniqueConstraint("codigo", name="uq_competencias_codigo"),
    )


class Club(Base):
    """Club de fútbol."""

    __tablename__ = "clubes"

    club_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transfermarkt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    pais: Mapped[Optional[str]] = mapped_column(String(50), default="Argentina")
    # "club" o "seleccion": una selección nacional no tiene liga doméstica y sus DTs
    # no compiten en el ranking de clubes.
    tipo: Mapped[str] = mapped_column(String(10), default="club", nullable=False)

    __table_args__ = (
        UniqueConstraint("transfermarkt_id", name="uq_clubes_tm_id"),
        CheckConstraint("tipo IN ('club', 'seleccion')", name="check_tipo_club"),
    )


class SnapshotElo(Base):
    """Estado del ELO de cada DT al cierre de una semana (inmutable por versión)."""

    __tablename__ = "snapshots_elo"

    semana_fin: Mapped[date] = mapped_column(Date, primary_key=True)
    dt_id: Mapped[int] = mapped_column(ForeignKey("entrenadores.dt_id"), primary_key=True)
    modelo_version: Mapped[str] = mapped_column(String(20), primary_key=True)
    elo: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    rank_global: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pj_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    publicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    etiqueta: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        Index("idx_snapshots_rank", "semana_fin", "rank_global"),
        Index("idx_snapshots_dt", "dt_id", "semana_fin"),
    )


class EjecucionPipeline(Base):
    """Registro de cada corrida del pipeline semanal (para auditar y no repetir)."""

    __tablename__ = "ejecuciones_pipeline"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    semana_fin: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    iniciado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    terminado_en: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    resumen: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class MatchCoach(Base):
    """Registro histórico de partidos y evolución del ELO de los DTs."""

    __tablename__ = "partidos_dt"

    partido_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transfermarkt_match_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    competencia_id: Mapped[int] = mapped_column(
        ForeignKey("competencias.competencia_id"), nullable=False
    )

    # Entrenador y club local
    dt_local_id: Mapped[int] = mapped_column(ForeignKey("entrenadores.dt_id"), nullable=False)
    club_local_id: Mapped[int] = mapped_column(ForeignKey("clubes.club_id"), nullable=False)
    elo_local_previo: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    elo_local_nuevo: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    goles_local: Mapped[int] = mapped_column(Integer, nullable=False)

    # Entrenador y club visitante
    dt_visita_id: Mapped[int] = mapped_column(ForeignKey("entrenadores.dt_id"), nullable=False)
    club_visita_id: Mapped[int] = mapped_column(ForeignKey("clubes.club_id"), nullable=False)
    elo_visita_previo: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    elo_visita_nuevo: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    goles_visita: Mapped[int] = mapped_column(Integer, nullable=False)

    # Métricas de lectura de juego
    marcador_pre_cambios_local: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    marcador_pre_cambios_visita: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    impacto_banco_local: Mapped[int] = mapped_column(Integer, default=0)
    impacto_banco_visita: Mapped[int] = mapped_column(Integer, default=0)
    factor_k: Mapped[int] = mapped_column(Integer, default=20)

    __table_args__ = (
        UniqueConstraint("fecha", "competencia_id", "dt_local_id", "dt_visita_id", name="uq_partido_fecha_dts"),
        UniqueConstraint("transfermarkt_match_id", name="uq_partidos_tm_match_id"),
        CheckConstraint("factor_k IN (20, 30, 40)", name="check_factor_k"),
        CheckConstraint("impacto_banco_local IN (-1, 0, 1)", name="check_impacto_local"),
        CheckConstraint("impacto_banco_visita IN (-1, 0, 1)", name="check_impacto_visita"),
        CheckConstraint("goles_local >= 0", name="check_goles_local"),
        CheckConstraint("goles_visita >= 0", name="check_goles_visita"),
    )
