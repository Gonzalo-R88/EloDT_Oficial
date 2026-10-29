# AEP: índice de ejecución por fases y tareas

Este índice es el punto de entrada. El plan completo y razonado está en `aep-elo-pipeline.md` (referencia). **Si hay diferencias entre ese archivo y los archivos de fase (`01`...`07`), mandan los archivos de fase** (son la versión refinada).

## Cómo usarlo

1. **Una sola vez:** copiar el plan al repo para que el modelo de Build lo lea sin salir del proyecto. Prompt:

   ```
   Copiá todos los archivos de /home/gonzalo/.opencode/plan/ a /mnt/f/ProyectoDT/docs/plan/ sin modificarlos. No hagas nada más.
   ```

2. **Por cada tarea (o paquete)**, pegar la plantilla cambiando el ID:

   ```
   Ejecutá SOLAMENTE la tarea <ID> del plan. Leé primero /mnt/f/ProyectoDT/AGENTS.md, /mnt/f/ProyectoDT/ESTADO.md,
   /mnt/f/ProyectoDT/docs/plan/00-INDICE.md (reglas generales) y el archivo de fase que contiene la tarea
   (ver tabla del índice). No avances a otras tareas. Si la tarea necesita VPN, scraping largo o una decisión mía,
   parate y preguntame antes. Al terminar: corré python3 -m pytest, actualizá ESTADO.md, marcá la tarea en
   docs/plan/00-INDICE.md y dame un resumen con la evidencia del criterio de aceptación.
   ```

   Para un paquete: "Ejecutá SOLAMENTE las tareas T0.1 y T0.2, en ese orden..." (resto igual).

3. Revisá el resultado y recién entonces pedí la siguiente tarea.

Los pendientes del usuario (acciones y decisiones) se acumulan en **`docs/plan/PENDIENTES.md`**.
Leerlo antes de empezar cada sesión y actualizarlo al cerrar la tarea (agregar lo nuevo que
quede pendiente, tachar lo hecho).

## Reglas generales (valen para TODAS las tareas)

- Respetar las convenciones del repo (`AGENTS.md`): nombres de dominio en español, docstrings y comentarios en español, Python 3.12, SQLAlchemy 2.0.
- Tests: `python3 -m pytest` desde la raíz (nunca `pytest` pelado). No se necesita Postgres para los tests (SQLite en memoria). Los 36 tests existentes deben seguir pasando.
- Migraciones: SQL plano e idempotente en `migrations/`; aplicar con `python migrate.py`. Hacer `bash scripts/backup_db.sh` (cuando exista, T0.1) antes de cualquier migración, recompute o carga masiva.
- **No tocar `.env`, no imprimir secretos en logs/respuestas, no borrar `data/raw/` (caché de scraping)**.
- **Scraping:** solo con VPN activa y confirmación del usuario. Ritmo máximo ~14 req/min (3 workers, delay 8-18 s). No subirlo. Ante 403 esperar `TM_BLOCKED_WAIT`; ante CAPTCHA (HTTP 405, "Human Verification") parar y avisar para cambiar de servidor VPN. Los scrapes largos van en `tmux`, reanudables, con logs en `data/logs/`.
- Cada tarea cambia lo mínimo necesario. Nada de sobreingeniería ni refactors no pedidos.
- Después de cambiar fórmula/coeficientes: `recompute`; después de cualquier carga o recompute: `python3 scripts/validate_elo.py` en verde (sin duplicados, suma cero, masa conservada).
- Al terminar cada tarea: actualizar `ESTADO.md` (qué se hizo, qué sigue), marcar la casilla en la tabla de abajo y reportar la evidencia del criterio de aceptación (salidas de comandos, números).
- Si algo del plan no coincide con la realidad del repo, parar y reportarlo; no improvisar.

## Tabla de tareas

Leyenda: 🔒 = necesita VPN/scraping (pedir confirmación) · 👤 = requiere acción o decisión del usuario · ⚙️ = solo código/DB local.

