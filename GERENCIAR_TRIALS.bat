@echo off
cd /d "%~dp0"
echo === MagicWalls SaaS - Painel CLI de Trials (15 dias) ===
".venv\Scripts\python.exe" scripts\gerenciar_trials.py %*
echo.
pause
