# Plan AEP: ELO de entrenadores + pipeline semanal automatizado

Proyecto: `/mnt/f/ProyectoDT` (WSL `Ubuntu-24.04`, también `F:\ProyectoDT` en Windows).
Plan elaborado el 2026-10-27. Lo ejecuta un modelo en modo Build. Leer antes `AGENTS.md` y `ESTADO.md`.

Convenciones del repo que hay que respetar:
- Python 3.12, SQLAlchemy 2.0, Postgres. Nombres de dominio en español (`dt_id`, `partidos_dt`, `goles_local`...).
- Docstrings y comentarios en español.
- Tests: `python3 -m pytest` desde la raíz (nunca `pytest` pelado, escanea `data/` y cuelga). Usan SQLite en memoria, sin Postgres.
- Migraciones: SQL plano en `migrations/`, idempotentes, orden numérico. `Base.metadata.create_all` NO crea columnas generadas ni lo agregado por SQL; los `.sql` son la fuente de verdad de la DB.
- Tras cambiar la fórmula ELO o un coeficiente: `recompute`, no re-scrapear.
- Scraping: requiere VPN + Chromium (Playwright). Ritmo máximo ~14 req/min (3 workers, delay 8-18 s). No subirlo. Ante 403 esperar `TM_BLOCKED_WAIT`. Ante CAPTCHA (HTTP 405, `Human Verification`) cambiar de servidor VPN.
- Postgres corre en el host Windows (`DB_HOST=winhost`). El `.env` es local y está en `.gitignore`.

---

## 1. Decisiones del usuario (cerradas)

| Tema | Decisión |
|---|---|
| Prioridad de contenido | Argentina primero, global después. |
| Scraping | VPN gratuita + `WafChallengeSolver`. Sin API paga (no aceptan gastar ~USD 20/mes). |
| Dónde corre | PC local del usuario. Si estaba apagada el lunes, corre la próxima vez que se encienda. |
| Qué se publica | Solo lo fiable (ver regla `publicable`, tarea T0.5). |
| Mínimo para aparecer en rankings | 15 partidos. |
| Interinos | Se muestran: los de menos de 15 partidos aparecen solo en "subidas y bajadas", con etiqueta "interino/provisorio" y mínimo 5 partidos. En Top 10 solo con 15 o más. |
| Uso | Marca personal (no se monetiza). |
| Publicación | Lunes. Un post por semana al inicio; se puede ampliar. |
| Herramientas | n8n (instalado en Windows, aún NO instalado) + Telegram. |
| Datos históricos | Se arreglan; no se recorta el modelo a "desde 2015" salvo que el experimento de sensibilidad (T1.5) lo justifique. |
| Marca | Se sigue con el handle placeholder `@AEP_Analitica` hasta definirla. |
| Capa de ELO ajustado por plantel | Deseada, depende de la dificultad (evaluada como media-baja): se hace como experimento (T1.8-T1.10). |
| Distro WSL | `Ubuntu-24.04` (WSL2). Node disponible solo en Windows: `F:\Doom\LLM\node.exe` v24.21.0. No hay Docker ni n8n instalados. |

---

## 2. Estado encontrado (línea base)

- Base `aep_football_analytics`: 191.931 partidos, 6.686 DTs, 1.470 clubes, 51 competencias; rango 2000-05-04 a 2026-10-08 (19 días de atraso al 2026-10-27).
- Invariantes OK: sin duplicados de `tm_match_id`, suma cero por partido, masa ELO = 6.686 × 1000. 36 tests verdes.
- ELO actual (`elo.py`): K en {20,30,40}, coeficiente C por nivel (S 1,3 / A 1,0 / B 0,8 / C 0,6), ventaja local fija +30, MOV (1,0 / 1,5 / (1,75+d)/3), inicial 1000, suma cero. 99,4 % de los partidos tiene K=20.
- `partidos_dt` guarda `elo_*_previo` y `elo_*_nuevo` por partido (de ahí se puede reconstruir el historial). No hay snapshots semanales.
- Ranking top actual (>=100 PJ): Arteta, Flick, Guardiola, Klopp, Kompany, Heynckes, Inzaghi, Jorge Jesus, Ancelotti. Plausible.
- Backtest preliminar (2021+, 43.296 partidos con ambos DTs >=30 PJ previos), Brier del resultado esperado: constante 0,1783; HFA 0 -> 0,1681; HFA 30 -> 0,1637; HFA 60 -> 0,1622; HFA 90 -> 0,1635. HFA empírico por tipo: liga ~51, copa ~53, internacional ~70.

Problemas, por gravedad:

