//+------------------------------------------------------------------+
//|                                 Jumba_Portfolio_Live_Monitor.mq5 |
//|     Jumba Quant / Antigravity - Monitor de Operações & Histórico |
//|     Acompanha 11 Robôs OOS+ Validados (Walls+NWE): WIN(8)+WDO(3) |
//|     Guarda e Compara MaxDD (BT vs Live) e Loss Streak (BT vs Live)|
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property description "Monitor em Tempo Real e Historico dos 11 Robos OOS+ Validados (8 WIN + 3 WDO - Proposta B - Walls TP/SL/BE + NWE)."
#property description "Compara Operacoes Abertas, PnL, MaxDD (BT vs Live) e Sequencia de Loss (BT vs Live)."
#property version   "3.00"
#property strict

enum ENUM_BT_DD_MODE
  {
   BT_DD_BY_TRADE = 0, // MaxDD BT Trade-a-Trade (Mais Conservador)
   BT_DD_BY_DAY   = 1  // MaxDD BT Fechamento Diario (212 Pregões 2026)
  };

enum ENUM_HIST_SOURCE
  {
   HIST_AUTO_HYBRID    = 0, // Auto: Deals MT5 por Magic + Fallback Audit CSV (Netting)
   HIST_MT5_DEALS_ONLY = 1, // Apenas Histórico Nativo de Deals do MT5
   HIST_AUDIT_CSV_ONLY = 2  // Apenas Arquivo jumba_live_trades_audit_<Login>.csv
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

#define TOTAL_MONITORED_ROBOTS 11
#define IDX_SUMMARY_WIN        11
#define IDX_SUMMARY_WDO        12
#define IDX_SUMMARY_PORTFOLIO  13
#define TOTAL_ROWS             14

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
string           g_prefix = "JMB_MON_";
datetime         g_last_update = 0;

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

   // --- 8 ROBÔS WIN OOS+ VALIDADOS (Magic 88001, 88003, 88004, 88005, 88007, 88013..88015) · 212 Pregões 2026 ---
   SetRowConfig(0,  "EST-01", "WIN_PA_PINBAR_WALL",      false, 1,  InpWinBaseMagic + 1,  dt_orig,  828, 32.4, 1.10,  1844.0,  891.0,  951.0, 24);
   SetRowConfig(1,  "EST-03", "WIN_M15_FAKEOUT_TRAP",    false, 3,  InpWinBaseMagic + 3,  dt_nov,  1713, 53.5, 1.27,  7091.0, 1279.0, 1289.0, 12);
   SetRowConfig(2,  "EST-04", "WIN_PB_WDO_ALIGNED",      false, 4,  InpWinBaseMagic + 4,  dt_orig,  364, 43.4, 1.30,  2149.0,  594.0,  694.0, 10);
   SetRowConfig(3,  "EST-05", "WIN_M15_MIDWALL_PULLBACK",false, 5,  InpWinBaseMagic + 5,  dt_nov,   198, 42.4, 2.47,  2253.0,  204.0,  215.0,  9);
   SetRowConfig(4,  "EST-07", "WIN_OF_CLIMAX_WALL",      false, 7,  InpWinBaseMagic + 7,  dt_orig,  554, 37.2, 1.17,  2127.0,  675.0,  742.0, 11);
   SetRowConfig(5,  "EST-13", "WIN_SG_SCALPER_3C",       false, 13, InpWinBaseMagic + 13, dt_nov,   454, 63.0, 1.35,  4660.0,  791.0,  875.0,  4);
   SetRowConfig(6,  "EST-14", "WIN_SG_MOMENTUM_3C",      false, 14, InpWinBaseMagic + 14, dt_nov,   504, 64.1, 1.35,  5334.0, 1052.0, 1155.0,  4);
   SetRowConfig(7,  "EST-15", "WIN_SG_Z30_REV_WALL",     false, 15, InpWinBaseMagic + 15, dt_nov,   488, 63.3, 1.26,  3951.0, 1080.0, 1080.0,  5);

   // --- 3 ROBÔS WDO OOS+ VALIDADOS (Magic 89001, 89005, 89007) · 212 Pregões 2026 ---
   SetRowConfig(8,  "WDO-01", "WDO_PA_WALL_SCALPER_NY",  true,  1,  InpWdoBaseMagic + 1,  dt_nov,   705, 51.3, 1.17,  3940.0, 1325.0, 1330.0,  6);
   SetRowConfig(9,  "WDO-05", "WDO_PA_CLUSTER_NWE",      true,  5,  InpWdoBaseMagic + 5,  dt_nov,   745, 61.9, 1.24,  5995.0,  880.0, 1170.0,  6);
   SetRowConfig(10, "WDO-07", "WDO_OF_CLIMAX_WALL",      true,  7,  InpWdoBaseMagic + 7,  dt_orig,  475, 54.7, 1.26,  3685.0, 1225.0, 1255.0,  5);

   // --- 3 LINHAS DE CONSOLIDAÇÃO (WIN 08, WDO 03, PORTFÓLIO TOTAL 11 - PROPOSTA B) ---
   SetRowConfig(IDX_SUMMARY_WIN,       "WIN 08",   "SUBTOTAL INDICE (08 ROBOS)",  false, 99,  0, dt_orig, 5103, 50.0, 1.27, 29409.0, 2848.0, 3090.0, 20);
   SetRowConfig(IDX_SUMMARY_WDO,       "WDO 03",   "SUBTOTAL DOLAR (03 ROBOS)",   true,  99,  0, dt_orig, 1925, 56.3, 1.22, 13620.0, 3235.0, 3265.0,  6);
   SetRowConfig(IDX_SUMMARY_PORTFOLIO, "TOTAL 11", "PORTFOLIO ELITE (11 ROBOS)",  false, 100, 0, dt_orig, 7028, 51.7, 1.25, 43029.0, 3384.0, 3852.0, 15);
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
   return StringFormat("jumba_monitor_records_v2_%I64d.csv", login);
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
   string fname = StringFormat("jumba_portfolio_live_monitor_%I64d.csv", login);
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

   // Fallback / Modo Netting: Lê jumba_live_trades_audit_<Login>.csv se não houver deals por Magic individual
   if(InpHistorySource == HIST_AUDIT_CSV_ONLY || (InpHistorySource == HIST_AUTO_HYBRID && native_matched_deals == 0))
     {
      string audit_fn = StringFormat("jumba_live_trades_audit_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
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
            Alert(StringFormat("[JUMBA MONITOR] ALERTA MAX DD: %s (%s) atingiu R$ %.0f no Live (> BT R$ %.0f)!",
                               g_rows[i].code, g_rows[i].strat_name, g_rows[i].live_max_dd_brl, bt_dd));
           }
         if(g_rows[i].bt_max_loss_streak > 0 && g_rows[i].live_curr_loss_streak > g_rows[i].bt_max_loss_streak && !g_rows[i].alerted_streak)
           {
            g_rows[i].alerted_streak = true;
            Alert(StringFormat("[JUMBA MONITOR] ALERTA LOSS STREAK: %s (%s) atingiu %d losses seguidos no Live (> BT %d)!",
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
   int hdr_h = 46;
   int tbl_w = 1135;
   int tbl_h = hdr_h + (TOTAL_ROWS + 2) * row_h + 14;

   // Fundo Principal
   UpsertRect(g_prefix + "BG_MAIN", x0, y0, tbl_w, tbl_h, C'15,20,28', C'55,70,95');
   UpsertRect(g_prefix + "BG_HDR",  x0 + 2, y0 + 2, tbl_w - 4, hdr_h - 4, C'22,32,46', C'45,65,90');

   string dd_mode_str = (InpBtDdReference == BT_DD_BY_DAY) ? "MaxDD Diario (212d 2026)" : "MaxDD Trade-a-Trade (212d 2026)";
   string title = StringFormat("JUMBA QUANT MONITOR LIVE vs BACKTEST  |  11 ROBOS OOS+ ELITE (8 WIN + 3 WDO · PROPOSTA B)  |  Ref BT: %s  |  Atualizado: %s",
                               dd_mode_str, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));
   UpsertLabel(g_prefix + "LBL_TITLE", x0 + 10, y0 + 6, title, C'100,210,255', InpFontSize + 1);

   string subtitle = StringFormat("Conta: %I64d  |  PNL Hoje Total: R$ %+.0f  |  PNL Acum Live: R$ %+.0f  |  DD Atual/Max Live: R$ %.0f / R$ %.0f (BT: R$ %.0f)  |  Loss Streak Atual/Max Live: %d / %d (BT: %d)",
                                  AccountInfoInteger(ACCOUNT_LOGIN),
                                  g_rows[IDX_SUMMARY_PORTFOLIO].live_day_brl + g_rows[IDX_SUMMARY_PORTFOLIO].open_floating_brl,
                                  g_rows[IDX_SUMMARY_PORTFOLIO].live_net_brl,
                                  g_rows[IDX_SUMMARY_PORTFOLIO].live_curr_dd_brl,
                                  g_rows[IDX_SUMMARY_PORTFOLIO].live_max_dd_brl,
                                  GetBtMaxDD(IDX_SUMMARY_PORTFOLIO),
                                  g_rows[IDX_SUMMARY_PORTFOLIO].live_curr_loss_streak,
                                  g_rows[IDX_SUMMARY_PORTFOLIO].live_max_loss_streak,
                                  g_rows[IDX_SUMMARY_PORTFOLIO].bt_max_loss_streak);
   UpsertLabel(g_prefix + "LBL_SUBTITLE", x0 + 10, y0 + 24, subtitle, C'220,230,242', InpFontSize);

   // Posições X das Colunas
   int cx_code   = x0 + 10;
   int cx_name   = x0 + 75;
   int cx_magic  = x0 + 255;
   int cx_pos    = x0 + 315;
   int cx_trades = x0 + 445;
   int cx_wr     = x0 + 545;
   int cx_pnl    = x0 + 645;
   int cx_dd     = x0 + 795;
   int cx_streak = x0 + 960;
   int cx_status = x0 + 1055;

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
//| Exporta todos os deals das EAs Jumba (88001-88016 / 89001-89016) |
//| para jumba_live_deals_<Login>.csv em FILE_COMMON.                |
//| Usado pelo Calendário do Live Trading do dashboard (server.py).  |
//+------------------------------------------------------------------+
int      g_deals_exported_total = -1;
datetime g_deals_exported_at    = 0;

bool IsJumbaMagic(ulong magic)
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

   // 1ª passada: posições abertas por EAs Jumba (para incluir saídas manuais com magic 0)
   ulong jumba_pos[];
   int n_pos = 0;
   for(int d = 0; d < total; d++)
     {
      ulong tk = HistoryDealGetTicket(d);
      if(tk == 0)
         continue;
      if(IsJumbaMagic((ulong)HistoryDealGetInteger(tk, DEAL_MAGIC)))
        {
         ArrayResize(jumba_pos, n_pos + 1, 256);
         jumba_pos[n_pos++] = (ulong)HistoryDealGetInteger(tk, DEAL_POSITION_ID);
        }
     }

   string fname = StringFormat("jumba_live_deals_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
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
      bool ok = IsJumbaMagic(magic);
      if(!ok)
         for(int k = 0; k < n_pos; k++)
            if(jumba_pos[k] == pos_id) { ok = true; break; }
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
//| Ciclo Completo de Atualização do Monitor                         |
//+------------------------------------------------------------------+
void RefreshMonitor()
  {
   UpdateOpenPositionsAndOrders();
   UpdateTradeHistoryAndMetrics();
   SavePersistentRecords();
   ExportCsvSnapshot();
   ExportLiveDealsHistory();
   RenderDashboardPanel();
   g_last_update = TimeCurrent();
  }

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   ObjectsDeleteAll(0, g_prefix);
   InitBenchmarks();
   LoadPersistentRecords();
   EventSetTimer(MathMax(1, InpRefreshSeconds));
   RefreshMonitor();
   Print("[JUMBA MONITOR] Inicializado com sucesso para 11 Robos OOS+ Validados (8 WIN + 3 WDO - Proposta B · Walls TP/SL/BE + NWE).");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   SavePersistentRecords();
   ObjectsDeleteAll(0, g_prefix);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Timer event                                                      |
//+------------------------------------------------------------------+
void OnTimer()
  {
   RefreshMonitor();
  }

//+------------------------------------------------------------------+
//| Tick event                                                       |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(TimeCurrent() - g_last_update >= InpRefreshSeconds)
      RefreshMonitor();
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
      RefreshMonitor();
     }
  }
//+------------------------------------------------------------------+
