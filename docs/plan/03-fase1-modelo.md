# Fase 1: Modelo ELO v2

Leer antes: `AGENTS.md`, `ESTADO.md` y las reglas generales de `00-INDICE.md`.
Tareas de este archivo: T1.1 a T1.7 (modelo) y T1.8 a T1.10 (experimento capa B).

## Contexto necesario

**ELO actual (`elo.py`, `services.py`):** `ΔELO = K·C·G·(R−E)`; inicial 1000; ventaja local +30; escala 400; MOV = 1,0 (diferencia ≤1), 1,5 (2), `(1,75+d)/3` (≥3); K ∈ {20,30,40} (99,4 % de los partidos tiene K=20); C por nivel de competencia (S 1,3 / A 1,0 / B 0,8 / C 0,6); suma cero; `recompute_all_elo` reproduce el histórico en orden (`fecha`, `transfermarkt_match_id`, `partido_id`) desde 1000.

**Línea base del backtest (2021+, 43.296 partidos con ambos DTs ≥30 PJ previos), Brier del resultado esperado:** constante 0,1783; HFA 0 → 0,1681; HFA 30 → 0,1637; HFA 60 → 0,1622; HFA 90 → 0,1635. HFA empírico por tipo: liga ~51, copa ~53, internacional ~70.

**Decisiones del modelo (especificación):**

| Tema | Especificación |
|---|---|
| Inicial | 1000. |
| Calibración (DTs nuevos) | Multiplicador por DT `m = 1 + max(0, (30 − n)/30)` (n = partidos previos): 2,0 en n=0; 1,0 desde n=30. El K efectivo del partido usa el **promedio de m de ambos DTs** (preserva suma cero y conservación de masa). |
| K base | 20 liga, 30 eliminatorias, 40 finales (arreglar la detección, T1.4) × multiplicador de calibración. |
| Ventaja de local | Valor global único, ajustado por grilla en {45, 55, 60, 65, 75}. |
| MOV | Variantes a comparar: (a) actual, (b) actual con tope 2,0, (c) amortiguada por favorito: `ln(|d|+1) · 2,2 / (diff_elo_ganador·0,001 + 2,2)`. |
| Inactividad | No se degrada el rating. Al volver tras ≥12 meses sin partidos se trata como si tuviera 15 partidos previos (m=1,5). "Activo" = jugó en los últimos 365 días. |
| Interinos | El rating pertenece a la persona. Si falta un DT y no se puede imputar, el partido se descarta (no hay DT fantasma). |
| Capa A | Cabecera pública: ELO DT vs ELO DT. |
| Capa B | Experimento (T1.8-T1.10): ELO ajustado por plantel (ver T1.8). |

**Protocolo de validación:**
1. `scripts/validate_elo.py` (suma cero, masa, duplicados).
2. Backtest walk-forward desde 2016 con ambos DTs ≥30 PJ previos: Brier del resultado esperado, log-loss 1X2 (modelo de empate fijo estilo Davidson, parámetro ajustado), tabla de calibración por tramos de E; desgloses por año y nivel de competencia; línea base = constante local.
3. Grilla chica (12-16 combinaciones): HFA, K base, calibración on/off, variante de MOV, `inicio ∈ {2000, 2012, 2015}`. Entrenar con 2016-2022; validar con 2023-2026. Elegir la configuración más simple a menos de 0,0005 del mejor log-loss.
4. Sanidad con ~10 DTs conocidos (lista aprobada por el usuario): ≥7 en el top 30 de activos con ≥100 PJ.
5. Estabilidad semana a semana: ningún DT activo se mueve de forma absurda.

---

## T1.1: Harness de backtest

