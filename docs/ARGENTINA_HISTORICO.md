# Argentina 2000-2014: estudio de factibilidad

Documento de **T0.11** (2026-11-19). Responde si se puede recuperar la liga argentina anterior a 2015, con qué fuentes, cuánto cuesta y qué cambia. **No se implementó nada**: la decisión es del usuario (sección 8).

## 1. El problema

La base no tiene ningún partido de la liga argentina anterior a 2015. De 2000 a 2014 sólo hay copas internacionales (`CLI`, `CS`). Consecuencias medidas:

- Los técnicos argentinos con carrera previa a 2015 llevan un ELO armado sólo con copas: en septiembre de 2013 los cinco grandes estaban entre 981 y 1037, pegados al 1000 inicial.
- El caso que lo mostró: en el post de GTA V/GTA VI no se pudo comparar el ELO de Bianchi (2013) con el de Arruabarrena (hoy) sin que el de hoy pareciera mucho mejor.
- Falcioni, por ejemplo, suma 16 partidos de copa en Boca en 2011-2012 y le faltan 76 de liga.

## 2. Transfermarkt: confirmado que no los tiene

Verificado el 2026-11-19 con el cliente del proyecto (pocas requests):

- La Primera (`AR1N`) lista 67 temporadas en su selector, pero salta de 1938/39 a **2014/15**. No hay nada entre 1939 y 2013.
- Pedir una temporada intermedia no falla: devuelve la actual (2024) como respaldo. Por eso `season_is_aligned` las rechaza.
- La lista de competencias argentinas (`/wettbewerbe/national/wettbewerbe/9`) no tiene ningún torneo Inicial, Final ni Transición. Sólo aparecen restos como la promoción de 2011/12 o la Liguilla 2014/15.
- La Primera Nacional (`ARG2`) lista 21 temporadas con huecos (2000, 2004, 2007 a 2025), pero la base no tiene ninguna anterior a 2015 (auditoría: 0 fixtures).

## 3. Fuentes de resultados

| Fuente | Cobertura | Qué trae por partido | Formato | Notas |
|---|---|---|---|---|
| **football-data.co.uk** (`/new/ARG.csv`) | 2012/13 a hoy (6.475 filas) | fecha, hora, local, visitante, goles | CSV | Cubre toda la brecha 2012-2014. |
| **RSSSF** (`rsssf.org/tablesa/`) | 2000/01 a 2011/12 y más | fecha (día), local, visitante, goles, goleadores | texto plano | Una página por temporada. |
| Wikipedia (es) | todos los torneos | fecha, hora, estadio, goles | HTML | Respaldo y verificación. |

### football-data.co.uk

Temporadas relevantes y cantidad de partidos:

| Temporada | Partidos | Torneos |
|---|---|---|
| 2012/2013 | 381 | Inicial 2012 + Final 2013 |
| 2013/2014 | 383 | Inicial 2013 + Final 2014 |
| 2014 | 190 | Transición 2014 |

Son **954 partidos** que cierran con los torneos que se jugaron. Se contrastó con la base para 2016/17 a 2019/20: 450, 378, 324 y 276 partidos contra 450, 378, 325 y 276 de `AR1N`. Coinciden salvo un partido.

### RSSSF

| Página | Temporada | Estado |
|---|---|---|
| `arg01` a `arg09` | 2000/01 a 2008/09 | Una por temporada; con rondas, fecha (`[Aug 13]`) y goles. |
| `arg2010` | 2009/10 | Apertura 2009 y Clausura 2010. |
| `arg2011` | 2010/11 | Completa (Primera y Primera B Nacional). |
| `arg2012` | 2011/12 | Completa. |
| `arg2013` | 2012/13 | Sirve para cruzar con football-data. |

Doce páginas para la Primera de 2000/01 a 2011/12 (~4.560 partidos si todas tienen 20 equipos). Se verificó cada página de `arg01` a `arg2010`: todas traen 38 rondas con fechas y entre 353 y 395 líneas de partido, y el título coincide con la temporada. El año se infiere de la temporada. Hay que manejar las líneas `abd` (abandonado) y `awd` (adjudicado), y la codificación latin-1.

Las páginas traen también la Primera B Nacional, lo que deja abierta la etapa C (sección 7).

## 4. Qué técnico dirigía cada partido (lo difícil)

Ninguna fuente de resultados dice quién dirigía. Hay que armarlo desde el **historial de técnicos de cada club**.

Transfermarkt lo tiene: `/{slug}/mitarbeiterhistorie/verein/{id}` lista cada etapa con técnico, fecha de inicio, fecha de fin, partidos, y marca los interinos. Se probó con Boca (59 etapas). Es la fuente que T0.7 buscaba.

**Salvedad de precisión.** Muchas fechas vienen redondeadas al 1 de enero o al 31 de diciembre:

