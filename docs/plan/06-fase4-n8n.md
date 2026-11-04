# Fase 4: n8n y Telegram

> **Estado real al 2026-11-04.** Este plan suponía n8n **nativo en Windows** (`npm install -g
> n8n` con el Node de `F:\Doom\LLM`) y que no había Docker. Gonzalo lo instaló **en Docker
> Desktop** (contenedor `n8n`, `n8nio/n8n:latest`, puerto 5678).
>
> Un contenedor no ve el host: `docker exec n8n sh -c "command -v wsl.exe"` y `command -v
> python3` fallan dentro de la imagen, y el nodo `n8n-nodes-base.executeCommand` está
> excluido por defecto (`Unrecognized node type`). Por eso **n8n no puede disparar el
> pipeline**.
>
> Lo implementado es la **tarea `AEP-Semanal` del Programador de tareas de Windows**, que sí
> ejecuta `wsl.exe`; ver `docs/automatizacion_semanal.md`. T4.1 (Telegram) se completó;
> T4.2/T4.3 se escribieron como código pero quedaron inactivos; **T4.4 se resolvió con el
> disparador diario + `--skip-if-done-this-week`** en vez de un webhook de n8n.

Leer antes: `AGENTS.md`, `ESTADO.md` y las reglas generales de `00-INDICE.md`.
Tareas de este archivo: T4.1, T4.2, T4.3, T4.4. Varias partes las hace el usuario a mano; el Build debe **parar y pedirle esos pasos**, no inventarlos.

## Contexto necesario

- n8n **no está instalado**, y no hay Docker. En WSL no hay Node; en Windows sí: `F:\Doom\LLM\node.exe` v24.21.0. Decisión: **instalar n8n en Windows** (verificar compatibilidad con Node 24; fallback: Node 22 LTS).
- La VPN y Postgres viven en Windows. WSL (`Ubuntu-24.04`, WSL2) se apaga con los reinicios; si n8n corre en Windows y llama a `wsl.exe`, WSL arranca solo.
- Comando para invocar Python desde n8n (nodo Execute Command): `wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /mnt/f/ProyectoDT && python3 scripts/weekly_run.py <subcomando> --json"`. Verificar que el nodo Execute Command esté habilitado (algunas versiones lo deshabilitan por defecto).
- El proyecto es visible desde Windows como `F:\ProyectoDT` (los PNG salen en `F:\ProyectoDT\data\output\YYYY-Www\`).
- El usuario va a mostrar este workflow en LinkedIn: nodos con nombres claros y orquestación visible. La lógica pesada sigue en Python.
- **El "Retry On Fail" de n8n limita la espera entre intentos a ~5 s** (verificar). Para esperar a la VPN usar un lazo con IF + nodo Wait de 30 min, hasta 6 intentos.
- `weekly_run.py` (T2.5) devuelve códigos de salida 0 (ok), 10 (bloqueo/VPN, reintentable), 20 (validación fallida) y 30 (otro error); imprime JSON por stdout con `--json`.
- Nada se publica solo: el usuario revisa y publica a mano.
- Telegram: enviar las imágenes como **documento** (para no perder calidad) y un mensaje con el resumen y los textos sugeridos.

---

## T4.1: Bot de Telegram y `notify.py`

- **Tipo:** ⚙️ + 👤.
- **Depende de:** —.
- **Pasos manuales del usuario:** crear el bot con BotFather, copiar el token, escribirle al bot y obtener su `chat_id`; poner `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en `.env`. El Build **no** ve ni imprime esos valores.
- **Archivos:** `notify.py` (`enviar_texto`, `enviar_documento`, `enviar_paquete(carpeta)`; usa `requests`; sin dependencias nuevas), `scripts/weekly_run.py` (`notify`, `notify --test`), `.env.example` (agregar las claves vacías), `tests/test_notify.py` (con `requests` simulado).
- **Aceptación:** `weekly_run.py notify --test` entrega un mensaje con una imagen al chat del usuario; los tests pasan sin red; ningún log contiene el token.

## T4.2: Instalar n8n en Windows

- **Tipo:** 👤 (guiado).
- **Depende de:** T2.5.
- **Archivos:** `docs/n8n_setup.md` (pasos exactos), `scripts/start_n8n.bat` (arranque), tarea de Windows Task Scheduler "n8n al iniciar sesión".
- **Pasos:** guiar al usuario para `npm install -g n8n` con el Node de Windows (o instalar Node 22 LTS si hay incompatibilidad), definir variables (`GENERIC_TIMEZONE=America/Argentina/Buenos_Aires`, `TZ`, habilitar Execute Command si hace falta), arrancar con `n8n start` y crear la tarea de arranque. El Build documenta y verifica lo que pueda desde WSL (por ejemplo, `curl http://localhost:5678` y el comando de `wsl.exe`) y pide al usuario ejecutar lo que requiera Windows.
- **Aceptación:** tras reiniciar Windows, `http://localhost:5678` responde; un nodo Execute Command de prueba ejecuta `wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /mnt/f/ProyectoDT && python3 --version"` y devuelve la versión.

## T4.3: Workflows de n8n

- **Tipo:** 👤 (guiado).
- **Depende de:** T3.8, T4.1, T4.2.
- **Archivos:** `n8n/weekly_aep.json`, `n8n/error_alert.json`, `docs/n8n_workflows.md` (capturas opcionales y explicación para LinkedIn).
- **Flujo `weekly_aep`:**
  1. Triggers: Schedule (lunes 08:00, zona horaria America/Argentina/Buenos_Aires) y Webhook `aep-catchup` (mismo flujo).
  2. Execute Command `preflight`. Si el código es 10: contador + IF + Wait de 30 min, hasta 6 intentos; al agotarlos, alerta de Telegram ("VPN apagada o bloqueo: revisá la VPN").
  3. Execute Command `update --skip-if-done-this-week` (timeout 60 min). Si devuelve 20 o 30: alerta de Telegram.
  4. Execute Command `render`; ramas en paralelo por formato leyendo los PNG de `F:\ProyectoDT\data\output\YYYY-Www\`.
  5. Telegram: enviar documentos y un mensaje con el resumen y los textos sugeridos (de `post.md`), más alertas de calidad de `summary.json`.
- **Flujo `error_alert`:** Error Trigger → Telegram con el nombre del nodo y el mensaje.
- **Aceptación:** una corrida manual completa entrega imágenes y textos en Telegram; un fallo forzado (VPN apagada o DB mal) dispara la alerta; el lazo de espera de VPN funciona con un código 10 simulado; los JSON importan sin error en un n8n limpio.

## T4.4: Recuperación tras PC apagada

- **Tipo:** 👤 (guiado).
- **Depende de:** T4.3.
- **Archivos:** `scripts/aep_catchup.bat`, tarea de Windows Task Scheduler "AEP-Catchup" y `docs/n8n_setup.md`.
- **Comportamiento:** la tarea corre "al iniciar sesión" con 2 minutos de demora y ejecuta `curl http://localhost:5678/webhook/aep-catchup`. `--skip-if-done-this-week` evita duplicados. n8n no recupera por sí solo una ejecución perdida, por eso existe el webhook.
- **Aceptación:** prender la PC un miércoles dispara una sola corrida de la semana; un segundo inicio de sesión el mismo día no repite; si la VPN está apagada, el lazo de espera de T4.3 avisa por Telegram.
