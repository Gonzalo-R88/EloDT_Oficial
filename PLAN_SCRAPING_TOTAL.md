# PLAN — SCRAPING TOTAL (2000–2026)

> Objetivo: backfill histórico de las principales ligas del mundo en
> Transfermarkt, para luego enriquecer con la API key. Fuente de datos:
> `scraping/leagues_catalog.py` (50 competencias verificadas).

## 1. Universo

| Confederación | Competencias | Ejemplos |
| :--- | ---: | :--- |
| UEFA | 25 | GB1, GB2, ES1, ES2, IT1, IT2, L1, L2, FR1, FR2, PO1, NL1, BE1, TR1, GR1, RU1, UKR1, SC1, A1, C1, DK1, SE1, NO1, PL1, TS1 |
| CONMEBOL | 22 | AR1N, ARG2, CDLP, CDCA, ARCA, CLI, CS, RESU, BRA1, BRA2, URU1, CLPD, COL1, EC1N, TDeA, TDeC, PR1A, PR1C, BO1A, BO1C, VZ1A, VZ1C |
| CONCACAF | 2 | MEX1, MLS1 |
| AFC | 2 | JAP1, SA1 |
| **Total** | **51** | |

Ventana: **2000–2026 (27 temporadas)**. `saison_offset=1` en las ligas de año
calendario (Sudamérica + Suecia, Noruega y Japón, que Transfermarkt agrupa bajo
el `saison_id` del año anterior). Perú, Paraguay, Bolivia y Venezuela tienen
Apertura/Clausura (dos competencias por año).

## 2. Modelo de estimación

```
requests_totales = Σ_ligas [ temporadas × (1 fixture + partidos_por_temporada) ]
segundos_por_request = (delay_min + delay_max)/2 + latencia_red
                        = (1.5 + 4.0)/2 + 0.3 = 3.05 s
horas_totales = requests_totales × 3.05 / 3600
días = horas_totales / (workers × horas_por_día)
```

- **Requests totales: ~350.510** (≈ 349.000 reportes de partido + ~1.380 fixtures).
- Es una **cota superior**: no todas las ligas tienen datos desde 2000 (muchas
  arrancan ~2010), y algunos reportes no traen DT (se omiten al persistir, pero
  igual cuestan un request).

## 3. Escenarios de tiempo

| Workers | 24/7 | 8 h/día |
| ---: | ---: | ---: |
| 1 | 12,4 días | 37,1 días |
| 2 | 6,2 días | 18,6 días |
| 3 | 4,1 días | **12,4 días** |
| 4 | 3,1 días | 9,3 días |
| 6 | 2,1 días | 6,2 días |

Recomendado: **3 workers**. En la práctica (2026-09-23) se corre **24/7** en tmux
(el cliente reintenta con backoff y TM no está devolviendo 429/503), lo que baja
el total de ~12,4 a **~4,1 días**. El modelo asume `3,05 s/request`; la tasa
observada en logs (~1 partido cada 3 s) lo confirma.

## 4. Plan diario (3 workers × 8 h ≈ 28.300 requests/día)

Cada "tramo" es una liga (o parte de una liga) asignada a ese día. El scraper es
reanudable por partido, así que cortar una liga entre dos días es seguro.

```
Día  1: ARG2, GB2
Día  2: GB2, MLS1, ES2
Día  3: ES2, BRA1, BRA2, GB1
Día  4: GB1, ES1, IT1, IT2
Día  5: IT2, JAP1, AR1N, TR1
Día  6: TR1, FR2, L1, L2
Día  7: L2, FR1, PO1, NL1
Día  8: NL1, PL1, SA1, CLPD, BO1C
Día  9: BO1C, BE1, RU1, UKR1, SE1
Día 10: SE1, NO1, TS1, C1, BO1A, SC1
Día 11: SC1, CDLP, COL1, A1, GR1, TDeA
Día 12: TDeA, CS, CLI, TDeC, MEX1, PR1A, PR1C, DK1, URU1
Día 13: URU1, VZ1A, VZ1C, ARCA, EC1N, CDCA, RESU
```

Generar/actualizar el plan en cualquier momento:

```bash
python scripts/plan_scraping.py --workers 3 --hours-per-day 8
python scripts/plan_scraping.py --workers 3 --hours-per-day 8 --csv data/output/plan_scraping.csv
```

## 5. Fases de ejecución

