import os
import shutil
import subprocess

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
MT5_PROJ_DIR = os.path.join(PROJECT_ROOT, "mt5")
MT5_INC_DIR = os.path.join(MT5_PROJ_DIR, "Include")
MT5_EXP_DIR = os.path.join(MT5_PROJ_DIR, "Experts", "Jumba_GEX_NWE")

os.makedirs(MT5_INC_DIR, exist_ok=True)
os.makedirs(MT5_EXP_DIR, exist_ok=True)

# 1. Patch gex/engine/main.py cleanly if not already patched
main_py_path = os.path.join(PROJECT_ROOT, "gex", "engine", "main.py")
with open(main_py_path, "r", encoding="utf-8") as f:
    main_txt = f.read()

if "export_to_mt5_common" not in main_txt:
    anchor = '    print("\\n" + "=" * 50)\n    print("  Pipeline concluido com sucesso!")'
    hook_code = '''    # 8. Export to MT5 Common\\Files + Firebase Backup
    print("\\n[8/8] Exportando MagicWalls para MetaTrader 5 (Common\\\\Files + Firebase)...")
    try:
        from .mt5_exporter import export_to_mt5_common
        export_to_mt5_common(walls=walls, ref_date=trading_date, current_win=current_win)
    except Exception as e:
        print(f"      Aviso: Falha ao exportar para MT5 Common\\\\Files ({e})")
    try:
        push_walls_to_firebase(walls)
    except Exception as e:
        print(f"      Aviso: Falha ao publicar no Firebase ({e})")

'''
    if anchor in main_txt:
        main_txt = main_txt.replace(anchor, hook_code + anchor, 1)
        with open(main_py_path, "w", encoding="utf-8") as f:
            f.write(main_txt)
        print("[OK] Patched gex/engine/main.py with Step [8/8] MT5 Common\\Files + Firebase export!")

# 2. Keep canonical Jumba_GEX_NWE_Core.mqh (do not overwrite with legacy embedded string)
core_path = os.path.join(MT5_INC_DIR, "Jumba_GEX_NWE_Core.mqh")
wdo_core_path = os.path.join(MT5_INC_DIR, "Jumba_WDO_GEX_NWE_Core.mqh")

# 3. Write Jumba_GEX_NWE_Portfolio_Master.mq5
master_mq5 = r"""//+------------------------------------------------------------------+
//|                               Jumba_GEX_NWE_Portfolio_Master.mq5 |
//|     EA Mestre Unificado de Portfólio GEX MagicWalls + NWE (WIN)  |
//|     Inclui Presets PORT-01, PORT-03, LEVE-01, LEVE-03 e Custom   |
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property version   "1.00"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input group "=== 1. SELECAO DO PORTFOLIO & EXECUCAO ==="
input ENUM_PORTFOLIO_PRESET InpPreset         = PRESET_PORT_01_COMPLETO; // Preset de Portfólio (8 Estratégias Corr < 0.40)
input ENUM_EXECUTION_MODE   InpExecMode       = EXEC_NETTING_VIRTUAL_SYNC; // Modo de Execução (Netting B3 ou Hedging)
input double                InpLotMultiplier  = 1.0;    // Multiplicador de Lotes (1.0 = Lote Base do Backtest)
input double                InpMaxDailyLoss   = 2500.0; // Trava de Perda Máxima Diária do Portfólio (R$)
input ulong                 InpBaseMagic      = 88000;  // Magic Number Base
input bool                  InpDrawLevels     = true;   // Desenhar MagicWalls no Gráfico
input string                InpWdoSymbol      = "WDO$N"; // Símbolo do Dólar (p/ EST-03)

input group "=== 2. CHAVES INDIVIDUAIS (USADAS NO MODO PRESET_CUSTOM_MANUAL) ==="
input bool Enable_EST01_Scalper_NY            = false;
input bool Enable_EST02_Scalper_Full          = false;
input bool Enable_EST03_Scalper_WDO           = false;
input bool Enable_EST04_Pullback_Retest       = true;
input bool Enable_EST05_Pullback_Cluster      = false;
input bool Enable_EST06_Pullback_LimitSlope   = false;
input bool Enable_EST07_Breakout_NY           = true;
input bool Enable_EST08_Breakout_Core         = false;
input bool Enable_EST09_Breakout_StopWall     = true;
input bool Enable_EST10_Breakout_StopWick     = true;
input bool Enable_EST11_Grid_TrendPullback    = true;
input bool Enable_EST12_Pyramid_Profit11      = false;
input bool Enable_EST13_SmartGrid_RSI         = true;
input bool Enable_EST14_Grid_Institucional    = true;
input bool Enable_EST15_EOD_Breakout          = true;
input bool Enable_EST16_EOD_ExtremeFade       = false;

CJumbaGexNweEngine g_engine;

int OnInit()
  {
   g_engine.Init(InpBaseMagic, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      InpPreset, 0,
      Enable_EST01_Scalper_NY, Enable_EST02_Scalper_Full, Enable_EST03_Scalper_WDO, Enable_EST04_Pullback_Retest,
      Enable_EST05_Pullback_Cluster, Enable_EST06_Pullback_LimitSlope, Enable_EST07_Breakout_NY, Enable_EST08_Breakout_Core,
      Enable_EST09_Breakout_StopWall, Enable_EST10_Breakout_StopWick, Enable_EST11_Grid_TrendPullback, Enable_EST12_Pyramid_Profit11,
      Enable_EST13_SmartGrid_RSI, Enable_EST14_Grid_Institucional, Enable_EST15_EOD_Breakout, Enable_EST16_EOD_ExtremeFade
   );
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   Comment("");
  }

void OnTick()
  {
   g_engine.OnTickProcess();
  }
"""

