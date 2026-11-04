@echo off
rem AEP: paquete semanal. Lo dispara el Programador de tareas de Windows (tarea AEP-Semanal).
rem Es idempotente: si la semana ya se proceso, weekly_run --skip-if-done-this-week
rem devuelve 0 en menos de un segundo y no manda nada a Telegram.
rem Log: C:\Users\Gonzalo\aep_semanal.log (el detalle queda en F:\ProyectoDT\data\logs\weekly.log)
set LOG=C:\Users\Gonzalo\aep_semanal.log
echo [%date% %time%] START >> %LOG%
wsl.exe -d Ubuntu-24.04 -u gonzalo bash /mnt/f/ProyectoDT/scripts/entrada_windows.sh all --skip-if-done-this-week --json >> %LOG% 2>&1
set CODIGO=%ERRORLEVEL%
echo [%date% %time%] EXIT %CODIGO% >> %LOG%
rem El codigo de salida queda visible en el Programador de tareas (columna "Ultimo resultado").
exit /b %CODIGO%
