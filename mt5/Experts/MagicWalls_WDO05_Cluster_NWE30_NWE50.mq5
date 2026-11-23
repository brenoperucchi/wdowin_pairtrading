//+------------------------------------------------------------------+
//|                                MagicWalls_WDO05_Cluster_NWE30_NWE50.mq5
//|        Magic Walls - WDO-05 Cluster NWE30 + NWE50 + Wall
//+------------------------------------------------------------------+
#property copyright "Magic Walls"
#property version   "1.00"
#property description "WDO-05 Cluster NWE30 + NWE50 + Wall (Magic 89005)"

#include <MagicWalls_WDO_GEX_NWE_Core.mqh>

input long                     InpBaseMagic        = 89000;                        // Magic Base (Slot 5 -> 89005)
input double                   InpLotMultiplier    = 1.0;                          // Multiplicador de Lotes
input double                   InpMaxDailyLossBRL  = 2000.0;                       // Perda Maxima Diaria (R$)
input ENUM_MW_WDO_EXEC_MODE InpExecMode         = WDO_EXEC_HEDGING_DIRECT_MAGIC;// Modo de Execucao
input bool                     InpDrawGexLevels    = true;                         // Desenhar MagicWalls
input bool                     InpShowHud          = true;                         // Mostrar Painel HUD
input bool                     InpUseFlowFilter    = false;                        // Filtro de Fluxo Institucional Nativo (CopyTicks)
input string                   InpMaxEntryTime     = "15:00";                      // Horario Limite Novas Entradas (HH:MM, vazio=off)

CMagicWallsWdoGexNweEngine ExtEngine;

int OnInit()
  {
   ExtEngine.Init(InpBaseMagic, InpLotMultiplier, InpMaxDailyLossBRL,
                  InpDrawGexLevels, InpShowHud, InpExecMode,
                  false, false, false, false, true, false, false, false, false, false, false, false, false, false, false, false);
   ExtEngine.SetUseFlowFilter(InpUseFlowFilter);
   ExtEngine.SetMaxEntryTime(InpMaxEntryTime);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ExtEngine.Deinit();
  }

void OnTick()
  {
   ExtEngine.OnTickProcess();
  }
//+------------------------------------------------------------------+
