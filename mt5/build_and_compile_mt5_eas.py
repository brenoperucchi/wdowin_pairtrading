import os
import shutil
import subprocess

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
MT5_PROJ_DIR = os.path.join(PROJECT_ROOT, "mt5")
MT5_INC_DIR = os.path.join(MT5_PROJ_DIR, "Include")
MT5_EXP_DIR = os.path.join(MT5_PROJ_DIR, "Experts", "Jumba_GEX_NWE")

os.makedirs(MT5_INC_DIR, exist_ok=True)
os.makedirs(MT5_EXP_DIR, exist_ok=True)

# 1. Keep canonical Jumba_GEX_NWE_Core.mqh
core_path = os.path.join(MT5_INC_DIR, "Jumba_GEX_NWE_Core.mqh")
wdo_core_path = os.path.join(MT5_INC_DIR, "Jumba_WDO_GEX_NWE_Core.mqh")

# 2. Write Jumba_GEX_NWE_Portfolio_Master.mq5 (Default = PRESET_TODAS_16_ATIVAS - MIX CAMPEÃO)
master_mq5 = r"""//+------------------------------------------------------------------+
//|                               Jumba_GEX_NWE_Portfolio_Master.mq5 |
//|   EA Mestre Unificado de Portfólio GEX MagicWalls + NWE (WIN)    |
//|   Portfólio MIX CAMPEÃO (EST-01 a EST-16 | Ret/DD 18.45 | PF 1.50)|
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property version   "2.00"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input group "=== 1. SELECAO DO PORTFOLIO & EXECUCAO (MIX CAMPEAO) ==="
input ENUM_PORTFOLIO_PRESET InpPreset         = PRESET_TODAS_16_ATIVAS;   // Preset de Portfólio (Padrão: Todas 16 do Mix Campeão)
input ENUM_EXECUTION_MODE   InpExecMode       = EXEC_NETTING_VIRTUAL_SYNC;// Modo de Execução (Netting B3 ou Hedging)
input double                InpLotMultiplier  = 1.0;    // Multiplicador de Lotes (1.0 = Lote Base do Mix Campeão)
input double                InpMaxDailyLoss   = 2500.0; // Trava de Perda Máxima Diária do Portfólio (R$)
input ulong                 InpBaseMagic      = 88000;  // Magic Number Base
input bool                  InpDrawLevels     = true;   // Desenhar MagicWalls no Gráfico
input string                InpWdoSymbol      = "WDO$N";// Símbolo do Dólar (p/ EST-03)

input group "=== 2. CHAVES INDIVIDUAIS (USADAS NO MODO PRESET_CUSTOM_MANUAL) ==="
input bool Enable_EST01_Scalper_NY            = true;
input bool Enable_EST02_Scalper_Full          = true;
input bool Enable_EST03_Scalper_WDO           = true;
input bool Enable_EST04_Pullback_Retest       = true;
input bool Enable_EST05_Pullback_Cluster      = true;
input bool Enable_EST06_Pullback_LimitSlope   = true;
input bool Enable_EST07_Breakout_NY           = true;
input bool Enable_EST08_Breakout_Core         = true;
input bool Enable_EST09_Breakout_StopWall     = true;
input bool Enable_EST10_Breakout_StopWick     = true;
input bool Enable_EST11_Grid_TrendPullback    = true;
input bool Enable_EST12_Pyramid_Profit11      = true;
input bool Enable_EST13_SmartGrid_RSI         = true;
input bool Enable_EST14_Grid_Institucional    = true;
input bool Enable_EST15_EOD_Breakout          = true;
input bool Enable_EST16_EOD_ExtremeFade       = true;

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
   g_engine.Deinit();
  }

void OnTick()
  {
   g_engine.OnTickProcess();
  }
"""

master_path = os.path.join(MT5_EXP_DIR, "Jumba_GEX_NWE_Portfolio_Master.mq5")
with open(master_path, "w", encoding="utf-8-sig") as f:
    f.write(master_mq5)

