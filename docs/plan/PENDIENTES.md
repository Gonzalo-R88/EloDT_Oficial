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

- [ ] **Crear el bot de Telegram** (se pide recién en la tarea **T4.1**, cuando haya algo
  para enviar).
  - Cómo: en Telegram, hablar con **@BotFather**, escribir `/newbot`, elegir nombre y
    usuario. Te da un **token**. Después escribirle algo al bot creado y obtener tu
    **chat_id** (por ejemplo con @userinfobot).
  - Qué hacer con eso: pegarlos en `.env` como `TELEGRAM_BOT_TOKEN=` y `TELEGRAM_CHAT_ID=`.

- [ ] **Instalar n8n en Windows** (se pide en **T4.2**; hoy no está instalado y no hay
  Docker).
  - Se usa el Node que ya tenés en `F:\Doom\LLM\node.exe` (v24). Si n8n no lo acepta, se
    instala Node 22 LTS.
  - El agente te va a dar los pasos exactos y después verifica que n8n responda y que
    pueda ejecutar los scripts de Python.

- [ ] **Confirmar VPN y tiempo antes de cada scrape grande** (más de ~500 requests).
  - Los backfills largos se corren en `tmux` y pueden tardar horas.

---

## 2. Decisiones (aprobar)

- [ ] **Cobertura de Argentina** — al terminar **T0.4**.
  - Qué vas a ver: una tabla año por año de `AR1N`, `ARG2` y `CDLP`, con los huecos y su
    causa. Hoy faltan **2017-2020** y **2025-26** en Primera (y 2017-2020 en la B).
  - Qué tenés que decir: si la cobertura alcanza para publicar rankings de Argentina.

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

- [ ] **¿Intentamos recuperar Argentina 2000-2014?** — en **T0.11**.
  - Transfermarkt no tiene esas ligas. El estudio dirá si alguna fuente gratuita sirve y
    cuánto trabajo implica. Puede quedar como "histórico incompleto" sin costo.

- [ ] **Diseño del primer Top 10** — en **T3.3**.
  - Qué vas a ver: el primer PNG con datos reales de Argentina. Aprobás o pedís cambios
    (colores, tipografía, qué datos se muestran).

- [ ] **Marca y handle** — antes del primer post.
  - Hoy es un placeholder: `@AEP_Analitica`. Cuando definas el nombre, se cambia en un
    solo lugar.

---

## 3. Ya hecho por vos

- [x] Prioridad: Argentina primero, después global.
- [x] Sin API paga; scraping con la VPN (gratuita).
- [x] Corre en tu PC; si estaba apagada el lunes, corre al encenderse.
- [x] Publicar solo datos fiables; mínimo 15 partidos; mostrar interinos.
- [x] Un post por semana, los lunes; n8n + Telegram.
- [x] Uso personal (marca personal), sin monetizar.
- [x] Arreglar los datos históricos en lugar de recortar el modelo.
