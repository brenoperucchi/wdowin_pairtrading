@echo off
title Launcher - WINxWDO Pair Trading
echo ========================================================
echo        Iniciando Sistema WINxWDO Regime Monitor
echo ========================================================
echo.

echo [1/4] Limpando processos antigos (Portas 8080 e 5174)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8080" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5174" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
echo Pronto.
echo.

echo [2/4] Iniciando WDO Backend (FastAPI porta 8080)...
cd /d "%~dp0\.."
start "WDO Backend (FastAPI)" cmd /k ".venv\Scripts\python.exe server.py"
echo Pronto.
echo.

echo [3/4] Iniciando WDO Frontend (Vite porta 5174)...
cd /d "%~dp0"
start "WDO Frontend (Vite)" cmd /k "npm run dev"
echo Pronto.
echo.

echo [4/4] Aguardando inicializacao...
timeout /t 5 /nobreak >nul
start http://localhost:5174/

echo.
echo ========================================================
echo  Sistema inicializado com sucesso!
echo  Lembre-se de deixar as janelas do Backend e Frontend abertas.
echo ========================================================
timeout /t 5
