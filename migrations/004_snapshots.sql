-- Migración 004: historial semanal de ELO y registro de corridas del pipeline
-- Base de Datos: aep_football_analytics
-- Reejecutable (idempotente).
--
-- `partidos_dt` guarda el ELO después de cada partido, pero no "cómo estaba el
-- ranking el domingo". Los snapshots son inmutables: lo que se publicó una semana no
-- cambia aunque después cambie el modelo (`modelo_version` en la clave).

CREATE TABLE IF NOT EXISTS snapshots_elo (
    semana_fin DATE NOT NULL,
    dt_id INT NOT NULL REFERENCES entrenadores(dt_id),
    modelo_version VARCHAR(20) NOT NULL,
    elo NUMERIC(7, 2) NOT NULL,
    rank_global INT,
    pj_total INT NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT FALSE,
    publicable BOOLEAN NOT NULL DEFAULT FALSE,
    etiqueta VARCHAR(20),
    PRIMARY KEY (semana_fin, dt_id, modelo_version)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_rank ON snapshots_elo(semana_fin, rank_global);
CREATE INDEX IF NOT EXISTS idx_snapshots_dt ON snapshots_elo(dt_id, semana_fin DESC);

CREATE TABLE IF NOT EXISTS ejecuciones_pipeline (
    run_id SERIAL PRIMARY KEY,
    semana_fin DATE,
    iniciado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    terminado_en TIMESTAMP WITH TIME ZONE,
    estado VARCHAR(20) NOT NULL,
    resumen JSONB
);