1. **Argentina incompleta.** `AR1N` solo tiene 2015-16 y 2021-24 (termina 2024-12-17). `ARG2` falta 2017-2020. `CDLP` termina 2024-04. El caché y los logs muestran que `AR1N/ARG2/CDLP` de 2017-2020 y `AR1N/CDLP` 2025-26 fueron descartados por el guard `season_is_aligned` ("TM devolvió otra temporada"). Hipótesis: (a) cambios de formato/códigos en TM (Superliga, Copa de la Liga 2020, Apertura/Clausura 2025) y pandemia 2020; (b) posible falso positivo del guard en temporadas agosto-junio (2016/17-2019/20), porque exige `min(año de fechas) == temporada pedida`. Sin diagnosticar.
2. **27 % de reportes cacheados descartados por falta de DT** (261.194 fixtures cacheados vs 191.931 cargados). Muestra de 3.000 reportes: sin algún DT en 58 % (2000-04), 62 % (2005-09), 24 % (2010-14), 6 % (2015-19), <=1 % (2020+). Ej.: GB1 con 31-370 partidos/año hasta 2008; BRA1 casi vacío antes de 2012. `persist_matches` omite el partido entero si falta un DT.
3. **Fechas corruptas:** 152 casos de un DT con más de un partido el mismo día (hasta 5, p. ej. Alianza Lima 2006-07-30, `TDeC`, `tm_match_id` 4472725/4472729/4472733/4472743/4472748). Sospecha: forward-fill de fecha en `parse_schedule`. Causa no confirmada.
4. **Faltan competencias UEFA** (Champions, Europa, Conference) y copas domésticas europeas. Ancelotti, Guardiola, Mourinho, Simeone tienen 12-44 partidos/año de liga, sin copas.
5. **HFA mal calibrado** (30 vs ~55-60 empírico).
6. **K casi constante**, sin calibración para DTs nuevos; la detección de eliminatorias de `infer_factor_k` casi nunca dispara (1.099 partidos con K != 20).
7. **Sin historial semanal** ni versionado del modelo.
8. **Datos de DT pobres:** `nacionalidad` y `fecha_nacimiento` 100 % nulos; 119 DTs con apellido `-` (se ve "Xavi -" en el ranking); 35 nombres repetidos con distinto id; 254 clubes con `pais="Conmebol"` (incluye clubes argentinos creados desde torneos internacionales).
9. **Operación frágil:** sin git; `ESTADO.md` con sección "Dónde estamos" desactualizada; el `DB_PASS` quedó expuesto en un log de sesión (recomendar rotarlo).
10. **Infografía actual** (`visualization.py`, matplotlib, 1600x900, Top 5 y 5, mezcla ligas y copas) sirve de base visual pero es de un solo formato.
11. Otras ligas con coberturas bajas respecto del fixture cacheado: VZ1C 26 %, COL1 48 %, MEX1 48 %, VZ1A 49 %, FR2 50 %, UKR1 53 %, BRA1 54 %, TS1 54 %, NL1 59 %, GR1 60 %, PL1 61 %, SC1 62 % (carga/fixture; por DT faltante, mayormente pre-2015).

Nota: desde WSL sin VPN, TM respondió HTTP 202 (challenge JS) el 2026-10-27, no el 403 duro que documenta `ESTADO.md`. Posible que el baneo de la IP de casa se haya levantado. No asumirlo: `preflight` lo prueba; mantener VPN por prudencia.

---

## 3. Modelo ELO v2 (especificación)

Principio: evolucionar lo existente; cada cambio se adopta solo si mejora el backtest. Todo parametrizado en un `EloParams` (T1.2) con defaults = comportamiento actual.

| Tema | Especificación |
|---|---|
| Rating inicial | 1000. |
| Calibración (DTs nuevos) | Multiplicador por DT `m = 1 + max(0, (30 - n) / 30)` (n = partidos previos): 2,0 en n=0, 1,0 desde n=30. El K efectivo del partido usa el **promedio de m de ambos DTs** (preserva suma cero y conservación de masa). |
| Etiqueta "provisorio" | DTs con 15 a 29 partidos. |
| K base | 20 liga; 30 eliminatorias; 40 finales (arreglar detección, T1.4). Más el multiplicador de calibración. |
| Ventaja de local | Un solo valor global ajustado por grilla en {45, 55, 60, 65, 75}. Configurable. |
| MOV | Probar 3 variantes: (a) actual, (b) actual con tope 2,0, (c) amortiguada por favorito (estilo FiveThirtyEight: `ln(|d|+1) * 2.2 / (diff_elo_ganador * 0.001 + 2.2)`). Elegir por backtest. |
| Rival | Capa A (cabecera pública): ELO DT vs ELO DT, como hoy. Capa B (experimento): ver abajo. |
| Competencias | Coeficientes por nivel (existentes). Amistosos y selecciones fuera. Se suma UEFA (T0.10). Coeficientes empíricos entre ligas: Fase 5. |
| Interinos / cambios de club | El rating pertenece a la persona y viaja entre clubes. Si falta un DT en un partido y no se puede imputar (T0.9), se descarta el partido (no se usa DT fantasma: rompe conservación de masa). |
| Inactividad | No se degrada el rating guardado. "Activo" = jugó en los últimos `ACTIVO_DIAS=365`. Al volver tras >=12 meses sin partidos, se trata como si tuviera 15 partidos previos (m = 1,5). |

