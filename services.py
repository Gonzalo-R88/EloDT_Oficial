"""Servicios de dominio: procesamiento de partidos y recálculo del ELO."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from db import SessionFactory
from elo import (
    INITIAL_ELO,
    VALID_BENCH_IMPACT,
    VALID_FACTOR_K,
    EloParams,
    compute_elo_delta,
    match_calibracion,
)
from models import Coach, Competition, MatchCoach

logger = logging.getLogger(__name__)

STATUS_PROCESSED = "procesado"
STATUS_DUPLICATE = "duplicado"


def _normalize_date(fecha: Union[date, str]) -> date:
    if isinstance(fecha, str):
        return datetime.strptime(fecha, "%Y-%m-%d").date()
    return fecha


def _dias_desde(fecha: date, anterior: Optional[date]) -> Optional[int]:
    """Días entre dos partidos del mismo DT (None si es el primero)."""
    return (fecha - anterior).days if anterior is not None else None


def _validate_bench_impact(value: int, field: str) -> None:
    if value not in VALID_BENCH_IMPACT:
        raise ValueError(
            f"{field} inválido: {value}. Valores permitidos: {VALID_BENCH_IMPACT}"
        )


def process_match_elo(
    dt_local_id: int,
    dt_visita_id: int,
    goles_local: int,
    goles_visita: int,
    competencia_id: int,
    fecha: Union[date, str],
    club_local_id: Optional[int] = None,
    club_visita_id: Optional[int] = None,
    factor_k: int = 20,
    marcador_pre_cambios_local: Optional[str] = None,
    marcador_pre_cambios_visita: Optional[str] = None,
    impacto_banco_local: int = 0,
    impacto_banco_visita: int = 0,
    apply_mov: bool = True,
    transfermarkt_match_id: Optional[int] = None,
    session: Optional[Session] = None,
) -> str:
    """Procesa un partido y actualiza el ELO de ambos DTs (idempotente).

    Devuelve `STATUS_PROCESSED` si se registró, o `STATUS_DUPLICATE` si el
    partido ya había sido procesado (por `transfermarkt_match_id` o por la
    combinación fecha/competencia/DTs).
    """
    if factor_k not in VALID_FACTOR_K:
        raise ValueError(f"factor_k inválido: {factor_k}. Permitidos: {VALID_FACTOR_K}")
    _validate_bench_impact(impacto_banco_local, "impacto_banco_local")
    _validate_bench_impact(impacto_banco_visita, "impacto_banco_visita")
    if goles_local < 0 or goles_visita < 0:
        raise ValueError("Los goles no pueden ser negativos.")

    match_date = _normalize_date(fecha)

    should_close_session = session is None
    db_session: Session = session if session is not None else SessionFactory()

    try:
        # A. Control de idempotencia (EXISTS evita materializar filas)
        if transfermarkt_match_id is not None:
            already_exists = db_session.execute(
                select(
                    exists().where(
                        MatchCoach.transfermarkt_match_id == transfermarkt_match_id
                    )
                )
            ).scalar()
            if already_exists:
                logger.info(
                    "Partido Transfermarkt %s ya procesado; se omite.", transfermarkt_match_id
                )
                return STATUS_DUPLICATE
        else:
            already_exists = db_session.execute(
                select(
                    exists().where(
                        MatchCoach.fecha == match_date,
                        MatchCoach.competencia_id == competencia_id,
                        MatchCoach.dt_local_id == dt_local_id,
                        MatchCoach.dt_visita_id == dt_visita_id,
                    )
                )
            ).scalar()
            if already_exists:
                logger.info(
                    "Partido fecha=%s comp=%s DTs=%s/%s ya procesado; se omite.",
                    match_date, competencia_id, dt_local_id, dt_visita_id,
                )
                return STATUS_DUPLICATE

        # B. Entrenadores
        coach_local = db_session.get(Coach, dt_local_id)
        if coach_local is None:
            raise ValueError(f"No se encontró el DT local con ID {dt_local_id}")
        coach_visita = db_session.get(Coach, dt_visita_id)
        if coach_visita is None:
            raise ValueError(f"No se encontró el DT visitante con ID {dt_visita_id}")

        elo_loc_previo = float(coach_local.elo_actual)
        elo_vis_previo = float(coach_visita.elo_actual)

        # C. Coeficiente de competencia
        competition = db_session.get(Competition, competencia_id)
        if competition is None:
            raise ValueError(f"No se encontró la competencia con ID {competencia_id}")
        coeficiente = float(competition.coeficiente)

        # D. Cálculo de la variación
        delta_local, delta_visita, mov_multiplier = compute_elo_delta(
            elo_loc_previo, elo_vis_previo, goles_local, goles_visita,
            factor_k, coeficiente, apply_mov=apply_mov,
        )

        elo_loc_nuevo = round(elo_loc_previo + delta_local, 2)
        elo_vis_nuevo = round(elo_vis_previo + delta_visita, 2)

        coach_local.elo_actual = Decimal(str(elo_loc_nuevo))
        coach_visita.elo_actual = Decimal(str(elo_vis_nuevo))

        match_record = MatchCoach(
            transfermarkt_match_id=transfermarkt_match_id,
            fecha=match_date,
            competencia_id=competencia_id,
            dt_local_id=dt_local_id,
            club_local_id=club_local_id,
            elo_local_previo=Decimal(str(elo_loc_previo)),
            elo_local_nuevo=Decimal(str(elo_loc_nuevo)),
            goles_local=goles_local,
            dt_visita_id=dt_visita_id,
            club_visita_id=club_visita_id,
            elo_visita_previo=Decimal(str(elo_vis_previo)),
            elo_visita_nuevo=Decimal(str(elo_vis_nuevo)),
            goles_visita=goles_visita,
            marcador_pre_cambios_local=marcador_pre_cambios_local,
            marcador_pre_cambios_visita=marcador_pre_cambios_visita,
            impacto_banco_local=impacto_banco_local,
            impacto_banco_visita=impacto_banco_visita,
            factor_k=factor_k,
        )
        db_session.add(match_record)
        db_session.flush()

        if should_close_session:
            db_session.commit()

        logger.info(
            "Partido TM %s procesado: local %s -> %s (%+.2f) | visita %s -> %s (%+.2f) | MOV %.2f",
            transfermarkt_match_id, elo_loc_previo, elo_loc_nuevo, delta_local,
            elo_vis_previo, elo_vis_nuevo, delta_visita, mov_multiplier,
        )
        return STATUS_PROCESSED

    except Exception:
        if should_close_session:
            db_session.rollback()
        raise
    finally:
        if should_close_session:
            db_session.close()


def recompute_all_elo(
    session: Optional[Session] = None,
    apply_mov: bool = True,
    params: Optional[EloParams] = None,
    aplicar_calibracion: bool = True,
) -> int:
    """Recalcula el ELO de todos los DTs reproduciendo el histórico desde 1000.

    Permite incorporar nuevas ligas/competencias sin re-scrapear: se apoya en los
    goles, el factor K y el coeficiente almacenados en `partidos_dt`.
    Con `params=None` se usa `EloParams()`, que reproduce exactamente el modelo
    original; la calibración de DTs nuevos se activa con `params.calibracion_n > 0`.
    Devuelve la cantidad de partidos reproducidos.
    """
    parametros = params or EloParams()
    should_close_session = session is None
    db_session: Session = session if session is not None else SessionFactory()

    try:
        coaches = db_session.execute(select(Coach)).scalars().all()
        elo_map: dict[int, float] = {c.dt_id: INITIAL_ELO for c in coaches}

        coefficients: dict[int, float] = {
            comp.competencia_id: float(comp.coeficiente)
            for comp in db_session.execute(select(Competition)).scalars().all()
        }

        matches = db_session.execute(
            select(MatchCoach).order_by(
                MatchCoach.fecha.asc(),
                MatchCoach.transfermarkt_match_id.asc().nulls_first(),
                MatchCoach.partido_id.asc(),
            )
        ).scalars().all()

        # Contadores para la calibración: partidos previos y última fecha por DT.
        partidos_previos: dict[int, int] = {}
        ultima_fecha: dict[int, date] = {}

        for match in matches:
            elo_local = elo_map.get(match.dt_local_id, INITIAL_ELO)
            elo_visita = elo_map.get(match.dt_visita_id, INITIAL_ELO)
            coeficiente = coefficients.get(match.competencia_id, 1.0)

            if aplicar_calibracion and parametros.calibracion_n > 0:
                mult_local = match_calibracion(
                    partidos_previos.get(match.dt_local_id, 0), parametros,
                    _dias_desde(match.fecha, ultima_fecha.get(match.dt_local_id)),
                )
                mult_visita = match_calibracion(
                    partidos_previos.get(match.dt_visita_id, 0), parametros,
                    _dias_desde(match.fecha, ultima_fecha.get(match.dt_visita_id)),
                )
            else:
                mult_local = mult_visita = 1.0

            delta_local, delta_visita, _ = compute_elo_delta(
                elo_local, elo_visita, match.goles_local, match.goles_visita,
                match.factor_k, coeficiente, apply_mov=apply_mov, params=parametros,
                mult_local=mult_local, mult_visita=mult_visita,
            )
            new_local = round(elo_local + delta_local, 2)
            new_visita = round(elo_visita + delta_visita, 2)

            match.elo_local_previo = Decimal(str(elo_local))
            match.elo_local_nuevo = Decimal(str(new_local))
            match.elo_visita_previo = Decimal(str(elo_visita))
            match.elo_visita_nuevo = Decimal(str(new_visita))

            elo_map[match.dt_local_id] = new_local
            elo_map[match.dt_visita_id] = new_visita
            for dt_id in (match.dt_local_id, match.dt_visita_id):
                partidos_previos[dt_id] = partidos_previos.get(dt_id, 0) + 1
                ultima_fecha[dt_id] = match.fecha

        for coach in coaches:
            coach.elo_actual = Decimal(str(elo_map.get(coach.dt_id, INITIAL_ELO)))

        db_session.flush()
        if should_close_session:
            db_session.commit()

        logger.info("Recálculo ELO completado: %s partidos reproducidos.", len(matches))
        return len(matches)

    except Exception:
        if should_close_session:
            db_session.rollback()
        raise
    finally:
        if should_close_session:
            db_session.close()
