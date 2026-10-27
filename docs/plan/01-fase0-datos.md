# Fase 0: Datos y base sana

Leer antes: `AGENTS.md`, `ESTADO.md` y las reglas generales de `00-INDICE.md`.
Tareas de este archivo: T0.1, T0.2, T0.3, T0.4, T0.6, T0.5 (en este orden).

## Contexto necesario

- Base `aep_football_analytics`: 191.931 partidos, 6.686 DTs, 1.470 clubes, 51 competencias, 2000-05-04 a 2026-10-08.
- Caché de scraping en `data/raw/{code}/{season}/fixtures.json` y `matches/{id}.json` (261.194 reportes en total; leer todos tarda mucho en `/mnt/f`).
- Fixtures cacheados: 261.194; cargados a la DB: 191.931. La diferencia son partidos descartados por `sin_dt` (falta algún DT en el reporte) y otros motivos.
- Cobertura de DT faltante en una muestra de 3.000 reportes: ~58 % (2000-04), ~62 % (2005-09), ~24 % (2010-14), ~6 % (2015-19), <=1 % (2020+).
- **Argentina:** `AR1N` solo tiene 2015-16 y 2021-24 (termina 2024-12-17); `ARG2` falta 2017-2020; `CDLP` termina 2024-04. Los logs (`data/logs/*.log`) muestran "Fixture ... desalineado (TM devolvió otra temporada); no se cachea" para `AR1N/ARG2/CDLP` 2017-2020 y `AR1N/CDLP` 2025-26. Hipótesis: (a) cambios de formato/código en TM (Superliga 2016/17-2019/20, Copa de la Liga 2020 por pandemia, Apertura/Clausura 2025); (b) falso positivo del guard `season_is_aligned` en temporadas agosto-junio, porque exige `min(año de fechas) == temporada pedida`. Sin diagnosticar.
- **Fechas corruptas:** 152 casos de un DT con más de un partido el mismo día (hasta 5). Ejemplo: Alianza Lima, 2006-07-30, competencia `TDeC`, `tm_match_id` 4472725, 4472729, 4472733, 4472743, 4472748. Sospecha: forward-fill de fecha de `parse_schedule`/`_extract_date`.
- **Clubes con `pais="Conmebol"`:** 254 clubes (incluye clubes argentinos creados primero desde la Libertadores/Sudamericana).
- `saison_offset`: 1 para Sudamérica y ligas de año calendario (SE1, NO1, JAP1, MLS...), 0 para Europa. `--season` es el año real; `saison_id = season - saison_offset`.
- Competencias de liga con `kind="liga"` tienen `pais`; los clubes también (`clubes.pais`).

---

## T0.1: Respaldo y control de versiones

- **Tipo:** ⚙️ + 👤 (el usuario rota `DB_PASS`).
- **Depende de:** nada.
- **Objetivo:** poder deshacer cambios antes de tocar la base o el código.
- **Archivos:** `scripts/backup_db.sh`, `.env.example`, `.git/` (init), `.gitignore` (verificar que excluya `.env`, `data/`, `__pycache__/`, `.pytest_cache/`).
- **Pasos:**
  1. `scripts/backup_db.sh`: `pg_dump` (formato custom) de `aep_football_analytics` a `data/backups/aep_YYYYmmdd_HHMM.dump`, leyendo `DB_*` del `.env` sin imprimirlos. Si `pg_dump` no está instalado en WSL, indicarlo y proponer la instalación (no instalar sin confirmar).
  2. `.env.example` con las mismas claves de `.env` y valores vacíos o de ejemplo (sin secretos reales).
  3. `git init`, primer commit sin `.env` ni `data/`.
- **Aceptación:** el dump se restaura en una base temporal (`createdb` + `pg_restore`) y `SELECT count(*) FROM partidos_dt` da 191.931; `git status` limpio tras el commit; `git ls-files` no incluye `.env` ni `data/`.
- **No hacer:** no cambiar `DB_PASS` (lo hace el usuario); no commitear el dump.
- **Aviso al usuario al terminar:** rotar `DB_PASS` (quedó expuesto en un log de sesión).

## T0.2: Auditoría de datos y cobertura