**Capa B (ELO ajustado por plantel), experimento T1.8-T1.10:**
- Cada equipo vale `R_club + D_dt`. `R_club` arranca en 1000 y `D_dt` en 0.
- Expectativa: `E = f(equipo_local + HFA, equipo_visita)`.
- `delta = K·C·G·(S − E)`. El DT recibe `α·delta` y el club `(1−α)·delta` (α en {0,5; 0,65; 0,8}); el visitante recibe el opuesto. Sigue siendo suma cero.
- ELO publicable de la capa B = `1000 + D_dt`.
- Se adopta solo si mejora el log-loss de validación >= 0,001 respecto de la capa A y pasa la sanidad (T1.6). Casos de control: DT que pasa de club grande a chico; DTs de larga permanencia (el club absorbe mérito).
- Si se adopta, se publica como contenido secundario ("rinde por encima de su plantel"); la cabecera sigue siendo la capa A salvo decisión del usuario.

**Validación (protocolo):**
1. Invariantes: `scripts/validate_elo.py` (suma cero, masa, duplicados).
2. Backtest walk-forward desde 2016 con ambos DTs >= 30 PJ previos: Brier del resultado esperado, log-loss 1X2 (modelo de empate fijo, estilo Davidson con parámetro ajustado), tabla de calibración por tramos de E; desgloses por año y nivel de competencia. Línea base: constante local (Brier 0,1783).
3. Grilla chica (~12-16 combinaciones): HFA, K base, calibración on/off, variante MOV, `inicio` en {2000, 2012, 2015}. Entrenar 2016-2022; validar 2023-2026. Elegir la configuración más simple a menos de 0,0005 del mejor log-loss.
4. Sanidad con DTs conocidos: lista fija de ~10 nombres (aprobada por el usuario) que deben estar en el top 30 de activos con >=100 PJ (al menos 7 de 10); revisar trayectorias (Klopp, Guardiola, Gallardo).
5. Estabilidad semana a semana: ningún DT activo se mueve de forma absurda.

---

## 4. Estrategia de datos

**Fuente incremental recomendada:** scraping incremental de Transfermarkt (ya construido, mismos IDs, 51 competencias, $0). Descartadas: dcaribou/transfermarkt-datasets (pausado desde julio 2026, sin Argentina); APIs de pago (el usuario no acepta el gasto; además requieren mapear ~6.700 DTs y 1.470 clubes). Cobertura de APIs gratuitas (API-Football 100 req/día, football-data.org) no verificada: no se pudo consultar precios/planes; solo plan B.

**Volumen semanal:** ~300 partidos nuevos + ~100 fixtures (51 competencias x 2 temporadas posibles) = ~450 requests = ~30 min a 14 req/min.

**Semana de trabajo:** `semana_fin` = domingo más reciente <= ayer. Solo se procesan partidos con fecha <= `semana_fin`; los posteriores esperan a la próxima corrida. Así el snapshot es siempre limpio aunque la PC se encienda un miércoles.

**Temporadas en curso** (`current_seasons(config, hoy)`): ligas con `saison_offset=0` (Europa): año si mes >= 7, si no año−1. Ligas con `saison_offset=1` (año calendario): año actual. Se prueba también la anterior y se conservan las que tengan fechas >= `since`.

**Incremental real:** hoy `--refresh` re-descarga todos los reportes de la temporada (`pending = [... if refresh or not has_match]`). Hace falta un modo nuevo que baje solo el fixture y los reportes que faltan.

**ELO incremental:** si hay partidos nuevos o correcciones, `recompute_all_elo` completo (determinista; medir el tiempo en T2.4). Solo si supera ~5 minutos se evalúa un `recompute_from(fecha)`.

**Correcciones:** comparar score del fixture contra la base en los últimos 21 días; si difiere, corregir y recalcular.

**Mapeo de IDs:** innecesario mientras se use TM. Si algún día se suma otra fuente: tabla `mapa_ids(fuente, tipo, id_externo, id_interno, confianza)`; clubes por (fecha, equipos normalizados, marcador); DTs por la alineación del mismo partido.

**Riesgos legales / ToS:** los ToS de TM prohíben el scraping automatizado; ya hubo un baneo de IP. El `WafChallengeSolver` elude una protección anti-bot, lo que agrava el riesgo. Mitigaciones: ritmo bajo (~450 req/semana), no redistribuir HTML/fotos/escudos, publicar solo cálculos propios (ELO) y datos fácticos (resultados, nombres), atribuir "Datos: Transfermarkt", leer `robots.txt`, no monetizar sin asesoría legal. Si el proyecto crece: pasar a una fuente licenciada.

**Recuperación de datos históricos (3 capas, de barata a cara):**
1. Argentina 2017-2020 y 2025-26 (T0.4) y UEFA (T0.10).
2. Recuperar partidos con DT faltante mediante etapas de DTs por club (T0.7-T0.9): hasta 69 mil partidos, mayormente pre-2015; costo ~2 h de requests si las etapas salen de la página de historial de DTs de cada club.
3. Argentina 2000-2014: TM no tiene esas ligas; estudio de factibilidad de fuentes externas (T0.11). Mientras tanto, los argentinos con carrera previa a 2015 se publican con la leyenda "histórico incompleto".
El experimento de sensibilidad de T1.5 mide cuánto afectan las capas 2 y 3 a los rankings de DTs activos.

