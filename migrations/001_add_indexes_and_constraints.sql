-- Migración 001: Índices y restricción de unicidad para tabla partidos_dt
-- Base de Datos: aep_football_analytics

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_partido_fecha_dts'
    ) THEN
        ALTER TABLE partidos_dt
        ADD CONSTRAINT uq_partido_fecha_dts UNIQUE (fecha, competencia_id, dt_local_id, dt_visita_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_partidos_dt_local ON partidos_dt(dt_local_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_partidos_dt_visita ON partidos_dt(dt_visita_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_partidos_fecha ON partidos_dt(fecha DESC);
CREATE INDEX IF NOT EXISTS idx_entrenadores_elo ON entrenadores(elo_actual DESC);