master_path = os.path.join(MT5_EXP_DIR, "Jumba_GEX_NWE_Portfolio_Master.mq5")
with open(master_path, "w", encoding="utf-8-sig") as f:
    f.write(master_mq5)

# 4. Generate all 16 Individual Strategy .mq5 files
indiv_specs = [
    (1,  "Jumba_EST01_Scalper_Hibrido_NY",       88001, "EST-01 [Scalper Limit+Mkt] Hibrido NY (10h-16h30)"),
    (2,  "Jumba_EST02_Scalper_Hibrido_DiaTodo",  88002, "EST-02 [Scalper Limit+Mkt] Dia Todo (09h-17h)"),
    (3,  "Jumba_EST03_Scalper_Cambial_WDO",      88003, "EST-03 [Scalper Cambial] Confluencia WIN+WDO"),
    (4,  "Jumba_EST04_Pullback_Reteste_Wall",    88004, "EST-04 [Pullback Limit] Reteste de Wall Rompida"),
    (5,  "Jumba_EST05_Pullback_Cluster_NWE",     88005, "EST-05 [Pullback Cluster] NWE Center + Wall"),
    (6,  "Jumba_EST06_Pullback_Limit_Slope",     88006, "EST-06 [Pullback Limit] Ordem Limit na Wall c/ Slope"),
    (7,  "Jumba_EST07_Breakout_Momentum_NY",     88007, "EST-07 [Breakout Mkt] Momentum Wall NY"),
    (8,  "Jumba_EST08_Breakout_Rapido_Core",     88008, "EST-08 [Breakout Mkt] Momentum Rapido Core"),
    (9,  "Jumba_EST09_Breakout_Stop_Wall",       88009, "EST-09 [Breakout Stop] Aceleracao Buy/Sell Stop Wall"),
    (10, "Jumba_EST10_Breakout_Stop_Wick",       88010, "EST-10 [Breakout Stop] Stop Wick Pavio na Wall"),
    (11, "Jumba_EST11_Grid_Pullback_Tendencia",  88011, "EST-11 [Grid Pullback Tendencia] 1+2 Lotes NWE"),
    (12, "Jumba_EST12_Piramidacao_Lucro_11L",    88012, "EST-12 [Piramidacao no Lucro] 1+1 Lote Anti-Martingale"),
    (13, "Jumba_EST13_SmartGrid_RSI_BE",         88013, "EST-13 [Smart Grid RSI+BE] 1+2 Lotes Curto"),
    (14, "Jumba_EST14_Grid_Institucional_123L",  88014, "EST-14 [Grid Institucional] Wall->MidWall->Wall 1+2+3L"),
    (15, "Jumba_EST15_Posicional_EOD_Breakout",  88015, "EST-15 [Posicional EOD] Breakout Matinal -> 17h15"),
    (16, "Jumba_EST16_Posicional_EOD_Fade",      88016, "EST-16 [Posicional EOD] Extreme Fade Matinal -> 17h15"),
]

