# ESTADO DEL PROYECTO — handoff entre sesiones

Última actualización: 2026-10-27.

> **PLAN DE TRABAJO VIGENTE:** `docs/plan/00-INDICE.md` (índice de tareas T0.1…T5.5, con
> reglas generales, paquetes sugeridos y paradas humanas) y los archivos `01`…`07` por fase.
> Se ejecuta **una tarea por sesión**, marcando la casilla en el índice. La sesión
> 2026-10-27 completó **T0.1**; sigue **T0.2** (auditoría de cobertura, sin VPN).

> **SCRAPING TOTAL COMPLETADO (2026-10-27).** Las 51 competencias quedaron
> backfilleadas 2000-2026 y cargadas a la DB (`validate_elo.py`):
> **191.931 partidos**, **6.686 DTs**, **51 competencias**, 0 duplicados
> `tm_id`, 0 partidos con suma ≠ 0, **masa ELO 6.686.000 = 6.686 × 1000 → OK**.
> Ya no hay scraper corriendo; el watchdog quedó **desactivado**.
>
> **Layout unificado (2026-10-27):** TODO vive en una sola carpeta,
> `F:\ProyectoDT` (WSL `/mnt/f/ProyectoDT`): el código y `data/` (caché `raw/`,
> `logs/`, `output/`) adentro. `DATA_DIR` ya no está en `.env` (se usa el default
> `./data`). Motivo del traslado desde Google Drive (`D:`): Drive detectaba
> "lookup spam" con ~260k JSON, y el Task Scheduler de Windows no ve `D:`.
>
> **Ojo VPN (si se rehace scraping):** si un reinicio de Windows deja WSL apagado
> y la VPN reconecta a otro servidor, TM puede responder **CAPTCHA** en vez del
> challenge JS (HTTP 405, `<title>Human Verification</title>`, `captcha.js`) —
> el solver no lo resuelve. Anduvieron WorldStream (NL) y Datacamp (Dallas);
> Proton Miami y M247 (LA) dieron 405/403. Ante eso: cambiar de servidor VPN.
>
> **Watchdog:** `scripts/watchdog_backfill.sh` relanza `aep-resto` si no está.
> Lo disparan las tareas del Task Scheduler `AEP-Watchdog-Logon`/`AEP-Watchdog-2h`
> (→ `C:\Users\Gonzalo\aep_watchdog_start.bat`). **Hoy están DESACTIVADAS** (el
> backfill terminó); reactivar con `schtasks /Change /TN "AEP-Watchdog-2h" /ENABLE`
> si se relanza scraping. Logs: `data/logs/watchdog.log` y
> `C:\Users\Gonzalo\aep_watchdog_windows.log`.
>
> **Otros cambios 2026-10-06/08:** delays default 3-6 s en `backfill_resto.sh`;
> `.env` `TM_BLOCKED_WAIT=300` (antes 1800).
>
> **Diagnóstico del bloqueo (28-sep, histórico):** la IP de casa (ARSAT) recibe
> **403 duro**; las IPs de datacenter VPN reciben el challenge JS de AWS WAF
> (`awswaf.com/challenge.js`), que `curl_cffi` no resuelve solo. Solución:
> Playwright/Chromium headless resuelve el reto, extrae `aws-waf-token` y lo
> inyecta a `curl_cffi`.

## Dónde estamos

- **Backfill por fases completado para Argentina + Conmebol.**
- Base de datos `aep_football_analytics` (PostgreSQL) al día de hoy:
  - **11.937 partidos**, **1.173 DTs**, **9 competencias**.
  - Argentina (AR1N, ARG2, CDLP, CDCA, ARCA) y Conmebol (CLI, CS, RESU)
    backfilleadas **2000-2026**; el "resto" está scrapeándose/cacheándose pero
    todavía sin `load` a la DB.
- Validación tras Conmebol (`python scripts/validate_elo.py`):
  - 0 duplicados `tm_match_id`, 0 partidos con suma ≠ 0.
  - Masa ELO 1.173.000 = 1000 × 1.173 → OK.
  - Cobertura: ARG2 3934, CLI 2366, AR1N 2116, CS 1834, CDLP 825, ARCA 543,
    CDCA 47, CLPD 240, RESU 32.
