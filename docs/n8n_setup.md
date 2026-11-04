# n8n: instalación y workflows del paquete semanal

n8n corre **en Windows** (no en WSL) y llama a los scripts de Python a través de
`wsl.exe`. Así WSL arranca solo cuando n8n lo necesita, y no depende de que alguien
haya abierto una terminal.

## 1. Instalación (hecha)

- n8n instalado en Windows con el Node de `F:\Doom\LLM` (v24).
- Responde en `http://localhost:5678`.
- Zona horaria de los workflows: `America/Argentina/Buenos_Aires`.

## 2. Ejecución de comandos (Execute Command)

n8n trae el nodo **Execute Command** deshabilitado por defecto en algunas versiones
(Settings → *Nodes* → permite ejecutar comandos, o la variable
`NODES_EXCLUDE` sin `n8n-nodes-base.executeCommand`). Si el nodo no aparece al
importar, es por eso.

El comando que usa el workflow es **una sola línea, sin comillas**:

```
wsl.exe -d Ubuntu-24.04 bash /mnt/f/ProyectoDT/scripts/weekly_run.py --help
```

En realidad el que se usa es el wrapper:

```
wsl.exe -d Ubuntu-24.04 bash /mnt/f/ProyectoDT/scripts/n8n_run.sh all --skip-if-done-this-week --json
```

**Por qué el wrapper:** `cmd.exe` destroza las comillas anidadas al pasar de Windows a
WSL, así que `bash -lc "cd ... && python3 ..."` llega roto. `scripts/n8n_run.sh` hace
ese trabajo adentro de WSL y recibe los argumentos limpios.

Probado desde Windows:

```
> wsl.exe -d Ubuntu-24.04 bash /mnt/f/ProyectoDT/scripts/n8n_run.sh preflight --json
{"ok": true, "motivo": "ok"}
```

## 3. Importar los workflows

1. n8n → **Workflows → Import from File**.
2. `n8n/aep_semanal.json` → el flujo principal.
3. `n8n/aep_errores.json` → alertas cuando un workflow falla.

Quedan **inactivos** a propósito: primero se prueban a mano.

## 4. Credencial de Telegram

Los nodos de Telegram necesitan una credencial con el token del bot:

1. n8n → **Credentials → New → Telegram API**.
2. Pegá el token de `AEPEloBot` (el mismo `TELEGRAM_BOT_TOKEN` del `.env`).
3. Abrí cada nodo de Telegram (3 en total) y seleccioná esa credencial.

El destino está escrito en el nodo (`@AEP_Analitica`). Si querés que el aviso llegue a
tu chat personal en vez del canal, cambiá ese valor por tu id numérico.

## 5. Cómo queda el flujo

```
Lunes 08:00 ─┐
             ├─► Execute Command (all --skip-if-done-this-week --json)
Cada 4 h ────┘                 │
                     ┌─────────┴─────────┐
                 exit 0              exit ≠ 0
                     │                   │
              Telegram ✅          Telegram ❌
```

- **Cada 4 horas** es el mecanismo de recupero: si el lunes la PC estaba apagada, la
  primera corrida que caiga con la PC encendida hace el trabajo.
  `--skip-if-done-this-week` consulta `ejecuciones_pipeline` y **no hace nada** si la
  semana ya se procesó (tarda menos de un segundo).
- Un solo comando hace todo: scraping incremental, correcciones, recálculo,
  validación, imágenes y envío del paquete a Telegram.
- **Códigos de salida** que interpreta el IF: 0 ok · 10 bloqueo/VPN (reintentar más
  tarde) · 20 validación del ELO fallida · 30 otro error.

## 6. Prueba antes de activar

1. Abrí `aep_semanal` y ejecutá **Execute Workflow** (botón de prueba).
2. Debería terminar en `Telegram OK` y el paquete tiene que aparecer en el chat.
3. Probá el camino de error apagando la VPN: el update devuelve 10 y tiene que llegar
   el mensaje ❌.
4. Recién entonces activá el workflow (toggle **Active**).

## 7. Qué NO hace n8n

- No calcula nada: toda la lógica (ELO, publicación, imágenes, textos) está en Python y
  se puede correr a mano con `python3 scripts/weekly_run.py all`.
- No publica en redes: el paquete llega a Telegram para que lo revises y publiques.
