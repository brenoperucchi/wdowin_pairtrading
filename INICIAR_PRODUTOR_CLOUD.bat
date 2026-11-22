@echo off
cd /d "%~dp0"
echo === MagicWalls SaaS - Produtor Push Cloud (127.0.0.1:8080 -> Nuvem) ===
echo Mantenha esta janela aberta durante o pregao.
".venv\Scripts\python.exe" scripts\cloud_publisher.py --role primary --producer-id pc-local-01
echo.
pause