- **Tipo:** ⚙️.
- **Depende de:** T0.1.
- **Objetivo:** reproducir los hallazgos y generar la tabla de cobertura que usan T0.5 y el pipeline.
- **Archivos:** `scripts/audit_data.py`, `tests/test_audit_data.py` (con datos sintéticos), salida en `data/audit/`.
- **Pasos:**
  1. Leer solo los `fixtures.json` del caché (≈1.300 archivos) y los `transfermarkt_match_id` de `partidos_dt` (una consulta).
  2. Por competencia, temporada de caché y **año calendario de la fecha del fixture**: `fixtures`, `cargados` (los que están en la DB) y `ratio`.
  3. Para cada competencia del catálogo, años desde `first_season` hasta el año actual: si no hay ningún fixture cacheado para ese año, `ratio = 0` (así los huecos como Argentina 2025-26 quedan visibles). Escribir `data/audit/cobertura.json` con la forma `{codigo: {año: {"fixtures": n, "cargados": n, "ratio": x}}}`.
  4. Listar los casos de DT con más de un partido el mismo día (consulta SQL) y escribirlos en `data/audit/conflictos_fecha.json` (dt, fecha, partidos, competencias, `tm_match_id`).
  5. Último partido por competencia y días desde entonces.
  6. Opción `--muestra N` (default 0): lee N reportes al azar y estima el porcentaje con DT faltante por quinquenio (no leer los 261k por defecto).
  7. Informe en Markdown `data/audit/auditoria_<fecha>.md` con totales y las competencias-temporada peor cubiertas.
- **Aceptación:** reproduce 261.194 fixtures cacheados vs 191.931 cargados; 152 conflictos de DT-día; detecta Argentina 2017-2020 y 2025-26 con `ratio = 0`; los tests pasan; corre en menos de 2 minutos sin `--muestra`.
- **No hacer:** no leer los 261k reportes por defecto; no modificar la DB.

## T0.3: Diagnóstico y arreglo del bug de fechas

- **Tipo:** 🔒.
- **Depende de:** T0.2.
- **Objetivo:** eliminar los 152 conflictos de fecha.
- **Archivos:** `scraping/parser.py` (`parse_schedule`, `_extract_date`), `tests/test_parser.py`, y las temporadas afectadas del caché.
- **Pasos:**
  1. Reproducir con `data/raw/TDeC/2006/fixtures.json`: ver qué fecha tiene cada fixture de Alianza Lima y por qué coinciden. Guardar un HTML mínimo de muestra en `tests/fixtures_html/` si hay que descargar el fixture (🔒, pocas requests).
  2. Identificar la causa (forward-fill sobre filas sin fecha, grupos de ronda, tabla distinta en copas o torneos Apertura/Clausura, etc.).
  3. Escribir primero el test que falla; luego arreglar el parser.
  4. Con la lista de `conflictos_fecha.json`, deducir las comp-temporadas afectadas; re-descargar solo esos fixtures con `--refresh --limit 0` o el modo equivalente (el fixture solamente, **sin re-descargar reportes**; si el CLI actual no lo permite, agregar un flag mínimo `--fixture-only`).
  5. Actualizar las fechas de `partidos_dt` de esos partidos (script `scripts/fix_fechas.py`, idempotente, con dry-run por defecto) y `recompute`.
- **Aceptación:** test de regresión que falla sin el arreglo y pasa con él; `audit_data.py` baja los conflictos de 152 a 0 o cada caso restante queda explicado por escrito; `recompute` y `validate_elo.py` en verde.
- **Parada:** si la causa no es el forward-fill, reportar antes de seguir.

## T0.4: Diagnosticar y recuperar Argentina

- **Tipo:** 🔒 + 👤 (parada para revisar cobertura).
- **Depende de:** T0.1, T0.2.
- **Objetivo:** cubrir `AR1N`, `ARG2` y `CDLP` en 2017-2020 y 2025-26, o documentar por qué TM no los tiene.
- **Archivos:** `scraping/pipeline.py` (`season_is_aligned`), `scripts/verify_competitions.py` (flag `--no-align-check`, que no cachea), `scraping/leagues_catalog.py`, `tests/test_pipeline.py`.
- **Pasos:**
  1. Con el guard apagado y sin cachear, pedir para `AR1N`, `ARG2` y `CDLP` las temporadas 2017, 2018, 2019, 2020, 2025 y 2026; imprimir cantidad de fixtures y fechas mínima y máxima de cada una. (~18 requests.)
  2. **Si TM devuelve temporadas agosto-junio correctas** (por ejemplo, 2016-08 a 2017-05 al pedir 2017): el guard es un falso positivo. Cambiar la regla a "aceptar si el año pedido está entre el año de la fecha mínima y el de la máxima". Debe seguir rechazando el caso original (pedir 2000 y que TM devuelva la temporada actual). Agregar tests de ambos casos.
  3. **Si devuelve otra temporada o vacío:** buscar en TM los códigos de competencia de la Superliga Argentina, Copa de la Liga/Copa Maradona 2020 y Apertura/Clausura 2025, sumarlos a `leagues_catalog.py` y verificarlos con `verify_competitions.py`.
  4. 🔒 Confirmar con el usuario, y luego `scrape` + `load` de las temporadas recuperadas (3 workers, ritmo estándar, en `tmux`), `recompute`, `validate_elo.py`, `audit_data.py`.
  5. Escribir `docs/ARGENTINA_COBERTURA.md`: tabla año × competencia con partidos cargados y, para los huecos, la causa (por ejemplo, "2020: pandemia").