# 3. Generate all 16 Individual Strategy .mq5 files (keeping exact filenames so existing charts reload automatically)
indiv_specs = [
    (1,  "Jumba_EST01_Scalper_Hibrido_NY",       88001, "EST-01 [3-Pilares BE_Wall(25) + TP_MainWall] Scalper Hibrido NY (Ret/DD 6.90)"),
    (2,  "Jumba_EST02_Scalper_Hibrido_DiaTodo",  88002, "EST-02 [3-Pilares Limit_50%B1 + TP_MainWall] Scalper Dia Todo (Ret/DD 3.80)"),
    (3,  "Jumba_EST03_Scalper_Cambial_WDO",      88003, "EST-03 [Mantido Original] Arbitragem Cambial WIN+WDO Wall (Ret/DD 6.68)"),
    (4,  "Jumba_EST04_Pullback_Reteste_Wall",    88004, "EST-04 [Matriz WDO Reteste 220p(off-5) + BE_2Stage(15) + TP_MidWall] (Ret/DD 4.88)"),
    (5,  "Jumba_EST05_Pullback_Cluster_NWE",     88005, "EST-05 [3-Pilares Limit_ExtB1 + TP_MainWall] Pullback Cluster NWE (Ret/DD 6.57)"),
    (6,  "Jumba_EST06_Pullback_Limit_Slope",     88006, "EST-06 [3-Pilares Stop_B1 + BE_Wall(15) + TP_MainWall] Slope Wall (Ret/DD 5.99)"),
    (7,  "Jumba_EST07_Breakout_Momentum_NY",     88007, "EST-07 [3-Pilares BE_Wall(15) + TP_Original] Breakout Momentum NY (Ret/DD 6.91)"),
    (8,  "Jumba_EST08_Breakout_Rapido_Core",     88008, "EST-08 [3-Pilares TP_MainWall Real] Breakout Rapido Core (Ret/DD 5.40)"),
    (9,  "Jumba_EST09_Breakout_Stop_Wall",       88009, "EST-09 [Mantido Original] Breakout Stop & Limit Wall NY (Ret/DD 4.53)"),
    (10, "Jumba_EST10_Breakout_Stop_Wick",       88010, "EST-10 [Matriz WDO MainWalls pos50+GammaFlip + BE_177k(240/45)] (Ret/DD 5.20)"),
    (11, "Jumba_EST11_Grid_Pullback_Tendencia",  88011, "EST-11 [NOVO-4 Stop Barra[1](2b) Hibrido + BE_Wall(25) + TP_MidWall 2C] (Ret/DD 3.00)"),
    (12, "Jumba_EST12_Piramidacao_Lucro_11L",    88012, "EST-12 [3-Pilares TP_MainWall Real] Piramidacao no Lucro 1+1L (Ret/DD 4.47)"),
    (13, "Jumba_EST13_SmartGrid_RSI_BE",         88013, "EST-13 [NOVO-1 Stop Barra[1](off15) Hibrido + BE_2Stage(25) + TP_MidWall 2C] (Ret/DD 4.55)"),
    (14, "Jumba_EST14_Grid_Institucional_123L",  88014, "EST-14 [NOVO-2 Rolling Stop Barra[1] Slope + BE_2Stage(25) + TP_MidWall 2C] (Ret/DD 3.85)"),
    (15, "Jumba_EST15_Posicional_EOD_Breakout",  88015, "EST-15 [3-Pilares Stop_B1 + BE_Wall(15) + TP_MainWall] EOD Breakout (Ret/DD 6.05)"),
    (16, "Jumba_EST16_Posicional_EOD_Fade",      88016, "EST-16 [NOVO-3 Rolling Stop Barra[1] Slope + BE_2Stage(25) + Parcial Mid/Main 2C] (Ret/DD 3.63)"),
]