### Fase 0 — Verificar códigos (✅ ejecutada)
```bash
python scripts/verify_competitions.py --season 2024
```
Resultado: **49/51 OK**. Dos con cobertura incompleta en TM (esperado):
- `EC1N` (Ecuador): TM sólo expone temporadas recientes → `first_season=2025`.
- `BO1A` (Bolivia Apertura): huecos de temporadas → el guard de temporada los saltea.

Correcciones aplicadas en el catálogo: `CHL1 → CLPD` (Chile), `VZ1L → VZ1A/VZ1C`
(Venezuela), `saison_offset=1` para SE1/NO1/JAP1 (año calendario). Se agregó en
`scraping/pipeline.py::season_is_aligned` un **guard** que descarta el fixture si
TM devuelve otra temporada (evita cachear partidos de otro año).

Las 51 competencias ya están dadas de alta en `scraping/competitions.py`
(`COMPETITIONS` se autoextiende desde el catálogo).

### Fase 1 — Backfill (≈13 días, en tmux)
Promover las ligas verificadas a `scraping/competitions.py` (`COMPETITIONS`) y
lanzar por lotes diarios. Un worker por lote:

```bash
tmux new -d -s aep-backfill 'python scraper_transfermarkt.py ingest \
  --leagues ARG2,GB2 --from 2000 --to 2026 2>&1 | tee data/logs/backfill.log'
tmux capture-pane -t aep-backfill -p | tail -20
```
La caché (`data/raw/{code}/{season}/`) es atómica y reanudable: repetir el mismo
comando salta lo ya descargado.

**Estado real (2026-09-23):** Argentina y Conmebol ya cargadas. El "resto"
(43 ligas, `scripts/backfill_resto.sh`, 3 workers en tmux `aep-resto`) va al
**5,4 %** y le restan **~290.000 requests → ~82 h**. Corriendo 24/7 son **~3,4
días** (a 8 h/día serían ~10,8 días). Estimarlo con el modelo del §2:

```bash
python scripts/plan_scraping.py --workers 3 --hours-per-day 24
# resto (43 ligas): ~306.635 requests -> ~82 h/worker
```

### Fase 2 — Carga y recompute
`ingest` ya persiste con ELO. Al cerrar cada liga (o al final):
```bash
python scraper_transfermarkt.py recompute
python scripts/validate_elo.py --min-partidos 20 --top 20
```

### Fase 3 — Actualización semanal
Un comando que scrapea la temporada en curso de todas las ligas y persiste los
partidos nuevos (idempotente por `transfermarkt_match_id`):
```bash
python scraper_transfermarkt.py ingest --all-competitions --season 2026
```
Automatizable por cron (ej. lunes 06:00). La API key se conecta después para
eventos/alineaciones y para no depender del scraping en vivo.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
| :--- | :--- |
| Rate limit / bloqueo de TM (429/503) | Delays 1.5–4 s, backoff exponencial ya implementado, no más de 3–4 workers, reintentos. |
| Códigos/slugs/offsets inválidos | Fase 0 de verificación antes de lanzar; `season_is_aligned` descarta fixtures de otra temporada. |
| Semántica de temporada (Apertura/Clausura, año calendario) | `saison_offset` por competencia; ligas de dos torneos se registran como dos competencias. |
| Ligas sin datos desde 2000 | `first_season` por competencia; la verificación ajusta el rango real. |
| Reportes sin DT (interinos) | Se omiten al persistir (`sin_dt`); quedan cacheados para reprocesar si se resuelve. |
| Coeficientes ELO para ligas globales | Provisional (S/A/B/C) en el catálogo; a revisar metodológicamente antes del `recompute` final. |
| Espacio en disco | ~15 MB por ~6.000 partidos → el backfill total ronda ~1 GB de JSON. |
| Corte del proceso | tmux + caché atómica + `--resume` por re-ejecución. |

## 7. Notas metodológicas a decidir

1. **Coeficientes globales**: el doc maestro define S/A/B/C para Argentina y
   Conmebol. Para ligas europeas/globales hay que fijar una jerarquía (hoy
   provisional en el catálogo).
2. **Apertura/Clausura**: ¿tratar cada torneo como competencia independiente
   (actual) o unificar el año? Afecta el volumen y la continuidad del ELO.
3. **API key**: definir si la API reemplaza el scraping en vivo o solo enriquece
   (eventos, sustituciones → `impacto_banco`).
