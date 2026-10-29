# Modelo ELO: parámetros elegidos y evidencia

Documento de **T1.5** (2026-10-29). Registra la búsqueda de parámetros, la configuración
recomendada y qué se gana (o no) con cada cambio. Reproducible con
`python3 scripts/tune_elo.py` (resultados completos en `data/audit/tune_elo.csv`).

## 1. Protocolo

- **Entrenamiento:** partidos de 2016 a 2022. **Validación:** 2023 a 2026 (nunca se mira
  para elegir).
- **Filtro de evaluación:** ambos DTs con **30 partidos previos** como mínimo (los
  partidos anteriores se juegan igual: el replay siempre actualiza el ELO, sólo no se
  evalúan). Son 45.323 partidos en la ventana de validación ampliada.
- **Métricas:** log-loss 1X2 (con `p_empate = 0,27·(1-|2E-1|)`) como métrica principal y
  Brier del resultado esperado como secundaria. Línea base de la constante: Brier 0,1782.
- **Regla de decisión:** elegir la configuración más simple que quede a menos de
  **0,0005** de log-loss del mejor (evita adoptar ruido).

## 2. Resultados

### Etapa A — ventaja de localía × ajuste por goleada

| Ventaja local | Goleada | Log-loss (valid.) | Brier (valid.) |
|---|---|---|---|
| 30 (actual) | actual | 1,0437 | 0,1638 |
| 30 | amortiguada | 1,0379 | 0,1629 |
| 45 | actual | 1,0416 | 0,1625 |
| **45** | **amortiguada** | **1,0355** | **0,1616** |
| 55 | actual | 1,0418 | 0,1622 |
| 55 | amortiguada | 1,0359 | 0,1613 |
| 65 | actual | 1,0432 | 0,1621 |
| 65 | amortiguada | 1,0375 | 0,1613 |

Dos conclusiones: la localía actual (30) es demasiado baja (el fútbol da ~50-55 puntos de
ventaja) y premiar igual una goleada del favorito que la del débil empeora las
predicciones.

### Etapa B — calibración de DTs nuevos × escala de K

Partiendo de la mejor de A (45 + amortiguada):

| Calibración | Escala de K | Log-loss (valid.) |
|---|---|---|
| no | 0,75 | 1,0354 |
| **no** | **1,0** | **1,0355** |
| no | 1,25 | 1,0365 |
| sí | 0,75 | 1,0357 |
| sí | 1,0 | 1,0362 |
| sí | 1,25 | 1,0375 |

La calibración de DTs nuevos **no mejora** la predicción (empeora ~0,0007): se deja
implementada pero apagada. La escala de K tampoco aporta (0,75 gana por 0,0001 → dentro
de la regla de simplicidad se elige 1,0, es decir el K que ya está en la base).

### Etapa C — desde qué año se calcula

| Inicio | Log-loss (valid.) |
|---|---|
| 2000 | 1,0354 |
| 2015 | 1,0352 |

Diferencia 0,0002: **no justifica tirar 15 años de historia**, así que se calcula desde
2000 (comportamiento actual).

## 3. Configuración recomendada

| Parámetro | Actual | Propuesto |
|---|---|---|
| Ventaja de localía (`hfa`) | 30 | **45** |
| Ajuste por goleada (`mov_mode`) | `actual` | **`amortiguado`** |
| Calibración de DTs nuevos | — | off (implementada, apagada) |
| Escala de K (`k_escala`) | 1,0 | 1,0 (sin cambio) |
| Inicio del cálculo | 2000 | 2000 (sin cambio) |

**Resultado en validación:** log-loss 1,0355 vs 1,0437 actual (**+0,0082**); Brier 0,1616
vs 0,1638.

## 4. Impacto en el ranking actual

Comparando los ratings finales con los 1.308 DTs de 100+ partidos:

- **Correlación de rangos: 0,9981** (los rankings son prácticamente los mismos).
- El top 10 cambia sólo en el orden interno: Flick, Arteta, Guardiola, Klopp, Kompany,
  Heynckes, Jorge Jesus, Inzaghi, Ancelotti y Luis Enrique (Zidane sale del top 10).
- Los ratings se comprimen (~1.450 en lugar de ~1.530 en la punta): la goleada
  amortiguada mueve menos el ELO en general. La escala es cosmética; el orden es lo que
  importa.

## 5. Sensibilidad: ¿importa el año de inicio?

Calculando desde 2000 vs desde 2015 (misma configuración), sobre todos los DTs:

- Correlación de rangos: **0,9476**.
- Los que más cambian son **técnicos veteranos**, porque pierden su historia previa:
  Heynckes −207, Hugo Broos −162, Leonardo −137, Van Gaal −131, Hiddink −126, Wenger −95.
- Los DTs activos casi no se mueven (que es lo que se publica).

Conclusión: calcular desde 2000 conserva el historial y no perjudica la predicción; el
costo es que los ratings de veteranos retirados dependen de datos previos a 2012, que
Transfermarkt tiene incompletos (ver `docs/ARGENTINA_COBERTURA.md` y la deuda de T0.9).

## 6. Adopción (T1.7, 2026-10-29)

**Aprobado por el usuario y aplicado.** `HOME_ADVANTAGE = 45`, `EloParams.mov_mode =
"amortiguado"` por defecto y `MODELO_VERSION = "elo-v2"` en `elo.py`. Se recalcularon los
203.064 partidos: `validate_elo.py` en verde (masa 6.806.000, 0 duplicados, suma cero).

Comparación guardada en `data/audit/ranking_antes_despues.md`: **correlación de rangos
0,9981** sobre los 1.308 DTs con 100+ partidos. Los ratings bajan en bloque (~70-85
puntos en la punta: Arteta 1531,8 → 1446,6) porque la goleada amortiguada mueve menos;
el orden se mantiene (Zidane y Luis Enrique intercambian el 10º puesto).

Revertir es cambiar los dos valores por defecto y volver a correr `recompute`.
