#!/usr/bin/env bash
# Roda dentro do container mt5-a. Sobe o server.py (FastAPI) com o MT5 da XP.
export WINEPREFIX=/home/mt5/.mt5 WINEDEBUG=-all TZ=BRT3 PYTHONIOENCODING=utf-8
export MW_MT5_PATH="C:/MT5-a/terminal64.exe"
cd /home/mt5/.mt5/drive_c/magicwalls || exit 1
exec /opt/wine-staging/bin/wine "C:\\Program Files\\Python312\\python.exe" server.py >> server.log 2>&1
