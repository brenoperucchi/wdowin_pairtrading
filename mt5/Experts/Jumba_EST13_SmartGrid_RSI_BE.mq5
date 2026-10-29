//+------------------------------------------------------------------+
//| Jumba_EST13_SmartGrid_RSI_BE.mq5
//| EST-13 [NOVO-1 Stop Barra[1](off15) Hibrido + BE_2Stage(25) + TP_MidWall 2C] (Ret/DD 4.55)
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property description "EST-13 [NOVO-1 Stop Barra[1](off15) Hibrido + BE_2Stage(25) + TP_MidWall 2C] (Ret/DD 4.55)"
#property version   "2.00"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input ENUM_EXECUTION_MODE InpExecMode      = EXEC_HEDGING_DIRECT_MAGIC; // Modo de Execução
input double              InpLotMultiplier = 1.0;    // Multiplicador de Lotes
input double              InpMaxDailyLoss  = 1000.0; // Perda Máxima Diária Individual (R$)
input ulong               InpMagicNumber   = 88013; // Magic Number Base
input bool                InpDrawLevels    = true;   // Desenhar MagicWalls no Gráfico
input string              InpWdoSymbol     = "WDO$N"; // Símbolo do Dólar (se usado)

CJumbaGexNweEngine g_engine;

int OnInit()
  {
   g_engine.Init(InpMagicNumber - 13, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      PRESET_SINGLE_ROBOT, 13,
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
