# Fechas de partidos: el defecto y los conflictos que quedan

Documento de cierre de **T0.3** (2026-10-27). Explica por qué había 152 casos de un DT
con más de un partido el mismo día, qué se corrigió y por qué quedan 25.

## 1. El defecto

En el calendario (`gesamtspielplan`) Transfermarkt imprime la fecha **solo en la primera
fila de cada bloque**; las filas siguientes traen la celda de fecha vacía
(`td.hide-for-small`). El parser hacía *forward-fill* de la última fecha vista.

Ese forward-fill es lo que TM indica (las filas heredan la fecha del bloque), pero el
bloque **no siempre es un solo día**: puede abarcar varias jornadas. Ejemplo testigo,
`TDeC` 2006 (Liga 1 de Perú):

| Jornada | Fecha en el calendario | Fecha real (página del partido) |
|---|---|---|
| 3 | 2006-07-30 | 2006-07-30 |
| 4 | 2006-07-30 (heredada) | **2006-08-05** |
| 5, 6, 7 | 2006-07-30 (heredada) | otras fechas |
| 8 | 2006-08-30 | 2006-08-30 |

Resultado: partidos con fecha corrida (a veces semanas), desorden en el replay del ELO y
152 casos de un DT con dos partidos el mismo día.

## 2. Lo que se arregló

1. **Código** (`scraping/parser.py`, `scraping/pipeline.py`, `scraping/dto.py`):
   `parse_report_date` extrae la fecha exacta de la página del partido
   (`p.sb-datum` → link `/datum/AAAA-MM-DD`), queda en `MatchReport.fecha` y
   `load_normalized` la prefiere sobre la del fixture. De ahora en adelante todos los
   partidos que se carguen usan la fecha buena.
2. **Histórico** (`scripts/fix_fechas.py`): se re-descargaron **669** páginas de partido
   (los 279 que generaban conflicto más los vecinos del mismo bloque) y se corrigieron
   **187** fechas en `partidos_dt`. Después: `recompute` + `validate_elo.py` en verde
   (0 duplicados, 0 partidas con suma ≠ 0, masa ELO 6.686.000 = 6.686 × 1000).
3. **Auditoría** (`scripts/audit_data.py`): los conflictos pasaron de **152 a 25**.

Los reportes cacheados ahora guardan `fecha`, así que una futura re-descarga no hace
falta. Si aparece un caso nuevo, `python3 scripts/fix_fechas.py --fetch --bloques` baja
solo los que falten y `--apply` los corrige (es idempotente).

## 3. Los conflictos que quedan (explicados)

> Actualización 2026-10-28: tras recuperar los partidos descartados por falta de DT
> (ver `ESTADO.md`) el total pasó de 25 a **32**: los 7 nuevos aparecieron porque
> ahora están cargados partidos que antes no estaban. Todos siguen el mismo patrón de
> error de atribución de TM (23 en la misma jornada, 9 en jornadas o competencias
> distintas en las que un club figura dos veces el mismo día). Las fechas están
> confirmadas por las páginas de partido.

Ninguno es un problema de fechas: **la fecha de esos partidos está confirmada por la
página del partido**. El problema es que Transfermarkt asigna el **mismo entrenador a dos
clubes distintos el mismo día**, que es imposible.

### 3.1. Misma jornada, dos clubes (20 casos)

El DT figura en dos partidos de la misma jornada, con clubes diferentes:

| DT | Fecha | Club A | Club B |
|---|---|---|---|
| Hikmet Karaman | 2001-04-28 | Kocaelispor | Galatasaray |
| Celso Roth | 2001-08-15 | Palmeiras | Sport Recife |
| Hanspeter Latour | 2004-10-31 | Young Boys | Grasshopper |
| Rıza Çalımbay | 2005-08-14 | Gençlerbirliği | Beşiktaş |

(20 en total; el listado completo está en `data/audit/conflictos_fecha.json`.)

Es un error de atribución de Transfermarkt: o el DT no dirigió a uno de los dos, o es un
homónimo que TM fusionó bajo el mismo `trainer_id`.

### 3.2. Ligas distintas, mismo día (5 casos)

**a) El DT aparece con dos clubes distintos en ligas distintas (3 casos):**

| DT | Fecha | Partido A | Partido B |
|---|---|---|---|
| Guto Ferreira | 2016-07-03 | Chapecoense (BRA1) | Bahia (BRA2) |
| Hernán Torres | 2018-08-19 | Independiente Medellín (COL1) | Cantolao (TDeA) |
| Mariano Echeverría | 2026-09-06 | Maipú (ARG2) | Trujillanos FC (VZ1C) |

El caso de Echeverría (Argentina y Venezuela el mismo día) es el más claro: son dos
personas distintas, o un cambio de club mal cerrado en TM.

**b) El mismo club aparece dos veces el mismo día, en jornadas distintas (1 caso):**

| DT | Fecha | Partido A | Partido B |
|---|---|---|---|
| Charles Lopéz | 2017-10-17 | Deportivo Táchira vs Anzoátegui (md 13) | Portuguesa vs Anzoátegui (md 15) |

Deportivo Anzoátegui "juega" dos partidos el mismo día. Error de fixture de TM
(Venezuela tiene series históricas incompletas).

**c) El mismo partido cargado en dos competencias (1 caso):**

| DT | Fecha | Partido A | Partido B |
|---|---|---|---|
| Gustavo Costas | 2020-10-26 | Guaraní vs Olimpia (PR1A, md 4) | Guaraní vs Cerro (PR1C, md 2) |

Paraguay jugó Apertura y Clausura en el mismo año calendario por la pandemia; el mismo
club tiene dos partidos el mismo día en los dos torneos. Es un solapamiento de fixtures
de TM, no un error de fecha.

## 4. Impacto en el ELO

Es chico: cada caso suma a lo sumo un partido de más para ese DT, y el replay usa la
fecha pero no prohíbe dos partidos el mismo día. Los rankings de punta no cambiaron
(Arteta 1530,99 / Flick 1529,67 en ambos casos).

**Decisión pendiente del usuario** (en `docs/plan/PENDIENTES.md`): dejarlos como están
(recomendado) o descartar esos partidos de la base en una limpieza posterior.

## 5. Cómo detectar casos nuevos

```
python3 scripts/audit_data.py          # conflictos + cobertura (sin VPN, ~15 s)
```

Si el número sube, revisar `data/audit/conflictos_fecha.json`: si los partidos tienen
**jornadas distintas**, es el defecto de fechas (usar `fix_fechas.py`); si es la misma
jornada, es atribución de TM.
