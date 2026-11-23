@echo off
:: ============================================================
::  Agenda a tarefa "GEX Daily Update" no Task Scheduler
::  Horario: 07:30 BRT, de segunda a sexta-feira
::  Requer execucao como Administrador
:: ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Este script precisa ser executado como Administrador!
    echo        Clique com botao direito ^> "Executar como administrador"
    echo.
    pause
    exit /b 1
)

set TASK_NAME=GEX Daily Update (Magic Walls Walls)
set XML_PATH=%~dp0gex_daily_task.xml

echo ==================================================
echo   AGENDAMENTO - GEX DAILY UPDATE
echo ==================================================
echo.
echo   Tarefa:    %TASK_NAME%
echo   Horario:   07:30 e 19:30 (Seg-Sex)
echo   Logs em:   %~dp0gex\logs\
echo.

:: Criar diretorio de logs se nao existir
if not exist "%~dp0gex\logs" mkdir "%~dp0gex\logs"

:: Remover tarefa anterior (se existir) para evitar duplicatas
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Criar a tarefa via XML (resolve problemas de caminhos com espaco)
schtasks /create /tn "%TASK_NAME%" /xml "%XML_PATH%" /f

if %errorlevel% equ 0 (
    echo.
    echo [OK] Tarefa agendada com sucesso!
    echo.
    echo     Nome:     "%TASK_NAME%"
    echo     Horario:  07:30 e 19:30 (Segunda a Sexta)
    echo     Wrapper:  GEX_DAILY_SCHEDULED.bat
    echo     Logs:     gex\logs\gex_daily_YYYYMMDD.log
    echo.
) else (
    echo.
    echo [ERRO] Falha ao criar a tarefa agendada.
    echo.
)

pause