| Técnico | En Transfermarkt | Real |
|---|---|---|
| Falcioni | 01/01/2011 a 31/12/2012 | 13/02/2011 a 08/12/2012 |
| Bianchi | 01/01/2013 a 28/08/2014 | 09/02/2013 a 27/08/2014 |

No molesta donde el cambio cae en el receso (no hay partidos en enero), pero un cambio a mitad de torneo con fecha aproximada asignaría mal los partidos del medio. Por eso hace falta validar.

**Muestra cruzada (Falcioni en Boca, 2011-2012).** Con el historial de etapas, los partidos que le tocarían son 4 torneos de 19 fechas (76) más 16 de copas internacionales que ya están en la base: **92, contra 96 que le asigna Transfermarkt**. Los 4 que faltan son casi seguro de la Copa Argentina 2011/12, que tampoco está cargada. Es consistente. Además, la primera fecha del Clausura 2011 en RSSSF (13/2, Boca 1-4 Godoy Cruz) es el debut real de Falcioni.

**Validación propuesta:** por cada etapa, comparar los partidos asignados contra los que informa Transfermarkt. Como incluyen competencias que no tenemos, la diferencia tiene que ser chica y explicable, y se revisa a mano la que no lo sea.

## 5. Cuánto cuesta

| Etapa | Partidos | Requests a Transfermarkt | Fuentes |
|---|---|---|---|
| A: 2012/13 a 2014 | ~950 | ~35 (historial de ~30 clubes) | football-data |
| B: 2000/01 a 2011/12 | ~4.560 | ~15 más | RSSSF |
| C (opcional): Primera B Nacional 2000-2014 | ~5.500 | ~60 más (clubes de ascenso) | RSSSF |

Todo queda lejos del umbral de 500 requests: son minutos a 14 req/min, no horas. El trabajo está en el código, no en el scraping:

1. Parsers de las dos fuentes y un CSV normalizado (`data/historico/`).
2. Tabla de nombres de club a `tm_id` (~45 clubes en A y B, revisada a mano).
3. Scraper y parser de las etapas de cada club (es T0.8 acotado a Argentina).
4. Asignación del técnico por fecha, con manejo de interinos y de partidos entre etapas.
5. Competencias nuevas para el histórico (`ARGH`, y `ARG2H` en C) y carga con `transfermarkt_match_id` nulo (la idempotencia ya existe por fecha, competencia y técnicos).
6. Validaciones y `recompute`.

Estimación: 1 a 2 sesiones por etapa.

## 6. Qué cambia (el costo real)

- **Todos los ELO se mueven**, no sólo los de Argentina: el ELO es suma cero y los técnicos con carrera previa a 2015 cambian, y con ellos sus rivales. Cambian los números ya publicados.
- **Las flechas de puestos** del Top 10 comparan contra el snapshot anterior, que tiene los ELO viejos. La primera semana después del recálculo saldría con saltos falsos. Hay que subir la versión del modelo o rehacer los snapshots.
- **Los partidos de liga entran al historial** de técnicos que hoy figuran con pocos partidos (`pj_total`), así que algunos pasan de "provisorio" a establecidos.
- **A favor:** desaparece la salvedad "histórico incompleto" para esa generación de técnicos, y el comparativo de GTA se podría rehacer con ELO real.

Mitigación: respaldo antes (`backup_db.sh --verify`), backtest antes y después (`scripts/backtest_elo.py`) midiendo si mejora la predicción de los partidos argentinos de 2016 en adelante (el ELO inicial de cada técnico debería ser mejor), y comparar el Top 10 antes y después.

## 7. Riesgos

| Riesgo | Efecto | Qué se hace |
|---|---|---|
| Nombres de club ambiguos ("Atlético Tucumán", "San Martín (SJ)") | Partido asignado al club equivocado | Tabla revisada a mano, 0 partidos sin club mapeado. |
| Fechas de etapas redondeadas | Técnico equivocado en cambios a mitad de torneo | Validación por conteo y revisión de las etapas que no cierren; usar fuentes de respaldo (Wikipedia). |
| Interinos sin etapa propia | Partidos sin técnico | Reportarlos y decidir caso por caso en lugar de inventar. |
| `abd` y `awd` en RSSSF | Resultado distinto al jugado | Usar el resultado final y dejar afuera los adjudicados por escritorio. |
| Torneos con formato raro (Reducido, promociones) | Partidos duplicados o faltantes | Comparar con la tabla de posiciones de cada torneo. |

## 8. Recomendación y decisión pendiente

**Recomendación: hacer, por etapas.**

1. **Etapa A primero** (~950 partidos, football-data + etapas de unos 30 clubes). Es lo más barato y repara el período más reciente: los técnicos con carrera de 2012 en adelante, incluido el caso de GTA.
2. **Etapa B** después (RSSSF, 2000/01 a 2011/12), si A sale bien.
3. **Etapa C** (Primera B Nacional) sólo si hace falta; no mejora el ELO de los técnicos de Primera de hoy tanto como A y B.

