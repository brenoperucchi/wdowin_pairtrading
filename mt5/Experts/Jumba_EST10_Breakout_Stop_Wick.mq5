//+------------------------------------------------------------------+
//| Jumba_EST10_Breakout_Stop_Wick.mq5
//| EST-10 [Matriz WDO MainWalls pos50+GammaFlip + BE_177k(240/45)] (Ret/DD 5.20)
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property description "EST-10 [Matriz WDO MainWalls pos50+GammaFlip + BE_177k(240/45)] (Ret/DD 5.20)"
#property version   "2.00"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input ENUM_EXECUTION_MODE InpExecMode      = EXEC_HEDGING_DIRECT_MAGIC; // Modo de Execução
input double              InpLotMultiplier = 1.0;    // Multiplicador de Lotes
input double              InpMaxDailyLoss  = 1000.0; // Perda Máxima Diária Individual (R$)
input ulong               InpMagicNumber   = 88010; // Magic Number Base
input bool                InpDrawLevels    = true;   // Desenhar MagicWalls no Gráfico
input string              InpWdoSymbol     = "WDO$N"; // Símbolo do Dólar (se usado)

CJumbaGexNweEngine g_engine;

int OnInit()
  {
   g_engine.Init(InpMagicNumber - 10, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      PRESET_SINGLE_ROBOT, 10,
      false,false,false,false,false,false,false,false,
      false,false,false,false,false,false,false,false
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