- `recompute` global ejecutado tras cada fase (determinista).
- **Fase 4 (Visualización) avanzada:** ya se generan las dos infografías
  publicables del plan, con la paleta de marca violeta/lila + celeste + blanco:
  - "Power Ranking de la Fecha" (PNG). Primera corrida real: ventana
    2024-12-11 → 2024-12-17, 15 partidos, en `data/output/power_ranking_2024-12-17.png`.
  - "Duelo de Pizarras" (PNG). Ejemplo: Gallardo vs Costas en
    `data/output/duelo_marcelo_gallardo_gustavo_costas.png`.
- **Scraping total — Fase 0 completada** (ver `PLAN_SCRAPING_TOTAL.md`): 51
  competencias verificadas (UEFA 25, CONMEBOL 22, CONCACAF 2, AFC 2), ventana
  2000–2026. Estimación: **~350.510 requests ≈ 297 h secuenciales**; plan
  recomendado 3 workers × 8 h/día ≈ **12,4 días**. Verificación: **49/51 OK**
  (EC1N y BO1A tienen cobertura parcial en TM → el guard los saltea). Las 51 ya
  están dadas de alta en `COMPETITIONS`.
- **Backfill por fases (en curso):**
  - **Argentina ✅ (2026-09-22):** scrape 2000-2026 (3 workers) + load + recompute
    + validate. **8.939 partidos**, 787 DTs, 0 duplicados, 0 suma≠0, masa OK.
    Cobertura: ARG2 3934, AR1N 2116, CDLP 825, ARCA 543, CDCA 47.
  - **Conmebol ✅ (2026-09-22):** CLI + CS (RESU ya estaba). **11.937 partidos**,
    1.173 DTs, validación OK. Cobertura: CLI 2366, CS 1834.
  - **Resto (corriendo 2026-09-25 20:14, cliente endurecido):** 43 ligas
    (UEFA/CONCACAF/AFC + Sudamérica faltante) en 3 workers balanceados.
    **Progreso real 2026-09-25: ~54.600 reportes cacheados de ~306.600 ≈ 17,8 %.**
    A ~14 req/min (rate nuevo anti-WAF) faltan **~252.000 requests ≈ 12-13 días
    24/7**. En curso: GB2, ES2, BRA2, BRA1, MLS1, GB1, IT1. Ver
    `PLAN_SCRAPING_TOTAL.md` §5. Reanudar con `bash scripts/backfill_resto.sh`
    en tmux. Script versionado en `scripts/backfill_resto.sh`.
  - TM sólo tiene las ligas argentinas/Conmebol desde ~2014-2015.

## Cambios de código de esta sesión (2026-10-27 — plan nuevo, T0.1)

1. `docs/plan/` (**nuevo**) — plan de trabajo dividido en fases y tareas
   (`00-INDICE.md`, `01-fase0-datos.md` … `07-fase5-mejoras.md`) más la
   referencia completa `aep-elo-pipeline.md`. El índice tiene la tabla de tareas
   con casillas, las reglas generales y las paradas humanas.
2. `scripts/backup_db.sh` (**nuevo**) — respaldo `pg_dump` en formato custom a
   `data/backups/aep_YYYYmmdd_HHMMSS.dump`, con `--verify` que restaura en una
   base temporal y compara `partidos_dt`. **Ojo:** el servidor es Postgres 18 y
   el `pg_dump` de WSL es 16, así que el script detecta la versión y usa el
   `pg_dump.exe` de Windows (`C:\Program Files\PostgreSQL\18\bin`), traduciendo
   rutas con `wslpath -w` y pasando `PGPASSWORD` vía `WSLENV` (sin eso el `.exe`
   se cuelga pidiendo contraseña). Verificado: dump de 5,1 MB y restauración con
   **191.931 partidos** en ambos lados.
