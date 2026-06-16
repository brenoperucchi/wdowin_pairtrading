@echo off
:: ============================================================
::  Wrapper para execução agendada do GEX Daily Update
::  Gera log com data no nome do arquivo automaticamente
:: ============================================================

:: Forçar o diretório de trabalho para a pasta do script
cd /d "%~dp0"

:: Sinalizar modo agendado (não-interativo) para pipelines que pedem input
set GEX_SCHEDULED=1

set LOG_DIR=%~dp0gex\logs
set YYYY=%date:~6,4%
set MM=%date:~3,2%
set DD=%date:~0,2%
set HH=%time:~0,2%
set MIN=%time:~3,2%
set LOG_FILE=%LOG_DIR%\gex_daily_%YYYY%%MM%%DD%.log

:: Criar diretorio de logs se nao existir
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================================ > "%LOG_FILE%"
echo [%date% %time%] Iniciando GEX Daily Update (agendado)... >> "%LOG_FILE%"
echo Diretorio de trabalho: %CD% >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

:: Executar cada pipeline individualmente (evita o pause do GEX_DAILY_ALL.bat)

echo [1/11] WIN Futures (B3)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main >> "%LOG_FILE%" 2>&1

echo [2/11] Dolar Futuro (B3)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_dol >> "%LOG_FILE%" 2>&1

echo [3/11] SP500 / ES (EUA)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_us >> "%LOG_FILE%" 2>&1

echo [4/11] Nasdaq 100 / NQ (EUA)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_nq >> "%LOG_FILE%" 2>&1

echo [5/11] Bitcoin / BTC (Cripto)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_btc >> "%LOG_FILE%" 2>&1

echo [6/11] EUR / USD (Forex)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_eur >> "%LOG_FILE%" 2>&1

echo [7/11] GBP / USD (Forex)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_gbp >> "%LOG_FILE%" 2>&1

echo [8/11] Ouro / XAUUSD (Metal)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_gold >> "%LOG_FILE%" 2>&1

echo [9/11] Dow Jones / US30 (EUA)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_dow >> "%LOG_FILE%" 2>&1

echo [10/11] USD / JPY (Forex)... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe -m gex.engine.main_jpy >> "%LOG_FILE%" 2>&1

echo. >> "%LOG_FILE%"
echo Salvando no Git... >> "%LOG_FILE%"
git add -f "gex/data/*.csv" "gex/data/*.json" "gex/docs/jumba_neologica" "gex/docs/jumba_tradingview.pine" "gex/docs/DAILY_REPORT*.txt" >> "%LOG_FILE%" 2>&1
git commit -m "chore(gex): atualizacao consolidada de GEX para 10 ativos e relatorios diarios" >> "%LOG_FILE%" 2>&1

echo. >> "%LOG_FILE%"
echo [SYNC] Sincronizando niveis GEX no dashboard IRAI... >> "%LOG_FILE%"
.\.venv\Scripts\python.exe ..\rastro_irado\scripts\sync_gex_to_irai.py >> "%LOG_FILE%" 2>&1

echo ============================================================ >> "%LOG_FILE%"
echo [%date% %time%] GEX Daily Update FINALIZADO com sucesso! >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"
