@echo off
REM ============================================================================
REM  INSTALADOR PLUG-AND-PLAY MAGIC WALLS QUANT GEX + NWE PARA METATRADER 5
REM  Instala:
REM    - 17 Robos .ex5 (1 EA Mestre de Portfolio + 16 EAs Individuais)
REM    - 2 Indicadores Visuais .ex5 (MagicWalls_NWE_Envelope + MagicWalls_GEX_Ind)
REM    - 4 Templates (.tpl) e 6 Perfis (Profiles) prontos em WIN$N M5
REM    - Atualiza Common\Files\magicwalls_gex_win_daily.csv e magicwalls_gex_win_history.csv
REM ============================================================================

cd /d "%~dp0"
echo [1/3] Sincronizando MagicWalls na pasta Common\Files do MT5...
.\.venv\Scripts\python.exe -c "from gex.engine.profit_exporter import load_cached_walls_data; from gex.engine.mt5_exporter import export_to_mt5_common; d=load_cached_walls_data('win'); export_to_mt5_common(walls=d.get('walls',[]), ref_date=d.get('ref_date'), session_date=d.get('ref_date'), current_win=d.get('current_price'))"

echo [2/3] Compilando e Instalando Robos (.ex5), Indicadores (.ex5), Templates e Perfis em todos os MT5...
.\.venv\Scripts\python.exe "mt5\build_and_compile_mt5_eas.py"
.\.venv\Scripts\python.exe "mt5\build_indicators_and_profiles.py"

echo [3/3] Instalacao Plug-and-Play concluida com sucesso!
echo Para abrir o MetaTrader 5 direto no perfil Magic Walls_PORT_01_Master:
echo "C:\Program Files\MetaTrader 5\terminal64.exe" /profile:Magic Walls_PORT_01_Master
pause
