# Pendientes tuyos (Gonzalo)

Todo lo que el plan necesita de vos: acciones (crear un bot, instalar algo) y decisiones
(aprobar números o diseños). **Ninguna tarea avanza sola en estos puntos**: el agente se
detiene, te muestra el resultado y espera tu respuesta.

Última actualización: 2026-10-27 (al cerrar T0.2).

## Cómo marcar

Cuando hagas o decidas algo, cambiá `[ ]` por `[x]` en esta lista. Si la decisión tiene
opciones, escribila debajo de la línea para que quede el registro.

---

## 1. Acciones (hacer)

- [ ] **Rotar la contraseña de la base (`DB_PASS`).**
  - Cuándo: cuanto antes.
  - Por qué: quedó escrita en un log de una sesión anterior. No es una fuga pública, pero
    conviene cambiarla.
  - Cómo: cambiarla en el Postgres de Windows y después en `F:\ProyectoDT\.env` (línea
    `DB_PASS=`). No lo hace el agente porque tocar credenciales es decisión tuya.

- [x] **Crear el bot de Telegram** (hecho 2026-11-04: `AEPEloBot`; el primer token estaba
  revocado y se regeneró).
  - Cómo: en Telegram, hablar con **@BotFather**, escribir `/newbot`, elegir nombre y
    usuario. Te da un **token**. Después escribirle algo al bot creado y obtener tu
    **chat_id** (por ejemplo con @userinfobot).
  - Qué hacer con eso: pegarlos en `.env` como `TELEGRAM_BOT_TOKEN=` y `TELEGRAM_CHAT_ID=`.

- [x] **Instalar n8n** (hecho 2026-11-04, pero **en Docker**, no nativo en Windows).
  - Consecuencia: n8n no puede ejecutar el pipeline (el contenedor no ve WSL ni Python).
    La automatización semanal quedó en el **Programador de tareas de Windows** (tarea
    `AEP-Semanal`), que sí puede. Detalle en `docs/automatizacion_semanal.md`.
  - Pendiente de decisión: qué hacer con los workflows de `n8n/` (quedaron inactivos).

- [ ] **Confirmar VPN y tiempo antes de cada scrape grande** (más de ~500 requests).
  - Los backfills largos se corren en `tmux` y pueden tardar horas.

---

## 2. Decisiones (aprobar)

- [x] **Cómo medir la cobertura de una liga** — elegiste la opción (b): por país, sumando las ligas del mismo país (2026-10-29).
  - Resultado: Bolivia pasa de 67 % a 98,6 % y Ecuador a 100 % (sus años existentes
    están completos). Ahora hay 743 publicables, 15 de Bolivia y 14 de Ecuador, y ya
    nadie queda afuera por cobertura. La auditoría sigue mostrando la cobertura por
    competencia, para ver los huecos reales de Transfermarkt.
  - Las otras dos opciones quedan descartadas.
  - Regla vigente: un DT es publicable si es el **DT actual de un club**, jugó en el
    último año, tiene 15+ partidos y su liga tiene 90 % o más de cobertura en los
    últimos 3 años.
  - Hoy: **715 publicables** de 6.806 DTs; 398 "sin trabajo"; quedan afuera 3.736
    inactivos, 1.804 con pocos partidos y 67 de ligas incompletas.
  - Por qué quedan afuera Bolivia y Ecuador: no se perdieron partidos, esas temporadas
    **no existen en Transfermarkt** con esos códigos (BO1A 2024 y EC1N 2022-2024
    devuelven la temporada actual). En Bolivia además Apertura y Clausura son
    competencias separadas, así que cada una tiene años en cero.
  - Opciones: (a) dejarlo así; (b) promediar todas las ligas del mismo país (arregla
    Bolivia, Ecuador sigue afuera); (c) mirar sólo los últimos 2 años (entran las dos).
  - Para verlo: `python3 scripts/publicables.py --motivos` y `--sin-trabajo`.

- [ ] **Cobertura de Argentina** — **T0.4 terminó el 2026-10-28** (queda tu comentario).
  - Resultado (detalle en `docs/ARGENTINA_COBERTURA.md`): Primera 2017-2020 recuperada
    (98-100 %), `ARG1`/`ARGC` 2025-26 nuevas (99-100 %), y la Primera Nacional 2018-2026
    por encima del 98 %. Los porcentajes más bajos (ARG2 2015-2017, hasta 65 %) son
    partidos que TM publica sin entrenador; se recuperan en T0.9.
  - Qué tenés que decir: si con esto alcanza para publicar rankings de Argentina.

