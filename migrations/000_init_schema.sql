-- Migración 000: Esquema base (DDL v1.1)
-- Base de Datos: aep_football_analytics
-- Reejecutable (idempotente). Ejecutar antes de 001 y 002.

CREATE TABLE IF NOT EXISTS entrenadores (
    dt_id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    nacionalidad VARCHAR(50),
    fecha_nacimiento DATE,
    elo_actual NUMERIC(6, 2) NOT NULL DEFAULT 1000.00,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS competencias (
    competencia_id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    nivel VARCHAR(10) NOT NULL CHECK (nivel IN ('S', 'A', 'B', 'C')),
    coeficiente NUMERIC(3, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS clubes (
    club_id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    pais VARCHAR(50) DEFAULT 'Argentina'
);

CREATE TABLE IF NOT EXISTS partidos_dt (
    partido_id SERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    competencia_id INT NOT NULL REFERENCES competencias(competencia_id),

    -- Entrenador y club local
    dt_local_id INT NOT NULL REFERENCES entrenadores(dt_id),
    club_local_id INT NOT NULL REFERENCES clubes(club_id),
    elo_local_previo NUMERIC(6, 2) NOT NULL,
    elo_local_nuevo NUMERIC(6, 2) NOT NULL,
    delta_elo_local NUMERIC(6, 2) GENERATED ALWAYS AS (elo_local_nuevo - elo_local_previo) STORED,
    goles_local INT NOT NULL CHECK (goles_local >= 0),

    -- Entrenador y club visitante
    dt_visita_id INT NOT NULL REFERENCES entrenadores(dt_id),
    club_visita_id INT NOT NULL REFERENCES clubes(club_id),
    elo_visita_previo NUMERIC(6, 2) NOT NULL,
    elo_visita_nuevo NUMERIC(6, 2) NOT NULL,
    delta_elo_visita NUMERIC(6, 2) GENERATED ALWAYS AS (elo_visita_nuevo - elo_visita_previo) STORED,
    goles_visita INT NOT NULL CHECK (goles_visita >= 0),

    -- Métricas de lectura de juego
    marcador_pre_cambios_local VARCHAR(10),
    marcador_pre_cambios_visita VARCHAR(10),
    impacto_banco_local INT CHECK (impacto_banco_local IN (-1, 0, 1)),
    impacto_banco_visita INT CHECK (impacto_banco_visita IN (-1, 0, 1)),

    factor_k INT NOT NULL DEFAULT 20 CHECK (factor_k IN (20, 30, 40)),

    CONSTRAINT uq_partido_fecha_dts UNIQUE (fecha, competencia_id, dt_local_id, dt_visita_id)
);