- **Tipo:** ⚙️.
- **Depende de:** T0.3 (fechas correctas).
- **Objetivo:** evaluar parámetros sin tocar la base.
- **Archivos:** `backtest.py` (lógica pura, sin DB ni matplotlib), `scripts/backtest_elo.py` (CLI que carga partidos de la DB a memoria), `tests/test_backtest.py` (datos sintéticos).
- **Pasos:**
  1. Cargar tuplas `(fecha, tm_match_id, partido_id, dt_local, dt_visita, goles, factor_k, coeficiente, tipo, nivel)` ordenadas como `recompute_all_elo`.
  2. Replay en memoria con `EloParams` (T1.2 puede venir antes; si no, parámetros mínimos propios y migrar después).
  3. Métricas: Brier del resultado esperado, log-loss 1X2 (empate Davidson con parámetro ajustado en el tramo de entrenamiento), tabla de calibración por tramos de E, desglose por año y nivel.
  4. Filtros: desde año, mínimo de PJ previos de ambos DTs.
- **Aceptación:** con los parámetros actuales (HFA 30, sin calibración) reproduce Brier ≈ 0,1637 en 2021+ con ambos DTs ≥30 PJ previos (tolerancia 0,0005) y ≈ 0,1783 la constante; tests del cálculo de métricas con datos chicos; sin escrituras en la DB.

## T1.2: `EloParams` retrocompatible

- **Tipo:** ⚙️.
- **Depende de:** —.
- **Objetivo:** parametrizar HFA, K, MOV, calibración e inactividad sin cambiar el comportamiento actual.
- **Archivos:** `elo.py`, `tests/test_elo.py`.
- **Pasos:** `@dataclass(frozen=True) EloParams(hfa=30.0, mov_mode="actual", mov_cap=None, prov_n=0, prov_mult=1.0, inactividad_dias=None, ...)`; `compute_elo_delta(..., params: EloParams | None = None)`. Con `params=None` el resultado es idéntico al actual. Mantener `HOME_ADVANTAGE`, `INITIAL_ELO` y las firmas públicas (también en `DT.py`).
- **Aceptación:** los 36 tests existentes pasan sin cambios; tests nuevos por cada parámetro (HFA, tope de MOV, variante amortiguada).

## T1.3: K de calibración e inactividad

- **Tipo:** ⚙️.
- **Depende de:** T1.2.
- **Objetivo:** multiplicador de K por experiencia (promedio de ambos DTs) y por regreso tras ≥12 meses.
- **Archivos:** `elo.py`, `services.py` (`recompute_all_elo` con contadores por DT: partidos previos y última fecha; `process_match_elo` obtiene el contador de la DB), `tests/test_elo.py`, `tests/test_services.py`.
- **Aceptación:** suma cero por partido y masa conservada (`validate_elo.py` en verde con parámetros activados); test de que dos DTs con 0 PJ mueven el doble que dos con ≥30; test de regreso tras inactividad; con los defaults el recompute da los mismos resultados que antes.

## T1.4: K de eliminatorias

- **Tipo:** ⚙️.
- **Depende de:** T1.2.
- **Objetivo:** que `infer_factor_k` detecte rondas reales (hoy casi nunca dispara).
- **Archivos:** `scraping/pipeline.py`, `scripts/refresh_factor_k.py` (dry-run por defecto, `--apply`), `tests/test_pipeline.py`.
- **Pasos:**
  1. Listar los textos distintos de `matchday` del caché para CLI, CS, ARCA, CDLP (y UEFA si ya está) con su frecuencia.
  2. Mapear a K (30 eliminatorias, 40 finales, 20 resto) y escribir tests con esos textos reales.
  3. El script recalcula `partidos_dt.factor_k` desde el caché (fixtures) por `transfermarkt_match_id`, sin requests.
- **Aceptación:** reporte antes/después de partidos con K ≠ 20 (hoy 1.099); tests con textos reales; el script es idempotente; después, `recompute` y `validate_elo.py` en verde.

## T1.5: Búsqueda de parámetros y sensibilidad al inicio

- **Tipo:** ⚙️ + 👤 (parada humana).
- **Depende de:** T1.1, T1.3, T1.4.
- **Objetivo:** elegir la configuración con evidencia.
- **Archivos:** `scripts/tune_elo.py`, `docs/MODELO_ELO.md`, CSV en `data/audit/tune_elo.csv`.
- **Pasos:**
  1. Grilla del protocolo (HFA {45,55,60,65,75}, K base {15,20,30}, calibración on/off, MOV {a,b,c}, `inicio` {2000, 2012, 2015}); no hace falta el producto completo, usar una grilla reducida de 12-16 combinaciones justificadas.
  2. Entrenar con 2016-2022 y validar con 2023-2026.
  3. **Experimento de sensibilidad:** ratings actuales de DTs activos calculando desde 2000 vs desde 2015 (correlación de rangos de Spearman y tabla de las 20 mayores diferencias, con nombre).
  4. `docs/MODELO_ELO.md` con la configuración elegida, su mejora vs la actual y la conclusión sobre el inicio.
