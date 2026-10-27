# Fase 2: Actualización incremental y orquestador

Leer antes: `AGENTS.md`, `ESTADO.md` y las reglas generales de `00-INDICE.md`.
Tareas de este archivo: T2.1, T2.2, T2.3, T2.4, T2.5.

## Contexto necesario

- Fuente: scraping incremental de Transfermarkt (VPN + `WafChallengeSolver`). Volumen semanal: ~300 partidos nuevos + ~100 fixtures (51 competencias × 2 temporadas posibles) = ~450 requests ≈ 30 min a 14 req/min.
- **El flag `--refresh` actual re-descarga todos los reportes de la temporada** (`pending = [... if refresh or not has_match]` en `scrape_season`). Hace falta un modo que baje solo el fixture y los reportes que faltan.
- **Semana de trabajo:** `semana_fin` = domingo más reciente ≤ ayer. Solo se procesan partidos con fecha ≤ `semana_fin`; los posteriores esperan a la próxima corrida. Así el snapshot es siempre limpio aunque la PC se encienda un miércoles.
- **Temporadas en curso** por competencia: `saison_offset=0` (Europa): año si mes ≥ 7, si no año−1; `saison_offset=1` (año calendario): año actual. Se prueba también la anterior y se conservan las que tengan fechas ≥ `since`.
- **ELO incremental:** si hay partidos nuevos o correcciones, `recompute_all_elo` completo (determinista). Medir el tiempo; solo si supera ~5 minutos evaluar un `recompute_from(fecha)`.
- **Correcciones:** comparar el score del fixture contra la base para los últimos 21 días; si difiere, corregir y recalcular.
- Los snapshots son inmutables: lo publicado no cambia aunque el modelo cambie (`modelo_version` en cada fila).
- Reglas de publicación: `publicacion.py` (T0.5) y `data/audit/cobertura.json` (T0.2).

---

## T2.1: Migración de snapshots y ejecuciones

- **Tipo:** ⚙️.
- **Depende de:** T1.7.
- **Archivos:** `migrations/00N_snapshots.sql` (usar el siguiente número libre; documentar en `AGENTS.md`), `models.py` (ORM de ambas tablas), `tests/`.
- **Tablas:**
  - `snapshots_elo(semana_fin DATE, dt_id INT REFERENCES entrenadores, elo NUMERIC(7,2), rank_global INT, pj_total INT, activo BOOLEAN, publicable BOOLEAN, etiqueta VARCHAR(20) NULL, modelo_version TEXT, PRIMARY KEY (semana_fin, dt_id, modelo_version))`, con índice por `(semana_fin, rank_global)`.
  - `ejecuciones_pipeline(run_id SERIAL PK, semana_fin DATE, iniciado_en TIMESTAMPTZ, terminado_en TIMESTAMPTZ NULL, estado VARCHAR(20), resumen JSONB)`.
- **Aceptación:** `python migrate.py` aplica y es idempotente (dos corridas seguidas sin error); tests con SQLite siguen pasando; backup previo hecho.

## T2.2: Snapshots e historial

- **Tipo:** ⚙️.
- **Depende de:** T2.1, T0.5.
- **Archivos:** `snapshots.py`, `scripts/backfill_snapshots.py`, `tests/test_snapshots.py`.
- **Pasos:**
  1. `take_snapshot(session, semana_fin, modelo_version)`: para cada DT, ELO al cierre de `semana_fin` (último `elo_nuevo` con `fecha ≤ semana_fin`), `pj_total`, `activo`, `publicable`/`etiqueta` (vía `publicacion.es_publicable`), `rank_global` entre los publicables. Idempotente (upsert por clave primaria).
  2. `backfill_snapshots.py`: reconstruye el historial semanal desde 2012 con el estado de `partidos_dt` (`publicable` histórico se calcula con las mismas reglas, aunque la cobertura sea la actual; documentar esa aproximación).
- **Aceptación:** el último snapshot coincide con `entrenadores.elo_actual` para todos los DTs; correr dos veces no duplica filas; `rank_global` es consecutivo entre publicables; tests con SQLite.

## T2.3: Comando `update` (scrape incremental)