- [ ] **Parámetros del modelo ELO** — al terminar **T1.5**.
  - Qué vas a ver: la configuración elegida por el backtest (ventaja de local, factor K,
    ajuste por diferencia de goles) y si conviene calcular desde el año 2000 o desde 2015.
  - Por qué importa: define el número que va a ir en las imágenes. Desde 2000 aprovecha
    todo el historial; desde 2015 es más consistente porque antes de 2012 faltan DTs.

- [ ] **Lista de DTs de sanidad** — en **T1.6**.
  - Qué vas a ver: una lista de ~10 entrenadores conocidos que deberían aparecer arriba.
    El agente propone una lista y vos la corregís.
  - Para qué: detectar si el modelo "se fue de tema".

- [ ] **¿Publicamos el ELO "ajustado por plantel"?** — en **T1.10**.
  - Es un segundo cálculo que intenta separar el mérito del técnico de la calidad del
    plantel ("rinde por encima de su plantel"). Se hace como experimento y solo se adopta
    si mejora las predicciones. Vos decidís si aparece en las imágenes y cómo.

- [x] **¿Intentamos recuperar Argentina 2000-2014?** — **ETAPA A HECHA el 2026-11-20**:
  1.373 partidos cargados (`ARGH` 2012/13, 2013/14 y Transición 2014; `ARG2H` B Nacional
  2013/14). 39 quedaron sin DT por huecos de Transfermarkt y no se inventaron. Detalle en
  `docs/ARGENTINA_HISTORICO.md` §10.
  - **Falta decidir la etapa B** (2000/01 a 2011/12, RSSSF, ~4.560 partidos). Mejora poco la
    predicción (0,0002 de Brier según el estudio) pero permite decir "desde 2000" sin asterisco.
  - Decidí: [ ] hacer etapa B · [ ] no hacer · [ ] incluir también la B Nacional completa (etapa C).

- [ ] **Qué hacer con los 25 partidos donde Transfermarkt asigna el mismo DT a dos equipos el mismo día** (al cerrar **T0.3** quedaron identificados y documentados en `docs/CONFLICTOS_FECHA.md`).
  - Qué pasa: no es un problema de fechas (la fecha está confirmada). Son errores de Transfermarkt: 20 casos del mismo DT en dos clubes de la misma jornada, 3 en ligas distintas, 1 club con dos partidos el mismo día y 1 partido cargado dos veces en distintas competencias.
  - Opciones: **dejarlos como están** (es lo que hice; el impacto en el ELO es mínimo) o descartar esos partidos de la base en una limpieza posterior.

- [ ] **Diseño del primer Top 10** — en **T3.3**.
  - Qué vas a ver: el primer PNG con datos reales de Argentina. Aprobás o pedís cambios
    (colores, tipografía, qué datos se muestran).

- [x] **Marca y handle** — definido 2026-11-05.
  - Cuenta de X: **@EloDT_oficial** (marca "ELO DT"). Correo: `elodt.oficial@gmail.com`.
  - El handle vive en `captions.py` (`HANDLE`) y en los defaults de
    `scripts/power_ranking.py`, `scripts/duelo_pizarras.py` y `scripts/weekly_run.py`.
  - Logo: tres propuestas en `assets/brand/` (perfil + banner); falta que elijas una.
    Se regeneran con `python3 scripts/logo.py`.

---

## 3. Ya hecho por vos

- [x] Prioridad: Argentina primero, después global.
- [x] Sin API paga; scraping con la VPN (gratuita).
- [x] Corre en tu PC; si estaba apagada el lunes, corre al encenderse.
- [x] Publicar solo datos fiables; mínimo 15 partidos; mostrar interinos.
- [x] Un post por semana, los lunes; n8n + Telegram.
- [x] Uso personal (marca personal), sin monetizar.
- [x] Arreglar los datos históricos en lugar de recortar el modelo.
- [x] T0.3: corregir fechas de los **bloques completos** (669 partidos re-descargados), no solo los conflictivos.
- [x] T0.4: backfill de Argentina completo (Primera + Primera Nacional), ~3.500 requests.
