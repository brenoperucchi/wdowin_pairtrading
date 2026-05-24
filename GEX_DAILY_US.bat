@echo off
echo ==================================================
echo   SP500 GEX JUMBA WALLS - ATUALIZACAO DIARIA (US)
echo ==================================================
echo.
echo Iniciando pipeline GEX do SP500 / ES...
echo.

.\.venv\Scripts\python.exe -m gex.engine.main_us

if %errorlevel% neq 0 (
    echo.
    echo Ocorreu um ERRO na execucao do script Python do SP500.
    echo Cancelando o commit no Git.
    pause
    exit /b %errorlevel%
)

echo.
echo Salvando historico do SP500 no Git...
git add -f "gex/docs/jumba_tradingview.pine" "gex/docs/DAILY_REPORT_US.txt"
git commit -m "chore(gex): atualizacao diaria do jumba walls e relatorio do SP500"

echo.
echo ==================================================
echo Atualizacao e commit do SP500 concluidos com sucesso!
echo ==================================================
pause
