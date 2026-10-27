@echo off
echo ==================================================
echo   JUMBA GEX WALLS - ATUALIZACAO DIARIA (14 ATIVOS)
echo ==================================================
echo.
echo Iniciando a atualizacao automatica de todos os mercados...
echo.

echo [0/14] Buscando Calendario Economico do Dia...
.\.venv\Scripts\python.exe -m gex.engine.calendar_fetcher
if %errorlevel% neq 0 (
    echo ERRO ao buscar o Calendario Economico. Continuando com os demais...
)
echo.

echo [1/14] Atualizando WIN Futures (B3)...
.\.venv\Scripts\python.exe -m gex.engine.main
if %errorlevel% neq 0 (
    echo ERRO na execucao da B3 WIN. Continuando com os demais...
)
echo.

echo [2/14] Atualizando Dolar Futuro / WDO (B3)...
.\.venv\Scripts\python.exe -m gex.engine.main_dol
if %errorlevel% neq 0 (
    echo ERRO na execucao do Dolar B3. Continuando com os demais...
)
echo.

echo [3/14] Atualizando S^&P 500 / ES Futures (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_us
if %errorlevel% neq 0 (
    echo ERRO na execucao do SP500. Continuando com os demais...
)
echo.

echo [4/14] Atualizando Nasdaq 100 / NQ Futures (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_nq
if %errorlevel% neq 0 (
    echo ERRO na execucao da Nasdaq. Continuando com os demais...
)
echo.

echo [5/14] Atualizando Bitcoin / BTC-USD (Cripto)...
.\.venv\Scripts\python.exe -m gex.engine.main_btc
if %errorlevel% neq 0 (
    echo ERRO na execucao do Bitcoin.
)
echo.

echo [6/14] Atualizando EUR / USD (Forex)...
.\.venv\Scripts\python.exe -m gex.engine.main_eur
if %errorlevel% neq 0 (
    echo ERRO na execucao do EUR/USD.
)
echo.

echo [7/14] Atualizando GBP / USD (Forex)...
.\.venv\Scripts\python.exe -m gex.engine.main_gbp
if %errorlevel% neq 0 (
    echo ERRO na execucao do GBP/USD.
)
echo.

echo [8/14] Atualizando Ouro / XAUUSD (Metal)...
.\.venv\Scripts\python.exe -m gex.engine.main_gold
if %errorlevel% neq 0 (
    echo ERRO na execucao do Ouro / XAUUSD.
)
echo.

echo [9/14] Atualizando Dow Jones / US30 (EUA)...
.\.venv\Scripts\python.exe -m gex.engine.main_dow
if %errorlevel% neq 0 (
    echo ERRO na execucao do Dow Jones / US30.
)
echo.

echo [10/14] Atualizando USD / JPY (Forex)...
.\.venv\Scripts\python.exe -m gex.engine.main_jpy
if %errorlevel% neq 0 (
    echo ERRO na execucao do USD/JPY.
)
echo.

echo [11/14] Atualizando DAX 40 / DE40 (Alemanha)...
.\.venv\Scripts\python.exe -m gex.engine.main_dax
if %errorlevel% neq 0 (
    echo ERRO na execucao do DAX 40.
)
echo.

echo [12/14] Atualizando Nikkei 225 / JP225 (Japao)...
.\.venv\Scripts\python.exe -m gex.engine.main_nikkei
if %errorlevel% neq 0 (
    echo ERRO na execucao do Nikkei 225.
)
echo.

echo [13/14] Atualizando Russell 2000 / US2000 (EUA Small Caps)...
.\.venv\Scripts\python.exe -m gex.engine.main_russell
if %errorlevel% neq 0 (
    echo ERRO na execucao do Russell 2000.
)
echo.

echo [14/14] Atualizando China 50 / FXI (China)...
.\.venv\Scripts\python.exe -m gex.engine.main_china
if %errorlevel% neq 0 (
    echo ERRO na execucao do China 50.
)
echo.

echo Salvando relatorios e indicador consolidado no Git...
git add -f "gex/data/*.csv" "gex/docs/jumba_neologica" "gex/docs/MagicWallManual.nts" "gex/docs/jumba_tradingview.pine" "gex/docs/DAILY_REPORT*.txt" "gex/docs/DAILY_ECONOMIC_CALENDAR.txt"
git commit -m "chore(gex): atualizacao consolidada de GEX para 14 ativos e relatorios diarios"

echo.
echo ==================================================
echo Atualizacao consolidada de 14 ativos concluida!
echo ==================================================
pause
