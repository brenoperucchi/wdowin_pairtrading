@echo off
cd /d "%~dp0"
echo === MagicWalls SaaS - Cadastro de Assinante / Admin ===
".venv\Scripts\python.exe" scripts\criar_usuario_saas.py
echo.
pause