---

## 5. Arquitectura del pipeline semanal

**Regla:** Python hace el trabajo pesado; n8n orquesta (disparador, secuencia, esperas, notificación, errores). El workflow debe quedar con nodos visibles y bien nombrados, porque el usuario lo va a mostrar en LinkedIn.

**Entry point único:** `scripts/weekly_run.py` con subcomandos que imprimen JSON por stdout y devuelven código de salida:
- `preflight`: DB responde y TM es alcanzable. Código 10 si no (VPN apagada, bloqueo 403, CAPTCHA 405; el mensaje indica si hay que cambiar de servidor VPN).
- `update`: scrape incremental -> load -> recompute -> validar invariantes (si falla, código 20) -> snapshot.
- `render`: genera paquete de imágenes + textos.
- `notify`: envía a Telegram (también `--test`).
- `all`: encadena todo.
- Flags: `--json`, `--skip-if-done-this-week`, lock file `data/weekly.lock`.
- Códigos: 0 ok, 10 bloqueo/VPN (reintentable), 20 validación fallida, 30 otro error.
- Logs: `data/logs/weekly_<fecha>.log` y fila en `ejecuciones_pipeline`.
- Resumen JSON de `update`: partidos nuevos, descartados (sin DT), correcciones, ligas sin partidos hace más de 14 días, días desde el último partido, tiempo de recompute.

**n8n en Windows** (Node 24 de `F:\Doom\LLM`; verificar compatibilidad al instalar, fallback Node 22 LTS). Invocación desde nodos Execute Command:
`wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /mnt/f/ProyectoDT && python3 scripts/weekly_run.py <subcomando> --json"`.
Verificar que el nodo Execute Command esté habilitado (algunas versiones lo deshabilitan por defecto). Ventaja: WSL arranca solo cuando n8n lo llama (se evita el problema de WSL apagado tras reiniciar Windows). La VPN y Postgres ya viven en Windows.

**Workflow `weekly_aep`:**
1. Triggers: Schedule (lunes 08:00, tz America/Argentina/Buenos_Aires) + Webhook `aep-catchup` (misma salida).
2. `preflight`. Si código 10: lazo con IF + nodo Wait de 30 min, hasta 6 intentos (el "Retry On Fail" de n8n limita la espera entre intentos a ~5 s; verificar), luego alerta Telegram.
3. `update` (timeout 60 min). Falla con 20/30: alerta Telegram.
4. `render` por formato (ramas en paralelo).
5. Leer PNG desde `F:\ProyectoDT\data\output\YYYY-Www\` (nodo de lectura de archivos) -> Telegram (documento, para no perder calidad) + mensaje de resumen y textos sugeridos.
6. Workflow aparte `error_alert` con Error Trigger -> Telegram ("falló nodo X: mensaje").
7. Nada se publica solo: el usuario revisa y publica a mano.

**Recuperación tras PC apagada:** tarea de Windows Task Scheduler "Al iniciar sesión" (con 2 min de demora) que ejecuta `curl http://localhost:5678/webhook/aep-catchup`. `--skip-if-done-this-week` evita duplicados. n8n no recupera por sí solo una ejecución perdida, por eso el webhook. n8n debe arrancar al iniciar sesión (otra tarea).

**Almacenamiento:** seguir con Postgres. Tablas nuevas (migración 003): `snapshots_elo(semana_fin DATE, dt_id, elo NUMERIC(7,2), rank_global INT, pj_total INT, activo BOOL, publicable BOOL, modelo_version TEXT, PK(semana_fin, dt_id, modelo_version))`, `ejecuciones_pipeline(run_id, iniciado_en, terminado_en, estado, resumen JSONB)`, `dt_etapas` (T0.8) y columna `dt_imputado` (T0.9). Los snapshots son inmutables: lo publicado no cambia aunque el modelo cambie.

