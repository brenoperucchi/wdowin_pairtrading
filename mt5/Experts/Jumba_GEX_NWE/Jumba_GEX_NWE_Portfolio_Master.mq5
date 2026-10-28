//+------------------------------------------------------------------+
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