- **Aceptación:** tabla de cobertura sin huecos sin explicar; `validate_elo.py` en verde; tests del guard; `cobertura.json` actualizado.
- **Parada humana:** presentar la tabla al usuario y esperar su visto bueno antes de T0.6/T0.5.

## T0.6: País real de los clubes

- **Tipo:** ⚙️.
- **Depende de:** T0.4.
- **Objetivo:** que "DT de Argentina" salga bien. Hoy 254 clubes tienen `pais="Conmebol"`.
- **Archivos:** `scripts/fix_club_country.py` (dry-run por defecto; `--apply`), `tests/test_fix_club_country.py`, `scraping/pipeline.py` (`ensure_club`: que un club nuevo creado desde una competencia internacional no reciba el país "Conmebol"; usar "desconocido" hasta resolverlo).
- **Qué hace:** para cada club con país "Conmebol" (o desconocido), tomar la competencia de `tipo="liga"` (o de copa doméstica) donde más partidos juega y asignarle el `pais` de esa competencia. Los clubes que solo aparecen en torneos internacionales quedan en "desconocido" y se listan.
- **Aceptación:** Boca, River, Racing y Talleres quedan con `pais="Argentina"`; informe de clubes sin país (cantidad y nombres); tests con datos sintéticos; idempotente.
- **No hacer:** no cambiar nada del ELO.

## T0.5: Reglas de publicación

- **Tipo:** ⚙️.
- **Depende de:** T0.2, T0.4, T0.6.
- **Objetivo:** centralizar qué DT y qué dato se puede publicar.
- **Archivos:** `config.py` (nuevos settings), `publicacion.py`, `tests/test_publicacion.py`.
- **Settings (variables de entorno con default):** `RANKING_MIN_PJ=15`, `PROVISORIO_PJ=30`, `INTERINO_MIN_PJ=5`, `ACTIVO_DIAS=365`, `COBERTURA_MIN=0.90`, `COBERTURA_ANIOS=3`, `COBERTURA_JSON=data/audit/cobertura.json`.
- **Funciones en `publicacion.py`:**
  - `cobertura_liga(codigo, hasta)`: promedio del `ratio` de `cobertura.json` sobre los últimos `COBERTURA_ANIOS` años calendario hasta `hasta` (años sin datos cuentan 0 si son >= `first_season`).
  - `liga_domestica_de_club(session, club_id, hasta)`: la competencia de `tipo="liga"` donde el club más jugó en los últimos 3 años (si ninguna, `None`).
  - `es_publicable(session, dt_id, hasta)` devuelve un objeto con `publicable` (bool), `etiqueta` (`None`, `"provisorio"` o `"interino"`) y `motivo` si no es publicable.
- **Reglas:**
  - `publicable` si: `pj_total >= RANKING_MIN_PJ`, último partido a menos de `ACTIVO_DIAS` días de `hasta`, y su **último club** pertenece a una liga doméstica con `cobertura_liga >= COBERTURA_MIN`. DT cuyo último club no tiene liga doméstica conocida: no publicable.
  - Etiqueta `provisorio` si `RANKING_MIN_PJ <= pj_total < PROVISORIO_PJ`.
  - `interino`: solo para "subidas y bajadas" (ver Fase 3): `INTERINO_MIN_PJ <= pj_total < RANKING_MIN_PJ`; nunca en Top 10.
- **Aceptación:** tests con casos: DT con 14 PJ; DT activo vs inactivo; liga con cobertura 80 % (no publicable); liga con año sin fixtures (cobertura 0 -> ningún DT de esa liga publicable); DT provisorio; interino. Con los datos reales, tras T0.4, los DTs argentinos activos son publicables si `AR1N` queda con cobertura >= 90 %.
- **Nota:** `cobertura.json` se regenera en cada corrida semanal (lo hace T2.5).