for sid, fname, magic, desc in indiv_specs:
    indiv_code = f"""//+------------------------------------------------------------------+
//| {fname}.mq5
//| {desc}
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property description "{desc}"
#property version   "1.00"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input ENUM_EXECUTION_MODE InpExecMode      = EXEC_HEDGING_DIRECT_MAGIC; // Modo de Execução
input double              InpLotMultiplier = 1.0;    // Multiplicador de Lotes
input double              InpMaxDailyLoss  = 1000.0; // Perda Máxima Diária Individual (R$)
input ulong               InpMagicNumber   = {magic}; // Magic Number Base
input bool                InpDrawLevels    = true;   // Desenhar MagicWalls no Gráfico
input string              InpWdoSymbol     = "WDO$N"; // Símbolo do Dólar (se usado)

CJumbaGexNweEngine g_engine;

int OnInit()
  {{
   g_engine.Init(InpMagicNumber - {sid}, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      PRESET_SINGLE_ROBOT, {sid},
      false,false,false,false,false,false,false,false,
      false,false,false,false,false,false,false,false
   );
   return(INIT_SUCCEEDED);
  }}

void OnDeinit(const int reason)
  {{
   Comment("");
  }}

void OnTick()
  {{
   g_engine.OnTickProcess();
  }}
"""
    with open(os.path.join(MT5_EXP_DIR, f"{fname}.mq5"), "w", encoding="utf-8-sig") as f:
        f.write(indiv_code)

# 5. Copy to MT5 Data Folder and Compile with metaeditor64.exe
TERM_BASE = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
TERM_DATA = r"C:\Users\ryzen\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\MQL5"
if not os.path.exists(TERM_DATA) and os.path.exists(TERM_BASE):
    for d in os.listdir(TERM_BASE):
        cand = os.path.join(TERM_BASE, d, "MQL5")
        if os.path.isdir(cand):
            TERM_DATA = cand
            break
TERM_INC  = os.path.join(TERM_DATA, "Include")
TERM_EXP  = os.path.join(TERM_DATA, "Experts", "Jumba_GEX_NWE")
os.makedirs(TERM_INC, exist_ok=True)
os.makedirs(TERM_EXP, exist_ok=True)

shutil.copy2(core_path, os.path.join(TERM_INC, "Jumba_GEX_NWE_Core.mqh"))
if os.path.exists(wdo_core_path):
    shutil.copy2(wdo_core_path, os.path.join(TERM_INC, "Jumba_WDO_GEX_NWE_Core.mqh"))

METAEDITOR = r"C:\Program Files\MetaTrader 5 EXNESS\metaeditor64.exe"
mq5_files = sorted([f for f in os.listdir(MT5_EXP_DIR) if f.endswith(".mq5")])

compiled_ok = 0
for mq5 in mq5_files:
    src = os.path.join(MT5_EXP_DIR, mq5)
    dst = os.path.join(TERM_EXP, mq5)
    shutil.copy2(src, dst)
    log_file = dst.replace(".mq5", ".log")
    if os.path.exists(log_file):
        os.remove(log_file)
    cmd = [METAEDITOR, f'/compile:{dst}', f'/inc:{TERM_DATA}', f'/log:{log_file}']
    subprocess.run(cmd, check=False)
    ex5_dst = dst.replace(".mq5", ".ex5")
    ex5_src = src.replace(".mq5", ".ex5")
    if os.path.exists(ex5_dst):
        shutil.copy2(ex5_dst, ex5_src)
        compiled_ok += 1
        print(f"[COMPILED OK] {os.path.basename(ex5_src)} ({os.path.getsize(ex5_src):,} bytes)")
    else:
        print(f"[COMPILE FAILED] {mq5}")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-16", errors="ignore") as lf:
                print(lf.read())

print(f"\nTotal .ex5 compiled successfully: {compiled_ok}/{len(mq5_files)}")
