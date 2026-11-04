# Automatización semanal (Windows)

El paquete de la semana lo dispara el **Programador de tareas de Windows**, no n8n.
Esta página explica cómo quedó, cómo probarlo y por qué n8n no puede hacer este trabajo
en esta máquina.

## 1. Qué corre y cuándo

Tarea programada **`AEP-Semanal`**:

| Campo | Valor |
|---|---|
| Disparador | todos los días a las **09:00**, con *Ejecutar la tarea lo antes posible si se omitió un inicio programado* |
| Acción | `C:\Users\Gonzalo\aep_semanal.bat` |
| Log | `C:\Users\Gonzalo\aep_semanal.log` (detalle en `F:\ProyectoDT\data\logs\weekly.log`) |
| Código de salida | 0 ok · 10 bloqueo/VPN · 20 validación del ELO · 30 otro error |

El `.bat` hace una sola cosa:

```
wsl.exe -d Ubuntu-24.04 -u gonzalo bash /mnt/f/ProyectoDT/scripts/entrada_windows.sh all --skip-if-done-this-week --json
```

`weekly_run.py all` = update + render + notify, y **`--skip-if-done-this-week`** consulta
`ejecuciones_pipeline`: si la semana ISO ya se procesó, termina en menos de un segundo sin
regenerar ni mandar nada.

### Por qué diario y no "lunes a las 8"

Porque el disparador diario + el *skip* dan lo mismo que un cron semanal, pero con
recuperación automática: si el lunes la PC estaba apagada, corre el martes 09:00 (o en el
primer arranque, por *start when available*) y **el paquete es el de la misma semana**.
Si el lunes falló por VPN, al día siguiente reintenta solo. Un cron semanal no reintenta
hasta siete días después.

## 2. Instalación en otra máquina

```bat
schtasks /create /tn "AEP-Semanal" /xml windows\aep_semanal_task.xml /f
schtasks /run  /tn "AEP-Semanal"        :: prueba manual
schtasks /query /tn "AEP-Semanal" /v /fo list
```

El XML fija la ruta del `.bat` y el usuario (`TURRON\Gonzalo`): si cambia la máquina,
editá `windows/aep_semanal_task.xml` antes de registrarlo. Para desactivarla:
`schtasks /change /tn "AEP-Semanal" /DISABLE`.

## 3. Por qué no n8n

n8n está instalado **en Docker** (`n8nio/n8n:latest`, contenedor `n8n`, puerto 5678) y el
flujo necesitaba el nodo *Execute Command* para llamar a Python. Eso no puede funcionar:

| Comprobación | Resultado |
|---|---|
| `docker exec n8n sh -c "command -v wsl.exe"` | no existe: el contenedor no ve WSL |
| `docker exec n8n sh -c "command -v python3"` | no existe: no hay Python en la imagen |
| nodo `n8n-nodes-base.executeCommand` | excluido por defecto (`Unrecognized node type`) |

Un contenedor no puede invocar el subsistema Linux del host. Para que n8n sirviera habría
que montar un puente HTTP dentro de WSL (un servicio extra que hay que mantener vivo) o
instalar n8n nativo en Windows y habilitar el nodo, que es exactamente lo que el
Programador de tareas ya resuelve sin sumar piezas.

Los workflows de `n8n/` quedan como referencia de ese diseño descartado: están inactivos.

## 4. Qué NO hace

- No publica en redes: el paquete llega a Telegram para revisarlo y publicarlo a mano.
- No apaga la PC. Si querés el apagado después de la corrida, está
  `scripts/apagar_al_terminar.sh`, que se lanza aparte.
