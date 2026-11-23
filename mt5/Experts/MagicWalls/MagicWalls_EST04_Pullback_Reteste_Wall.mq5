//+------------------------------------------------------------------+
//| MagicWalls_EST04_Pullback_Reteste_Wall.mq5
//| EST-04 [Matriz WDO Reteste 220p(off-5) + BE_2Stage(15) + TP_MidWall] (Ret/DD 4.88)
//+------------------------------------------------------------------+
#property copyright "Magic Walls"
#property description "EST-04 [Matriz WDO Reteste 220p(off-5) + BE_2Stage(15) + TP_MidWall] (Ret/DD 4.88)"
#property version   "2.00"
#property strict

#include <MagicWalls_GEX_NWE_Core.mqh>

input ENUM_EXECUTION_MODE InpExecMode      = EXEC_HEDGING_DIRECT_MAGIC; // Modo de Execução
input double              InpLotMultiplier = 1.0;    // Multiplicador de Lotes
input double              InpMaxDailyLoss  = 1000.0; // Perda Máxima Diária Individual (R$)
input ulong               InpMagicNumber   = 88004; // Magic Number Base
input bool                InpDrawLevels    = true;   // Desenhar MagicWalls no Gráfico
input string              InpWdoSymbol     = "WDO$N"; // Símbolo do Dólar (se usado)
input bool                InpUseFlowFilter = false;   // Filtro de Fluxo Institucional Nativo (CopyTicks)
input string              InpMaxEntryTime  = "16:00"; // Horario Limite Novas Entradas (HH:MM, vazio=off)

CMagicWallsGexNweEngine g_engine;

int OnInit()
  {
   g_engine.Init(InpMagicNumber - 4, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      PRESET_SINGLE_ROBOT, 4,
      false,false,false,false,false,false,false,false,
      false,false,false,false,false,false,false,false
   );
   g_engine.SetUseFlowFilter(InpUseFlowFilter);
   g_engine.SetMaxEntryTime(InpMaxEntryTime);
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
