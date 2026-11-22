//+------------------------------------------------------------------+
//| Jumba_EST09_Breakout_Stop_Wall.mq5
//| EST-09 [Mantido Original] Breakout Stop & Limit Wall NY (Ret/DD 4.53)
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property description "EST-09 [Validado 5/5 · MaxTr=2/dia] Breakout Stop & Limit Wall NY (MT5 Ret/DD 3.93x)"
#property version   "2.10"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input ENUM_EXECUTION_MODE InpExecMode      = EXEC_HEDGING_DIRECT_MAGIC; // Modo de Execução
input double              InpLotMultiplier = 1.0;    // Multiplicador de Lotes
input double              InpMaxDailyLoss  = 1000.0; // Perda Máxima Diária Individual (R$)
input ulong               InpMagicNumber   = 88009; // Magic Number Base
input bool                InpDrawLevels    = true;   // Desenhar MagicWalls no Gráfico
input string              InpWdoSymbol     = "WDO$N"; // Símbolo do Dólar (se usado)
input bool                InpUseFlowFilter = false;   // Filtro de Fluxo Institucional Nativo (CopyTicks)
input string              InpMaxEntryTime  = "16:00"; // Horario Limite Novas Entradas (HH:MM, vazio=off)

CJumbaGexNweEngine g_engine;

int OnInit()
  {
   g_engine.Init(InpMagicNumber - 9, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      PRESET_SINGLE_ROBOT, 9,
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
