# Cobertura de Argentina

Documento de **T0.4** (2026-10-27). Explica por qué faltaban temporadas argentinas en
la base, qué se recuperó y qué queda afuera.

## 1. Diagnóstico

Había tres causas distintas, no una sola:

### a) El guard de temporada descartaba las temporadas agosto-junio (bug)

`season_is_aligned` exigía que la temporada arrancara **exactamente** en el año pedido
(`min(año de fechas) == season`). Para las Ligas 2016/17 a 2019/20, Transfermarkt
devuelve fechas de agosto del año anterior, así que el fixture se descartaba entero con
el mensaje "desalineado (TM devolvió otra temporada)".

Al pedir `--season 2017` TM devuelve la temporada 2016/17:

| Pedido | Partidos | Fechas |
|---|---|---|
| AR1N 2017 | 450 | 2016-08 a 2017-06 |
| AR1N 2018 | 378 | 2017-08 a 2018-05 |
| AR1N 2019 | 325 | 2018-08 a 2019-05 |
| AR1N 2020 | 276 | 2019-07 a 2020-05 |
| ARG2 2017 | 230 | 2016-08 a 2017-06 |
| ARG2 2018 | 300 | 2017-08 a 2018-05 |
| ARG2 2019 | 300 | 2018-08 a 2019-05 |
| ARG2 2020 | 333 | 2019-07 a 2020-05 |

**Arreglo:** el guard ahora acepta la temporada si cae **dentro** del rango de fechas
(`min <= season <= max`). Sigue rechazando el caso peligroso de pedir un año inexistente
y recibir la temporada actual (por ejemplo, pedir 2000 y recibir fechas de 2026).

### b) La Primera División cambió de competencia en 2025 (no es un bug)

Transfermarkt da por terminada la competencia `AR1N` ("Professional Football League
(- 23/24)"): su selector de temporadas llega hasta 23/24. Desde 2025 la Primera se juega
como **Torneo Apertura** y **Torneo Clausura**, cada uno con su propio código:

| Código | Nombre | Temporadas | Partidos por torneo |
|---|---|---|---|
| `ARG1` | Torneo Apertura | 2025, 2026 | 240 |
| `ARGC` | Torneo Clausura | 2025, 2026 | 240 |

Mismos clubes que `AR1N` (Boca, River, Racing, Independiente, San Lorenzo…), misma
`kind="liga"`, `saison_offset=1` (año calendario). **Arreglo:** se dieron de alta en el
catálogo con `first_season=2025`.

### c) La Copa de la Liga dejó de jugarse (nada que recuperar)

`CDLP` tiene datos hasta 2024 porque en 2025 se reemplazó por el formato
Apertura/Clausura. Al pedirle 2017-2026 TM devuelve siempre la temporada 2024 (fallback),
así que el guard la rechaza correctamente y no se descarga.

## 2. Lo que se recuperó

Backfill ejecutado el 2026-10-27/28 (`scripts/backfill_argentina.sh`): ~3.500 requests
a 3 workers durante ~5 h. Resultado: la base pasó de 191.931 a **195.299 partidos**
(+3.368) y de 6.686 a **6.732 DTs**; `validate_elo.py` en verde (0 duplicados, suma 0,
masa 6.732.000). Los conflictos de fecha no cambiaron (25).

Cobertura por año calendario (`ratio = partidos en la base / partidos en TM`):

| Competencia | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AR1N (Liga) | 1,00 | 0,90 | **0,98** | **1,00** | **1,00** | **1,00** | 0,99 | 0,99 | 0,99 | 1,00 | — | — |
| ARG2 (Primera Nacional) | 0,65 | 0,71 | **0,79** | **0,98** | **1,00** | **0,98** | 0,98 | 0,99 | 0,98 | 1,00 | 0,99 | 1,00 |
| ARG1 (Apertura) | — | — | — | — | — | — | — | — | — | — | **0,99** | **1,00** |
| ARGC (Clausura) | — | — | — | — | — | — | — | — | — | — | **1,00** | **1,00** |

En negrita lo que se recuperó en T0.4 (antes 0 % o inexistente). Último partido cargado:
`ARGC` 2026-10-27 (el Clausura está en juego), `ARG2` 2026-09-21, `ARG1` 2026-05-05
(el Apertura terminó).

Los porcentajes que faltan son partidos que Transfermarkt publica **sin entrenador** en
el reporte (interinos y datos viejos), no huecos del calendario: en `ARG2` 2017 son 108
de 230. Se van a recuperar con la imputación por etapas de DT (T0.9).

## 3. Qué queda afuera y por qué

- **Argentina 2000-2014**: Transfermarkt no tiene esas ligas. Requiere una fuente externa;
  está como estudio en T0.11. Mientras tanto, los DTs con carrera previa a 2015 llevan la
  salvedad "histórico incompleto".
- **Copa de la Liga 2017-2019**: no existía (empezó en 2020, y dejó de jugarse en 2024).
- **Partidos con DT faltante**: cubierto en la sección 2 (T0.9).

## 4. Cómo se mantiene al día

El pipeline semanal (T2.3) pide las temporadas en curso de cada competencia del catálogo:
para Argentina, `ARG1`/`ARGC` (año calendario) y `ARG2`. `AR1N` y `CDLP` tienen
`last_season=2024` en el catálogo, así que la auditoría no las reporta con huecos y el
pipeline no las pide.

## 5. Cambios de código de T0.4

- `scraping/pipeline.py::season_is_aligned`: acepta la temporada si cae dentro del rango
  de fechas (antes exigía que arrancara exactamente en ese año). +3 tests.
- `scraping/leagues_catalog.py`: alta de `ARG1` y `ARGC` (`first_season=2025`) y nuevo
  campo `last_season` (usado por `AR1N` y `CDLP`, ambas cerradas en 2024).
- `scripts/verify_competitions.py`: `--no-align-check`, `--saison-offset` y `--path` para
  diagnosticar códigos y temporadas fuera del catálogo; el detalle ahora muestra las
  fechas mínima y máxima.
- `auditoria.py` / `scripts/audit_data.py`: `ultima_temporada` para no reportar huecos
  posteriores al cierre de una competencia. +1 test.
- `scripts/backfill_argentina.sh` (**nuevo**): backfill reproducible a 3 workers.
