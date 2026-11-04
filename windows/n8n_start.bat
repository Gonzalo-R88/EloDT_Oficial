@echo off
rem Arranca n8n nativo en Windows (puerto 5678). Lo dispara la tarea "n8n-AEP" al iniciar sesion.
rem Node vive en F:\Doom\LLM, asi que se agrega al PATH: el n8n.cmd de npm lo busca ahi.
set PATH=F:\Doom\LLM;%PATH%
set N8N_PORT=5678
set GENERIC_TIMEZONE=America/Argentina/Buenos_Aires
set TZ=America/Argentina/Buenos_Aires
set N8N_DIAGNOSTICS_ENABLED=false
set N8N_VERSION_NOTIFICATIONS_ENABLED=false
rem n8n excluye Execute Command por defecto; vacio la lista para poder llamar a wsl.exe.
set NODES_EXCLUDE=[]
rem Destino de los avisos de n8n: el mismo chat que usa notify.py en .env.
rem Las expresiones de los nodos leen esta variable, por eso hay que permitir el acceso al entorno.
set TELEGRAM_CHAT_ID=5251543129
set N8N_BLOCK_ENV_ACCESS_IN_NODE=false

echo [%date% %time%] START n8n >> C:\Users\Gonzalo\aep_n8n.log
call "C:\Users\Gonzalo\AppData\Roaming\npm\n8n.cmd" start >> C:\Users\Gonzalo\aep_n8n.log 2>&1
echo [%date% %time%] EXIT %ERRORLEVEL% >> C:\Users\Gonzalo\aep_n8n.log
