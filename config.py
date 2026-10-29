"""Configuración central del proyecto AEP (Analítica de Entrenadores & Performance).

Todas las credenciales y parámetros de operación se leen de variables de entorno
(definidas en el archivo .env) evitando valores sensibles en el repositorio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de la aplicación."""

    # Base de datos
    db_user: str
    db_pass: str
    db_host: str
    db_port: int
    db_name: str

    # Scraping / almacenamiento
    data_dir: Path
    transfermarkt_domain: str
    request_delay_min: float
    request_delay_max: float
    max_retries: int
    request_timeout: int
    blocked_wait: float
    blocked_retries: int
    impersonate: str
    waf_solver: bool
    waf_headless: bool
    waf_wait_seconds: float
    max_waf_solves: int

    # Reglas de publicación (ver `publicacion.py`)
    ranking_min_pj: int
    provisorio_pj: int
    interino_min_pj: int
    activo_dias: int
    cobertura_min: float
    cobertura_anios: int
    cobertura_json: Path


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "si", "sí")


def load_settings() -> Settings:
    """Construye la configuración a partir del entorno."""
    data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).expanduser()
    return Settings(
        db_user=os.getenv("DB_USER", "postgres"),
        db_pass=os.getenv("DB_PASS", ""),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=_get_int("DB_PORT", 5432),
        db_name=os.getenv("DB_NAME", "aep_football_analytics"),
        data_dir=data_dir,
        transfermarkt_domain=os.getenv("TM_DOMAIN", "www.transfermarkt.com"),
        request_delay_min=_get_float("TM_DELAY_MIN", 6.0),
        request_delay_max=_get_float("TM_DELAY_MAX", 12.0),
        max_retries=_get_int("TM_MAX_RETRIES", 4),
        request_timeout=_get_int("TM_TIMEOUT", 30),
        blocked_wait=_get_float("TM_BLOCKED_WAIT", 1800.0),
        blocked_retries=_get_int("TM_BLOCKED_RETRIES", 192),
        impersonate=os.getenv("TM_IMPERSONATE", "chrome124"),
        waf_solver=_get_bool("TM_WAF_SOLVER", True),
        waf_headless=_get_bool("TM_WAF_HEADLESS", True),
        waf_wait_seconds=_get_float("TM_WAF_WAIT", 15.0),
        max_waf_solves=_get_int("TM_WAF_SOLVES", 5),
        ranking_min_pj=_get_int("RANKING_MIN_PJ", 15),
        provisorio_pj=_get_int("PROVISORIO_PJ", 30),
        interino_min_pj=_get_int("INTERINO_MIN_PJ", 5),
        activo_dias=_get_int("ACTIVO_DIAS", 365),
        cobertura_min=_get_float("COBERTURA_MIN", 0.90),
        cobertura_anios=_get_int("COBERTURA_ANIOS", 3),
        cobertura_json=Path(
            os.getenv("COBERTURA_JSON", str(data_dir / "audit" / "cobertura.json"))
        ),
    )


settings = load_settings()