3. `scripts/gitw.sh` (**nuevo**) + `git init` — el repo ahora tiene historial. El
   git de Linux **no funciona** en `/mnt/f` (drvfs sin chmod: falla al escribir
   `.git`), así que se usa el git de Windows a través de este wrapper. El repo
   quedó con `core.autocrlf=false`.
4. `.env.example` (**nuevo**) — claves de `.env` sin secretos.
5. `AGENTS.md` — comandos de respaldo y git + gotchas de versiones de Postgres,
   `WSLENV` y `chmod` en `/mnt/f`.

**Pendiente del usuario:** rotar `DB_PASS` (quedó expuesto en el log de una sesión).

## Cambios de código de la sesión anterior (2026-09-21)

1. `scraping/pipeline.py::build_schedule_url` — la URL del fixture ahora lleva
   `?saison_id=...&spieltagVon=1&spieltagBis=99`. Sin eso, la temporada más
   reciente devolvía solo 1 fecha (14 partidos en vez de 378).
2. `scraping/competitions.py` — nuevo campo `saison_offset` (1 para las 7
   competencias sudamericanas). `--season` ahora es el **año real** de temporada;
   Transfermarkt usa `saison_id = año − 1`.
3. `scraper_transfermarkt.py` — ayuda de `--season` actualizada.
4. `AGENTS.md` — gotchas de temporada/URL documentados.
5. `tests/test_pipeline.py` — 2 tests nuevos (offset + query string).
6. Caché migrada: `data/raw/AR1N/2023 → data/raw/AR1N/2024` (378 reportes preservados).

## Cambios de código de esta sesión (2026-09-22)

1. `ranking.py` — nueva capa de datos del **Power Ranking de la Fecha**:
   `compute_power_ranking(session, desde, hasta, dias=7, top=5, competencia_id)`
   agrega deltas de ELO por DT en una ventana (default: últimos 7 días hasta el
   último partido cargado), devuelve `PowerRanking` con `subidas`/`bajadas`.
   Incluye `resolve_window` y `resolve_competition_id`. Sin dependencias de dibujo.
2. `duel.py` — nueva capa de datos del **Duelo de Pizarras**: `compute_duel`
   agrega PJ/G-E-P/goles/forma por DT y el historial de enfrentamientos directos.
   `resolve_coach` acepta `dt_id` numérico o parte del nombre.
3. `visualization.py` — render matplotlib (backend Agg) de **ambas** infografías
   16:9 (1600×900), con la paleta de marca **violeta/lila + celeste + blanco**
   (`render_power_ranking`, `render_duel`). No toca la DB. Tipografías
   **Poppins** (cuerpo) y **Anton** (títulos y cifras), cargadas desde
   `assets/fonts/` (OFL) con fallback a DejaVu.
4. `scripts/power_ranking.py` — CLI: `--desde --hasta --dias --top --competition --output --title --handle`.
   Salida por defecto: `data/output/power_ranking_<hasta>.png`.
5. `scripts/duelo_pizarras.py` — CLI: `--dt-a --dt-b --forma --output --title --subtitle --handle`.
   Salida por defecto: `data/output/duelo_<a>_<b>.png`.
6. `tests/test_ranking.py` (5), `tests/test_duel.py` (5) y `test_pipeline.py`
   (alineación de temporada + `get_competition` case-insensitive) — **36 tests verdes.**
7. `requirements.txt` — se agregó `matplotlib>=3.8` (instalado localmente).
8. `scraping/leagues_catalog.py` — universo de **51** competencias del scraping
   total, con `saison_offset`, `est_matches`, `tier`, `first_season` y flag
   `verified`. Códigos verificados contra TM (incluye CLPD, TDeA/TDeC, BO1A/BO1C,
   VZ1A/VZ1C, MEX1, RESU).
9. `scraping/competitions.py` — `COMPETITIONS` se **autoextiende** desde el
   catálogo (las 7 a mano tienen prioridad).
10. `scraping/pipeline.py` — `season_is_aligned`: descarta fixtures de otra
    temporada (TM devuelve la actual si falta el `saison_id`).
