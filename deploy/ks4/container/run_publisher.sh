#!/usr/bin/env bash
# Roda dentro do container mt5-a. Empurra os snapshots do server local para a API cloud (HMAC).
# MW_PUSH_HMAC_SECRET vem do ambiente do exec (nao fica em arquivo aqui).
export WINEPREFIX=/home/mt5/.mt5 WINEDEBUG=-all TZ=BRT3 PYTHONIOENCODING=utf-8
export MW_CLOUD_API_URL="https://magicwalls.imentore.com"
# IP da API cloud na rede privada (nao versionado): exporte antes, ex. no ambiente do exec.
: "${MW_CLOUD_CONNECT_IP:?defina MW_CLOUD_CONNECT_IP com o IP da API cloud}"
export MW_CLOUD_CONNECT_IP
export MW_LOCAL_BACKEND_URL="http://127.0.0.1:8080"
export MW_PRODUCER_ID="ks4-mt5-a"
export MW_PRODUCER_ROLE="primary"
cd /home/mt5/.mt5/drive_c/magicwalls || exit 1
exec /opt/wine-staging/bin/wine "C:\\Program Files\\Python312\\python.exe" scripts/cloud_publisher.py >> publisher.log 2>&1
