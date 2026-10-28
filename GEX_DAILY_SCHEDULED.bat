@echo off
REM ============================================================
REM  Wrapper para execucao agendada do GEX Daily Update (14 Ativos)
REM  Gera log com data no nome do arquivo automaticamente
REM  Inclui retry automatico a cada 30 minutos das 07:30 ate 09:30
REM ============================================================

REM Forcar o diretorio de trabalho para a pasta do script
cd /d "%~dp0"

set GEX_SCHEDULED=1

set HH=%time:~0,2%
if "%HH:~0,1%"==" " set HH=0%HH:~1,1%
if %HH% GEQ 17 exit /b 0


for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY_ISO=%%i
set YYYY=%TODAY_ISO:~0,4%
set MM=%TODAY_ISO:~5,2%
set DD=%TODAY_ISO:~8,2%
set LOG_DIR=%~dp0gex\logs\%YYYY%-%MM%
set LOG_FILE=%LOG_DIR%\gex_daily_%YYYY%%MM%%DD%.log

REM Criar diretorio de logs se nao existir
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================================ > "%LOG_FILE%"
echo [%date% %time%] Iniciando GEX Daily Supervisor (14 Ativos)... >> "%LOG_FILE%"
echo Diretorio de trabalho: %CD% >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

.\.venv\Scripts\python.exe -u -m gex.engine.scheduled_runner >> "%LOG_FILE%" 2>&1

echo. >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"
echo [%date% %time%] Execucao finalizada. >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