11. `scripts/plan_scraping.py` — estima requests/tiempo y genera el plan diario
    por ligas (modelo de delay + latencia; export CSV opcional).
12. `scripts/verify_competitions.py` — smoke test del catálogo (OK/REVISAR/VACIO/
    FUERA/ERROR; valida que `min_year == season`).
13. `scraper_transfermarkt.py` — nuevo flag `--leagues A,B,C` para lotes diarios;
    `load` ahora **omite** temporadas sin fixture cacheado (antes abortaba el
    lote con `FileNotFoundError`).
14. `scraping/competitions.py::get_competition` — ahora **case-insensitive**
    (`tdea` → `TDeA`), necesario para los códigos mixtos de Perú.
15. `PLAN_SCRAPING_TOTAL.md` — el plan completo (universo, estimación,
    escenarios, calendario diario, fases, riesgos).
16. `scripts/backfill_resto.sh` — orquestador del "resto": 43 ligas en 3 workers
    balanceados + `load`/`recompute`/`validate` al final. Reanudable.

## Cambios de código de esta sesión (2026-09-28)

1. `scraping/waf.py` (**nuevo**) — `WafChallengeSolver`: lanza un Chromium
   headless (Playwright) contra la home, espera a que aparezca la cookie
   `aws-waf-token` y devuelve las cookies de sesión. Playwright se importa de
   forma perezosa (tests y entornos sin él siguen funcionando).
2. `scraping/client.py` — detecta el challenge AWS WAF (`_is_waf_challenge`,
   200/202/403 con marcadores `awswaf`/`gokuprops`/…); si hay `waf_solver` lo
   invoca, inyecta las cookies (`_apply_cookies`) y reintenta (hasta
   `max_waf_solves`). `warm_up()` también resuelve el reto. HTTP 403 sin
   marcadores sigue tratándose como bloqueo de IP (espera + reintenta).
3. `config.py` — nuevos `Settings`: `waf_solver` (`TM_WAF_SOLVER`, default
   `true`), `waf_headless` (`TM_WAF_HEADLESS`, `true`), `waf_wait_seconds`
   (`TM_WAF_WAIT`, 15 s), `max_waf_solves` (`TM_WAF_SOLVES`, 5); helper
   `_get_bool`.
4. `scraper_transfermarkt.py` — `build_client` construye el `WafChallengeSolver`
   cuando `TM_WAF_SOLVER` está activo.
5. `requirements.txt` — se agregó `playwright>=1.40` (`playwright install chromium`).
6. `AGENTS.md` — gotcha de CloudFront reescrito: 403 duro (ARSAT) vs 202
   challenge (VPN), resuelto con `WafChallengeSolver`.
7. **Verificado en vivo** (VPN activa): el navegador resuelve el reto y
   `curl_cffi` con `aws-waf-token` da **200**; `scrape --competition GB1
   --season 2023 --refresh --limit 3` bajó fixture (380) + 3 reportes OK.
   Los 36 tests siguen pasando.

## Cambios de código de esta sesión (2026-09-25)

1. `config.py` — `Settings` ahora incluye `blocked_wait` (`TM_BLOCKED_WAIT`,
   default 600 s) y `blocked_retries` (`TM_BLOCKED_RETRIES`, default 144).
2. `scraping/client.py` — HTTP **403** se trata como bloqueo temporal de IP:
   espera `blocked_wait` y reintenta hasta `blocked_retries` veces en vez de
   abortar; 429/5xx/red mantienen el backoff previo.
3. `scraper_transfermarkt.py` — `build_client` pasa los nuevos parámetros; un
   `RuntimeError` de una temporada ya no mata al worker (se omite y continúa).

### Endurecimiento anti-baneo (2026-09-25 noche)

