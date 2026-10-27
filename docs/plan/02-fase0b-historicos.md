# Fase 0b: Datos históricos

Leer antes: `AGENTS.md`, `ESTADO.md` y las reglas generales de `00-INDICE.md`.
Tareas de este archivo: T0.10, T0.7, T0.8, T0.9, T0.11. Se pueden hacer en paralelo con la Fase 1; **no bloquean el primer post de Argentina** salvo que el experimento de sensibilidad (T1.5) indique lo contrario.

## Contexto necesario

- Faltan competencias UEFA (Champions, Europa League, Conference) y copas domésticas europeas. Ancelotti, Guardiola, Mourinho y Simeone tienen hoy 12-44 partidos/año, todos de liga.
- ~69 mil partidos (de 261.194 fixtures cacheados) se descartaron por falta de DT en el reporte, la mayoría anteriores a 2015. El fixture ya trae club y fecha de cada partido: con un historial de etapas por club se puede asignar el DT.
- TM no tiene ligas argentinas anteriores a ~2014-15. Falcioni tiene 1-6 partidos/año entre 2004 y 2014. Esto exige una fuente externa (T0.11).
- Ritmo de scraping máximo ~14 req/min. Todo scrape va en `tmux`, reanudable, con VPN y con confirmación del usuario.

---

## T0.10: UEFA al catálogo y backfill

- **Tipo:** 🔒.
- **Depende de:** T0.1.
- **Objetivo:** sumar Champions League, Europa League y Conference League 2000-2026 (Conference desde su primera edición).
- **Archivos:** `scraping/leagues_catalog.py`, `scripts/verify_competitions.py`, `scripts/backfill_uefa.sh` (siguiendo el estilo de `backfill_resto.sh`), `tests/` si hay lógica nueva.
- **Pasos:**
  1. Averiguar los códigos de competencia de TM (no asumirlos): verificarlos con `scripts/verify_competitions.py --codes ...` en una temporada de muestra (`saison_offset=0`, `path="pokalwettbewerb"` o el que corresponda; usar `--no-align-check` si la verificación lo necesita).
  2. Agregar al catálogo: Champions (`tier="S"`, `coefficient=1.30`), Europa League (`A`, `1.00`), Conference (`B`, `0.80`), `kind="internacional"`, `confederation="UEFA"`, con `est_matches` observados.
  3. 🔒 Estimar requests con `scripts/plan_scraping.py` y **pedir confirmación** (≈15 mil requests, ≈18 horas, en tandas).
  4. Backfill reanudable en `tmux`, `load`, `recompute`, `validate_elo.py`.
  5. Revisar `infer_factor_k` con las rondas de estas copas (grupos, octavos, etc.); si el mapeo de rondas no existe todavía (T1.4), dejar K=20 y anotarlo.
- **Aceptación:** los tres códigos verificados; partidos de esas competencias cargados con `validate_elo.py` en verde; Ancelotti, Guardiola, Mourinho y Simeone suman partidos de copa visibles en `partidos_dt`; coberturas por temporada reportadas con `audit_data.py`.
- **Parada:** confirmar tiempo y VPN antes del backfill.

## T0.7: Estudio de la fuente de etapas de DTs

- **Tipo:** 🔒 + 👤.
- **Depende de:** T0.4.
- **Objetivo:** confirmar qué página de TM da DT, club, desde y hasta (historial de DTs del club vs historial del perfil del DT) y cuántas requests cuesta.
- **Archivos:** `docs/ETAPAS_DTS.md`.
- **Pasos:**
  1. Con VPN y el cliente existente (`TransfermarktClient` + `WafChallengeSolver`), descargar muestras de las candidatas: la página de historial de entrenadores de un club (por ejemplo Boca Juniors o Real Madrid) y la de estaciones del perfil de un DT (por ejemplo Ancelotti y Falcioni). Guardar el HTML en `data/raw_etapas_muestras/` (no en el caché normal).
  2. Escribir un parser exploratorio que extraiga, por etapa: DT (`tm_id` y nombre), club (`tm_id`), fecha de inicio, fecha de fin y, si existe, partidos jugados.
  3. Probar con 3 casos: un DT con varias etapas, un interino y un DT actual (fecha de fin abierta).
  4. Elegir la fuente (la de menos requests y datos más completos) y estimar total de requests y tiempo a 14 req/min.
