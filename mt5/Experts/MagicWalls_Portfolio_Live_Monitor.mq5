//+------------------------------------------------------------------+
//|                                 MagicWalls_Portfolio_Live_Monitor.mq5 |
//|     Magic Walls - Monitor de Operações & Histórico |
//|     Acompanha 10 Robôs Elite (Walls+NWE B3): WIN(7) + WDO(3)     |
//|     Guarda e Compara MaxDD (BT vs Live) e Loss Streak (BT vs Live)|
//+------------------------------------------------------------------+
#property copyright "Magic Walls"
#property description "Monitor em Tempo Real e Historico dos 10 Robos Elite (7 WIN + 3 WDO | B3 WDO<15h WIN<16h)."
#property description "Compara Operacoes Abertas, PnL, MaxDD (BT vs Live) e Sequencia de Loss (BT vs Live) + Stop Diario Maximo."
#property version   "4.20"
#property strict

#include <Trade\Trade.mqh>
CTrade g_trade;

enum ENUM_BT_DD_MODE
  {
   BT_DD_BY_TRADE = 0, // MaxDD BT Trade-a-Trade (Mais Conservador)
   BT_DD_BY_DAY   = 1  // MaxDD BT Fechamento Diario (212 Pregões 2026)
  };

enum ENUM_HIST_SOURCE
  {
   HIST_AUTO_HYBRID    = 0, // Auto: Deals MT5 por Magic + Fallback Audit CSV (Netting)
   HIST_MT5_DEALS_ONLY = 1, // Apenas Histórico Nativo de Deals do MT5
   HIST_AUDIT_CSV_ONLY = 2  // Apenas Arquivo magicwalls_live_trades_audit_<Login>.csv
  };

input ulong            InpWinBaseMagic     = 88000;            // Magic Base WIN (88001..88016)
input ulong            InpWdoBaseMagic     = 89000;            // Magic Base WDO (89001..89016)
input ENUM_BT_DD_MODE  InpBtDdReference    = BT_DD_BY_DAY;     // Referência de MaxDD do Backtest
input ENUM_HIST_SOURCE InpHistorySource    = HIST_AUTO_HYBRID; // Fonte do Histórico de Trades Fechados
input int              InpRefreshSeconds     = 2;                // Intervalo de Atualização (Segundos)
input datetime         InpHistoryStartDate   = D'2025.01.01';    // Data Inicial do Histórico Live
input bool             InpResetReplacedSlots = true;             // Zerar Histórico de Slots Substituídos em 01/11/2026
input bool             InpIncludeFloatingDD  = true;             // Incluir PnL Flutuante Aberto no Cálculo de DD Live
input bool            InpExportCsvReport  = true;           // Exportar Relatório CSV em FILE_COMMON
input bool            InpAlertOnBtBreach  = true;           // Emitir Alerta Sonoro/Log se Live > MaxDD/Streak BT
input int             InpPanelX           = 12;             // Posição X do Painel no Gráfico
input int             InpPanelY           = 24;             // Posição Y do Painel no Gráfico
input int             InpFontSize         = 8;              // Tamanho da Fonte da Tabela

input group "=== GERENCIA DE STOP DIARIO MAXIMO ==="
input bool            InpEnableDailyStop      = true;       // Ativar Gerência de Stop Diário Máximo
input double          InpMaxDailyLossGlobal   = 950.0;      // Stop Diário Global WIN+WDO (R$, 0=Desativado)
input double          InpMaxDailyLossWin      = 400.0;      // Sub-limite Diário WIN (R$, 0=Desativado)
input double          InpMaxDailyLossWdo      = 0.0;        // Sub-limite Diário WDO (R$, 0=Desativado)
input double          InpStopWarningPct       = 70.0;       // Percentual para Alerta Amarelo (%)
input bool            InpClosePositionsOnStop = true;       // Fechar Posições Abertas ao Atingir Stop
input bool            InpCancelPendingOnStop  = true;       // Cancelar Ordens Pendentes ao Atingir Stop
input bool            InpIncludeAllMwMagics= true;       // Somar Todos Magics Magic Walls (88000..88016 e 89000..89016)
input bool            InpUseAuctionFilter     = true;       // Suspender Disparo Durante Leilão/Spread Anômalo
input string          InpBlockFrom1           = "08:55";    // Início Janela Leilão Abertura
input string          InpBlockTo1             = "09:02";    // Fim Janela Leilão Abertura
input string          InpBlockFrom2           = "17:55";    // Início Janela Leilão Fechamento
input string          InpBlockTo2             = "18:35";    // Fim Janela Leilão Fechamento
input bool            InpSendPushOnStop       = true;       // Enviar Notificação Push ao Atingir Stop
input bool            InpClearStopOnRemove    = false;      // Limpar Trava Global ao Remover o Monitor (F3 mantém)

#define TOTAL_MONITORED_ROBOTS 10
#define IDX_SUMMARY_WIN        10
#define IDX_SUMMARY_WDO        11
#define IDX_SUMMARY_PORTFOLIO  12
#define TOTAL_ROWS             13

struct SRobotMonitorRow
  {
   string            code;
   string            strat_name;
   bool              is_wdo;
   int               slot_id;
   ulong             magic;
   datetime          valid_from;        // Data de ativação do modelo atual no slot
   // --- Benchmarks do Backtest (124 Pregões Validados) ---
   int               bt_trades;
   double            bt_wr;
   double            bt_pf;
   double            bt_net_brl;
   double            bt_max_dd_day_brl;
   double            bt_max_dd_trade_brl;
   int               bt_max_loss_streak;
   // --- Estado em Tempo Real (Posições / Ordens) ---
   int               open_dir;          // 1 = BUY, -1 = SELL, 0 = FLAT
   double            open_lots;
   double            open_price;
   double            open_floating_brl;
   int               pending_orders;
   // --- Histórico Fechado + Persistência Live ---
   int               live_trades;
   int               live_wins;
   int               live_losses;
   double            live_gross_win;
   double            live_gross_loss;
   double            live_net_brl;
   double            live_day_brl;
   double            live_peak_brl;
   double            live_curr_dd_brl;
   double            live_max_dd_brl;       // Guardado e Persistido em Disco
   int               live_curr_loss_streak; // Sequência Atual de Trades em Loss
   int               live_max_loss_streak;  // Maior Sequência de Loss no Live (Persistida)
   datetime          last_trade_time;
   bool              alerted_dd;
   bool              alerted_streak;
  };

struct SDealRecord
  {
   datetime          time;
   ulong             ticket;
   int               row_idx;
   double            net_pnl;
  };

SRobotMonitorRow g_rows[TOTAL_ROWS];
string           g_prefix = "MW_MON_";
datetime         g_last_update = 0;
datetime         g_last_full_refresh = 0;
ulong            g_last_stop_check_ms = 0;
datetime         g_last_state_export = 0;

// --- Estado da Gerência de Stop Diário Máximo ---
double           g_stop_day_key      = 0.0;
bool             g_stop_global_hit   = false;
bool             g_stop_win_hit      = false;
bool             g_stop_wdo_hit      = false;
bool             g_warn_global_sent  = false;
bool             g_warn_win_sent     = false;
bool             g_warn_wdo_sent     = false;
datetime         g_last_retry_close  = 0;
double           g_day_closed_win    = 0.0;
double           g_day_closed_wdo    = 0.0;
double           g_day_float_win     = 0.0;
double           g_day_float_wdo     = 0.0;
double           g_day_total_win     = 0.0;
double           g_day_total_wdo     = 0.0;
double           g_day_total_global  = 0.0;
double           g_day_mae_win       = 0.0;
double           g_day_mae_wdo       = 0.0;
double           g_day_mae_global    = 0.0;