1. `requirements.txt` — se agregó `curl_cffi>=0.7` (instalado: 0.16.3).
2. `scraping/client.py` — **reescrito**:
   - Usa `curl_cffi` con `impersonate="chrome124"` (huella TLS/HTTP de Chrome real);
     fallback a `requests` si falta la dependencia.
   - Headers de navegador + `Referer` encadenado (home → fixture → reportes).
   - `warm_up()` best-effort (un solo intento) para obtener cookies antes de scrapear.
   - Delay con jitter (default 6-12 s) y manejo de 403/429/5xx como antes.
3. `scraping/pipeline.py` — `scrape_season` pasa `referer` al pedir el fixture y
   cada reporte (navegación coherente, menos "bot-like").
4. `scraper_transfermarkt.py` — `build_client` pasa `impersonate` y `domain`;
   `cmd_scrape` llama a `client.warm_up()` antes de arrancar.
5. `config.py` — nuevo `Settings.impersonate` (`TM_IMPERSONATE`, default
   `chrome124`); delays default subidos a **6-12 s**.
6. `scripts/backfill_resto.sh` — exporta `TM_DELAY_MIN=8`/`TM_DELAY_MAX=18`
   (3 workers ≈ 14 req/min) para no volver a disparar el WAF.
7. `pytest.ini` — `testpaths = tests` (el `pytest` pelado escaneaba `data/` y se
   colgaba; ahora `python3 -m pytest` corre los 36 tests).

## Caveats / deuda conocida

- 93 reportes cacheados no se persistieron por `sin_dt` (DTs interinos/ausentes):
  `persist_matches` los omite a propósito. Revisar `coverage` por temporada si importa.
- Los clubes de competencias Conmebol se etiquetan con `pais="Conmebol"` (todos).
  No afecta al ELO, pero conviene corregir el país real si se usa para análisis.
- `CDCA` (playoffs) solo aporta 4 partidos/temporada; su `saison_id` funciona pero
  el volumen es bajo.
- No hay git en este directorio (no hay historial de commits).
- El ranking usa una **ventana móvil de 7 días** (no una "fecha" de calendario
  estricta); puede mezclar liga y copa. El filtro `--competition` lo separa.
- El "Duelo" agrega **todo el historial** del DT (no una temporada puntual).
- El PNG usa el `handle` de marca placeholder `@AEP_Analitica`: cambiarlo cuando
  se defina la cuenta real.
- Fuentes Poppins/Anton viven en `assets/fonts/` (licencia OFL). Si faltan, el
  render cae a DejaVu Sans sin romperse.

## Próximo paso propuesto

Seguir el plan `docs/plan/00-INDICE.md`, una tarea por sesión. Próximas:

1. **T0.2 — Auditoría de datos y cobertura** (`scripts/audit_data.py`): no
   necesita VPN; genera `data/audit/cobertura.json`, la lista de conflictos de
   fecha (152 casos) y el informe Markdown.
2. **T0.3 — Bug de fechas del fixture** (requiere VPN, pocas requests).
3. **T0.4 — Recuperar Argentina** (requiere VPN; parada humana al terminar).

## Comandos útiles para retomar

```bash
python3 -m pytest -q                                  # 36 tests (pytest.ini: testpaths=tests)
python3 scripts/validate_elo.py --min-partidos 20 --top 12
python3 scripts/power_ranking.py --top 6              # PNG en data/output/
python3 scripts/duelo_pizarras.py --dt-a Gallardo --dt-b Costas
python3 scraper_transfermarkt.py coverage --competition AR1N --season 2024
python3 scraper_transfermarkt.py recompute            # solo si se cambia la fórmula/coef.
tmux new -d -s aep-resto 'bash scripts/backfill_resto.sh'   # reanudar el resto (con VPN)
```

> **Scraping: requiere VPN activa + Chromium.** Con la IP de casa (ARSAT) hay
> 403 duro; con IPs de datacenter hay challenge JS de AWS WAF que resuelve
> `WafChallengeSolver`. Instalación: `pip install --user playwright && playwright install chromium`.
> Desactivar el solver con `TM_WAF_SOLVER=false`.

Caché de scrape: `data/raw/{code}/{season}/fixtures.json` y `matches/{id}.json`.
Salidas gráficas: `data/output/`. Log: `data/logs/ingest.log`.
