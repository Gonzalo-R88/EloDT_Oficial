# ESTADO DEL PROYECTO — handoff entre sesiones

Última actualización: 2026-11-19.

> **Marca (2026-11-10):** X **@EloDT_oficial**, correo elodt.oficial@gmail.com.
> Logo: `assets/brand/perfil.png` (generado con `scripts/logo.py`) y
> `assets/brand/Banner ajustado.jpg` (versión final del banner, hecha a mano por Gonzalo). El handle ya reemplazó al placeholder en todo el código.
>
> **Calendario (2026-11-10):** la semana se cierra el lunes. `semana_fin()` sin fecha, si hoy
> es domingo, devuelve el domingo anterior (si no, el paquete del domingo a la mañana saldría
> sin los partidos de ese día y el lunes se saltearía por estar "hecha"). Con fecha explícita
> el domingo se respeta, así `--semana-fin` no cambia de sentido.
>
> **Fecha FIFA (2026-11-17):** cuando hay una pausa de selecciones, el paquete de clubes
> queda flojo (en W46 salía un +9,7 y un −9,7 por un solo partido de Copa Argentina), así
> que ahora se publica **un paquete aparte** con los 5 seleccionadores que más subieron y
> bajaron. `selecciones.py` detecta la ventana sola (días con 6+ partidos de selecciones
> mayores, huecos de hasta 2 días), y `weekly_run.py selecciones` baja amistosos (`FS`, con
> filtro de juveniles) y torneos oficiales, carga, recalcula y publica en
> `data/output/fifa-<hasta>/`. Reglas: publica 2 días después del último partido
> (`DIAS_GRACIA_FIFA`) y **una sola vez** por ventana (marcador `summary.json`).
> `all --selecciones` (lo que llama `entrada_windows.sh`) corre las dos cosas. **No hay
> mínimo de partidos**: medido sobre selecciones desde 2022, el debut mueve el ELO lo mismo
> que cualquier partido (6,5 vs 6,6 de media); a quien tiene menos de 5 partidos se lo
> etiqueta "debutante". **Pendiente:** backfill de amistosos 2015-2025 + `recompute` (los
> niveles de los seleccionadores quedan incompletos hasta entonces) y revisar los
> walkovers (Nueva Zelanda-India aparece como resultado normal).
>
> **Contenido semanal (2026-11-17):** los textos ya no anuncian el día ("actualizado cada
> semana", `captions.CIERRE`). **Subieron y cayeron** se omite si hay menos de 3 subidas o 3
> bajadas (`content.MIN_MOVERS`; en fecha FIFA quedaba un +x y un -x) y el sugerido salta al
> siguiente formato disponible. **DT revelación** sólo entre `content.LIGAS_REVELACION`
> (ARG1/ARGC/AR1N, BRA1, GB1, ES1, IT1, L1, FR1, NL1, PO1), con 30+ partidos y sin repetir a
> quien salió en las últimas 8 semanas (`summary.json` guarda `elegidos`). **Pendiente
> (optativo):** en fecha FIFA publicar un formato de selecciones; el **Duelo** también sale
> flojo esas semanas (W46: Mirassol vs Mineiro, 2275 de ELO combinado).
>
> **Técnicos sin club (2026-11-19):** ranking bajo demanda de DTs libres cuyo último
> club fue argentino. `python3 scripts/weekly_run.py sin_club [--sin-envio]` genera
> `data/output/sin-club-<fecha>/` con la imagen (3 variantes), el texto para X y el alt.
> No toca la red: lee la base como está. Quedan afuera los que no dirigieron en los
> últimos 365 días (`--dias`), así que no aparecen técnicos con más de un año sin
> dirigir. El último club no se muestra: la segunda línea dice los partidos dirigidos.
> El ELO es el acumulado de la base (desde 2000), no un rendimiento de los últimos dos
> años.
>
> **Entrega por Telegram (2026-11-10):** un post por bloque — imagen apaisada con la
> leyenda `POST i de N · <nombre> · X + LinkedIn`, y después el texto y el alt en bloque
> monoespaciado para copiar. **Un solo texto por pieza** (≤280, sirve para X y LinkedIn),
> sin hashtags, sin "Transfermarkt" y sin el handle (va en el pie de la imagen). El Top 10
> mundial ya no se titula "de Argentina" y el duelo ya no sale como "DT A vs DT B".
> Verificado enviando el paquete de 2026-W44: 5 imágenes + 6 mensajes.
>
> **PLAN DE TRABAJO VIGENTE:** `docs/plan/00-INDICE.md` (índice de tareas T0.1…T5.5, con
> reglas generales, paquetes sugeridos y paradas humanas) y los archivos `01`…`07` por fase.
> Se ejecuta **una tarea por sesión**, marcando la casilla en el índice.
> Hechas: **T0.1-T0.6, T1.1-T1.7, T2.1-T2.5, T3.1-T3.8 y T4.1-T4.4** (+ la Recopa y la
> recuperación de partidos sin DT, que no estaban en el plan). **Siguiente: Fase 5** —
> T5.1 (coeficientes por liga) es la primera sin dependencias del usuario.
> Los pendientes del usuario viven en `docs/plan/PENDIENTES.md`.
>
> **Estado de la base (2026-11-04):** 215.099 partidos, 8.002 DTs, 2000-2026 + selecciones.
> `validate_elo.py` en verde: masa 8.002.000 = 8.002 × 1.000, 0 duplicados tm_id, 0 partidos
> con suma ≠ 0. 181 tests verdes. Último update: run 8 de `ejecuciones_pipeline`,
> 1.628 partidos nuevos, 0 errores de scraping.
>
> **Pipeline completo:** `python3 scripts/weekly_run.py all` = update + render + notify.
> Lo dispara **n8n nativo en Windows** (`n8n-AEP` al iniciar sesión; workflow `AEP — paquete
> semanal`, lunes 08:00 + cada 4 h) con `--skip-if-done-this-week`, y la tarea `AEP-Semanal`
> del Programador de tareas (diaria 09:00) queda como respaldo idempotente. Ver
> `docs/automatizacion_semanal.md`.
>
> **n8n:** primero se probó en Docker y no servía (el contenedor no ve WSL ni Python); el
> contenedor quedó detenido y se instaló nativo con el Node de `F:\Doom\LLM` (v2.46.6).
> Trampas documentadas: `NODES_EXCLUDE=[]`, `publish:workflow` + reinicio, no setear
> `N8N_USER_FOLDER` en los imports, y desde WSL usar `http://winhost:5678`.

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

## Cambios de código de esta sesión (2026-10-27 — plan nuevo, T0.1 y T0.2)

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
5. `AGENTS.md` — comandos de respaldo, git y auditoría + gotchas de versiones de
   Postgres, `WSLENV` y `chmod` en `/mnt/f`.
6. `auditoria.py` (**nuevo**) — capa de datos de la auditoría (misma separación que
   `ranking.py`/`duel.py`): cobertura por competencia y **año calendario**, huecos
   (`ratio = 0`), conflictos de fecha por DT-día, últimos partidos y estimación de
   reportes sin DT por quinquenio. Sin escritura ni dibujo.
7. `scripts/audit_data.py` (**nuevo**) — CLI: escribe `data/audit/cobertura.json`
   (`{codigo: {anio: {fixtures, cargados, ratio}}}`), `conflictos_fecha.json` y
   `auditoria_<fecha>.md`. Sin `--muestra` tarda ~7-16 s.
8. `tests/test_audit_data.py` (**nuevo**, 13 tests) — **49 tests en total, verdes.**
9. `docs/plan/PENDIENTES.md` (**nuevo**) — registro de lo que depende del usuario
   (acciones y decisiones), con cuándo se pide cada cosa.
10. **T0.3 — fechas (NUEVO).** La fecha del fixture no es confiable: TM imprime la
    fecha una sola vez por bloque y el bloque puede abarcar varias jornadas. Ahora
    `scraping/parser.py::parse_report_date` saca la fecha exacta de la página del
    partido (`p.sb-datum` → `/datum/AAAA-MM-DD`), queda en `MatchReport.fecha` y
    `load_normalized` la prefiere sobre la del fixture. `scripts/fix_fechas.py`
    (**nuevo**: `--fetch` / dry-run / `--apply`) re-descarga solo los reportes
    necesarios y corrige `partidos_dt.fecha`. `tests/test_fix_fechas.py` (**nuevo**,
    4 tests) y 5 tests más de parser/pipeline → **59 tests verdes**.
    `docs/CONFLICTOS_FECHA.md` (**nuevo**) explica el defecto y los casos restantes.
11. **T0.6 — país de los clubes (NUEVO).** `ensure_club` guardaba el país de la
    **competencia**: para Libertadores/Sudamericana eso es "Conmebol", así que 254
    clubes quedaban con `pais="Conmebol"` y el filtro "DT de Argentina" devolvía 3 en
    vez de ~146. Ahora un club nace como `desconocido` si la competencia es
    internacional, se autocorrige al jugar una liga doméstica, y
    `scripts/fix_club_country.py` (**nuevo**, dry-run + `--apply`, idempotente) asignó
    el país según la liga doméstica donde el club más juega (+6 tests). Resultado:
    **0 clubes "Conmebol"**, 12 quedan `desconocido` (sólo jugaron torneos
    internacionales) y hay **146 DTs activos con club argentino** (107 con ≥15 PJ).
    `ensure_competition` ahora sincroniza nombre/país/tipo desde el catálogo (nunca
    `nivel`/`coeficiente`, que necesitan `recompute`). ELO intacto (masa 6.732.000).
12. **Hallazgo: `RESU` no es la Recopa Sudamericana.** En TM es **"Relegation
    Superettan"** (playoffs suecos de noviembre). Estaba en el catálogo como
    competencia internacional de Conmebol, y por eso clubes suecos figuraban como
    "Conmebol". Reclasificada como copa sueca de tier C (coef 0,60) en el catálogo y
    en la DB.
13. **Bug del parser con los reportes viejos (importante).** Las páginas antiguas no
    tienen `tr.bench-table__tr`: los técnicos están en el encabezado de cada equipo
    (`div.box`). `_parse_coaches` sólo miraba el layout nuevo, así que **descartaba
    partidos con DT presente en la página** (`sin_dt`). Ahora lee el DT por fila del
    banco (fila 0 local, fila 1 visitante) y cae a `div.box` si la página es vieja, y
    **no adivina el lado cuando hay un solo DT** (antes lo asignaba al local y podía
    invertir el resultado). Medición sobre 36 reportes "sin DT": **89 % recupera ambos
    entrenadores**. `scripts/refetch_reportes.py` (**nuevo**) permite re-descargar los
    afectados (`--sin-dt --desde 2015 --hasta 2026 --codes ... --apply`).
    **Decisión del usuario (2026-10-28):** recuperar **2012-2026 = 8.932 partidos**
    (`scripts/backfill_dts.sh`, 3 workers, ~9-10 h). Pre-2015 queda para T0.9
    (imputación por etapas, sin requests).
    **Resultado (28-oct, tras un reinicio de la PC y reanudación):** 8.932 re-descargados
    (3.363 en la segunda tanda), **7.720 partidos nuevos cargados** → base de
    **203.064 partidos** y **6.806 DTs**, `validate_elo.py` en verde (masa 6.806.000).
    Cobertura 2012-2026: **94,6 %-100 % por año** (2013 en adelante ≥99 %). Los
    conflictos de fecha subieron de 25 a **32** (todos rarezas de TM, no de parseo). `persist_matches` ganó un fast-path: saltea
    los `tm_match_id` ya cargados antes de hacer consultas por partido, así la recarga
    de una temporada entera tarda segundos.
14. **Fase 1 del modelo (T1.2, T1.3, T1.4, T1.1).** `elo.py` tiene `EloParams`
    (ventaja de local, modos de MOV: `actual`/`cap`/`amortiguado`, calibración de DTs
    nuevos y regreso tras inactividad) y `match_calibracion`; con `EloParams()` los
    números son **idénticos** a los de antes. `services.recompute_all_elo` acepta
    `params` y aplica la calibración cuando `calibracion_n > 0` (sigue siendo suma
    cero y conserva la masa). `infer_factor_k` ahora reconoce las rondas reales de TM
    ("First/Second Round", "Play Off", "Playoffs", "Qualifying Round"...);
    `scripts/refresh_factor_k.py` recategorizó **1.717 partidos de K=20 a K=30** (ahora
    2.835 con K=30 y 116 con K=40) y se recalculó. `backtest.py` +
    `scripts/backtest_elo.py` (**nuevos**) reproducen el histórico en memoria (203 mil
    partidos en ~1,8 s) y miden Brier del resultado, Brier y log-loss 1X2, calibración
    por tramos de E, y desglose por año y nivel.
    **Línea base reproducida:** 45.323 partidos (2021+, ambos DTs con ≥30 PJ):
    **Brier 0,1638** (constante 0,1782). Primeras señales: `hfa=55` baja a 0,1624;
    `mov amortiguado` a 0,1629; ambos juntos a **0,1616** (log-loss 1,0370 vs 1,0441).
    Esas señales se confirman o descartan en T1.5. **113 tests verdes.**
15. **Selecciones nacionales (2026-10-29, pedido del usuario).** La base sólo tenía
    clubes: un DT que dirigía una selección aparecía como "sin trabajo" (Ancelotti,
    que dirigió Brasil hasta el Mundial 2026, figuraba inactivo desde mayo de 2025).
    - Migración **003**: `competencias.tipo` admite `'selecciones'` y `clubes.tipo`
      distingue `'club'`/`'seleccion'`. Ya aplicada en la base.
    - `publicacion.py`: un DT de selección no compite en el ranking de clubes y **no**
      es "sin trabajo" (`en_seleccion=True`).
    - Catálogo: FIWC, COPA, EURO, AFCN, AFAC, GOCU, **UNLA/UNLB/UNLC/UNLD/UNFI**
      (Nations League) y las eliminatorias (WMQ1-4, WMQ6, POWM, EMQ, AFCQ, ACQU, GCQU).
    - **El `saison_id` de estas competencias no sigue una regla fija** (Copa Oro 2023
      vive en 2022, Asiática 2024 en 2022, Euro 2024 en 2023, Copa América 2024 en
      2024) y si el año no existe TM devuelve la última edición. Por eso
      `scripts/backfill_selecciones.sh` usa `scripts/scrape_ediciones.py`, que recorre
      los `saison_id`, deduplica y cachea cada edición bajo el año de su primer partido.
    - **Torneos cargados:** +2.005 partidos (AFCN 491, FIWC 488, GOCU 340, EURO 246,
      AFAC 224, COPA 216), base en **205.069 partidos / 7.082 DTs**. `validate_elo` en
      verde. Ancelotti quedó con partidos del Mundial y `en_seleccion=True`.
    - **Eliminatorias + Nations League: TERMINADO (2026-11-03).** 21 competencias de
      selecciones, **10.404 partidos**: WMQ6 1.738, EMQ 1.484, WMQ1 1.155, WMQ2 1.091,
      WMQ3 807, WMQ4 608, AFCN 491, FIWC 488, ACQU 391, GOCU 340, AFCQ 253, EURO 246,
      AFAC 224, UNLC 218, COPA 216, UNLA 199, UNLB 193, UNLD 104, POWM 83, GCQU 51,
      UNFI 24.
    - **Base final: 213.468 partidos · 7.979 DTs · 209 selecciones.** `validate_elo` en
      verde (masa 7.979.000, 0 duplicados, suma cero); conflictos de fecha 44 del todo
      (rarezas de TM, ver `docs/CONFLICTOS_FECHA.md`).
    - **Dos errores propios corregidos en el camino:** `POWM` faltaba en el catálogo y
      tumbó un worker (se agregó), y `scrape_ediciones.py` ahora omite un código
      desconocido en vez de abortar el lote. El backfill total se cortó dos veces por
      reinicios de WSL: es reanudable y no perdió trabajo.
16. **T1.5 + T1.7 — modelo ELO v2 adoptado (2026-10-29).** Búsqueda de parámetros con
    entrenamiento 2016-2022 y validación 2023-2026 (`scripts/tune_elo.py`, CSV en
    `data/audit/tune_elo.csv`); protocolo, resultados y alternativas en
    `docs/MODELO_ELO.md`. **Decisión del usuario:** localía **45** (antes 30) y margen
    de victoria **amortiguado**. Aplicado en `elo.py` (`HOME_ADVANTAGE = 45`,
    `mov_mode="amortiguado"` por defecto, `MODELO_VERSION = "elo-v2"`) y recalculados
    los 203.064 partidos: `validate_elo.py` en verde (masa 6.806.000). Documentado:
    la calibración de DTs nuevos **no mejora** la predicción (queda implementada y
    apagada) y calcular desde 2000 en vez de 2015 no cambia las predicciones (0,0002),
    así que se conserva todo el historial. Comparación de rankings en
    `data/audit/ranking_antes_despues.md` (correlación 0,9981; los ratings bajan en
    bloque ~70-85 puntos porque la goleada amortiguada mueve menos).
17. **T0.5 — reglas de publicación (NUEVO).** `publicacion.py` (**nuevo**) es la única
    fuente de verdad de "esto se publica": `es_publicable(dt)` / `estado_publicacion()`
    combinan (1) mínimo de partidos (15; 5 para interinos), (2) actividad (jugó en los
    últimos 365 días), (3) la liga doméstica del club actual y (4) su cobertura
    (`data/audit/cobertura.json`, ≥90 % en los últimos 3 años). Etiqueta "provisorio"
    entre 15 y 29 PJ; los interinos (5-14) sólo van a "subidas y bajadas". Umbrales en
    `config.py` (`RANKING_MIN_PJ`, `PROVISORIO_PJ`, `INTERINO_MIN_PJ`, `ACTIVO_DIAS`,
    `COBERTURA_MIN`, `COBERTURA_ANIOS`, `COBERTURA_JSON`). `scripts/publicables.py`
    (**nuevo**) muestra quién entra y por qué no. `tests/test_publicacion.py` (**14
    tests**, 87 en total).
    **Corrección del mismo día (pedido del usuario):** el ranking se arma **por club
    y con su DT actual**, no por DT suelto. `dt_actual_por_club()` define "DT actual"
    como el técnico del último partido del club; `ranking_por_club()` devuelve una fila
    por club. Así no aparecen técnicos desactualizados (Quinteros en Independiente,
    Gallardo en River) ni dos DTs del mismo club (Boca mostraba a Arruabarrena y
    Úbeda). Los DT que dirigieron en el último año pero hoy no tienen club quedan
    marcados `sin_trabajo` (398) para el futuro ranking de técnicos libres.
    **Números reales (2026-10-29):** 6.806 DTs evaluados, **715 publicables** (56
    provisorios), 81 interinos, 398 sin trabajo. Excluidos: 3.736 inactivos, 1.804 con
    pocos partidos, 398 sin club actual, 67 por cobertura baja, 5 sin liga doméstica.
    **Cobertura baja:** BO1A y EC1N no es que se hayan descartado partidos: esas
    temporadas **no existen en TM bajo esos códigos** (BO1A 2024 y EC1N 2022-2024
    devuelven la temporada actual). **Cambio del 29-oct (decisión del usuario):** la
    cobertura ahora se mide **por país**, sumando todas las ligas (Apertura y Clausura
    son competencias separadas) y ponderando por partidos. BO1A pasa de 0,667 a 0,986
    y EC1N a 1,0 (sus años existentes están completos). Resultado: **743 publicables**
    (Bolivia 15, Ecuador 14, Argentina 72 clubes), 430 sin trabajo, y ya no hay
    excluidos por cobertura. La auditoría sigue mostrando la cobertura **por
    competencia** (para ver huecos reales de TM).
18. **Recopa Sudamericana real: código `RECO`.** Verificado contra TM (saison_id
    2024 = Racing 2-0 Botafogo, 2025 = Lanús 1-0 Flamengo). Alta en el catálogo con
    `first_season=2003` (no se jugó 2000-2002), `kind="internacional"`, offset 1.
    Backfill 2003-2026: **39 partidos** cargados. Base: **195.338 partidos**,
    **6.734 DTs**, `validate_elo.py` en verde, conflictos de fecha 25.
    Faltan en TM las ediciones 2007, 2009 y 2010 (ratio 0 en la auditoría).
19. **T0.4 — Argentina (NUEVO).** Ver `docs/ARGENTINA_COBERTURA.md`. Tres causas
    distintas: (a) el guard de temporada descartaba las temporadas agosto-junio
    (bug, corregido: ahora acepta la temporada si cae dentro del rango de fechas);
    (b) TM cerró `AR1N` en 23/24 y desde 2025 la Primera va como **`ARG1`** (Torneo
    Apertura) y **`ARGC`** (Torneo Clausura), dados de alta con `first_season=2025`;
    (c) `CDLP` dejó de jugarse en 2024. Nuevo campo `LeagueCandidate.last_season`
    (AR1N y CDLP en 2024) para no reportar huecos falsos ni pedir temporadas que
    ya no existen. `scripts/verify_competitions.py` ganó `--no-align-check`,
    `--saison-offset` y `--path`. `scripts/backfill_argentina.sh` (**nuevo**).
    **Resultado:** ~3.500 requests en ~5 h → base de **195.299 partidos** y
    **6.732 DTs** (+3.368 partidos), `validate_elo.py` en verde, conflictos de
    fecha sin cambios (25). Cobertura argentina 2017-2020 recuperada (0,98-1,00)
    y 2025-26 nueva (0,99-1,00). 62 tests verdes.
20. **Resultado de T0.3:** 669 páginas de partido re-descargadas (~2 h en `tmux`),
    **187 fechas corregidas**, `recompute` + `validate_elo.py` en verde. Los conflictos
    de DT-día bajaron de **152 a 25**, y los 25 restantes no son de fecha: son errores
    de atribución de TM (20 del mismo DT en dos clubes de la misma jornada, 3 en ligas
    distintas, 1 club con dos partidos el mismo día, 1 partido duplicado en dos
    competencias). Los rankings de punta no se movieron.

**Resultado de la auditoría (2026-10-27, `--muestra 3000`):**
- 261.194 fixtures cacheados (26 sin fecha usable) vs **191.931 cargados** → hay
  191.931 filas en la base: todas vienen del caché. Cobertura global 73,5 %.
- **152 conflictos de fecha** (unchanged, se atacan en T0.3).
- **Argentina:** `AR1N` con 2017-2020 y 2025-26 en **0 %**; `ARG2` con 2017-2020 en 0 %;
  `CDLP` con 2025-26 en 0 %. `ARG2` 2015 (65 %) y 2016 (85 %) incompletos.
  `AR1N` no tiene partidos desde 2024-12-17 (679 días).
- 24 competencias con algún año en hueco. Reportes sin algún DT por quinquenio:
  2000-04 65 %, 2005-09 67 %, 2010-14 28 %, 2015-19 8 %, 2020-24 0,6 %, 2025+ 0 %.

**Pendiente del usuario** (ver `docs/plan/PENDIENTES.md`): rotar `DB_PASS`.

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

## Sesión 2026-11-02/03 — imágenes y snapshots

**T2.1/T2.2 (snapshots):** migración 004 (`snapshots_elo` + `ejecuciones_pipeline`),
`snapshots.py` y `backfill_snapshots.py`. **52 snapshots semanales** (86.397 filas); el
último coincide exactamente con `entrenadores.elo_actual`.

**T3.1 a T3.8 (contenido e imágenes):**
- `content.py`: `top_n` (uno por club con su DT actual y ▲▼ vs el snapshot previo),
  `top_por_pais`, `movers` (interinos etiquetados), `duelo_de_la_semana`,
  `revelacion` (menos de 2 años y mayor suba en 90 días) y `serie_elo`/`polilinea`
  para el gráfico del duelo.
- `render_html.py`: Jinja2 + Chromium; variantes portrait/landscape/square/story;
  **falla si el contenido no entra en el lienzo** (una imagen cortada no se publica).
- Plantillas: `top10.html`, `movers.html`, `duelo.html` (con gráfico SVG) y
  `revelacion.html`, sobre `base.css` (paleta y fuentes de la marca).
- `captions.py`: LinkedIn / X (≤280 con recorte) / Instagram / alt text.
- `scripts/weekly_run.py render`: genera `data/output/YYYY-Www/` con 15 PNG (5 formatos
  × 3 variantes), `post.md` y `summary.json`; rota el formato sugerido por semana ISO.
  `preflight`/`update`/`notify`/`all` quedan para las fases 2 y 4.
- 159 tests verdes.

**Corte por tormenta (2026-10-29 ~21:00):** el backfill de eliminatorias + Nations
League quedó **pausado a propósito** (procesos detenidos, caché íntegro: 0 JSON
corruptos, base en 205.069 partidos con masa 7.082.000 OK). Reanudar con:

```bash
cd /mnt/f/ProyectoDT && tmux new -d -s aep-eli 'bash scripts/backfill_eliminatorias.sh'
```

Es reanudable: saltea los reportes ya cacheados (WMQ4 tenía 4 temporadas, EMQ 2,
WMQ1 4). Al terminar encadena load → recompute → validate → audit.

Después, lo que queda de la Fase 1 y el contenido:

Los datos y las reglas de publicación están listos. Sigue la **Fase 1 (modelo ELO v2)**,
toda sin VPN:

1. **T1.2 — `EloParams` retrocompatible.** Parametrizar HVA, K, MOV, calibración e
   inactividad sin cambiar el comportamiento actual (los tests viejos deben pasar).
2. **T1.4 — K de eliminatorias.** `infer_factor_k` casi nunca dispara (99,4 % de los
   partidos con K=20); mapear los textos reales de `matchday` y refrescar desde el caché.
3. **T1.1 — Harness de backtest.** Reproducir la línea base (Brier ≈ 0,1637 en 2021+).
4. **T0.7 → T0.8 → T0.10** (Fase 0b, con VPN) quedan para cuando haya hueco: etapas de
   DTs (imputación pre-2015) y UEFA.

## Comandos útiles para retomar

```bash
python3 -m pytest -q                                  # 73 tests (pytest.ini: testpaths=tests)
python3 scripts/validate_elo.py --min-partidos 20 --top 12
python3 scripts/audit_data.py                         # cobertura + conflictos (sin VPN, ~15 s)
python3 scripts/power_ranking.py --top 6              # PNG en data/output/
python3 scripts/duelo_pizarras.py --dt-a Gallardo --dt-b Costas
python3 scraper_transfermarkt.py coverage --competition AR1N --season 2024
python3 scraper_transfermarkt.py recompute            # solo si se cambia la fórmula/coef.
bash scripts/backup_db.sh --verify                    # respaldo + prueba de restauración
bash scripts/gitw.sh log --oneline | head             # git de Windows (el de WSL no sirve en /mnt/f)

# Con VPN - todo en tmux y reanudable:
bash scripts/backfill_argentina.sh                    # AR 2017-2020 + ARG1/ARGC 2025-26
bash scripts/backfill_dts.sh                          # recuperar partidos sin DT (2012-2026)
python3 scripts/refetch_reportes.py --sin-dt --codes RECO --apply
python3 scripts/fix_fechas.py --bloques --apply       # corregir fechas desde el reporte
```

> **Scraping: requiere VPN activa + Chromium.** Con la IP de casa (ARSAT) hay
> 403 duro; con IPs de datacenter hay challenge JS de AWS WAF que resuelve
> `WafChallengeSolver`. Instalación: `pip install --user playwright && playwright install chromium`.
> Desactivar el solver con `TM_WAF_SOLVER=false`.

Caché de scrape: `data/raw/{code}/{season}/fixtures.json` y `matches/{id}.json`.
Salidas gráficas: `data/output/`. Log: `data/logs/ingest.log`.