- **Aceptación:** CSV con todas las combinaciones; la configuración elegida mejora el log-loss de validación respecto de la actual; documento escrito.
- **Parada humana:** el usuario aprueba los parámetros y el inicio (2000 vs 2015) antes de T1.6/T1.7.

## T1.6: Sanidad con DTs conocidos

- **Tipo:** ⚙️ + 👤.
- **Depende de:** T1.5.
- **Archivos:** `scripts/sanity_check.py`, `data/sanity_coaches.json`.
- **Pasos:** imprimir el top 25 de activos con ≥100 PJ con la configuración elegida; proponer una lista de ~10 DTs (por ejemplo Guardiola, Ancelotti, Simeone, Klopp, Arteta, Flick, Luis Enrique, Inzaghi, Gallardo y algunos argentinos) para que el usuario la corrija; verificar que ≥7 estén en el top 30; revisar trayectorias de Klopp, Guardiola y Gallardo.
- **Aceptación:** el script corre y reporta; el usuario aprueba la lista.
- **Parada humana:** aprobar la lista.

## T1.7: Aplicar el modelo y recalcular

- **Tipo:** ⚙️.
- **Depende de:** T1.6.
- **Archivos:** constantes/defaults de `EloParams` con los valores elegidos, `MODELO_VERSION` en `elo.py`, `ESTADO.md`.
- **Pasos:** backup de la DB (T0.1); aplicar parámetros; `refresh_factor_k.py --apply` si T1.4 lo requiere; `recompute`; `validate_elo.py`; guardar comparación de rankings antes/después en `data/audit/ranking_antes_despues.md`.
- **Aceptación:** `validate_elo.py` en verde; tests en verde; comparación guardada.

## T1.8: Capa B en el harness (ELO ajustado por plantel)

- **Tipo:** ⚙️.
- **Depende de:** T1.1.
- **Objetivo:** implementar el experimento sin tocar la DB.
- **Especificación:**
  - Cada equipo vale `R_club + D_dt`. `R_club` arranca en 1000 y `D_dt` en 0.
  - Expectativa: `E` con equipo local + HFA vs equipo visita (escala 400).
  - `delta = K·C·G·(S − E)`. El DT recibe `α·delta` y su club `(1−α)·delta`; el visitante recibe el opuesto (suma cero). α ∈ {0,5; 0,65; 0,8}.
  - ELO publicable de la capa B = `1000 + D_dt`.
- **Archivos:** `backtest.py` (modo `plantel`), tests.
- **Aceptación:** tests de suma cero y de invarianza (con clubes idénticos, la capa B se reduce a la capa A); el modo corre sobre los datos reales.

## T1.9: Comparar capa B vs capa A

- **Tipo:** ⚙️.
- **Depende de:** T1.8, T1.5.
- **Archivos:** `scripts/tune_elo.py`, `docs/MODELO_ELO.md`.
- **Pasos:** log-loss de validación de ambas capas; casos de control: DT que pasa de club grande a chico (rating antes y después) y DTs de larga permanencia (el club absorbe mérito); top 20 de la capa B.
- **Aceptación:** tabla comparativa y análisis de los casos de control escritos en el documento.

## T1.10: Decisión de la capa B

- **Tipo:** ⚙️ + 👤.
- **Depende de:** T1.9.
- **Criterio de adopción:** mejora del log-loss de validación ≥ 0,001 sobre la capa A **y** pasa la sanidad (T1.6).
- **Aceptación:** `docs/MODELO_ELO.md` con la recomendación (adoptar como contenido secundario "rinde por encima de su plantel", o descartar); el usuario decide. Si se adopta, crear una tarea nueva para guardarla en snapshots (no se hace aquí).
