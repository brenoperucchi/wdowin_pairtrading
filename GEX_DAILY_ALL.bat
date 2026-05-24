@echo off
echo ==================================================
echo   JUMBA GEX WALLS - ATUALIZACAO DIARIA (5 ATIVOS)
echo ==================================================
echo.
echo Iniciando a atualizacao automatica de todos os mercados...
echo.

echo [1/5] Atualizando WIN Futures (B3)...
.\.venv\Scripts\python.exe -m gex.engine.main
if %errorlevel% neq 0 (
    echo ERRO na execucao da B3 WIN. Continuando com os demais...
)
echo.

echo [2/5] Atualizando Dolar Futuro / WDO (B3)...
.\.venv\Scripts\python.exe -m gex.engine.main_dol
if %errorlevel% neq 0 (
    echo ERRO na execucao do Dolar B3. Continuando com os demais...
)
echo.

echo [3/5] Atualizando S^&P 500 / ES Futures (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_us
if %errorlevel% neq 0 (
    echo ERRO na execucao do SP500. Continuando com os demais...
)
echo.

echo [4/5] Atualizando Nasdaq 100 / NQ Futures (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_nq
if %errorlevel% neq 0 (
    echo ERRO na execucao da Nasdaq. Continuando com os demais...
)
echo.

echo [5/7] Atualizando Bitcoin / BTC-USD (Cripto)...
.\.venv\Scripts\python.exe -m gex.engine.main_btc
if %errorlevel% neq 0 (
    echo ERRO na execucao do Bitcoin.
)
echo.

echo [6/7] Atualizando EUR / USD (Forex)...
.\.venv\Scripts\python.exe -m gex.engine.main_eur
if %errorlevel% neq 0 (
    echo ERRO na execucao do EUR/USD.
)
echo.

echo [7/7] Atualizando GBP / USD (Forex)...
.\.venv\Scripts\python.exe -m gex.engine.main_gbp
if %errorlevel% neq 0 (
    echo ERRO na execucao do GBP/USD.
)
echo.

echo Salvando relatorios e indicador consolidado no Git...
git add -f "gex/docs/jumba_tradingview.pine" "gex/docs/DAILY_REPORT*.txt"
git commit -m "chore(gex): atualizacao consolidada de GEX para 7 ativos e relatorios diarios"

echo.
echo ==================================================
echo Atualizacao consolidada de 7 ativos concluida!
echo ==================================================
pause
