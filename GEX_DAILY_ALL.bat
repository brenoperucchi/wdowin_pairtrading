@echo off
echo ==================================================
echo   JUMBA GEX WALLS - ATUALIZACAO DIARIA (9 ATIVOS)
echo ==================================================
echo.
echo Iniciando a atualizacao automatica de todos os mercados...
echo.

echo [1/9] Atualizando WIN Futures (B3)...
.\.venv\Scripts\python.exe -m gex.engine.main
if %errorlevel% neq 0 (
    echo ERRO na execucao da B3 WIN. Continuando com os demais...
)
echo.

echo [2/9] Atualizando Dolar Futuro / WDO (B3)...
.\.venv\Scripts\python.exe -m gex.engine.main_dol
if %errorlevel% neq 0 (
    echo ERRO na execucao do Dolar B3. Continuando com os demais...
)
echo.

echo [3/9] Atualizando S^&P 500 / ES Futures (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_us
if %errorlevel% neq 0 (
    echo ERRO na execucao do SP500. Continuando com os demais...
)
echo.

echo [4/9] Atualizando Nasdaq 100 / NQ Futures (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_nq
if %errorlevel% neq 0 (
    echo ERRO na execucao da Nasdaq. Continuando com os demais...
)
echo.

echo [5/9] Atualizando Bitcoin / BTC-USD (Cripto)...
.\.venv\Scripts\python.exe -m gex.engine.main_btc
if %errorlevel% neq 0 (
    echo ERRO na execucao do Bitcoin.
)
echo.

echo [6/9] Atualizando EUR / USD (Forex)...
.\.venv\Scripts\python.exe -m gex.engine.main_eur
if %errorlevel% neq 0 (
    echo ERRO na execucao do EUR/USD.
)
echo.

echo [7/9] Atualizando GBP / USD (Forex)...
.\.venv\Scripts\python.exe -m gex.engine.main_gbp
if %errorlevel% neq 0 (
    echo ERRO na execucao do GBP/USD.
)
echo.

echo [8/9] Atualizando Ouro / XAUUSD (Metal)...
.\.venv\Scripts\python.exe -m gex.engine.main_gold
if %errorlevel% neq 0 (
    echo ERRO na execucao do Ouro / XAUUSD.
)
echo.

echo [9/9] Atualizando Dow Jones / US30 (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_dow
if %errorlevel% neq 0 (
    echo ERRO na execucao do Dow Jones / US30.
)
echo.

echo Salvando relatorios e indicador consolidado no Git...
git add -f "gex/data/*.csv" "gex/docs/jumba_neologica" "gex/docs/jumba_tradingview.pine" "gex/docs/DAILY_REPORT*.txt"
git commit -m "chore(gex): atualizacao consolidada de GEX para 9 ativos e relatorios diarios"

echo.
echo ==================================================
echo Atualizacao consolidada de 9 ativos concluida!
echo ==================================================
pause
