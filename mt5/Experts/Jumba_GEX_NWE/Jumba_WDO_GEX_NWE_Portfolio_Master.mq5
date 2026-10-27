//+------------------------------------------------------------------+
//|                         Jumba_WDO_GEX_NWE_Portfolio_Master.mq5   |
//|        Jumba Quantitative Trading - Portfolio Master 16 WDO$N    |
//+------------------------------------------------------------------+
#property copyright "Jumba Quantitative Trading"
#property version   "1.00"
#property description "Portfolio Master consolidando as 16 Estrategias WDO$N GEX MagicWalls + NWE (Magics 89001..89016)"

#include <Jumba_WDO_GEX_NWE_Core.mqh>

input long                     InpBaseMagic        = 89000;                        // Magic Base (89001..89016)
input double                   InpLotMultiplier    = 1.0;                          // Multiplicador de Lotes
input double                   InpMaxDailyLossBRL  = 5000.0;                       // Perda Maxima Diaria do Portfolio (R$)
input ENUM_JUMBA_WDO_EXEC_MODE InpExecMode         = WDO_EXEC_HEDGING_DIRECT_MAGIC;// Modo de Execucao
input bool                     InpDrawGexLevels    = true;                         // Desenhar MagicWalls
input bool                     InpShowHud          = true;                         // Mostrar Painel HUD
input bool                     InpEnableWDO01      = true;
input bool                     InpEnableWDO02      = true;
input bool                     InpEnableWDO03      = true;
input bool                     InpEnableWDO04      = true;
input bool                     InpEnableWDO05      = true;
input bool                     InpEnableWDO06      = true;
input bool                     InpEnableWDO07      = true;
input bool                     InpEnableWDO08      = true;
input bool                     InpEnableWDO09      = true;
input bool                     InpEnableWDO10      = true;
input bool                     InpEnableWDO11      = true;
input bool                     InpEnableWDO12      = true;
input bool                     InpEnableWDO13      = true;
input bool                     InpEnableWDO14      = true;
input bool                     InpEnableWDO15      = true;
input bool                     InpEnableWDO16      = true;

CJumbaWdoGexNweEngine ExtEngine;

int OnInit()
  {
   ExtEngine.Init(InpBaseMagic, InpLotMultiplier, InpMaxDailyLossBRL,
                  InpDrawGexLevels, InpShowHud, InpExecMode,
                  InpEnableWDO01, InpEnableWDO02, InpEnableWDO03, InpEnableWDO04,
                  InpEnableWDO05, InpEnableWDO06, InpEnableWDO07, InpEnableWDO08,
                  InpEnableWDO09, InpEnableWDO10, InpEnableWDO11, InpEnableWDO12,
                  InpEnableWDO13, InpEnableWDO14, InpEnableWDO15, InpEnableWDO16);
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