//+------------------------------------------------------------------+
//| Inicializa os Benchmarks Oficiais de Backtest dos 18 Robôs       |
//+------------------------------------------------------------------+
void InitBenchmarks()
  {
   for(int i = 0; i < TOTAL_ROWS; i++)
     {
      g_rows[i].open_dir              = 0;
      g_rows[i].open_lots             = 0.0;
      g_rows[i].open_price            = 0.0;
      g_rows[i].open_floating_brl     = 0.0;
      g_rows[i].pending_orders        = 0;
      g_rows[i].live_trades           = 0;
      g_rows[i].live_wins             = 0;
      g_rows[i].live_losses           = 0;
      g_rows[i].live_gross_win        = 0.0;
      g_rows[i].live_gross_loss       = 0.0;
      g_rows[i].live_net_brl          = 0.0;
      g_rows[i].live_day_brl          = 0.0;
      g_rows[i].live_peak_brl         = 0.0;
      g_rows[i].live_curr_dd_brl      = 0.0;
      g_rows[i].live_max_dd_brl       = 0.0;
      g_rows[i].live_curr_loss_streak = 0;
      g_rows[i].live_max_loss_streak  = 0;
      g_rows[i].last_trade_time       = 0;
      g_rows[i].alerted_dd            = false;
      g_rows[i].alerted_streak        = false;
     }

   datetime dt_orig = D'2025.01.01 00:00';
   datetime dt_nov  = D'2026.11.01 00:00'; // Data em que os novos modelos (>=100tr + WF + Rollover Fix) substituíram os slots antigos
   datetime dt_19   = D'2026.11.19 00:00'; // Data de inclusão EST-09 (MaxTr=2/d) e EST-10 (MaxTr=1/d) validados 5/5

   // --- 7 ROBÔS WIN ATIVOS (Magic 88004, 07, 09, 10, 13, 14, 15) · MT5 Tester B3 (WIN<16h) ---
   SetRowConfig(0,  "EST-04", "WIN_PB_WDO_ALIGNED",      false, 4,  InpWinBaseMagic + 4,  dt_orig,  323, 44.9, 1.40,  2525.0,  482.0,  582.0, 10);
   SetRowConfig(1,  "EST-07", "WIN_OF_CLIMAX_WALL",      false, 7,  InpWinBaseMagic + 7,  dt_orig,  521, 33.6, 1.17,  2048.0,  580.0,  654.0, 16);
   SetRowConfig(2,  "EST-09", "WIN_BO_STOP_LIM_NY_2D",   false, 9,  InpWinBaseMagic + 9,  dt_19,    363, 59.8, 1.36,  2689.0,  608.0,  659.0,  5);
   SetRowConfig(3,  "EST-10", "WIN_MAINWALL_STOP_1D",    false, 10, InpWinBaseMagic + 10, dt_19,    168, 60.7, 1.39,  1310.0,  552.0,  552.0,  6);
   SetRowConfig(4,  "EST-13", "WIN_SG_SCALPER_3C",       false, 13, InpWinBaseMagic + 13, dt_nov,   653, 56.2, 1.65,  8620.0, 1202.0, 1310.0, 10);
   SetRowConfig(5,  "EST-14", "WIN_SG_MOMENTUM_3C",      false, 14, InpWinBaseMagic + 14, dt_nov,   685, 54.9, 1.34,  5216.0,  806.0,  806.0,  8);
   SetRowConfig(6,  "EST-15", "WIN_SG_Z30_REV_WALL",     false, 15, InpWinBaseMagic + 15, dt_nov,   629, 61.0, 1.41,  5170.0,  574.0,  670.0, 10);

   // --- 3 ROBÔS WDO ATIVOS (Magic 89001, 89005, 89007) · MT5 Tester B3 (WDO<15h) ---
   SetRowConfig(7,  "WDO-01", "WDO_PA_WALL_SCALPER_NY",  true,  1,  InpWdoBaseMagic + 1,  dt_nov,   613, 63.8, 1.34,  6610.0,  720.0,  815.0,  4);
   SetRowConfig(8,  "WDO-05", "WDO_PA_CLUSTER_NWE",      true,  5,  InpWdoBaseMagic + 5,  dt_nov,   657, 64.4, 1.29,  6515.0, 1005.0, 1105.0,  5);
   SetRowConfig(9,  "WDO-07", "WDO_OF_CLIMAX_WALL",      true,  7,  InpWdoBaseMagic + 7,  dt_orig,  389, 56.0, 1.37,  4295.0,  960.0,  960.0,  4);

   // --- 3 LINHAS DE CONSOLIDAÇÃO (WIN 07, WDO 03, PORTFÓLIO TOTAL 10) ---
   SetRowConfig(IDX_SUMMARY_WIN,       "WIN 07",   "SUBTOTAL INDICE (07 ROBOS)",  false, 99,  0, dt_orig, 3342, 52.8, 1.39, 27578.0, 1178.0, 1307.0, 15);
   SetRowConfig(IDX_SUMMARY_WDO,       "WDO 03",   "SUBTOTAL DOLAR (03 ROBOS)",   true,  99,  0, dt_orig, 1659, 62.2, 1.32, 17420.0, 1960.0, 2240.0,  9);
   SetRowConfig(IDX_SUMMARY_PORTFOLIO, "TOTAL",    "PORTFOLIO ELITE (10 ROBOS)",  false, 100, 0, dt_orig, 5001, 55.9, 1.36, 44998.0, 1697.0, 2053.0, 12);
  }

//+------------------------------------------------------------------+
//| Configura uma linha da tabela                                    |
//+------------------------------------------------------------------+
void SetRowConfig(int idx, string code, string name, bool is_wdo, int slot, ulong magic, datetime valid_from,
                  int bt_tr, double bt_wr, double bt_pf, double bt_net,
                  double bt_dd_day, double bt_dd_tr, int bt_streak)
  {
   g_rows[idx].code                = code;
   g_rows[idx].strat_name          = name;
   g_rows[idx].is_wdo              = is_wdo;
   g_rows[idx].slot_id             = slot;
   g_rows[idx].magic               = magic;
   g_rows[idx].valid_from          = valid_from;
   g_rows[idx].bt_trades           = bt_tr;
   g_rows[idx].bt_wr               = bt_wr;
   g_rows[idx].bt_pf               = bt_pf;
   g_rows[idx].bt_net_brl          = bt_net;
   g_rows[idx].bt_max_dd_day_brl   = bt_dd_day;
   g_rows[idx].bt_max_dd_trade_brl = bt_dd_tr;
   g_rows[idx].bt_max_loss_streak  = bt_streak;
  }

//+------------------------------------------------------------------+
//| Retorna o MaxDD de referência do Backtest conforme Input         |
//+------------------------------------------------------------------+
double GetBtMaxDD(int idx)
  {
   if(InpBtDdReference == BT_DD_BY_DAY)
      return g_rows[idx].bt_max_dd_day_brl;
   return g_rows[idx].bt_max_dd_trade_brl;
  }

//+------------------------------------------------------------------+
//| Localiza índice da linha pelo Magic Number (0..17 ou -1)         |
//+------------------------------------------------------------------+
int FindRowByMagic(ulong magic)
  {
   for(int i = 0; i < TOTAL_MONITORED_ROBOTS; i++)
     {
      if(g_rows[i].magic == magic)
         return i;
     }
   return -1;
  }

//+------------------------------------------------------------------+
//| Nome do arquivo de persistência de recordes Live em FILE_COMMON  |
//+------------------------------------------------------------------+
string GetPersistentStateFileName()
  {
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   return StringFormat("magicwalls_monitor_records_v2_%I64d.csv", login);
  }