- **Aceptación:** `docs/ETAPAS_DTS.md` con la URL elegida, el selector/parseo, los 3 ejemplos contrastados a mano contra la web y la estimación de requests.

## T0.8: Scrape de etapas y perfiles

- **Tipo:** 🔒.
- **Depende de:** T0.7.
- **Objetivo:** tabla `dt_etapas` y datos de perfil (nacionalidad, fecha de nacimiento) de los DTs activos.
- **Archivos:** `migrations/003_etapas.sql` (si T2.1 todavía no existe; si ya hay una 003, usar el siguiente número libre) con `dt_etapas(etapa_id, dt_id NULL, dt_tm_id, club_id, desde DATE, hasta DATE NULL, pj_tm INT NULL)`, `models.py`, `scraping/parser.py`, `scripts/scrape_etapas.py`, `tests/test_parser_etapas.py` (con HTML de muestra de T0.7).
- **Pasos:**
  1. Migración idempotente y modelo ORM; actualizar `AGENTS.md` si cambia el orden de migraciones.
  2. Parser con tests sobre las muestras de T0.7.
  3. `scrape_etapas.py`: reanudable (caché en `data/raw_etapas/`), mismo ritmo y cliente que el scraper, con `--limit` para pruebas; carga a `dt_etapas`.
  4. Nacionalidad y fecha de nacimiento: cargarlas en `entrenadores` para los DTs activos (último partido en los últimos 365 días); si no están en la misma página, hacer un segundo scrape de perfiles solo para esos DTs.
- **Aceptación:** `migrate.py` idempotente; etapas cargadas para los clubes de la base; `entrenadores.nacionalidad` y `fecha_nacimiento` completos para los DTs activos; los tests pasan; se puede interrumpir y reanudar.
- **Parada:** pedir confirmación antes del scrape completo.

## T0.9: Imputación de DTs por etapas

- **Tipo:** ⚙️.
- **Depende de:** T0.8.
- **Objetivo:** recuperar los partidos descartados por DT faltante.
- **Archivos:** `scraping/pipeline.py` (`load_normalized` consulta `dt_etapas` si falta el DT del reporte), columna `dt_imputado BOOLEAN DEFAULT FALSE` en `partidos_dt` (migración nueva, idempotente), `models.py`, `scripts/validar_imputacion.py`, tests.
- **Reglas:**
  - Se imputa un DT solo si exactamente **una** etapa cubre ese club en esa fecha (`desde <= fecha <= hasta`, con `hasta` abierta si es NULL).
  - Si hay cero o más de una etapa candidata, el partido se sigue descartando (no se inventa).
  - El partido imputado queda marcado con `dt_imputado = TRUE`; el DT que falta tiene que existir en `entrenadores` (si solo aparece en `dt_etapas`, crearlo con `ensure_coach`).
- **Pasos:**
  1. Implementar la imputación y los tests.
  2. `validar_imputacion.py`: toma partidos con ambos DTs conocidos, **esconde** el DT de un lado al azar, imputa y mide el acierto.
  3. Cargar con `load` (los reportes ya están cacheados; sin requests), `recompute`, `validate_elo.py`, `audit_data.py`.
- **Aceptación:** acierto del hold-out >= 95 %; reporte de partidos recuperados por competencia y por quinquenio; `validate_elo.py` en verde; tests.

## T0.11: Estudio de factibilidad de Argentina 2000-2014

- **Tipo:** ⚙️ + 👤 (decide el usuario).
- **Depende de:** T0.8.
- **Objetivo:** decidir si vale la pena y cómo cubrir los partidos argentinos de 2000-2014 (no existen en TM).
- **Archivos:** `docs/ARGENTINA_HISTORICO.md`.
- **Pasos:**
  1. Relevar fuentes candidatas con acceso gratuito (RSSSF, Wikipedia, datasets abiertos en GitHub/Kaggle, otras): cobertura de torneos 2000-2014, si traen fecha y goles por partido, licencia, formato y esfuerzo de extracción.
  2. Con las etapas de DTs (T0.8), armar una **muestra cruzada** para Falcioni en una temporada: resultados de la fuente externa + DT por etapa, y ver si cierra con lo que se sabe de su carrera.
  3. Estimar partidos totales, trabajo y riesgo.
- **Aceptación:** documento con la tabla de fuentes, la muestra cruzada y una recomendación explícita (hacer / no hacer / hacer parcial).
- **Parada humana:** el usuario decide. No implementar nada sin esa decisión.