for sid, fname, magic, desc in indiv_specs:
    indiv_code = f"""//+------------------------------------------------------------------+
//| {fname}.mq5
//| {desc}
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property description "{desc}"
#property version   "2.00"
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
   g_engine.Deinit();
  }}

void OnTick()
  {{
   g_engine.OnTickProcess();
  }}
"""
    with open(os.path.join(MT5_EXP_DIR, f"{fname}.mq5"), "w", encoding="utf-8-sig") as f:
        f.write(indiv_code)

# 4. Copy to ALL MT5 Terminal Data Folders and Compile with metaeditor64.exe
TERM_BASE = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
term_mql5_dirs = []
if os.path.exists(TERM_BASE):
    for d in os.listdir(TERM_BASE):
        cand = os.path.join(TERM_BASE, d, "MQL5")
        if os.path.isdir(cand):
            term_mql5_dirs.append(cand)

PRIMARY_TERM_DATA = r"C:\Users\ryzen\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5"
if not os.path.exists(PRIMARY_TERM_DATA) and term_mql5_dirs:
    PRIMARY_TERM_DATA = term_mql5_dirs[0]

TERM_INC = os.path.join(PRIMARY_TERM_DATA, "Include")
TERM_EXP = os.path.join(PRIMARY_TERM_DATA, "Experts", "Jumba_GEX_NWE")
os.makedirs(TERM_INC, exist_ok=True)
os.makedirs(TERM_EXP, exist_ok=True)

shutil.copy2(core_path, os.path.join(TERM_INC, "Jumba_GEX_NWE_Core.mqh"))
if os.path.exists(wdo_core_path):
    shutil.copy2(wdo_core_path, os.path.join(TERM_INC, "Jumba_WDO_GEX_NWE_Core.mqh"))

METAEDITOR_CANDIDATES = [
    r"C:\Program Files\MetaTrader 5\metaeditor64.exe",
    r"C:\Program Files\MetaTrader 5 EXNESS\metaeditor64.exe",
    r"C:\Program Files\Tickmill MT5 Terminal\metaeditor64.exe",
]
METAEDITOR = next((p for p in METAEDITOR_CANDIDATES if os.path.exists(p)), METAEDITOR_CANDIDATES[0])
mq5_files = sorted([f for f in os.listdir(MT5_EXP_DIR) if f.endswith(".mq5")])

compiled_ok = 0
for mq5 in mq5_files:
    src = os.path.join(MT5_EXP_DIR, mq5)
    dst = os.path.join(TERM_EXP, mq5)
    shutil.copy2(src, dst)
    log_file = dst.replace(".mq5", ".log")
    if os.path.exists(log_file):
        os.remove(log_file)
    cmd = [METAEDITOR, f"/compile:{dst}", f"/inc:{PRIMARY_TERM_DATA}", f"/log:{log_file}"]
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

# Replicate compiled .ex5 and .mqh to all other MT5 Terminal directories on the machine
for t_mql5 in term_mql5_dirs:
    if os.path.normcase(t_mql5) == os.path.normcase(PRIMARY_TERM_DATA):
        continue
    t_inc = os.path.join(t_mql5, "Include")
    t_exp = os.path.join(t_mql5, "Experts", "Jumba_GEX_NWE")
    os.makedirs(t_inc, exist_ok=True)
    os.makedirs(t_exp, exist_ok=True)
    shutil.copy2(core_path, os.path.join(t_inc, "Jumba_GEX_NWE_Core.mqh"))
    if os.path.exists(wdo_core_path):
        shutil.copy2(wdo_core_path, os.path.join(t_inc, "Jumba_WDO_GEX_NWE_Core.mqh"))
    for f in os.listdir(MT5_EXP_DIR):
        if f.endswith((".mq5", ".ex5")):
            shutil.copy2(os.path.join(MT5_EXP_DIR, f), os.path.join(t_exp, f))
    print(f"[SYNCED TERMINAL] {t_mql5}")

print(f"\nTotal .ex5 compiled successfully: {compiled_ok}/{len(mq5_files)}")
