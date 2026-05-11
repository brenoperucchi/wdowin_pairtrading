@echo off
echo ==================================================
echo   GEX JUMBA WALLS - ATUALIZACAO DIARIA (17:00)
echo ==================================================
echo.
echo Lembrete: Voce ja baixou o arquivo "Posicoes em aberto.csv" 
echo da B3 e colocou na pasta gex\data\ ?
echo.
pause

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
git add gex/data/Posi*.csv gex/docs/jumba_neologica
git commit -m "chore(gex): atualizacao diaria do jumba walls (automacao)"

echo.
echo ==================================================
echo Atualizacao e commit concluidos. Pode fechar esta janela.
echo ==================================================
pause
