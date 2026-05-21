@echo off
echo ==================================================
echo   GEX JUMBA WALLS - ATUALIZACAO DIARIA (17:00)
echo ==================================================
echo.
echo O download do arquivo "Posições em aberto.csv" da B3 agora é 
echo 100% AUTOMATIZADO via Playwright no navegador headless!
echo.
timeout /t 3


echo Iniciando pipeline GEX (Buscando M5 close das 16:55)...
python -m gex.engine.main

if %errorlevel% neq 0 (
    echo.
    echo Ocorreu um ERRO na execucao do script Python.
    echo Cancelando o commit no Git.
    pause
    exit /b %errorlevel%
)

echo.
echo Salvando historico no Git...
git add -f "gex/data/*.csv" "gex/docs/jumba_neologica" "gex/docs/DAILY_REPORT.txt"
git commit -m "chore(gex): atualizacao diaria do jumba walls e relatorio de tendencia"

echo.
echo ==================================================
echo Atualizacao e commit concluidos. Pode fechar esta janela.
echo ==================================================
pause