| ✔ | ID | Título | Archivo de fase | Tipo | Depende de |
|---|---|---|---|---|---|
| [x] | T0.1 | Respaldo y git | `01-fase0-datos.md` | ⚙️ 👤 | — |
| [x] | T0.2 | Auditoría de datos y cobertura | `01-fase0-datos.md` | ⚙️ | T0.1 |
| [x] | T0.3 | Bug de fechas del fixture | `01-fase0-datos.md` | 🔒 | T0.2 |
| [x] | T0.4 | Recuperar Argentina | `01-fase0-datos.md` | 🔒 👤 | T0.1, T0.2 |
| [x] | T0.6 | País real de los clubes | `01-fase0-datos.md` | ⚙️ | T0.4 |
| [x] | T0.5 | Reglas de publicación | `01-fase0-datos.md` | ⚙️ | T0.2, T0.4, T0.6 |
| [ ] | T0.10 | UEFA al catálogo y backfill | `02-fase0b-historicos.md` | 🔒 | T0.1 |
| [ ] | T0.7 | Estudio: fuente de etapas de DTs | `02-fase0b-historicos.md` | 🔒 👤 | T0.4 |
| [ ] | T0.8 | Scrape de etapas y perfiles | `02-fase0b-historicos.md` | 🔒 | T0.7 |
| [ ] | T0.9 | Imputación de DTs por etapas | `02-fase0b-historicos.md` | ⚙️ | T0.8 |
| [ ] | T0.11 | Estudio: Argentina 2000-2014 | `02-fase0b-historicos.md` | ⚙️ 👤 | T0.8 |
| [x] | T1.1 | Harness de backtest | `03-fase1-modelo.md` | ⚙️ | T0.3 |
| [x] | T1.2 | `EloParams` retrocompatible | `03-fase1-modelo.md` | ⚙️ | — |
| [x] | T1.3 | K de calibración e inactividad | `03-fase1-modelo.md` | ⚙️ | T1.2 |
| [x] | T1.4 | K de eliminatorias | `03-fase1-modelo.md` | ⚙️ | T1.2 |
| [x] | T1.5 | Búsqueda de parámetros y sensibilidad | `03-fase1-modelo.md` | ⚙️ 👤 | T1.1, T1.3, T1.4 |
| [x] | T1.6 | Sanidad con DTs conocidos | `03-fase1-modelo.md` | ⚙️ 👤 | T1.5 |
| [x] | T1.7 | Aplicar modelo y recalcular | `03-fase1-modelo.md` | ⚙️ | T1.6 |
| [ ] | T1.8 | Capa B en el harness | `03-fase1-modelo.md` | ⚙️ | T1.1 |
| [ ] | T1.9 | Comparar capa B vs A | `03-fase1-modelo.md` | ⚙️ | T1.8, T1.5 |
| [ ] | T1.10 | Decisión de la capa B | `03-fase1-modelo.md` | ⚙️ 👤 | T1.9 |
| [ ] | T2.1 | Migración de snapshots y ejecuciones | `04-fase2-incremental.md` | ⚙️ | T1.7 |
| [ ] | T2.2 | Snapshots e historial | `04-fase2-incremental.md` | ⚙️ | T2.1, T0.5 |
| [ ] | T2.3 | Comando `update` incremental | `04-fase2-incremental.md` | 🔒 | T0.3 |
| [ ] | T2.4 | Correcciones y recálculo | `04-fase2-incremental.md` | ⚙️ | T2.3 |
| [ ] | T2.5 | Orquestador `weekly_run.py` | `04-fase2-incremental.md` | ⚙️ 🔒 | T2.2, T2.4 |
| [ ] | T3.1 | Capa de datos de contenido | `05-fase3-imagenes.md` | ⚙️ | T2.2, T0.6 |
| [ ] | T3.2 | Infraestructura de render HTML | `05-fase3-imagenes.md` | ⚙️ | — |
| [ ] | T3.3 | Plantilla Top 10 | `05-fase3-imagenes.md` | ⚙️ | T3.1, T3.2 |
| [ ] | T3.4 | Plantilla Subidas y bajadas | `05-fase3-imagenes.md` | ⚙️ | T3.1, T3.2 |
| [ ] | T3.5 | Plantilla Duelo | `05-fase3-imagenes.md` | ⚙️ | T3.1, T3.2 |
| [ ] | T3.6 | Plantilla Revelación | `05-fase3-imagenes.md` | ⚙️ | T3.1, T3.2 |
| [ ] | T3.7 | Textos sugeridos | `05-fase3-imagenes.md` | ⚙️ | T3.1 |
| [ ] | T3.8 | Subcomando `render` | `05-fase3-imagenes.md` | ⚙️ | T3.3-T3.7, T2.5 |
| [ ] | T4.1 | Bot de Telegram y `notify.py` | `06-fase4-n8n.md` | ⚙️ 👤 | — |
| [ ] | T4.2 | Instalar n8n en Windows | `06-fase4-n8n.md` | 👤 | T2.5 |
| [ ] | T4.3 | Workflows de n8n | `06-fase4-n8n.md` | 👤 | T3.8, T4.1, T4.2 |
| [ ] | T4.4 | Recuperación tras PC apagada | `06-fase4-n8n.md` | 👤 | T4.3 |
| [ ] | T5.1 | Coeficientes empíricos por liga | `07-fase5-mejoras.md` | ⚙️ | T1.7 |
| [ ] | T5.2 | Limpieza de nombres | `07-fase5-mejoras.md` | ⚙️ | — |
| [ ] | T5.3 | Backups semanales | `07-fase5-mejoras.md` | ⚙️ | T0.1 |
| [ ] | T5.4 | Ligas con baja cobertura | `07-fase5-mejoras.md` | 🔒 | T0.9 |
| [ ] | T5.5 | Contenido "argentinos en el mundo" | `07-fase5-mejoras.md` | ⚙️ | T0.8, T3.1 |