- **Tipo:** 🔒 (la prueba real).
- **Depende de:** T0.3.
- **Archivos:** `scraper_transfermarkt.py` (subcomando `update`), `scraping/pipeline.py` (`scrape_incremental`, `current_seasons`), `tests/test_pipeline.py` (con cliente falso).
- **Comportamiento:**
  1. Para cada competencia y cada temporada en curso, descargar solo el fixture (1 request).
  2. Bajar solo los reportes de partidos con fecha ≤ `semana_fin` que no estén cacheados.
  3. `load` de lo nuevo (con imputación de DT por etapas si T0.9 ya existe) y `persist_matches`.
  4. Opciones: `--since-days N` (default 21), `--competitions A,B,C`, `--dry-run` (solo cuenta cuántas requests haría), `--semana-fin YYYY-MM-DD`.
  5. Mismo ritmo y manejo de 403/CAPTCHA que el scraper actual.
- **Aceptación:** test de que **no re-descarga** lo cacheado; test de `current_seasons` para Europa y año calendario; `--dry-run` informa la cantidad de requests; una corrida real (pedir confirmación y VPN) trae unos ~300 partidos con menos de 600 requests.
- **No hacer:** no cambiar el comportamiento de `scrape` ni de `--refresh`.

## T2.4: Correcciones y política de recálculo

- **Tipo:** ⚙️.
- **Depende de:** T2.3.
- **Archivos:** `services.py` (`detectar_correcciones`), `scripts/weekly_run.py` (si ya existe) o módulo `pipeline_semanal.py`, `tests/test_services.py`.
- **Comportamiento:**
  - Comparar score y fecha del fixture contra la DB para los últimos 21 días; devolver la lista de diferencias; aplicar la corrección y marcar `necesita_recompute`.
  - Si hubo partidos nuevos o correcciones: `recompute_all_elo` completo.
  - Medir y registrar el tiempo de recompute.
- **Aceptación:** test con una corrección simulada; dos recomputes seguidos dan el mismo hash de `elo_actual` (determinismo); el tiempo de recompute queda registrado en el resumen; `validate_elo.py` en verde.

## T2.5: Orquestador `weekly_run.py`

- **Tipo:** ⚙️ + 🔒 (prueba de `preflight`).
- **Depende de:** T2.2, T2.4.
- **Archivos:** `scripts/weekly_run.py`, `tests/test_weekly_run.py`.
- **Subcomandos (salida JSON por stdout con `--json`; logs en `data/logs/weekly_<fecha>.log`):**
  - `preflight`: DB responde; TM alcanzable. Detecta VPN apagada, 403, CAPTCHA (405 "Human Verification"; el mensaje dice "cambiar de servidor VPN"). Informa si la IP de casa responde 200/202 sin VPN. Código 10 si falla.
  - `update`: `preflight` implícito → `update` incremental (T2.3) → correcciones y recompute (T2.4) → `validate_elo.py` (si falla, código 20) → regenerar `data/audit/cobertura.json` → `take_snapshot`. Registra la fila en `ejecuciones_pipeline`.
  - `render` y `notify`: se completan en las fases 3 y 4 (dejar el esqueleto que falla con mensaje claro).
  - `all`: encadena todo.
- **Flags:** `--json`, `--skip-if-done-this-week` (sale 0 sin hacer nada si ya hay una ejecución exitosa para esa `semana_fin`), `--semana-fin`.
- **Lock:** `data/weekly.lock` para evitar corridas simultáneas (si existe y el proceso sigue vivo, salir con código 30 y mensaje claro).
- **Códigos de salida:** 0 ok; 10 bloqueo/VPN (reintentable); 20 validación fallida; 30 otro error.
- **Resumen JSON de `update`:** `semana_fin`, `nuevos`, `descartados_sin_dt`, `correcciones`, `competencias_sin_partidos_14d`, `dias_desde_ultimo_partido`, `tiempo_recompute_s`, `snapshot_filas`.
- **Aceptación:** una segunda corrida inmediata no trae partidos nuevos y termina con código 0; `--skip-if-done-this-week` funciona; `preflight` falla (código 10) con la VPN apagada y pasa con la VPN prendida; el lock evita ejecuciones paralelas; tests de los códigos de salida con dependencias simuladas.
