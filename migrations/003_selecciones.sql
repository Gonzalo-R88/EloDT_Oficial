-- Migración 003: selecciones nacionales
-- Base de Datos: aep_football_analytics
-- Reejecutable (idempotente).
--
-- Hasta ahora la base sólo tenía clubes: un DT que dirigía una selección
-- (Ancelotti en Brasil, Scaloni en Argentina...) aparecía como "sin trabajo"
-- porque sus partidos no existían. Esta migración agrega el tipo de competencia
-- `selecciones` y el tipo de equipo `seleccion`.

-- ============================================================================
-- 1. Competencias: nuevo tipo 'selecciones'
-- ============================================================================
ALTER TABLE competencias DROP CONSTRAINT IF EXISTS check_tipo_competencia;

ALTER TABLE competencias
    ADD CONSTRAINT check_tipo_competencia
    CHECK (tipo IS NULL OR tipo IN ('liga', 'copa', 'internacional', 'selecciones'));

-- ============================================================================
-- 2. Equipos: distinguir clubes de selecciones
-- ============================================================================
ALTER TABLE clubes
    ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) NOT NULL DEFAULT 'club';

ALTER TABLE clubes DROP CONSTRAINT IF EXISTS check_tipo_club;

ALTER TABLE clubes
    ADD CONSTRAINT check_tipo_club
    CHECK (tipo IN ('club', 'seleccion'));

CREATE INDEX IF NOT EXISTS idx_clubes_tipo ON clubes(tipo);
