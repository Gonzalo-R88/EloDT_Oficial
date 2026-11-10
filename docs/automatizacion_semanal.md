# Automatización semanal (Windows + n8n nativo)

El paquete de la semana lo dispara **n8n nativo en Windows**, con una tarea del
Programador de tareas como red de seguridad. Esta página explica cómo quedó, cómo probarlo
y cómo se instala de cero.

## 1. Piezas

| Pieza | Qué hace |
|---|---|
| Tarea **`n8n-AEP`** (Programador de tareas) | Arranca n8n al iniciar sesión (1 min de demora) |
| `windows/n8n_start.bat` | Define el entorno de n8n y lo levanta en el puerto 5678 |
| Workflow **`AEP — paquete semanal`** | Lunes 08:00 + cada 4 h → `Execute Command` → ✅/❌ por Telegram |
| Workflow **`AEP — alertas de error`** | Error Trigger → Telegram si un workflow se rompe |
| Tarea **`AEP-Semanal`** (Programador de tareas) | Respaldo: todos los días 09:00, mismo comando (si n8n no estaba corriendo) |

Todo termina en el mismo lugar: `scripts/entrada_windows.sh all --skip-if-done-this-week`,
que es update + render + notify con corte por semana ISO.

## 2. La cadena

```
n8n (Lunes 08:00 / cada 4 h)
   └─ Execute Command: wsl.exe ... entrada_windows.sh all --skip-if-done-this-week --json
          ├─ exit 0  → Telegram ✅ (con el stdout)
          └─ exit ≠0 → Telegram ❌ (con el stderr)
```

Los dos workflows están **activos y publicados**. El "cada 4 horas" es el recupero: si el
lunes la PC estaba apagada, la primera corrida que caiga con la PC encendida hace el
trabajo; si la semana ya se procesó, el comando sale en <2 s sin tocar nada.

**Por qué hay dos disparadores (n8n + Programador de tareas):** son idempotentes y se pisan
por el lock `data/weekly.lock`. Si n8n no está corriendo, la tarea `AEP-Semanal` salva la
semana; si n8n corre, es la que gana. Nunca se duplica el envío.

## 3. Configuración que hace que funcione

En `windows/n8n_start.bat`, todas críticas:

| Variable | Por qué |
|---|---|
| `PATH=F:\Doom\LLM;%PATH%` | Node vive ahí; el `n8n.cmd` de npm lo busca en el PATH |
| `NODES_EXCLUDE=[]` | n8n **excluye Execute Command por defecto**; sin esto el nodo ni se carga |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` + `TELEGRAM_CHAT_ID` | los nodos de Telegram leen el destino de `$env` en vez de tenerlo escrito |
| `GENERIC_TIMEZONE` / `TZ` | America/Argentina/Buenos_Aires, para que "lunes 08:00" sea local |

La credencial **`Telegram AEP`** (`telegramApi`) es la que usan los dos workflows. Se importó
por CLI desde el token de `.env`, así que el token no está escrito en ningún nodo.

## 4. Instalación de cero

```bat
:: 1. n8n con el Node de F:
set PATH=F:\Doom\LLM;%PATH%
npm install -g n8n

:: 2. entorno + arranque (ver contenido en windows/n8n_start.bat)
copy windows\n8n_start.bat C:\Users\Gonzalo\n8n_start.bat

:: 3. tareas
schtasks /create /tn "n8n-AEP"      /xml windows\n8n_start_task.xml /f
schtasks /create /tn "AEP-Semanal"  /xml windows\aep_semanal_task.xml /f

:: 4. workflows (necesitan la credencial ya importada)
n8n.cmd import:credentials --input=credenciales.json
n8n.cmd import:workflow    --input=n8n\aep_semanal.json
n8n.cmd import:workflow    --input=n8n\aep_errores.json
n8n.cmd publish:workflow   --id=<id del workflow>
```

**Trampas que costaron tiempo:**

- `n8n import:workflow` **desactiva** el workflow si estaba activo; hay que volver a
  `publish:workflow` y **reiniciar n8n** para que el scheduler lo registre.
- `n8n update:workflow --active=true` está deprecado y deja el workflow *desactivado*.
  Usar siempre `publish:workflow`.
- `n8n import:credentials` con `N8N_USER_FOLDER` seteado crea la DB en
  `<carpeta>\.n8n\.n8n` (anidada) en vez de usarla. No setearlo.
- Desde WSL, `localhost:5678` **no** llega al n8n de Windows: usar `http://winhost:5678`
  (la entrada de `/etc/hosts` que ya usa Postgres).
- El destino de Telegram es el chat **personal** (`TELEGRAM_CHAT_ID` en `.env`), no el canal
  `@AEP_Analitica`: con el handle, el nodo devolvía `400 chat not found`.
- **`winhost` se pierde en cada arranque de WSL**: `/etc/hosts` se regenera y la línea que
  apunta al Postgres de Windows desaparece. El `update_winhost` de `~/.bashrc` lo arregla
  sólo en terminales interactivas, y estas corridas no lo son, así que la tarea fallaba con
  `could not translate host name "winhost"`. `scripts/entrada_windows.sh` ahora detecta que
  `winhost` no resuelve y usa como respaldo el **gateway por defecto**, que en WSL2 es la IP
  del host de Windows (no necesita permisos).

## 5. Cómo probarlo

```bat
:: ver si n8n está arriba
curl http://localhost:5678

:: correr el workflow ahora, sin esperar el lunes (desde la UI: "Execute workflow")
```

El estado de cada corrida queda en la tabla `execution_entity` de
`C:\Users\Gonzalo\.n8n\database.sqlite`:

```sql
select id, status, startedAt, stoppedAt from execution_entity order by id desc limit 5;
```

Y las corridas del pipeline, con partidos cargados y errores, en `ejecuciones_pipeline`
(Postgres) y `data/logs/weekly.log`.

## 6. Por qué no se usó el n8n de Docker

La primera versión corrió en Docker (`n8nio/n8n`, contenedor `n8n`). Un contenedor no ve el
host: `docker exec n8n sh -c "command -v wsl.exe"` y `command -v python3` fallan, así que
no puede ejecutar el pipeline. El contenedor quedó **detenido** (se puede borrar con
`docker rm n8n`); la DB y los workflows viejos viven ahí, no en la instancia nativa.
