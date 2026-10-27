//+------------------------------------------------------------------+
//|                                Jumba_WDO02_Scalper_Hibrido_CORE.mq5
//|        Jumba Quantitative Trading - WDO-02 Scalper Hibrido CORE (09h10-16h15)
//+------------------------------------------------------------------+
#property copyright "Jumba Quantitative Trading"
#property version   "1.00"
#property description "WDO-02 Scalper Hibrido CORE (09h10-16h15) (Magic 89002)"

#include <Jumba_WDO_GEX_NWE_Core.mqh>

input long                     InpBaseMagic        = 89000;                        // Magic Base (Slot 2 -> 89002)
input double                   InpLotMultiplier    = 1.0;                          // Multiplicador de Lotes
input double                   InpMaxDailyLossBRL  = 2000.0;                       // Perda Maxima Diaria (R$)
input ENUM_JUMBA_WDO_EXEC_MODE InpExecMode         = WDO_EXEC_HEDGING_DIRECT_MAGIC;// Modo de Execucao
input bool                     InpDrawGexLevels    = true;                         // Desenhar MagicWalls
input bool                     InpShowHud          = true;                         // Mostrar Painel HUD

CJumbaWdoGexNweEngine ExtEngine;

int OnInit()
  {
   ExtEngine.Init(InpBaseMagic, InpLotMultiplier, InpMaxDailyLossBRL,
                  InpDrawGexLevels, InpShowHud, InpExecMode,
                  false, true, false, false, false, false, false, false, false, false, false, false, false, false, false, false);
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