//+------------------------------------------------------------------+
//| Carrega MaxDD Live e MaxLossStreak Live persistidos em disco     |
//+------------------------------------------------------------------+
void LoadPersistentRecords()
  {
   string fname = GetPersistentStateFileName();
   if(!FileIsExist(fname, FILE_COMMON))
      return;

   int h = FileOpen(fname, FILE_COMMON | FILE_READ | FILE_CSV | FILE_ANSI, ';');
   if(h == INVALID_HANDLE)
      return;

   while(!FileIsEnding(h))
     {
      string code = FileReadString(h);
      if(StringLen(code) == 0)
         continue;
      double saved_max_dd     = StringToDouble(FileReadString(h));
      int    saved_max_streak = (int)StringToInteger(FileReadString(h));
      double saved_peak_brl   = StringToDouble(FileReadString(h));

      for(int i = 0; i < TOTAL_ROWS; i++)
        {
         if(g_rows[i].code == code)
           {
            if(saved_max_dd > g_rows[i].live_max_dd_brl)
               g_rows[i].live_max_dd_brl = saved_max_dd;
            if(saved_max_streak > g_rows[i].live_max_loss_streak)
               g_rows[i].live_max_loss_streak = saved_max_streak;
            if(saved_peak_brl > g_rows[i].live_peak_brl)
               g_rows[i].live_peak_brl = saved_peak_brl;
            break;
           }
        }
     }
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| Salva MaxDD Live e MaxLossStreak Live em FILE_COMMON             |
//+------------------------------------------------------------------+
void SavePersistentRecords()
  {
   string fname = GetPersistentStateFileName();
   int h = FileOpen(fname, FILE_COMMON | FILE_WRITE | FILE_CSV | FILE_ANSI, ';');
   if(h == INVALID_HANDLE)
      return;

   for(int i = 0; i < TOTAL_ROWS; i++)
     {
      FileWrite(h,
                g_rows[i].code,
                DoubleToString(g_rows[i].live_max_dd_brl, 2),
                IntegerToString(g_rows[i].live_max_loss_streak),
                DoubleToString(g_rows[i].live_peak_brl, 2));
     }
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| Exporta Relatório Completo CSV em FILE_COMMON                    |
//+------------------------------------------------------------------+
void ExportCsvSnapshot()
  {
   if(!InpExportCsvReport)
      return;

   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string fname = StringFormat("magicwalls_portfolio_live_monitor_%I64d.csv", login);
   int h = FileOpen(fname, FILE_COMMON | FILE_WRITE | FILE_CSV | FILE_ANSI, ';');
   if(h == INVALID_HANDLE)
      return;

   FileWrite(h,
             "Code", "Strategy", "Magic", "OpenDir", "OpenLots", "FloatingBRL", "PendingOrders",
             "LiveTrades", "LiveWR_Pct", "LivePF", "LiveDayBRL", "LiveNetBRL",
             "LiveCurrDD_BRL", "LiveMaxDD_BRL", "BT_MaxDD_BRL", "DD_Used_Pct",
             "LiveCurrLossStreak", "LiveMaxLossStreak", "BT_MaxLossStreak",
             "BT_Trades", "BT_WR_Pct", "BT_PF", "BT_NetBRL");

   for(int i = 0; i < TOTAL_ROWS; i++)
     {
      double live_wr = (g_rows[i].live_trades > 0) ? (100.0 * g_rows[i].live_wins / g_rows[i].live_trades) : 0.0;
      double live_pf = (g_rows[i].live_gross_loss > 0.01) ? (g_rows[i].live_gross_win / g_rows[i].live_gross_loss) : 0.0;
      double bt_dd   = GetBtMaxDD(i);
      double dd_pct  = (bt_dd > 0.01) ? (100.0 * g_rows[i].live_max_dd_brl / bt_dd) : 0.0;

      FileWrite(h,
                g_rows[i].code,
                g_rows[i].strat_name,
                IntegerToString(g_rows[i].magic),
                IntegerToString(g_rows[i].open_dir),
                DoubleToString(g_rows[i].open_lots, 1),
                DoubleToString(g_rows[i].open_floating_brl, 2),
                IntegerToString(g_rows[i].pending_orders),
                IntegerToString(g_rows[i].live_trades),
                DoubleToString(live_wr, 1),
                DoubleToString(live_pf, 2),
                DoubleToString(g_rows[i].live_day_brl, 2),
                DoubleToString(g_rows[i].live_net_brl, 2),
                DoubleToString(g_rows[i].live_curr_dd_brl, 2),
                DoubleToString(g_rows[i].live_max_dd_brl, 2),
                DoubleToString(bt_dd, 2),
                DoubleToString(dd_pct, 1),
                IntegerToString(g_rows[i].live_curr_loss_streak),
                IntegerToString(g_rows[i].live_max_loss_streak),
                IntegerToString(g_rows[i].bt_max_loss_streak),
                IntegerToString(g_rows[i].bt_trades),
                DoubleToString(g_rows[i].bt_wr, 1),
                DoubleToString(g_rows[i].bt_pf, 2),
                DoubleToString(g_rows[i].bt_net_brl, 2));
     }
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| Atualiza posições abertas e ordens pendentes no MT5              |
//+------------------------------------------------------------------+
void UpdateOpenPositionsAndOrders()
  {
   for(int i = 0; i < TOTAL_ROWS; i++)
     {
      g_rows[i].open_dir          = 0;
      g_rows[i].open_lots         = 0.0;
      g_rows[i].open_price        = 0.0;
      g_rows[i].open_floating_brl = 0.0;
      g_rows[i].pending_orders    = 0;
     }

   // 1. Posições Abertas Nativas por Magic Number
   int pos_total = PositionsTotal();
   for(int p = 0; p < pos_total; p++)
     {
      ulong ticket = PositionGetTicket(p);
      if(ticket == 0)
         continue;
      ulong magic  = PositionGetInteger(POSITION_MAGIC);
      int idx      = FindRowByMagic(magic);
      if(idx < 0)
         continue;

      long ptype   = PositionGetInteger(POSITION_TYPE);
      double lots  = PositionGetDouble(POSITION_VOLUME);
      double price = PositionGetDouble(POSITION_PRICE_OPEN);
      double prof  = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);

      g_rows[idx].open_dir          = (ptype == POSITION_TYPE_BUY) ? 1 : -1;
      g_rows[idx].open_lots        += lots;
      g_rows[idx].open_price        = price;
      g_rows[idx].open_floating_brl+= prof;
     }

   // 2. Ordens Pendentes Nativas por Magic Number
   int ord_total = OrdersTotal();
   for(int o = 0; o < ord_total; o++)
     {
      ulong ticket = OrderGetTicket(o);
      if(ticket == 0)
         continue;
      ulong magic  = OrderGetInteger(ORDER_MAGIC);
      int idx      = FindRowByMagic(magic);
      if(idx < 0)
         continue;
      g_rows[idx].pending_orders++;
     }

   // 3. Consolida Subtotais de Posições Abertas e Ordens
   for(int i = 0; i < TOTAL_MONITORED_ROBOTS; i++)
     {
      int sum_idx = g_rows[i].is_wdo ? IDX_SUMMARY_WDO : IDX_SUMMARY_WIN;
      if(g_rows[i].open_dir != 0)
        {
         g_rows[sum_idx].open_dir               += g_rows[i].open_dir;
         g_rows[sum_idx].open_lots              += g_rows[i].open_lots;
         g_rows[sum_idx].open_floating_brl      += g_rows[i].open_floating_brl;

         g_rows[IDX_SUMMARY_PORTFOLIO].open_dir += g_rows[i].open_dir;
         g_rows[IDX_SUMMARY_PORTFOLIO].open_lots+= g_rows[i].open_lots;
         g_rows[IDX_SUMMARY_PORTFOLIO].open_floating_brl += g_rows[i].open_floating_brl;
        }
      g_rows[sum_idx].pending_orders               += g_rows[i].pending_orders;
      g_rows[IDX_SUMMARY_PORTFOLIO].pending_orders += g_rows[i].pending_orders;
     }
  }

//+------------------------------------------------------------------+
//| Registra um trade fechado em uma linha específica (Robô/Subtotal)|
//+------------------------------------------------------------------+
void ApplyClosedDealToRow(int idx, double net_pnl, datetime deal_time, datetime today_start)
  {
   g_rows[idx].live_trades++;
   g_rows[idx].live_net_brl += net_pnl;
   if(deal_time >= today_start)
      g_rows[idx].live_day_brl += net_pnl;
   if(deal_time > g_rows[idx].last_trade_time)
      g_rows[idx].last_trade_time = deal_time;

   if(net_pnl > 0.001)
     {
      g_rows[idx].live_wins++;
      g_rows[idx].live_gross_win += net_pnl;
      g_rows[idx].live_curr_loss_streak = 0;
     }
   else if(net_pnl < -0.001)
     {
      g_rows[idx].live_losses++;
      g_rows[idx].live_gross_loss += MathAbs(net_pnl);
      g_rows[idx].live_curr_loss_streak++;
      if(g_rows[idx].live_curr_loss_streak > g_rows[idx].live_max_loss_streak)
         g_rows[idx].live_max_loss_streak = g_rows[idx].live_curr_loss_streak;
     }

   if(g_rows[idx].live_net_brl > g_rows[idx].live_peak_brl)
      g_rows[idx].live_peak_brl = g_rows[idx].live_net_brl;

   double dd = g_rows[idx].live_peak_brl - g_rows[idx].live_net_brl;
   if(dd < 0.0)
      dd = 0.0;
   g_rows[idx].live_curr_dd_brl = dd;
   if(dd > g_rows[idx].live_max_dd_brl)
      g_rows[idx].live_max_dd_brl = dd;
  }

//+------------------------------------------------------------------+
//| Atualiza histórico de trades fechados, MaxDD Live e Loss Streak  |
//+------------------------------------------------------------------+
void UpdateTradeHistoryAndMetrics()
  {
   // Preserva recordes históricos já carregados do disco antes de recalcular
   double prev_max_dd[TOTAL_ROWS];
   int    prev_max_streak[TOTAL_ROWS];
   for(int i = 0; i < TOTAL_ROWS; i++)
     {
      prev_max_dd[i]     = g_rows[i].live_max_dd_brl;
      prev_max_streak[i] = g_rows[i].live_max_loss_streak;

      g_rows[i].live_trades           = 0;
      g_rows[i].live_wins             = 0;
      g_rows[i].live_losses           = 0;
      g_rows[i].live_gross_win        = 0.0;
      g_rows[i].live_gross_loss       = 0.0;
      g_rows[i].live_net_brl          = 0.0;
      g_rows[i].live_day_brl          = 0.0;
      g_rows[i].live_peak_brl         = 0.0;
      g_rows[i].live_curr_dd_brl      = 0.0;
      g_rows[i].live_curr_loss_streak = 0;
      g_rows[i].last_trade_time       = 0;
     }

   MqlDateTime dt_now;
   TimeCurrent(dt_now);
   dt_now.hour = 0;
   dt_now.min  = 0;
   dt_now.sec  = 0;
   datetime today_start = StructToTime(dt_now);

   int native_matched_deals = 0;
   if(InpHistorySource != HIST_AUDIT_CSV_ONLY && HistorySelect(InpHistoryStartDate, TimeCurrent() + 86400))
     {
      int total_deals = HistoryDealsTotal();
      for(int d = 0; d < total_deals; d++)
        {
         ulong ticket = HistoryDealGetTicket(d);
         if(ticket == 0)
            continue;

         long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
         if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT && entry != DEAL_ENTRY_OUT_BY)
            continue;

         ulong magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
         int idx     = FindRowByMagic(magic);
         if(idx < 0)
            continue;

         double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT)
                       + HistoryDealGetDouble(ticket, DEAL_SWAP)
                       + HistoryDealGetDouble(ticket, DEAL_COMMISSION)
                       + HistoryDealGetDouble(ticket, DEAL_FEE);
         datetime dtime = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
         if(InpResetReplacedSlots && dtime < g_rows[idx].valid_from)
            continue;
         native_matched_deals++;

         // Aplica ao Robô Individual
         ApplyClosedDealToRow(idx, profit, dtime, today_start);

         // Aplica ao Subtotal (WIN ou WDO)
         int sum_idx = g_rows[idx].is_wdo ? IDX_SUMMARY_WDO : IDX_SUMMARY_WIN;
         ApplyClosedDealToRow(sum_idx, profit, dtime, today_start);

         // Aplica ao Portfólio Geral (18 Robôs)
         ApplyClosedDealToRow(IDX_SUMMARY_PORTFOLIO, profit, dtime, today_start);
        }
     }

   // Fallback / Modo Netting: Lê magicwalls_live_trades_audit_<Login>.csv se não houver deals por Magic individual
   if(InpHistorySource == HIST_AUDIT_CSV_ONLY || (InpHistorySource == HIST_AUTO_HYBRID && native_matched_deals == 0))
     {
      string audit_fn = StringFormat("magicwalls_live_trades_audit_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
      if(FileIsExist(audit_fn, FILE_COMMON))
        {
         int ha = FileOpen(audit_fn, FILE_COMMON | FILE_READ | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_TXT | FILE_ANSI);
         if(ha != INVALID_HANDLE)
           {
            while(!FileIsEnding(ha))
              {
               string line = FileReadString(ha);
               if(StringLen(line) < 10)
                  continue;
               string cols[];
               int n_cols = StringSplit(line, ';', cols);
               if(n_cols >= 9)
                 {
                  datetime dtime = StringToTime(cols[0]);
                  if(dtime < InpHistoryStartDate)
                     continue;
                  ulong magic   = (ulong)StringToInteger(cols[2]);
                  double profit = StringToDouble(cols[8]);
                  int idx       = FindRowByMagic(magic);
                  if(idx >= 0)
                    {
                     if(InpResetReplacedSlots && dtime < g_rows[idx].valid_from)
                        continue;
                     ApplyClosedDealToRow(idx, profit, dtime, today_start);
                     int sum_idx = g_rows[idx].is_wdo ? IDX_SUMMARY_WDO : IDX_SUMMARY_WIN;
                     ApplyClosedDealToRow(sum_idx, profit, dtime, today_start);
                     ApplyClosedDealToRow(IDX_SUMMARY_PORTFOLIO, profit, dtime, today_start);
                    }
                 }
              }
            FileClose(ha);
           }
        }
     }

   // Incorpora PnL flutuante aberto (se habilitado) e restaura recordes persistidos
   for(int i = 0; i < TOTAL_ROWS; i++)
     {
      if(InpIncludeFloatingDD && g_rows[i].open_dir != 0)
        {
         double eq_now = g_rows[i].live_net_brl + g_rows[i].open_floating_brl;
         if(eq_now > g_rows[i].live_peak_brl)
            g_rows[i].live_peak_brl = eq_now;
         double float_dd = g_rows[i].live_peak_brl - eq_now;
         if(float_dd > g_rows[i].live_curr_dd_brl)
            g_rows[i].live_curr_dd_brl = float_dd;
         if(float_dd > g_rows[i].live_max_dd_brl)
            g_rows[i].live_max_dd_brl = float_dd;
        }

      if(prev_max_dd[i] > g_rows[i].live_max_dd_brl)
         g_rows[i].live_max_dd_brl = prev_max_dd[i];
      if(prev_max_streak[i] > g_rows[i].live_max_loss_streak)
         g_rows[i].live_max_loss_streak = prev_max_streak[i];

      // Verifica Alertas de Violação do Backtest
      double bt_dd = GetBtMaxDD(i);
      if(InpAlertOnBtBreach)
        {
         if(bt_dd > 0.0 && g_rows[i].live_max_dd_brl > bt_dd && !g_rows[i].alerted_dd)
           {
            g_rows[i].alerted_dd = true;
            Alert(StringFormat("[MAGIC WALLS MONITOR] ALERTA MAX DD: %s (%s) atingiu R$ %.0f no Live (> BT R$ %.0f)!",
                               g_rows[i].code, g_rows[i].strat_name, g_rows[i].live_max_dd_brl, bt_dd));
           }
         if(g_rows[i].bt_max_loss_streak > 0 && g_rows[i].live_curr_loss_streak > g_rows[i].bt_max_loss_streak && !g_rows[i].alerted_streak)
           {
            g_rows[i].alerted_streak = true;
            Alert(StringFormat("[MAGIC WALLS MONITOR] ALERTA LOSS STREAK: %s (%s) atingiu %d losses seguidos no Live (> BT %d)!",
                               g_rows[i].code, g_rows[i].strat_name, g_rows[i].live_curr_loss_streak, g_rows[i].bt_max_loss_streak));
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Helper para criar/atualizar Retângulo no Gráfico                 |
//+------------------------------------------------------------------+
void UpsertRect(string name, int x, int y, int w, int h, color bg_color, color border_color)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg_color);
   ObjectSetInteger(0, name, OBJPROP_COLOR, border_color);
  }

//+------------------------------------------------------------------+
//| Helper para criar/atualizar Label de Texto no Gráfico            |
//+------------------------------------------------------------------+
void UpsertLabel(string name, int x, int y, string text, color clr, int font_size, string font_name = "Consolas")
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, font_size);
   ObjectSetString(0, name, OBJPROP_FONT, font_name);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
  }

//+------------------------------------------------------------------+
//| Renderiza o Painel Completo no Gráfico                           |
//+------------------------------------------------------------------+
void RenderDashboardPanel()
  {
   int x0    = InpPanelX;
   int y0    = InpPanelY;
   int row_h = InpFontSize + 10;
   int hdr_h = 66;
   int tbl_w = 1170;
   int tbl_h = hdr_h + (TOTAL_ROWS + 2) * row_h + 14;

   color hdr_bd = C'45,65,90';
   if(g_stop_global_hit)
      hdr_bd = C'255,75,75';
   else if(g_stop_win_hit || g_stop_wdo_hit)
      hdr_bd = C'255,180,60';

   // Fundo Principal
   UpsertRect(g_prefix + "BG_MAIN", x0, y0, tbl_w, tbl_h, C'15,20,28', C'55,70,95');
   UpsertRect(g_prefix + "BG_HDR",  x0 + 2, y0 + 2, tbl_w - 4, hdr_h - 4, C'22,32,46', hdr_bd);

   // Labels divididos em Esquerda/Direita (<60 chars cada) para nunca truncar no limite de 63 chars do MT5
   string dd_mode_str = (InpBtDdReference == BT_DD_BY_DAY) ? "DD Diario 2026" : "DD Trade 2026";
   string title_l = "MAGIC WALLS MONITOR LIVE vs BT | PORTFOLIO ELITE (10 ROBOS)";
   string title_r = StringFormat("Ref BT: %s | Atualizado: %s",
                                 dd_mode_str, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));
   UpsertLabel(g_prefix + "LBL_TITLE",   x0 + 10,  y0 + 6, title_l, C'100,210,255', InpFontSize + 1);
   UpsertLabel(g_prefix + "LBL_TITLE_R", x0 + 575, y0 + 6, title_r, C'155,215,245', InpFontSize);

   string sub_l = StringFormat("Conta: %I64d | Hoje: R$ %+.0f | Acum Live: R$ %+.0f",
                               AccountInfoInteger(ACCOUNT_LOGIN),
                               g_rows[IDX_SUMMARY_PORTFOLIO].live_day_brl + g_rows[IDX_SUMMARY_PORTFOLIO].open_floating_brl,
                               g_rows[IDX_SUMMARY_PORTFOLIO].live_net_brl);
   string sub_r = StringFormat("DD Atu/Max: R$ %.0f/%.0f (BT %.0f) | Streak: %d/%d (BT %d)",
                               g_rows[IDX_SUMMARY_PORTFOLIO].live_curr_dd_brl,
                               g_rows[IDX_SUMMARY_PORTFOLIO].live_max_dd_brl,
                               GetBtMaxDD(IDX_SUMMARY_PORTFOLIO),
                               g_rows[IDX_SUMMARY_PORTFOLIO].live_curr_loss_streak,
                               g_rows[IDX_SUMMARY_PORTFOLIO].live_max_loss_streak,
                               g_rows[IDX_SUMMARY_PORTFOLIO].bt_max_loss_streak);
   UpsertLabel(g_prefix + "LBL_SUBTITLE",   x0 + 10,  y0 + 24, sub_l, C'220,230,242', InpFontSize);
   UpsertLabel(g_prefix + "LBL_SUBTITLE_R", x0 + 575, y0 + 24, sub_r, C'220,230,242', InpFontSize);

   // 3a Linha: Barra de Stop Diário Máximo em Tempo Real
   string stop_badge = "OK";
   color  stop_clr   = C'90,235,145';
   if(!InpEnableDailyStop)
     {
      stop_badge = "DESATIVADO";
      stop_clr   = C'150,165,180';
     }
   else if(g_stop_global_hit)
     {
      stop_badge = "TRAVA GLOBAL";
      stop_clr   = C'255,85,85';
     }
   else if(g_stop_win_hit && g_stop_wdo_hit)
     {
      stop_badge = "TRAVA WIN+WDO";
      stop_clr   = C'255,85,85';
     }
   else if(g_stop_win_hit)
     {
      stop_badge = "TRAVA WIN";
      stop_clr   = C'255,195,85';
     }
   else if(g_stop_wdo_hit)
     {
      stop_badge = "TRAVA WDO";
      stop_clr   = C'255,195,85';
     }
   else if(IsInAuctionBlockWindow())
     {
      stop_badge = "PAUSA LEILAO";
      stop_clr   = C'255,210,90';
     }
   else if(g_warn_global_sent || g_warn_win_sent || g_warn_wdo_sent)
     {
      stop_badge = StringFormat("ALERTA >=%.0f%%", InpStopWarningPct);
      stop_clr   = C'255,205,85';
     }

   double pct_glob = (InpMaxDailyLossGlobal > 0.0 && g_day_total_global < 0.0) ? (100.0 * MathAbs(g_day_total_global) / InpMaxDailyLossGlobal) : 0.0;
   string str_glob = (InpMaxDailyLossGlobal > 0.0)
                     ? StringFormat("R$ %+.0f / -R$ %.0f (%.0f%%)", g_day_total_global, InpMaxDailyLossGlobal, pct_glob)
                     : StringFormat("R$ %+.0f (OFF)", g_day_total_global);
   string str_win  = (InpMaxDailyLossWin > 0.0)
                     ? StringFormat("%+.0f/-%.0f", g_day_total_win, InpMaxDailyLossWin)
                     : StringFormat("%+.0f(OFF)", g_day_total_win);
   string str_wdo  = (InpMaxDailyLossWdo > 0.0)
                     ? StringFormat("%+.0f/-%.0f", g_day_total_wdo, InpMaxDailyLossWdo)
                     : StringFormat("%+.0f(OFF)", g_day_total_wdo);
   string stop_l = StringFormat("STOP DIARIO [%s] | GLOBAL: %s", stop_badge, str_glob);
   string stop_r = StringFormat("WIN: %s | WDO: %s | MAE G/W/D: %.0f/%.0f/%.0f",
                                str_win, str_wdo,
                                g_day_mae_global, g_day_mae_win, g_day_mae_wdo);
   UpsertLabel(g_prefix + "LBL_STOPBAR",   x0 + 10,  y0 + 43, stop_l, stop_clr, InpFontSize);
   UpsertLabel(g_prefix + "LBL_STOPBAR_R", x0 + 575, y0 + 43, stop_r, stop_clr, InpFontSize);

   // Posições X das Colunas
   int cx_code   = x0 + 10;
   int cx_name   = x0 + 75;
   int cx_magic  = x0 + 255;
   int cx_pos    = x0 + 315;
   int cx_trades = x0 + 445;
   int cx_wr     = x0 + 545;
   int cx_pnl    = x0 + 645;
   int cx_dd     = x0 + 795;
   int cx_streak = x0 + 955;
   int cx_status = x0 + 1085;

   int y_col = y0 + hdr_h + 2;
   UpsertRect(g_prefix + "BG_COLHDR", x0 + 4, y_col - 2, tbl_w - 8, row_h, C'30,42,58', C'50,65,85');
   UpsertLabel(g_prefix + "CH_CODE",   cx_code,   y_col, "SLOT",                  C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_NAME",   cx_name,   y_col, "ESTRATEGIA",            C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_MAGIC",  cx_magic,  y_col, "MAGIC",                 C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_POS",    cx_pos,    y_col, "POSICAO / ORD",         C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_TR",     cx_trades, y_col, "TR (LIVE/BT)",          C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_WR",     cx_wr,     y_col, "WR% (LIVE/BT)",         C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_PNL",    cx_pnl,    y_col, "HOJE / ACUM (BT)",      C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_DD",     cx_dd,     y_col, "DD ATU/MAX (BT)",       C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_STRK",   cx_streak, y_col, "LOSS ATU/MAX(BT)",      C'165,185,210', InpFontSize);
   UpsertLabel(g_prefix + "CH_STAT",   cx_status, y_col, "SAUDE",                 C'165,185,210', InpFontSize);

   for(int i = 0; i < TOTAL_ROWS; i++)
     {
      int y_row = y_col + (i + 1) * row_h + (i >= IDX_SUMMARY_WIN ? 4 : 0);
      bool is_sum = (i >= IDX_SUMMARY_WIN);

      color row_bg = is_sum ? C'28,40,56' : ((i % 2 == 0) ? C'18,25,35' : C'22,30,42');
      color row_bd = is_sum ? C'65,90,120' : row_bg;
      UpsertRect(StringFormat("%sR_BG_%d", g_prefix, i), x0 + 4, y_row - 2, tbl_w - 8, row_h, row_bg, row_bd);

      // 1. Código e Nome
      color code_clr = is_sum ? C'255,215,90' : (g_rows[i].is_wdo ? C'120,220,255' : C'150,245,170');
      UpsertLabel(StringFormat("%sR_CD_%d", g_prefix, i), cx_code, y_row, g_rows[i].code, code_clr, InpFontSize);
      UpsertLabel(StringFormat("%sR_NM_%d", g_prefix, i), cx_name, y_row, g_rows[i].strat_name, C'225,232,240', InpFontSize);

      // 2. Magic
      string magic_str = (g_rows[i].magic > 0) ? IntegerToString(g_rows[i].magic) : "---";
      UpsertLabel(StringFormat("%sR_MG_%d", g_prefix, i), cx_magic, y_row, magic_str, C'145,160,180', InpFontSize);

      // 3. Posição Aberta / Ordem Pendente
      string pos_str = "FLAT";
      color  pos_clr = C'125,140,160';
      if(g_rows[i].open_dir != 0 || (is_sum && g_rows[i].open_lots > 0.0))
        {
         string dir_lbl = is_sum ? "NET" : ((g_rows[i].open_dir > 0) ? "BUY" : "SELL");
         pos_str = StringFormat("%s %.0f (R$%+.0f)", dir_lbl, g_rows[i].open_lots, g_rows[i].open_floating_brl);
         pos_clr = (g_rows[i].open_floating_brl >= 0.0) ? C'80,245,140' : C'255,105,105';
        }
      else if(g_rows[i].pending_orders > 0)
        {
         pos_str = StringFormat("PEND (%d)", g_rows[i].pending_orders);
         pos_clr = C'255,210,90';
        }
      UpsertLabel(StringFormat("%sR_PS_%d", g_prefix, i), cx_pos, y_row, pos_str, pos_clr, InpFontSize);

      // 4. Trades (Live / BT)
      string tr_str = StringFormat("%d / %d", g_rows[i].live_trades, g_rows[i].bt_trades);
      UpsertLabel(StringFormat("%sR_TR_%d", g_prefix, i), cx_trades, y_row, tr_str, C'215,225,235', InpFontSize);

      // 5. Win Rate (Live / BT)
      double live_wr = (g_rows[i].live_trades > 0) ? (100.0 * g_rows[i].live_wins / g_rows[i].live_trades) : 0.0;
      string wr_str  = (g_rows[i].live_trades > 0)
                       ? StringFormat("%.0f%% / %.0f%%", live_wr, g_rows[i].bt_wr)
                       : StringFormat("-- / %.0f%%", g_rows[i].bt_wr);
      color wr_clr   = (g_rows[i].live_trades == 0) ? C'150,165,180'
                       : ((live_wr >= g_rows[i].bt_wr - 5.0) ? C'110,235,155' : C'255,195,95');
      UpsertLabel(StringFormat("%sR_WR_%d", g_prefix, i), cx_wr, y_row, wr_str, wr_clr, InpFontSize);

      // 6. PnL Hoje / Acumulado Live (e BT Net em milhar)
      string pnl_str = StringFormat("%+.0f / %+.0f (%.1fk)",
                                    g_rows[i].live_day_brl,
                                    g_rows[i].live_net_brl,
                                    g_rows[i].bt_net_brl / 1000.0);
      color pnl_clr  = (g_rows[i].live_net_brl > 0.0) ? C'95,240,145'
                       : ((g_rows[i].live_net_brl < 0.0) ? C'255,110,110' : C'175,185,200');
      UpsertLabel(StringFormat("%sR_PNL_%d", g_prefix, i), cx_pnl, y_row, pnl_str, pnl_clr, InpFontSize);

      // 7. Drawdown Atual / MaxDD Live vs MaxDD BT
      double bt_dd  = GetBtMaxDD(i);
      double dd_pct = (bt_dd > 0.0) ? (100.0 * g_rows[i].live_max_dd_brl / bt_dd) : 0.0;
      string dd_str = StringFormat("%.0f / %.0f (%.0f)",
                                   g_rows[i].live_curr_dd_brl,
                                   g_rows[i].live_max_dd_brl,
                                   bt_dd);
      color dd_clr  = C'115,235,155';
      if(dd_pct >= 100.0)
         dd_clr = C'255,85,85';
      else if(dd_pct >= 75.0)
         dd_clr = C'255,205,85';
      UpsertLabel(StringFormat("%sR_DD_%d", g_prefix, i), cx_dd, y_row, dd_str, dd_clr, InpFontSize);

      // 8. Sequência de Loss Atual / Max Loss Streak Live vs BT
      string strk_str = StringFormat("%d / %d (%d)",
                                     g_rows[i].live_curr_loss_streak,
                                     g_rows[i].live_max_loss_streak,
                                     g_rows[i].bt_max_loss_streak);
      bool active_strk_breach = (g_rows[i].bt_max_loss_streak > 0 && g_rows[i].live_curr_loss_streak > g_rows[i].bt_max_loss_streak);
      bool past_strk_breach   = (g_rows[i].bt_max_loss_streak > 0 && g_rows[i].live_max_loss_streak > g_rows[i].bt_max_loss_streak && !active_strk_breach);

      color strk_clr  = C'115,235,155';
      if(active_strk_breach)
         strk_clr = C'255,85,85';
      else if(past_strk_breach || (g_rows[i].live_curr_loss_streak == g_rows[i].bt_max_loss_streak && g_rows[i].bt_max_loss_streak > 0))
         strk_clr = C'255,205,85';
      UpsertLabel(StringFormat("%sR_SK_%d", g_prefix, i), cx_streak, y_row, strk_str, strk_clr, InpFontSize);

      // 9. Saúde / Alerta
      string st_str = "OK";
      color  st_clr = C'90,235,145';
      bool dd_breach = (bt_dd > 0.0 && g_rows[i].live_max_dd_brl > bt_dd);
      if(dd_breach && active_strk_breach)
        {
         st_str = "DD+STRK>BT!";
         st_clr = C'255,75,75';
        }
      else if(dd_breach)
        {
         st_str = "MAXDD > BT!";
         st_clr = C'255,85,85';
        }
      else if(active_strk_breach)
        {
         st_str = "STREAK>BT!";
         st_clr = C'255,85,85';
        }
      else if(dd_pct >= 80.0 || (g_rows[i].bt_max_loss_streak > 0 && g_rows[i].live_curr_loss_streak >= g_rows[i].bt_max_loss_streak))
        {
         st_str = "ATENCAO";
         st_clr = C'255,205,85';
        }
      else if(past_strk_breach)
        {
         st_str = "OK (RECUP)";
         st_clr = C'115,235,155';
        }
      UpsertLabel(StringFormat("%sR_ST_%d", g_prefix, i), cx_status, y_row, st_str, st_clr, InpFontSize);
     }

   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Exporta todos os deals das EAs Magic Walls (88001-88016 / 89001-89016) |
//| para magicwalls_live_deals_<Login>.csv em FILE_COMMON.                |
//| Usado pelo Calendário do Live Trading do dashboard (server.py).  |
//+------------------------------------------------------------------+
int      g_deals_exported_total = -1;
datetime g_deals_exported_at    = 0;

bool IsMwMagic(ulong magic)
  {
   if(FindRowByMagic(magic) >= 0)
      return true;
   if(magic >= InpWinBaseMagic + 1 && magic <= InpWinBaseMagic + 16)
      return true;
   if(magic >= InpWdoBaseMagic + 1 && magic <= InpWdoBaseMagic + 16)
      return true;
   return false;
  }

void ExportLiveDealsHistory(bool force = false)
  {
   if(!HistorySelect(InpHistoryStartDate, TimeCurrent() + 86400))
      return;
   int total = HistoryDealsTotal();
   // Só regrava quando entrar deal novo (ou a cada 5 min como segurança)
   if(!force && total == g_deals_exported_total && TimeCurrent() - g_deals_exported_at < 300)
      return;

   // 1ª passada: posições abertas por EAs Magic Walls (para incluir saídas manuais com magic 0)
   ulong mw_pos[];
   int n_pos = 0;
   for(int d = 0; d < total; d++)
     {
      ulong tk = HistoryDealGetTicket(d);
      if(tk == 0)
         continue;
      if(IsMwMagic((ulong)HistoryDealGetInteger(tk, DEAL_MAGIC)))
        {
         ArrayResize(mw_pos, n_pos + 1, 256);
         mw_pos[n_pos++] = (ulong)HistoryDealGetInteger(tk, DEAL_POSITION_ID);
        }
     }

   string fname = StringFormat("magicwalls_live_deals_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
   int h = FileOpen(fname, FILE_COMMON | FILE_WRITE | FILE_SHARE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, "time;ticket;position_id;magic;symbol;type;entry;volume;price;profit;swap;commission;fee;reason;comment\r\n");
   for(int d = 0; d < total; d++)
     {
      ulong tk = HistoryDealGetTicket(d);
      if(tk == 0)
         continue;
      long type = HistoryDealGetInteger(tk, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL)
         continue;
      ulong magic  = (ulong)HistoryDealGetInteger(tk, DEAL_MAGIC);
      ulong pos_id = (ulong)HistoryDealGetInteger(tk, DEAL_POSITION_ID);
      bool ok = IsMwMagic(magic);
      if(!ok)
         for(int k = 0; k < n_pos; k++)
            if(mw_pos[k] == pos_id) { ok = true; break; }
      if(!ok)
         continue;
      string cm = HistoryDealGetString(tk, DEAL_COMMENT);
      StringReplace(cm, ";", ",");
      FileWriteString(h, StringFormat("%s;%I64u;%I64u;%I64u;%s;%d;%d;%.2f;%.5f;%.2f;%.2f;%.2f;%.2f;%d;%s\r\n",
                      TimeToString((datetime)HistoryDealGetInteger(tk, DEAL_TIME), TIME_DATE | TIME_SECONDS),
                      tk, pos_id, magic, HistoryDealGetString(tk, DEAL_SYMBOL),
                      (int)type, (int)HistoryDealGetInteger(tk, DEAL_ENTRY),
                      HistoryDealGetDouble(tk, DEAL_VOLUME), HistoryDealGetDouble(tk, DEAL_PRICE),
                      HistoryDealGetDouble(tk, DEAL_PROFIT), HistoryDealGetDouble(tk, DEAL_SWAP),
                      HistoryDealGetDouble(tk, DEAL_COMMISSION), HistoryDealGetDouble(tk, DEAL_FEE),
                      (int)HistoryDealGetInteger(tk, DEAL_REASON), cm));
     }
   FileClose(h);
   g_deals_exported_total = total;
   g_deals_exported_at    = TimeCurrent();
  }

//+------------------------------------------------------------------+
//| GERENCIA DE STOP DIARIO MAXIMO (GLOBAL + WIN + WDO)              |
//+------------------------------------------------------------------+
datetime SafeNow()
  {
   datetime t = TimeCurrent();
   return (t > 0) ? t : TimeLocal();
  }

double TodayDateKey()
  {
   MqlDateTime dt;
   TimeToStruct(SafeNow(), dt);
   return (double)(dt.year * 10000 + dt.mon * 100 + dt.day);
  }

datetime TodayStartDatetime()
  {
   MqlDateTime dt;
   TimeToStruct(SafeNow(), dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt);
  }

int ParseHHMMSeconds(const string hhmm)
  {
   if(StringLen(hhmm) < 5)
      return -1;
   int h = (int)StringToInteger(StringSubstr(hhmm, 0, 2));
   int m = (int)StringToInteger(StringSubstr(hhmm, 3, 2));
   return h * 3600 + m * 60;
  }

bool IsTimeInWindow(int now_sec, const string from_s, const string to_s)
  {
   int w_from = ParseHHMMSeconds(from_s);
   int w_to   = ParseHHMMSeconds(to_s);
   if(w_from < 0 || w_to < 0)
      return false;
   if(w_from <= w_to)
      return (now_sec >= w_from && now_sec <= w_to);
   return (now_sec >= w_from || now_sec <= w_to);
  }

bool IsInAuctionBlockWindow()
  {
   if(!InpUseAuctionFilter)
      return false;
   MqlDateTime dt;
   TimeToStruct(SafeNow(), dt);
   int now_sec = dt.hour * 3600 + dt.min * 60 + dt.sec;
   if(IsTimeInWindow(now_sec, InpBlockFrom1, InpBlockTo1))
      return true;
   if(IsTimeInWindow(now_sec, InpBlockFrom2, InpBlockTo2))
      return true;
   return false;
  }

// Retorna 0 = fora do escopo, 1 = WIN, 2 = WDO
int ClassifyMwMagic(ulong magic)
  {
   if(!InpIncludeAllMwMagics)
     {
      int idx = FindRowByMagic(magic);
      if(idx < 0)
         return 0;
      return g_rows[idx].is_wdo ? 2 : 1;
     }
   if(magic >= InpWinBaseMagic && magic <= InpWinBaseMagic + 16)
      return 1;
   if(magic >= InpWdoBaseMagic && magic <= InpWdoBaseMagic + 16)
      return 2;
   return 0;
  }

void SyncDailyStopGvFlag(const string gv_name, double today_key, bool &hit_flag)
  {
   if(!GlobalVariableCheck(gv_name))
      return;
   double val = GlobalVariableGet(gv_name);
   if(MathAbs(val - today_key) < 0.5)
      hit_flag = true;
   else if(val > 0.0 && MathAbs(val - today_key) >= 0.5)
      GlobalVariableDel(gv_name);
  }

void ResetDailyStopIfNewDay()
  {
   double today_key = TodayDateKey();
   if(MathAbs(today_key - g_stop_day_key) < 0.5)
      return;

   g_stop_day_key     = today_key;
   g_stop_global_hit  = false;
   g_stop_win_hit     = false;
   g_stop_wdo_hit     = false;
   g_warn_global_sent = false;
   g_warn_win_sent    = false;
   g_warn_wdo_sent    = false;
   g_day_mae_win      = 0.0;
   g_day_mae_wdo      = 0.0;
   g_day_mae_global   = 0.0;

   SyncDailyStopGvFlag("MW_DAILY_STOP_GLOBAL", today_key, g_stop_global_hit);
   SyncDailyStopGvFlag("MW_DAILY_STOP_WIN",    today_key, g_stop_win_hit);
   SyncDailyStopGvFlag("MW_DAILY_STOP_WDO",    today_key, g_stop_wdo_hit);
  }

void ComputeTodayStopMetrics()
  {
   g_day_closed_win = 0.0;
   g_day_closed_wdo = 0.0;
   g_day_float_win  = 0.0;
   g_day_float_wdo  = 0.0;

   datetime now_t       = SafeNow();
   datetime today_start = TodayStartDatetime();

   // 1. P&L Fechado de Hoje por Ativo (inclui saídas manuais via POSITION_ID)
   if(HistorySelect(today_start - 7 * 86400, now_t + 86400))
     {
      int total = HistoryDealsTotal();
      ulong pos_win[];
      ulong pos_wdo[];
      int nw = 0;
      int nd = 0;

      for(int d = 0; d < total; d++)
        {
         ulong tk = HistoryDealGetTicket(d);
         if(tk == 0)
            continue;
         int cls = ClassifyMwMagic((ulong)HistoryDealGetInteger(tk, DEAL_MAGIC));
         if(cls == 0)
            continue;
         ulong pid = (ulong)HistoryDealGetInteger(tk, DEAL_POSITION_ID);
         if(pid == 0)
            continue;
         if(cls == 1)
           {
            ArrayResize(pos_win, nw + 1, 64);
            pos_win[nw++] = pid;
           }
         else
           {
            ArrayResize(pos_wdo, nd + 1, 64);
            pos_wdo[nd++] = pid;
           }
        }

      for(int d = 0; d < total; d++)
        {
         ulong tk = HistoryDealGetTicket(d);
         if(tk == 0)
            continue;
         datetime dtime = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
         if(dtime < today_start)
            continue;
         long entry = HistoryDealGetInteger(tk, DEAL_ENTRY);
         if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT && entry != DEAL_ENTRY_OUT_BY)
            continue;

         ulong magic = (ulong)HistoryDealGetInteger(tk, DEAL_MAGIC);
         int cls = ClassifyMwMagic(magic);
         if(cls == 0)
           {
            ulong pid = (ulong)HistoryDealGetInteger(tk, DEAL_POSITION_ID);
            for(int k = 0; k < nw; k++)
               if(pos_win[k] == pid) { cls = 1; break; }
            if(cls == 0)
               for(int k = 0; k < nd; k++)
                  if(pos_wdo[k] == pid) { cls = 2; break; }
           }
         if(cls == 0)
            continue;

         double net = HistoryDealGetDouble(tk, DEAL_PROFIT)
                    + HistoryDealGetDouble(tk, DEAL_SWAP)
                    + HistoryDealGetDouble(tk, DEAL_COMMISSION)
                    + HistoryDealGetDouble(tk, DEAL_FEE);
         if(cls == 1)
            g_day_closed_win += net;
         else
            g_day_closed_wdo += net;
        }
     }

   // 2. P&L Flutuante Aberto por Ativo
   for(int p = 0; p < PositionsTotal(); p++)
     {
      ulong tk = PositionGetTicket(p);
      if(tk == 0)
         continue;
      int cls = ClassifyMwMagic((ulong)PositionGetInteger(POSITION_MAGIC));
      if(cls == 0)
         continue;
      double fl = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      if(cls == 1)
         g_day_float_win += fl;
      else
         g_day_float_wdo += fl;
     }

   g_day_total_win    = g_day_closed_win + g_day_float_win;
   g_day_total_wdo    = g_day_closed_wdo + g_day_float_wdo;
   g_day_total_global = g_day_total_win + g_day_total_wdo;

   g_day_mae_win    = MathMax(g_day_mae_win,    MathMax(0.0, -g_day_total_win));
   g_day_mae_wdo    = MathMax(g_day_mae_wdo,    MathMax(0.0, -g_day_total_wdo));
   g_day_mae_global = MathMax(g_day_mae_global, MathMax(0.0, -g_day_total_global));
  }

// target_scope: 0=ALL, 1=WIN, 2=WDO
int CloseAndCancelScope(int target_scope)
  {
   int ops = 0;
   if(InpCancelPendingOnStop)
     {
      for(int o = OrdersTotal() - 1; o >= 0; o--)
        {
         ulong ot = OrderGetTicket(o);
         if(ot == 0)
            continue;
         int cls = ClassifyMwMagic((ulong)OrderGetInteger(ORDER_MAGIC));
         if(cls == 0 || (target_scope != 0 && cls != target_scope))
            continue;
         if(g_trade.OrderDelete(ot))
            ops++;
         else
            PrintFormat("[DAILY STOP] Erro ao cancelar ordem #%I64u (ret=%u)", ot, g_trade.ResultRetcode());
        }
     }

   if(InpClosePositionsOnStop)
     {
      g_trade.SetDeviationInPoints(50);
      for(int p = PositionsTotal() - 1; p >= 0; p--)
        {
         ulong pt = PositionGetTicket(p);
         if(pt == 0)
            continue;
         ulong pmagic = (ulong)PositionGetInteger(POSITION_MAGIC);
         int cls = ClassifyMwMagic(pmagic);
         if(cls == 0 || (target_scope != 0 && cls != target_scope))
            continue;
         g_trade.SetExpertMagicNumber((long)pmagic);
         if(g_trade.PositionClose(pt))
            ops++;
         else
            PrintFormat("[DAILY STOP] Erro ao fechar posicao #%I64u magic=%I64u (ret=%u)", pt, pmagic, g_trade.ResultRetcode());
        }
     }
   return ops;
  }

bool HasOpenOrPendingInScope(int target_scope)
  {
   if(InpClosePositionsOnStop)
     {
      for(int p = PositionsTotal() - 1; p >= 0; p--)
        {
         ulong pt = PositionGetTicket(p);
         if(pt == 0)
            continue;
         int cls = ClassifyMwMagic((ulong)PositionGetInteger(POSITION_MAGIC));
         if(cls != 0 && (target_scope == 0 || cls == target_scope))
            return true;
        }
     }
   if(InpCancelPendingOnStop)
     {
      for(int o = OrdersTotal() - 1; o >= 0; o--)
        {
         ulong ot = OrderGetTicket(o);
         if(ot == 0)
            continue;
         int cls = ClassifyMwMagic((ulong)OrderGetInteger(ORDER_MAGIC));
         if(cls != 0 && (target_scope == 0 || cls == target_scope))
            return true;
        }
     }
   return false;
  }

void LogDailyStopEvent(const string scope_name, double limit_val, double pnl_val, double mae_val)
  {
   string fn = StringFormat("magicwalls_daily_stop_events_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
   bool exists = FileIsExist(fn, FILE_COMMON);
   int h = FileOpen(fn, FILE_COMMON | FILE_READ | FILE_WRITE | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return;
   if(!exists || FileSize(h) == 0)
      FileWriteString(h, "time;login;scope;limit_brl;pnl_brl;mae_brl;win_pnl_brl;wdo_pnl_brl\r\n");
   else
      FileSeek(h, 0, SEEK_END);
   FileWriteString(h, StringFormat("%s;%I64d;%s;%.2f;%.2f;%.2f;%.2f;%.2f\r\n",
                                   TimeToString(SafeNow(), TIME_DATE | TIME_SECONDS),
                                   AccountInfoInteger(ACCOUNT_LOGIN),
                                   scope_name, limit_val, pnl_val, mae_val,
                                   g_day_total_win, g_day_total_wdo));
   FileClose(h);
  }

void ExportDailyStopStateCsv()
  {
   string fn = StringFormat("magicwalls_daily_stop_state_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
   int h = FileOpen(fn, FILE_COMMON | FILE_WRITE | FILE_SHARE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, "updated_at;day_key;enabled;auction_pause;stop_global_hit;stop_win_hit;stop_wdo_hit;"
                      "limit_global;limit_win;limit_wdo;total_global;total_win;total_wdo;"
                      "closed_win;closed_wdo;float_win;float_wdo;mae_global;mae_win;mae_wdo\r\n");
   FileWriteString(h, StringFormat("%s;%.0f;%d;%d;%d;%d;%d;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f\r\n",
                                   TimeToString(SafeNow(), TIME_DATE | TIME_SECONDS),
                                   g_stop_day_key,
                                   (InpEnableDailyStop ? 1 : 0),
                                   (IsInAuctionBlockWindow() ? 1 : 0),
                                   (g_stop_global_hit ? 1 : 0),
                                   (g_stop_win_hit ? 1 : 0),
                                   (g_stop_wdo_hit ? 1 : 0),
                                   InpMaxDailyLossGlobal, InpMaxDailyLossWin, InpMaxDailyLossWdo,
                                   g_day_total_global, g_day_total_win, g_day_total_wdo,
                                   g_day_closed_win, g_day_closed_wdo,
                                   g_day_float_win, g_day_float_wdo,
                                   g_day_mae_global, g_day_mae_win, g_day_mae_wdo));
   FileClose(h);
  }

bool EnforceDailyStop()
  {
   ResetDailyStopIfNewDay();
   ComputeTodayStopMetrics();

   bool triggered_now = false;
   double today_key = g_stop_day_key;

   if(InpEnableDailyStop && !IsInAuctionBlockWindow())
     {
      // 1) Gatilho Global WIN + WDO
      if(InpMaxDailyLossGlobal > 0.0 && !g_stop_global_hit && g_day_total_global <= -InpMaxDailyLossGlobal)
        {
         g_stop_global_hit = true;
         GlobalVariableSet("MW_DAILY_STOP_GLOBAL", today_key);
         CloseAndCancelScope(0);
         string msg = StringFormat("[MAGIC WALLS DAILY STOP GLOBAL] Conta %I64d atingiu R$ %.2f (Limite -R$ %.2f). Posicoes encerradas e travadas hoje.",
                                   AccountInfoInteger(ACCOUNT_LOGIN), g_day_total_global, InpMaxDailyLossGlobal);
         Print(msg);
         Alert(msg);
         if(InpSendPushOnStop)
            SendNotification(msg);
         LogDailyStopEvent("GLOBAL", InpMaxDailyLossGlobal, g_day_total_global, g_day_mae_global);
         triggered_now = true;
        }

      // 2) Sub-limite WIN
      if(InpMaxDailyLossWin > 0.0 && !g_stop_win_hit && g_day_total_win <= -InpMaxDailyLossWin)
        {
         g_stop_win_hit = true;
         GlobalVariableSet("MW_DAILY_STOP_WIN", today_key);
         CloseAndCancelScope(1);
         string msg = StringFormat("[MAGIC WALLS DAILY STOP WIN] Conta %I64d WIN atingiu R$ %.2f (Limite -R$ %.2f). WIN encerrado/travado hoje; WDO livre.",
                                   AccountInfoInteger(ACCOUNT_LOGIN), g_day_total_win, InpMaxDailyLossWin);
         Print(msg);
         Alert(msg);
         if(InpSendPushOnStop)
            SendNotification(msg);
         LogDailyStopEvent("WIN", InpMaxDailyLossWin, g_day_total_win, g_day_mae_win);
         triggered_now = true;
        }

      // 3) Sub-limite WDO
      if(InpMaxDailyLossWdo > 0.0 && !g_stop_wdo_hit && g_day_total_wdo <= -InpMaxDailyLossWdo)
        {
         g_stop_wdo_hit = true;
         GlobalVariableSet("MW_DAILY_STOP_WDO", today_key);
         CloseAndCancelScope(2);
         string msg = StringFormat("[MAGIC WALLS DAILY STOP WDO] Conta %I64d WDO atingiu R$ %.2f (Limite -R$ %.2f). WDO encerrado/travado hoje; WIN livre.",
                                   AccountInfoInteger(ACCOUNT_LOGIN), g_day_total_wdo, InpMaxDailyLossWdo);
         Print(msg);
         Alert(msg);
         if(InpSendPushOnStop)
            SendNotification(msg);
         LogDailyStopEvent("WDO", InpMaxDailyLossWdo, g_day_total_wdo, g_day_mae_wdo);
         triggered_now = true;
        }

      // Warnings amarelos (one-shot por dia)
      double warn_ratio = MathMax(0.10, MathMin(0.99, InpStopWarningPct / 100.0));
      if(InpMaxDailyLossGlobal > 0.0 && !g_stop_global_hit && !g_warn_global_sent && g_day_total_global <= -InpMaxDailyLossGlobal * warn_ratio)
        {
         g_warn_global_sent = true;
         string wmsg = StringFormat("[MAGIC WALLS MONITOR] ATENCAO %.0f%% STOP GLOBAL: PnL Hoje R$ %.2f / Limite -R$ %.2f",
                                    InpStopWarningPct, g_day_total_global, InpMaxDailyLossGlobal);
         Print(wmsg);
         Alert(wmsg);
        }
      if(InpMaxDailyLossWin > 0.0 && !g_stop_win_hit && !g_warn_win_sent && g_day_total_win <= -InpMaxDailyLossWin * warn_ratio)
        {
         g_warn_win_sent = true;
         PrintFormat("[MAGIC WALLS MONITOR] ATENCAO %.0f%% STOP WIN: WIN Hoje R$ %.2f / Limite -R$ %.2f",
                     InpStopWarningPct, g_day_total_win, InpMaxDailyLossWin);
        }
      if(InpMaxDailyLossWdo > 0.0 && !g_stop_wdo_hit && !g_warn_wdo_sent && g_day_total_wdo <= -InpMaxDailyLossWdo * warn_ratio)
        {
         g_warn_wdo_sent = true;
         PrintFormat("[MAGIC WALLS MONITOR] ATENCAO %.0f%% STOP WDO: WDO Hoje R$ %.2f / Limite -R$ %.2f",
                     InpStopWarningPct, g_day_total_wdo, InpMaxDailyLossWdo);
        }
     }

   // Retry automático a cada 2s enquanto houver trava ativa hoje (garante zero exposição residual)
   if(InpEnableDailyStop && (g_stop_global_hit || g_stop_win_hit || g_stop_wdo_hit))
     {
      if(g_stop_global_hit) GlobalVariableSet("MW_DAILY_STOP_GLOBAL", today_key);
      if(g_stop_win_hit)    GlobalVariableSet("MW_DAILY_STOP_WIN",    today_key);
      if(g_stop_wdo_hit)    GlobalVariableSet("MW_DAILY_STOP_WDO",    today_key);

      datetime now_r = SafeNow();
      if(now_r - g_last_retry_close >= 2)
        {
         g_last_retry_close = now_r;
         if(g_stop_global_hit && HasOpenOrPendingInScope(0))
            CloseAndCancelScope(0);
         else
           {
            if(g_stop_win_hit && HasOpenOrPendingInScope(1))
               CloseAndCancelScope(1);
            if(g_stop_wdo_hit && HasOpenOrPendingInScope(2))
               CloseAndCancelScope(2);
           }
        }
     }

   datetime now_exp = SafeNow();
   if(triggered_now || (now_exp - g_last_state_export >= MathMax(1, InpRefreshSeconds)))
     {
      g_last_state_export = now_exp;
      ExportDailyStopStateCsv();
     }
   return triggered_now;
  }

//+------------------------------------------------------------------+
//| Ciclo Completo de Atualização do Monitor                         |
//+------------------------------------------------------------------+
void RefreshMonitor(bool run_stop_check = true)
  {
   if(run_stop_check)
      EnforceDailyStop();
   UpdateOpenPositionsAndOrders();
   UpdateTradeHistoryAndMetrics();
   SavePersistentRecords();
   ExportCsvSnapshot();
   ExportLiveDealsHistory();
   RenderDashboardPanel();
   g_last_update       = TimeCurrent();
   g_last_full_refresh = SafeNow();
  }

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   ObjectsDeleteAll(0, g_prefix);
   InitBenchmarks();
   LoadPersistentRecords();
   EventSetTimer(1); // Checagem de Stop Diário a cada 1 segundo
   RefreshMonitor(true);
   PrintFormat("[MAGIC WALLS MONITOR v4.20] Inicializado (10 Robos B3) | Stop Diário: %s | Global=-R$ %.0f | WIN=-R$ %.0f | WDO=-R$ %.0f",
               (InpEnableDailyStop ? "ON" : "OFF"), InpMaxDailyLossGlobal, InpMaxDailyLossWin, InpMaxDailyLossWdo);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   SavePersistentRecords();
   if(InpClearStopOnRemove && reason == REASON_REMOVE)
     {
      GlobalVariableDel("MW_DAILY_STOP_GLOBAL");
      GlobalVariableDel("MW_DAILY_STOP_WIN");
      GlobalVariableDel("MW_DAILY_STOP_WDO");
     }
   ObjectsDeleteAll(0, g_prefix);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Timer event (1s para Stop Diário + Refresh completo periódico)   |
//+------------------------------------------------------------------+
void OnTimer()
  {
   bool trig = EnforceDailyStop();
   if(trig || (SafeNow() - g_last_full_refresh >= MathMax(1, InpRefreshSeconds)))
      RefreshMonitor(false);
  }

//+------------------------------------------------------------------+
//| Tick event (com throttle de 500ms para evitar I/O por tick)      |
//+------------------------------------------------------------------+
void OnTick()
  {
   ulong now_ms = GetTickCount64();
   if(now_ms - g_last_stop_check_ms < 500)
      return;
   g_last_stop_check_ms = now_ms;

   bool trig = EnforceDailyStop();
   if(trig || (TimeCurrent() - g_last_update >= MathMax(1, InpRefreshSeconds)))
      RefreshMonitor(false);
  }

//+------------------------------------------------------------------+
//| TradeTransaction event (atualiza imediatamente ao fechar/abrir)  |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD ||
      trans.type == TRADE_TRANSACTION_ORDER_ADD ||
      trans.type == TRADE_TRANSACTION_ORDER_DELETE)
     {
      g_last_stop_check_ms = GetTickCount64();
      EnforceDailyStop();
      RefreshMonitor(false);
     }
  }
//+------------------------------------------------------------------+