Después de cada etapa: validación, backtest antes y después, y `recompute` con respaldo.

**Qué tiene que decidir el usuario:**

- [ ] ¿Se hace? (hacer / no hacer / sólo etapa A)
- [ ] ¿Se acepta que el recálculo cambie los ELO ya publicados y que las flechas de la primera semana no sirvan?
- [ ] ¿Se incluye la Primera B Nacional (etapa C) o se deja afuera?

## 10. Etapa A implementada (2026-11-20)

Se hizo la etapa A: **Primera 2012/13, 2013/14 y 2014 más la B Nacional 2013/14**.

| Competencia | Temporada | Partidos | Por club |
|---|---|---|---|
| `ARGH` | 2012/13 | 380 | 38 |
| `ARGH` | 2013/14 | 380 | 38 |
| `ARGH` | 2014 (Transición) | 190 | 19 |
| `ARG2H` | 2013/14 | 462 | 42 |

**Cargados: 1.373 de 1.412** (97,2 %). Los 39 restantes no tienen entrenador asignable:

- **Instituto**: 17 partidos. Transfermarkt no registra a nadie entre el 30/09/2013 y el 05/03/2014.
- **Villa San Carlos**: 11 partidos. Su primera etapa en TM arranca el 09/10/2013, con la temporada ya empezada.
- **San Martín (SJ)**: 6. Hueco de 19-22 días entre etapas (Garnero y Azconzábal).
- **Independiente**: 4, pero el problema es del rival (Colón, San Martín SJ, Villa San Carlos), no del club.
- Resto: huecos de 1 a 12 días entre el fin de una etapa y el arranque de la siguiente.

No se cerraron esos huecos a propósito: asignar el DT saliente cuando la fecha de fin está redondeada es una suposición, y la regla del proyecto es no inventar (T0.9). Se pueden recuperar más adelante con otra fuente.

**Cinco partidos quedaron afuera por no ser de liga**, identificados uno por uno para que cada club cierre con 38 (o 19 en 2014, o 42 en la B):

| Fecha | Partido | Motivo |
|---|---|---|
| 2013-06-29 | Vélez-Newell's | Copa Campeonato 2012/13 |
| 2014-05-25 | San Lorenzo-River | Copa Campeonato 2013/14 |
| 2014-05-24 | Colón-Rafaela | desempate |
| 2015-01-29 | Boca-Vélez | tercer cruce de la temporada |
| 2014-06-11 | Independiente-Huracán | playoff de ascenso |

El caso Boca-Vélez engañaba: parecía un partido postergado de liga, pero es el tercer enfrentamiento del año. Sin sacarlo, Boca y Vélez quedaban con 39 partidos.

### Resultado

Antes de la carga, al 17/09/2013 los cinco grandes estaban entre 980,81 y 1.036,46, todos pegados al 1.000 inicial:

| Club | Antes | Después |
|---|---|---|
| Boca | 1.036,46 | 1.004,82 |
| River | 1.019,96 | 1.062,14 |
| Independiente | 1.009,15 | 1.027,81 |
| Racing | 986,23 | 1.044,99 |
| San Lorenzo | 980,81 | 1.062,90 |

San Lorenzo sube 82 puntos porque ganó el Inicial 2013, que es exactamente la señal que faltaba. El Top 10 mundial casi no se movió (Arteta 1.468, Flick 1.461, Kompany 1.419), como preveía el estudio: el ELO se olvida rápido de los partidos viejos.

**Costo real:** una sesión. 45 requests de historial de técnicos, 1.412 partidos parseados, 279 tests.

### Cómo se rehace

```bash
python3 scripts/historico_argentina.py fetch    # football-data + RSSSF (sin VPN)
python3 scripts/historico_argentina.py etapas   # ~45 páginas de TM (VPN)
python3 scripts/historico_argentina.py build    # resuelve DT por partido
python3 scripts/historico_argentina.py load     # carga + recompute
python3 scripts/historico_argentina.py check    # invariantes
```

### Consecuencia en los snapshots

Entró historial nuevo y todos los ELO se movieron, así que `MODELO_VERSION` pasó a **`elo-v3`** y se reconstruyeron 104 snapshots semanales. Sin eso, las flechas del Top 10 comparaban contra datos viejos.

### Lo que queda de T0.11

- **Etapa B** (2000/01 a 2011/12, RSSSF): ~4.560 partidos. Sigue pendiente de decisión. Mejora poco la predicción (0,0002 de Brier según el estudio) pero permite afirmar "desde 2000" sin asterisco.
- **Etapa C** (B Nacional completa): sólo si hace falta.
- **Los 39 partidos sin DT**: hace falta otra fuente de etapas.
