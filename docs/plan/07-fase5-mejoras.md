# Fase 5: Mejoras (después del MVP)

Leer antes: `AGENTS.md`, `ESTADO.md` y las reglas generales de `00-INDICE.md`.
Tareas de este archivo: T5.1 a T5.5. Ninguna bloquea el primer post. Hacerlas solo con el MVP funcionando.

---

## T5.1: Coeficientes empíricos por liga

- **Tipo:** ⚙️.
- **Depende de:** T1.7.
- **Objetivo:** estimar la fuerza relativa de cada liga con los partidos entre ligas (Libertadores, Sudamericana, Champions, Europa, Conference) y proponer coeficientes `C` basados en datos en vez de los niveles provisorios S/A/B/C.
- **Archivos:** `scripts/estimar_coeficientes.py`, `docs/MODELO_ELO.md` (sección nueva).
- **Aceptación:** tabla de fuerza relativa por liga con intervalo de confianza aproximado; propuesta de nuevos coeficientes; se evalúa con el harness (T1.1) y solo se adopta si mejora el log-loss de validación ≥ 0,001. Si se adopta, `recompute` y `validate_elo.py`.

## T5.2: Limpieza de nombres

- **Tipo:** ⚙️.
- **Depende de:** —.
- **Objetivo:** los 119 DTs con apellido `-` (por ejemplo "Xavi -") y los 35 nombres repetidos con distinto `transfermarkt_id`.
- **Archivos:** migración con `nombre_display VARCHAR(150)` en `entrenadores`, `scripts/fix_nombres.py` (dry-run por defecto), `tests/`.
- **Aceptación:** `nombre_display` completo para todos; "Xavi" se muestra como "Xavi"; lista de homónimos para revisión manual; `content.py` y las plantillas usan `nombre_display`.

## T5.3: Backups semanales

- **Tipo:** ⚙️.
- **Depende de:** T0.1.
- **Archivos:** subcomando `backup` en `scripts/weekly_run.py` (usa `scripts/backup_db.sh`), rotación de 8 respaldos en `data/backups/`.
- **Aceptación:** tras la corrida semanal quedan como máximo 8 dumps; el último se restaura en una base temporal.

## T5.4: Ligas con baja cobertura

- **Tipo:** 🔒.
- **Depende de:** T0.9.
- **Objetivo:** revisar las competencias con baja cobertura respecto de los fixtures cacheados: VZ1C 26 %, COL1 48 %, MEX1 48 %, VZ1A 49 %, FR2 50 %, UKR1 53 %, BRA1 54 %, TS1 54 %, NL1 59 %, GR1 60 %, PL1 61 %, SC1 62 % (valores antes de T0.9).
- **Pasos:** correr `audit_data.py --muestra 3000` tras T0.9; para lo que siga bajo 90 %, diagnosticar la causa (DT faltante no imputable, reportes no descargados, fixture truncado) y proponer arreglos.
- **Aceptación:** informe con causa por competencia y plan; si hay arreglos baratos, aplicarlos con confirmación del usuario.

## T5.5: Contenido "argentinos en el mundo"

- **Tipo:** ⚙️.
- **Depende de:** T0.8, T3.1.
- **Objetivo:** ranking de DTs de nacionalidad argentina que dirigen fuera de Argentina (Simeone, Pochettino, etc.) usando `entrenadores.nacionalidad`.
- **Archivos:** `content.py` (`top_por_nacionalidad`), `templates/top10.html` (título parametrizable), tests.
- **Aceptación:** con datos reales, el ranking incluye a los DTs argentinos activos con club fuera de Argentina, sin interinos en el Top; tests.