## Paquetes sugeridos (una sesión de Build cada uno)

Orden recomendado. Los que no necesitan VPN se pueden hacer mientras corre un scrape largo en otra terminal.

| Paquete | Tareas | Notas |
|---|---|---|
| A | T0.1 + T0.2 | Seguro, sin VPN. Da la línea base reproducible. |
| B | T0.3 | VPN. Corrige fechas de unas pocas temporadas. |
| C | T0.4 | VPN. **Parada humana:** revisar la tabla de cobertura de Argentina antes de seguir. |
| D | T0.6 + T0.5 | Sin VPN. |
| E | T1.2 + T1.3 + T1.4 | Sin VPN (T1.2 y T1.4 se pueden adelantar antes que A-D). |
| F | T1.1 | Sin VPN. Necesita T0.3 hecha. |
| G | T1.5 | **Parada humana:** aprobar parámetros elegidos. |
| H | T1.6 + T1.7 | **Parada humana:** aprobar lista de DTs de sanidad. |
| I | T2.1 + T2.2 | Sin VPN. |
| J | T2.3 + T2.4 | T2.3 usa VPN solo para la prueba real. |
| K | T2.5 | Sin VPN salvo la prueba de `preflight`. |
| L | T3.1 + T3.2 | Sin VPN (T3.2 se puede adelantar). |
| M | T3.3 + T3.7 | **Parada humana:** revisar visualmente el primer Top 10. Primer contenido publicable. |
| N | T3.4 + T3.5 + T3.6 + T3.8 | |
| O | T4.1 | Parte manual del usuario (BotFather). |
| P | T4.2 + T4.3 + T4.4 | Parte manual del usuario (instalación en Windows). |
| Q | T0.10, T0.7 → T0.8 → T0.9, T0.11 | Históricos. En paralelo al resto cuando haya VPN. |
| R | T1.8 → T1.9 → T1.10 | Experimento capa B. |
| S | Fase 5 | Mejoras. |

## Paradas humanas (el Build NO decide solo)

- Tras T0.4: confirmar que la cobertura de Argentina es aceptable.
- Tras T1.5: aprobar los parámetros y si se calcula desde 2000 o desde 2015.
- Tras T1.6: aprobar la lista de ~10 DTs de sanidad.
- Tras T1.10: decidir si la capa B se publica y cómo.
- Tras T0.11: decidir si se intenta Argentina 2000-2014.
- Tras T3.3: aprobar el diseño visual del primer Top 10.
- Antes de cualquier scrape de más de ~500 requests: confirmar VPN y tiempo.

## Datos útiles para todos los prompts

- Proyecto: `/mnt/f/ProyectoDT` (Windows: `F:\ProyectoDT`). Distro WSL: `Ubuntu-24.04`. Postgres en Windows (`DB_HOST=winhost`).
- Baseline: 191.931 partidos, 6.686 DTs, 51 competencias, hasta 2026-10-08. 36 tests verdes.
- Handle de marca placeholder: `@AEP_Analitica`.