**Notificación (Telegram):** imágenes como documento + un mensaje con: título de la semana, resumen numérico (partidos nuevos, DTs con mayor movimiento, #1), alertas de calidad (descartados, correcciones, ligas sin partidos), y tres textos sugeridos (LinkedIn, X <=280 caracteres, Instagram) más texto alternativo de cada imagen. Los textos salen de plantillas Python (sin LLM).

**Costo:** todo local ($0): Postgres, n8n, Python, Telegram bot, VPN gratuita.

---

## 6. Imágenes y contenido

**Enfoque:** plantillas HTML/CSS (Jinja2) renderizadas a PNG con Playwright/Chromium (ya es dependencia del scraper). Se mantienen la paleta (violeta/lila, celeste, blanco) y las fuentes Poppins/Anton de `assets/fonts/`. `visualization.py` (matplotlib) no se toca hasta que el HTML lo iguale. Sin escudos ni fotos de TM; banderas como código de país en texto. Agregar `jinja2` a `requirements.txt`; Pillow ya viene con matplotlib.

**Tamaños:**
| Uso | Tamaño |
|---|---|
| LinkedIn e Instagram (feed) | 1080x1350 (4:5), `portrait` |
| X (y alternativa LinkedIn) | 1600x900 (16:9), `landscape` |
| Respaldo | 1080x1080, `square` |
| Stories (opcional) | 1080x1920 |

**Formatos y datos:**
| Formato | Datos |
|---|---|
| Top 10 DTs en Argentina (DT cuyo último club es argentino, activos y publicables) | snapshot actual y anterior, club actual, PJ. |
| Subidas y bajadas (Argentina; global después) | partidos de la ventana, mínimo 15 PJ (interinos con >=5 PJ etiquetados), club. Reusa `ranking.py`. |
| Duelo de la semana | DTs que se enfrentaron esa semana con mayor ELO combinado, historial entre ellos, mini-gráfico de ELO (SVG). Reusa `duel.py`. |
| Top 10 global | snapshots. |
| DT revelación | <2 años de carrera, >=15 PJ, mayor suba en 90 días. |
| Top por país/liga (rotativo) | snapshots + país del club actual. |

**Rotación sugerida:** el workflow genera todos los formatos cada lunes y marca uno como "sugerido de la semana": semana ISO módulo 4 -> Top Argentina, Subidas y bajadas, Duelo, Top global.

**Regla `publicable` (T0.5):** DT con >=15 PJ, activo (último partido <= 365 días) y cuyas competencias de las últimas 3 temporadas tengan cobertura >= 90 % según la auditoría. DTs de 15 a 29 PJ llevan "provisorio". Interinos (<15 PJ) solo en "subidas y bajadas" con >=5 PJ y etiqueta. Si Argentina 2025-26 no está cargada, ningún DT de Argentina es publicable.

---

## 7. Plan por fases

Convención: cada tarea tiene Objetivo, Archivos, Aceptación y Depende de. "VPN" = necesita VPN activa.

### Camino crítico y orden

1. Fase 0: T0.1 -> T0.2 -> T0.3 -> T0.4 -> T0.6 -> T0.5.
2. Datos históricos (en paralelo con Fase 1): T0.10; T0.7 -> T0.8 -> T0.9; T0.11 al final.
3. Fase 1: T1.1 -> T1.2 -> T1.3 -> T1.4 -> T1.5 -> T1.6 -> T1.7. En paralelo, experimento capa B: T1.8 -> T1.9 -> T1.10.
4. Fase 2: T2.1 -> T2.2; T2.3 -> T2.4 -> T2.5.
5. Fase 3: T3.1 y T3.2, luego T3.3-T3.8 (Argentina primero).
6. Fase 4: T4.1 a T4.4.
7. Fase 5.

El primer post (Top 10 DTs de Argentina) sale al terminar Fase 0, T1.7, Fase 2 y T3.1 a T3.3. Los datos históricos (T0.7-T0.11) no lo bloquean, salvo que el experimento de sensibilidad (T1.5) indique lo contrario.

### Fase 0: Datos y base sana

**T0.1 Respaldo y control de versiones**
- Objetivo: poder deshacer cambios.
- Archivos: `scripts/backup_db.sh` (pg_dump a `data/backups/`), `.env.example` (sin secretos), `git init` (el `.gitignore` ya excluye `.env`, `data/`, `__pycache__`).
- Aceptación: el dump se restaura en una base temporal; primer commit sin `.env` ni `data/`. Aviso al usuario: rotar `DB_PASS` (no lo hace el modelo).
- Depende de: nada.

**T0.2 Auditoría de datos**
- Objetivo: hacer reproducibles los hallazgos de la sección 2.
- Archivos: `scripts/audit_data.py`.
- Aceptación: reporta en JSON y Markdown (a) fixtures cacheados vs cargados por competencia y temporada (debe dar 261.194 vs 191.931 en total), (b) casos de DT con más de un partido el mismo día (152), (c) huecos por competencia-temporada, (d) último partido por competencia, (e) porcentaje de partidos con DT faltante por temporada. Debe leer solo `fixtures.json` y consultas a la DB (leer los 261k reportes tarda demasiado en `/mnt/f`; el análisis de DT faltante usa una muestra o un caché de resultados).
- Depende de: T0.1.

**T0.3 Diagnóstico y arreglo del bug de fechas**
- Objetivo: eliminar los 152 conflictos de fecha.
- Archivos: `scraping/parser.py` (`parse_schedule`, `_extract_date`), `tests/test_parser.py`.
- Aceptación: causa documentada (partir del fixture cacheado `data/raw/TDeC/2006/fixtures.json`). Test que reproduce el bug y falla antes del arreglo. Re-descarga solo de las temporadas afectadas (listadas por T0.2). Después, el conteo baja de 152 a 0, o cada caso restante queda explicado. Recompute y `validate_elo.py` en verde.
- Depende de: T0.2. VPN.

**T0.4 Diagnosticar y recuperar Argentina**
- Objetivo: cubrir `AR1N`, `ARG2` y `CDLP` en 2017-2020 y 2025-26 (o documentar por qué TM no los tiene).
- Archivos: `scraping/pipeline.py` (guard `season_is_aligned`), `scripts/verify_competitions.py` (flag `--no-align-check`, no cachea), `scraping/leagues_catalog.py`, tests.
- Pasos:
  1. Pedir esas temporadas con el guard apagado; imprimir cantidad de fixtures y fechas mínima y máxima.
  2. Si TM devuelve temporadas agosto-junio correctas: el guard es falso positivo. Cambiar la regla a "aceptar si el año pedido está entre el año de la fecha mínima y el de la máxima", verificando que sigue rechazando el caso original (pedir 2000 y recibir la temporada actual). Test de regresión.
  3. Si devuelve otra temporada o vacío: buscar en TM los códigos de Superliga, Apertura/Clausura 2025 y copa 2020; sumarlos al catálogo y verificarlos.
  4. Descargar (3 workers, ritmo estándar), `load`, `recompute`, `validate_elo.py`, `audit_data.py`.
- Aceptación: tabla de cobertura de Argentina por año sin huecos, o cada hueco explicado (p. ej. "2020: pandemia"). `validate_elo.py` en verde. Test del guard.
- Depende de: T0.1, T0.2. VPN.

**T0.6 País real de los clubes**
- Objetivo: que "DT de Argentina" salga bien (hoy 254 clubes tienen `pais="Conmebol"`).
- Archivos: `scripts/fix_club_country.py`, test.
- Qué hace: asigna `pais` de cada club desde la liga doméstica donde aparece (`AR1N`, `ARG2`, `ARCA`, `CDLP`, etc.). Los que solo aparecen en torneos internacionales quedan como "desconocido" y se listan aparte.
- Aceptación: Boca, River, Racing y Talleres quedan con `pais="Argentina"`. Informe de clubes sin país.
- Depende de: T0.4.

**T0.5 Reglas de publicación**
- Objetivo: centralizar qué se puede publicar.
- Archivos: `config.py` (`RANKING_MIN_PJ=15`, `PROVISORIO_PJ=30`, `INTERINO_MIN_PJ=5`, `ACTIVO_DIAS=365`, `COBERTURA_MIN=0.90`, `COBERTURA_TEMPORADAS=3`), función `es_publicable` en el módulo de snapshots/contenido, `tests/`.
- Aceptación: variables leídas del entorno con defaults; tests de la regla de la sección 6 (casos: DT con 14 PJ, activo vs inactivo, competencia con cobertura 80 %).
- Depende de: T0.2 (cobertura por competencia-temporada), T0.4.

**T0.7 (estudio) Fuente de etapas de DTs**
- Objetivo: confirmar qué página de TM da DT, club, desde y hasta (historial de DTs del club vs perfil del DT).
- Archivos: `docs/ETAPAS_DTS.md`.
- Aceptación: URL elegida y 3 ejemplos parseados a mano contra TM (incluye un DT con varias etapas y un interino), con estimación de requests.
- Depende de: T0.4. VPN.

**T0.8 Scrape de etapas y perfiles**
- Objetivo: tabla de etapas + nacionalidad y fecha de nacimiento de DTs activos.
- Archivos: `migrations/003_etapas.sql` (`dt_etapas(dt_id, club_id, desde, hasta, pj_tm)`; o numerar según el orden real con T2.1), `models.py`, `scraping/parser.py`, `scripts/scrape_etapas.py`, tests con HTML de muestra.
- Aceptación: etapas cargadas para los clubes de la base; nacionalidad/fecha_nacimiento cargadas para los DTs activos; reanudable; ritmo estándar; `migrate.py` idempotente.
- Depende de: T0.7. VPN.

**T0.9 Imputación de DTs por etapas**
- Objetivo: recuperar partidos hoy descartados por DT faltante.
- Archivos: `scraping/pipeline.py` (`load_normalized` consulta `dt_etapas` si falta el DT), columna `dt_imputado BOOLEAN` en `partidos_dt`, tests.
- Aceptación: validación hold-out (esconder DT en partidos donde se conoce, imputar, medir acierto >= 95 %). Reporte de partidos recuperados por competencia. Partidos ambiguos (dos DTs en el mismo club y fecha) se siguen descartando. `recompute` y `validate_elo.py` en verde.
- Depende de: T0.8.

**T0.10 UEFA al catálogo**
- Objetivo: sumar Champions, Europa League y Conference League.
- Archivos: `scraping/leagues_catalog.py`, `scripts/verify_competitions.py`.
- Aceptación: códigos verificados contra TM (no asumir; verificar con `verify_competitions.py`). Coeficientes provisorios: Champions S=1,3; Europa League A=1,0; Conference B=0,8; `kind="internacional"`, `path="pokalwettbewerb"` (o el que corresponda). Backfill 2000-2026 (~15 mil requests, ~18 h en tandas, reanudable), `load`, `recompute`, `validate_elo.py`.
- Depende de: T0.1. VPN.

**T0.11 (estudio) Factibilidad Argentina 2000-2014**
- Objetivo: decidir si vale la pena (decide el usuario).
- Archivos: `docs/ARGENTINA_HISTORICO.md`.
- Aceptación: lista de fuentes candidatas (RSSSF, Wikipedia, datasets abiertos) con cobertura, licencia y esfuerzo; muestra cruzada para un DT (Falcioni) en una temporada; recomendación hacer / no hacer.
- Depende de: T0.8.

### Fase 1: Modelo ELO v2

**T1.1 Harness de backtest**
- Objetivo: evaluar parámetros sin tocar la base.
- Archivos: `backtest.py`, `scripts/backtest_elo.py`, `tests/test_backtest.py`.
- Aceptación: carga partidos en memoria, reproduce la línea base (Brier ~0,1637 con HFA 30 en 2021+ y ambos DTs >=30 PJ previos, tolerancia 0,0005). Reporta Brier, log-loss 1X2, calibración y desglose por año y nivel. Sin escrituras a la DB.
- Depende de: T0.3.

**T1.2 `EloParams` retrocompatible**
- Objetivo: parametrizar HFA, K, MOV, calibración, inactividad.
- Archivos: `elo.py`, `tests/test_elo.py`.
- Aceptación: con los defaults, los tests existentes pasan sin cambios; tests nuevos por parámetro.
- Depende de: nada.

**T1.3 K de calibración e inactividad**
- Objetivo: multiplicador por experiencia (promedio de ambos DTs) y por regreso tras >=12 meses.
- Archivos: `elo.py`, `services.py` (`recompute_all_elo` lleva contadores por DT: PJ previos y última fecha), tests.
- Aceptación: suma cero por partido y masa conservada (`validate_elo.py` OK); test de que dos DTs con 0 PJ mueven el doble que dos con 30.
- Depende de: T1.2.

**T1.4 Arreglar K de eliminatorias**
- Objetivo: que `infer_factor_k` detecte rondas reales.
- Archivos: `scraping/pipeline.py`, `scripts/refresh_factor_k.py`, tests.
- Aceptación: tabla de los textos de `matchday` distintos en el caché de CLI, CS, ARCA y CDLP y su mapeo a K, con tests. El script actualiza `partidos_dt.factor_k` desde el caché sin re-scrapear. Reporte antes/después de partidos con K != 20.
- Depende de: T1.2.

**T1.5 Búsqueda de parámetros y sensibilidad al inicio**
- Objetivo: elegir la configuración con evidencia.
- Archivos: `scripts/tune_elo.py`, `docs/MODELO_ELO.md`.
- Aceptación: grilla de la sección 3; entrenamiento 2016-22, validación 2023-26; CSV con resultados; configuración elegida con su mejora vs la actual. Incluye el experimento de sensibilidad: ratings de DTs activos calculando desde 2000 vs desde 2015 (correlación de rangos y tabla de las mayores diferencias).
- Depende de: T1.1, T1.3, T1.4.

**T1.6 Sanidad con DTs conocidos**
- Archivos: `scripts/sanity_check.py`, `data/sanity_coaches.json`.
- Aceptación: imprime el top 25 de activos con >=100 PJ y verifica la lista de ~10 nombres aprobada por el usuario (>=7 en el top 30).
- Depende de: T1.5.

**T1.7 Aplicar y recalcular**
- Archivos: constante `MODELO_VERSION` en `elo.py`.
- Aceptación: `recompute` y `validate_elo.py` en verde; comparación de rankings antes/después guardada.
- Depende de: T1.6.

**T1.8 Capa B en el harness**
- Archivos: `backtest.py` (modo `plantel`), tests.
- Aceptación: tests de suma cero y de invarianza (con clubes idénticos, la capa B se reduce a la capa A).
- Depende de: T1.1.

**T1.9 Comparar capa B vs capa A**
- Archivos: `scripts/tune_elo.py`.
- Aceptación: log-loss de validación de ambas; casos de control de la sección 3.
- Depende de: T1.8, T1.5.

**T1.10 Decisión de la capa B**
- Archivos: `docs/MODELO_ELO.md`.
- Aceptación: queda escrito si se adopta y como qué (cabecera o contenido secundario).
- Depende de: T1.9.

### Fase 2: Actualización incremental

**T2.1 Migración de snapshots y ejecuciones**
- Archivos: `migrations/003_snapshots.sql` (numerar de forma coherente con T0.8), `models.py`.
- Aceptación: `migrate.py` aplica y es idempotente; tests con SQLite siguen pasando.
- Depende de: T1.7.

**T2.2 Snapshots e historial**
- Archivos: `snapshots.py`, `scripts/backfill_snapshots.py`, tests.
- Aceptación: `take_snapshot` idempotente; el último snapshot coincide con `entrenadores.elo_actual`; historial retroactivo semanal desde 2012; calcula `activo` y `publicable`.
- Depende de: T2.1, T0.5.

**T2.3 Comando `update` (scrape incremental)**
- Archivos: `scraper_transfermarkt.py`, `scraping/pipeline.py`, tests con cliente falso.
- Aceptación: baja solo el fixture de las temporadas en curso de cada competencia y solo los reportes que faltan (test que prueba que no re-descarga lo cacheado); respeta `semana_fin`; una corrida real trae ~300 partidos con <600 requests.
- Depende de: T0.3.

**T2.4 Correcciones y política de recálculo**
- Archivos: `services.py`, `scripts/weekly_run.py`.
- Aceptación: compara scores del fixture vs la base (últimos 21 días) y los reporta; con partidos nuevos o correcciones, recompute completo; dos recomputes seguidos dan el mismo hash de `elo_actual`; se registra el tiempo de recompute.
- Depende de: T2.3.

**T2.5 Orquestador `weekly_run.py`**
- Archivos: `scripts/weekly_run.py`.
- Aceptación: subcomandos `preflight`, `update`, `render`, `notify`, `all`; JSON; códigos 0/10/20/30; log por corrida; lock file; `--skip-if-done-this-week`. Una segunda corrida inmediata no trae partidos nuevos y termina en 0. `preflight` falla con la VPN apagada y pasa con VPN prendida (y reporta si la IP de casa responde 202/200 sin VPN). El resumen incluye los campos de la sección 5.
- Depende de: T2.2, T2.4.

### Fase 3: Imágenes y contenido

**T3.1 Capa de datos de contenido**
- Archivos: `content.py`, `tests/test_content.py`.
- Aceptación: `top_n`, `movers` (con mínimos y etiquetas), `duelo_de_la_semana`, `revelacion` y `top_por_pais` con tests en SQLite; filtran por `publicable`.
- Depende de: T2.2, T0.6.

**T3.2 Infraestructura de render HTML**
- Archivos: `templates/base.css`, `render_html.py`, `requirements.txt` (+`jinja2`).
- Aceptación: PNG de prueba con dimensiones exactas 1080x1350 y 1600x900 (verificadas con Pillow); fuentes cargadas desde `assets/fonts/`.
- Depende de: nada.

**T3.3 Plantilla Top 10 (Argentina; reutilizable para global)** — `templates/top10.html`. Aceptación: sin desbordes con nombres de 40 caracteres, <1,5 MB, variantes `portrait`/`landscape`/`square`. Depende de: T3.1, T3.2.

**T3.4 Plantilla Subidas y bajadas** — `templates/movers.html`. Mismos criterios que T3.3. Depende de: T3.1, T3.2.

**T3.5 Plantilla Duelo** — `templates/duelo.html` (mini-gráfico SVG de ELO). Mismos criterios. Depende de: T3.1, T3.2.

**T3.6 Plantilla Revelación** — `templates/revelacion.html`. Mismos criterios. Depende de: T3.1, T3.2.

**T3.7 Textos sugeridos**
- Archivos: `captions.py`, `tests/test_captions.py`.
- Aceptación: tres textos por formato (LinkedIn, X <=280, Instagram) más texto alternativo; tests de longitud.
- Depende de: T3.1.

**T3.8 Subcomando `render`**
- Archivos: `scripts/weekly_run.py`.
- Aceptación: crea `data/output/YYYY-Www/` con los PNG, `post.md` y `summary.json`; idempotente por semana; marca el formato "sugerido de la semana" (ISO semana módulo 4).
- Depende de: T3.3 a T3.7, T2.5.

### Fase 4: n8n y Telegram

**T4.1 Bot de Telegram** (parte manual del usuario: BotFather y chat id)
- Archivos: `notify.py`, `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- Aceptación: `weekly_run.py notify --test` entrega un mensaje con una imagen.
- Depende de: nada.

**T4.2 Instalar n8n en Windows**
- Archivos: `docs/n8n_setup.md`, script de arranque, tarea de Task Scheduler de arranque.
- Aceptación: tras reiniciar Windows, `http://localhost:5678` responde; el nodo Execute Command ejecuta `wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /mnt/f/ProyectoDT && python3 --version"`.
- Depende de: T2.5.

**T4.3 Workflows**
- Archivos: `n8n/weekly_aep.json`, `n8n/error_alert.json`.
- Aceptación: corrida manual completa entrega imágenes y textos en Telegram; fallo forzado (VPN apagada o DB mal) dispara la alerta; el lazo de espera de VPN funciona (código 10 simulado).
- Depende de: T3.8, T4.1, T4.2.

**T4.4 Recuperación tras PC apagada**
- Archivos: tarea de Task Scheduler "al iniciar sesión" -> webhook `aep-catchup`.
- Aceptación: encender la PC un miércoles dispara una sola corrida de la semana; un segundo inicio de sesión no repite.
- Depende de: T4.3.

### Fase 5: Mejoras

- **T5.1** Coeficientes empíricos por fuerza de liga, estimados con partidos entre ligas.
- **T5.2** Limpieza de nombres: campo `nombre_display` para los 119 apellidos `-` y revisión de los 35 homónimos.
- **T5.3** Backups semanales con `pg_dump` y rotación de 8.
- **T5.4** Resto de ligas con baja cobertura (punto 11 de la sección 2): revisar causa tras T0.9.
- **T5.5** Contenido "argentinos en el mundo" usando nacionalidad cargada en T0.8.

---

## 8. Pendientes del usuario

- Rotar `DB_PASS` (quedó expuesto en un log de sesión).
- Crear el bot de Telegram (T4.1).
- Aprobar la lista de ~10 DTs de sanidad (T1.6).
- Decidir sobre Argentina 2000-2014 cuando salga el estudio de T0.11.
- Definir la marca y el handle antes del primer post.
