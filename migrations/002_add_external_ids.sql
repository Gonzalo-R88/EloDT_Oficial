-- Migración 002: IDs externos de Transfermarkt, soporte multi-liga e idempotencia robusta
-- Base de Datos: aep_football_analytics
-- Reejecutable (idempotente).

-- ============================================================================
-- 1. Entrenadores: identificador estable de Transfermarkt
-- ============================================================================
ALTER TABLE entrenadores
    ADD COLUMN IF NOT EXISTS transfermarkt_id INT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_entrenadores_tm_id
    ON entrenadores(transfermarkt_id)
    WHERE transfermarkt_id IS NOT NULL;

-- ============================================================================
-- 2. Clubes: identificador estable de Transfermarkt
-- ============================================================================
ALTER TABLE clubes
    ADD COLUMN IF NOT EXISTS transfermarkt_id INT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_clubes_tm_id
    ON clubes(transfermarkt_id)
    WHERE transfermarkt_id IS NOT NULL;

-- ============================================================================
-- 3. Competencias: código externo, país y tipo (liga / copa / internacional)
-- ============================================================================
ALTER TABLE competencias
    ADD COLUMN IF NOT EXISTS codigo VARCHAR(20);
ALTER TABLE competencias
    ADD COLUMN IF NOT EXISTS transfermarkt_id INT;
ALTER TABLE competencias
    ADD COLUMN IF NOT EXISTS pais VARCHAR(50);
ALTER TABLE competencias
    ADD COLUMN IF NOT EXISTS tipo VARCHAR(20);

CREATE UNIQUE INDEX IF NOT EXISTS uq_competencias_codigo
    ON competencias(codigo)
    WHERE codigo IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_tipo_competencia'
    ) THEN
        ALTER TABLE competencias
            ADD CONSTRAINT check_tipo_competencia
            CHECK (tipo IS NULL OR tipo IN ('liga', 'copa', 'internacional'));
    END IF;
END $$;

-- ============================================================================
-- 4. Partidos: id de partido de Transfermarkt (idempotencia robusta)
-- ============================================================================
ALTER TABLE partidos_dt
    ADD COLUMN IF NOT EXISTS transfermarkt_match_id INT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_partidos_tm_match_id
    ON partidos_dt(transfermarkt_match_id)
    WHERE transfermarkt_match_id IS NOT NULL;

-- ============================================================================
-- 5. Clubes obligatorios en partidos (si no hay filas con NULL)
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM partidos_dt WHERE club_local_id IS NULL) THEN
        ALTER TABLE partidos_dt ALTER COLUMN club_local_id SET NOT NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM partidos_dt WHERE club_visita_id IS NULL) THEN
        ALTER TABLE partidos_dt ALTER COLUMN club_visita_id SET NOT NULL;
    END IF;
END $$;

-- ============================================================================
-- 6. Timestamp con zona horaria en entrenadores
-- ============================================================================
ALTER TABLE entrenadores
    ALTER COLUMN creado_en TYPE TIMESTAMP WITH TIME ZONE
    USING creado_en AT TIME ZONE 'UTC';
