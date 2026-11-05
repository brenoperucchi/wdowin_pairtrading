//+------------------------------------------------------------------+
//|                                     Jumba_WDO_GEX_NWE_Core.mqh   |
//|        Jumba Quantitative Trading - Suite 16 Robôs WDO$N (B3)    |
//|   Motor Core M5/M1: GEX MagicWalls + NWE + GammaFlip + WIN Arb   |
//+------------------------------------------------------------------+
#property copyright "Jumba Quantitative Trading"
#property link      "https://wdo-win-dashboard-default-rtdb.firebaseio.com"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>
#include <Jumba_SafetyGuard.mqh>

enum ENUM_JUMBA_WDO_EXEC_MODE
  {
   WDO_EXEC_HEDGING_DIRECT_MAGIC = 0, // HEDGING: Ordens independentes c/ Magic por Robô (89001..89016)
   WDO_EXEC_NETTING_VIRTUAL_SYNC = 1  // NETTING: Slots Virtuais + Sincronização de Posição Líquida
  };

struct SGexWdoLevel
  {
   string            type;
   double            price;
   int               width;
  };

struct SWdoVirtualSlot
  {
   int               id;
   string            name;
   bool              enabled;
   int               dir;                 // 0=Flat, 1=Long, -1=Short
   int               lots;                // Lotes ativos
   int               leg_stage;           // 1, 2 ou 3
   double            p1_entry;            // Preço de entrada da Perna 1 (ancorado no Bid)
   double            avg_price;           // Preço médio atual (ancorado no Bid)
   double            curr_sl;             // Stop Loss atual (ancorado no Bid)
   double            curr_tp;             // Take Profit atual (ancorado no Bid)
   double            max_fav_pts;         // Máxima excursão favorável em pontos
   bool              be_active;           // Break-Even Estágio 1 já ativado?
   bool              be_stage2_active;    // Break-Even Estágio 2 já ativado?
   bool              opened_intrabar;     // Abriu via ordem pendente intrabar na barra atual?
   int               bars_held;           // Barras M5 completas em posição
   datetime          entry_bar_time;      // Timestamp da barra M5 da entrada
   datetime          last_entry_bar_time; // Evita reentrada na mesma barra M5
   string            last_trade_date;     // Usado nas EOD 15 e 16 (1 trade/dia)

   // Ordem Pendente Virtual / Nativa (1 ou 2 barras M5 de validade)
   int               pend_dir;            // 0=None, 1=Buy, -1=Sell
   int               pend_type;           // 1=Limit, 2=Stop
   double            pend_price;
   double            pend_tp_pts;
   double            pend_sl_pts;
   datetime          pend_bar_time;
   int               pend_bars_left;
   double            pend_def_wall;
   int               pend_be_mode;
   double            pend_wall_buf;

   // Parâmetros de Gerenciamento Dinâmico e Estrutural (Mix Campeão WDO)
   double            def_wall;
   int               be_mode;             // 0=BE_ZERO, 1=BE_WALL_SHIELD, 2=BE_WALL_2STAGE
   double            wall_shield_buf;
   double            be_trig;
   double            be_lock;
   double            tr_trig;
   double            tr_dist;
   double            step2_dist;
   double            step3_dist;
   int               lot1;
   int               lot2;
   int               lot3;
   double            tp_avg_pts;
   double            max_sl_pts;
   int               max_hold_bars;
   double            pyr_trig;
   double            pyr_lock;
   double            init_sl_pts;
   double            init_tp_pts;

   // Contabilidade de Performance em Tempo Real (MT5)
   bool              real_synced;
   double            closed_pnl_today_brl;
   double            closed_pnl_total_brl;
   int               trades_today;
   int               trades_total;
   int               wins_total;
  };

//+------------------------------------------------------------------+
//| Classe Principal do Motor Jumba WDO GEX + NWE (16 Estratégias)   |
//+------------------------------------------------------------------+
class CJumbaWdoGexNweEngine
  {
private:
   CTrade            m_trade;
   CPositionInfo     m_pos;
   COrderInfo        m_ord;

   long              m_base_magic;
   double            m_lot_mult;
   double            m_max_daily_loss_brl;
   bool              m_draw_levels;
   bool              m_show_hud;
   ENUM_JUMBA_WDO_EXEC_MODE m_exec_mode;
   CJumbaSafetyGuard m_guard;      // Kill-switch anti-loop (volume, exposicao, taxa de ordens)

   SWdoVirtualSlot   m_slots[17]; // Índices 1..16
   SGexWdoLevel      m_gex_raw[];
   double            m_levels_all[];
   double            m_levels_walls[];
   double            m_gamma_flip;
   double            m_max_gamma;
   double            m_min_gamma;
   string            m_loaded_date;
   string            m_gex_source;

   datetime          m_last_m5_bar_time;
   bool              m_state_reconciled;
   ulong             m_last_order_ms[17];
   double            m_last_sent_lots[17];
   ulong             m_last_net_sync_ms;

   // Indicadores Causais em Barra Fechada (b1 = barra 1, b2 = barra 2)
   double            m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1;
   double            m_n50_c_2, m_n50_u_2, m_n50_l_2, m_n50_s_2;
   double            m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1;
   double            m_n30_c_2, m_n30_u_2, m_n30_l_2, m_n30_s_2;
   double            m_rsi7_1,  m_rsi7_2;
   double            m_win_ret3_1, m_win_z_1;

public:
                     CJumbaWdoGexNweEngine()
     {
      m_base_magic = 89000;
      m_lot_mult = 1.0;
      m_max_daily_loss_brl = 3500.0;
      m_draw_levels = true;
      m_show_hud = true;
      m_exec_mode = WDO_EXEC_HEDGING_DIRECT_MAGIC;
      m_loaded_date = "";
      m_gex_source = "NONE";
      m_last_m5_bar_time = 0;
      m_state_reconciled = false;
      m_last_net_sync_ms = 0;
      for(int k=0; k<=16; k++)
        {
         m_last_order_ms[k] = 0;
         m_last_sent_lots[k] = 0.0;
        }
      m_gamma_flip = 0.0;
      m_max_gamma = 0.0;
      m_min_gamma = 0.0;
     }

   void              Init(long base_magic, double lot_mult, double max_daily_loss_brl,
                          bool draw_levels, bool show_hud, ENUM_JUMBA_WDO_EXEC_MODE exec_mode,
                          bool e1, bool e2, bool e3, bool e4,
                          bool e5, bool e6, bool e7, bool e8,
                          bool e9, bool e10, bool e11, bool e12,
                          bool e13, bool e14, bool e15, bool e16)
     {
      m_base_magic = base_magic;
      m_lot_mult = MathMin(10.0, MathMax(1.0, MathRound(lot_mult)));
      m_max_daily_loss_brl = max_daily_loss_brl;
      m_draw_levels = true; // Sempre desenha as Walls visuais no grafico WDO
      m_show_hud = show_hud;
      m_exec_mode = exec_mode;
      m_last_net_sync_ms = 0;
      for(int k=0; k<=16; k++)
        {
         m_last_order_ms[k] = 0;
         m_last_sent_lots[k] = 0.0;
        }

      m_trade.SetExpertMagicNumber(m_base_magic);
      m_trade.SetDeviationInPoints(100);
      m_trade.SetTypeFillingBySymbol(_Symbol);

      string names[17] =
        {
         "",
         "WDO-01 [DESATIVADO WF] Clone WDO-07",
         "WDO-02 [3Pil LimB1+2St+MidW] CORE",
         "WDO-03 [DESATIVADO <100tr] Arb WIN+WDO",
         "WDO-04 [DESATIVADO <100tr] MainW GammaFlip",
         "WDO-05 [DESATIVADO WF] Clone WDO-02",
         "WDO-06 [WF BrenoWick+MainW+Lim50%B1] Abs",
         "WDO-07 [3Pil BE_Wall+MidW] Absorcao NY",
         "WDO-08 [DESATIVADO <100tr] Abs MainW CORE",
         "WDO-09 [NOVO Cluster+LimWall] NWE30+50",
         "WDO-10 [WDO_S2 Reversao NWE 12-14h30]",
         "WDO-11 [SmartGrid GF+NextWall 1+2L]",
         "WDO-12 [DESATIVADO WF] Piram 1+1L Clone",
         "WDO-13 [DESATIVADO WF] SmartGrid 1+2L Clone",
         "WDO-14 [DESATIVADO WF] Grid 1+2+3L Clone",
         "WDO-15 [MainWall Z30_Rev070+CandleShield]",
         "WDO-16 [DESATIVADO <100tr] MainW EOD Wall"
        };

      bool en[17];
      en[0]=false;
      en[1]=false; en[2]=e2;    en[3]=false; en[4]=false;
      en[5]=false; en[6]=e6;    en[7]=e7;    en[8]=false;
      en[9]=e9;    en[10]=e10;   en[11]=e11;   en[12]=false;
      en[13]=false; en[14]=false; en[15]=e15;  en[16]=false;

      for(int k=1; k<=16; k++)
        {
         m_slots[k].id = k;
         m_slots[k].name = names[k];
         m_slots[k].enabled = en[k];
         ResetSlotPosition(k);
         m_slots[k].last_entry_bar_time = 0;
         m_slots[k].last_trade_date = "";
         m_slots[k].closed_pnl_today_brl = 0.0;
         m_slots[k].closed_pnl_total_brl = 0.0;
         m_slots[k].trades_today = 0;
         m_slots[k].trades_total = 0;
         m_slots[k].wins_total = 0;
        }

      int guard_slots = 0;
      for(int gk=1; gk<=16; gk++)
         if(m_slots[gk].enabled) guard_slots++;
      m_guard.Configure("JUMBA WDO", m_base_magic, m_lot_mult, guard_slots);
      m_guard.CheckAccountMode(GetSingleActiveSlotId() > 0);

      long acc_margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(acc_margin_mode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || GetSingleActiveSlotId() > 0)
        {
         if(m_exec_mode != WDO_EXEC_HEDGING_DIRECT_MAGIC)
            Print("[JUMBA WDO] Trava de Seguranca: Forcando WDO_EXEC_HEDGING_DIRECT_MAGIC (Conta Hedging ou Robo Individual).");
         m_exec_mode = WDO_EXEC_HEDGING_DIRECT_MAGIC;
        }
      else if(acc_margin_mode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         Print("[JUMBA WDO] Conta NETTING detectada na corretora. Alternando automaticamente para WDO_EXEC_NETTING_VIRTUAL_SYNC.");
         m_exec_mode = WDO_EXEC_NETTING_VIRTUAL_SYNC;
        }

      if(!MQLInfoInteger(MQL_TESTER))
        {
         GlobalVariablesDeleteAll("JUMBA_WDO_LOTS_");
         GlobalVariablesDeleteAll("JUMBA_WDO_TIME_");
        }

      SymbolSelect("WIN$N", true);
      SymbolSelect("WINZ26", true);

      m_state_reconciled = MQLInfoInteger(MQL_TESTER) ? true : false;
      if(!MQLInfoInteger(MQL_TESTER))
        {
         SymbolSelect("WDOX26", true);
         SymbolSelect("WDOZ26", true);
         SymbolSelect(_Symbol, true);
         m_last_m5_bar_time = iTime(_Symbol, PERIOD_M5, 0);
         datetime t_ref = SafeTime();
         ChartSetInteger(0, CHART_SCALEFIX, false);
         string init_date = DateStr(t_ref);
         string loc_date  = DateStr(TimeLocal());
         if(loc_date > init_date)
            init_date = loc_date;
         LoadDailyGexWalls(init_date);
         if(AccountInfoInteger(ACCOUNT_LOGIN) > 0)
           {
            LoadVirtualStateFromDisk();
            if(TerminalInfoInteger(TERMINAL_CONNECTED))
              {
               ReconcileWithBrokerOnStartup();
               m_state_reconciled = true;
              }
           }
         RenderHudComment();
         ChartRedraw(0);
        }
     }

   void              Deinit()
     {
      if(!MQLInfoInteger(MQL_TESTER))
         SaveVirtualStateToDisk();
      if(m_draw_levels)
         ObjectsDeleteAll(0, "JUMBA_WDO_GEX_");
      if(m_show_hud)
         Comment("");
     }

   datetime          SafeTime()
     {
      datetime t = TimeCurrent();
      if(t < D'2025.01.01')
         t = TimeTradeServer();
      if(t < D'2025.01.01')
         t = TimeLocal();
      return t;
     }

   int               GetSingleActiveSlotId()
     {
      int cnt = 0, last_k = 0;
      for(int k=1; k<=16; k++)
        {
         if(m_slots[k].enabled)
           {
            cnt++;
            last_k = k;
           }
        }
      return (cnt == 1) ? last_k : 0;
     }

   int               GetMaxBaseLotsForSlot(int k)
     {
      if(k == 11 || k == 13)
         return 3; // SmartGrid 1+2 lotes
      if(k == 12)
         return 2; // Piramidacao 1+1 lotes
      return 1;    // Demais estrategias operam estritamente 1 lote base
     }

   string            StateFileName()
     {
      long file_magic = m_base_magic + GetSingleActiveSlotId();
      return StringFormat("jumba_wdo_state_%I64d_%s_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN), _Symbol, file_magic);
     }

   void              SaveVirtualStateToDisk()
     {
      if(MQLInfoInteger(MQL_TESTER) || AccountInfoInteger(ACCOUNT_LOGIN) <= 0)
         return;
      int h = FileOpen(StateFileName(), FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(h == INVALID_HANDLE)
         return;
      string today = DateStr(SafeTime());
      FileWriteString(h, today + "\n");
      for(int k=1; k<=16; k++)
        {
         string line = StringFormat(
            "%d;%d;%d;%d;%.2f;%.2f;%.2f;%.2f;%.2f;%d;%d;%I64d;%I64d;%s;%.2f;%.2f;%d;%d;%d;%.2f;%.2f;%d;%d;%d;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%d;%.2f;%.2f;%.2f;%.2f;%d;%d;%.2f;%.2f;%.2f;%I64d;%.2f;%d;%.2f;%d;%d;%.2f;%d;%.2f\n",
            k, m_slots[k].dir, m_slots[k].lots, m_slots[k].leg_stage,
            m_slots[k].p1_entry, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp,
            m_slots[k].max_fav_pts, (m_slots[k].be_active ? 1 : 0), m_slots[k].bars_held,
            (long)m_slots[k].entry_bar_time, (long)m_slots[k].last_entry_bar_time, m_slots[k].last_trade_date,
            m_slots[k].closed_pnl_today_brl, m_slots[k].closed_pnl_total_brl,
            m_slots[k].trades_today, m_slots[k].trades_total, m_slots[k].wins_total,
            m_slots[k].step2_dist, m_slots[k].step3_dist,
            m_slots[k].lot1, m_slots[k].lot2, m_slots[k].lot3,
            m_slots[k].tp_avg_pts, m_slots[k].max_sl_pts,
            m_slots[k].be_trig, m_slots[k].be_lock, m_slots[k].tr_trig, m_slots[k].tr_dist,
            m_slots[k].max_hold_bars,
            m_slots[k].pyr_trig, m_slots[k].pyr_lock, m_slots[k].init_sl_pts, m_slots[k].init_tp_pts,
            m_slots[k].pend_dir, m_slots[k].pend_type, m_slots[k].pend_price,
            m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts, (long)m_slots[k].pend_bar_time,
            m_slots[k].def_wall, m_slots[k].be_mode, m_slots[k].wall_shield_buf,
            (m_slots[k].be_stage2_active ? 1 : 0),
            m_slots[k].pend_bars_left, m_slots[k].pend_def_wall, m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf
         );
         FileWriteString(h, line);
        }
      FileClose(h);
     }

   void              LoadVirtualStateFromDisk()
     {
      if(MQLInfoInteger(MQL_TESTER) || AccountInfoInteger(ACCOUNT_LOGIN) <= 0)
         return;
      int h = FileOpen(StateFileName(), FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(h == INVALID_HANDLE)
         return;
      string saved_date = FileReadString(h);
      StringReplace(saved_date, "\r", "");
      StringReplace(saved_date, "\n", "");
      string today = DateStr(SafeTime());
      if(saved_date != today)
        {
         FileClose(h);
         return;
        }
      while(!FileIsEnding(h))
        {
         string line = FileReadString(h);
         if(StringLen(line) < 5)
            continue;
         string p[];
         int cnt = StringSplit(line, ';', p);
         if(cnt >= 35)
           {
            int k = (int)StringToInteger(p[0]);
            if(k >= 1 && k <= 16 && m_slots[k].enabled)
              {
               m_slots[k].dir                  = (int)StringToInteger(p[1]);
               m_slots[k].lots                 = (int)MathMin((long)GetMaxBaseLotsForSlot(k), MathMax(0, StringToInteger(p[2])));
               m_slots[k].leg_stage            = (int)StringToInteger(p[3]);
               m_slots[k].p1_entry             = StringToDouble(p[4]);
               m_slots[k].avg_price            = StringToDouble(p[5]);
               m_slots[k].curr_sl              = StringToDouble(p[6]);
               m_slots[k].curr_tp              = StringToDouble(p[7]);
               m_slots[k].max_fav_pts          = StringToDouble(p[8]);
               m_slots[k].be_active            = (StringToInteger(p[9]) != 0);
               m_slots[k].bars_held            = (int)StringToInteger(p[10]);
               m_slots[k].entry_bar_time       = (datetime)StringToInteger(p[11]);
               m_slots[k].last_entry_bar_time  = (datetime)StringToInteger(p[12]);
               m_slots[k].last_trade_date      = p[13];
               m_slots[k].closed_pnl_today_brl = StringToDouble(p[14]);
               m_slots[k].closed_pnl_total_brl = StringToDouble(p[15]);
               m_slots[k].trades_today         = (int)StringToInteger(p[16]);
               m_slots[k].trades_total         = (int)StringToInteger(p[17]);
               m_slots[k].wins_total           = (int)StringToInteger(p[18]);
               m_slots[k].step2_dist           = StringToDouble(p[19]);
               m_slots[k].step3_dist           = StringToDouble(p[20]);
               m_slots[k].lot1                 = (int)StringToInteger(p[21]);
               m_slots[k].lot2                 = (int)StringToInteger(p[22]);
               m_slots[k].lot3                 = (int)StringToInteger(p[23]);
               m_slots[k].tp_avg_pts           = StringToDouble(p[24]);
               m_slots[k].max_sl_pts           = StringToDouble(p[25]);
               m_slots[k].be_trig              = StringToDouble(p[26]);
               m_slots[k].be_lock              = StringToDouble(p[27]);
               m_slots[k].tr_trig              = StringToDouble(p[28]);
               m_slots[k].tr_dist              = StringToDouble(p[29]);
               m_slots[k].max_hold_bars        = (int)StringToInteger(p[30]);
               m_slots[k].pyr_trig             = StringToDouble(p[31]);
               m_slots[k].pyr_lock             = StringToDouble(p[32]);
               m_slots[k].init_sl_pts          = StringToDouble(p[33]);
               m_slots[k].init_tp_pts          = StringToDouble(p[34]);
               if(cnt >= 41)
                 {
                  m_slots[k].pend_dir      = (int)StringToInteger(p[35]);
                  m_slots[k].pend_type     = (int)StringToInteger(p[36]);
                  m_slots[k].pend_price    = StringToDouble(p[37]);
                  m_slots[k].pend_tp_pts   = StringToDouble(p[38]);
                  m_slots[k].pend_sl_pts   = StringToDouble(p[39]);
                  m_slots[k].pend_bar_time = (datetime)StringToInteger(p[40]);
                 }
               if(cnt >= 49)
                 {
                  m_slots[k].def_wall         = StringToDouble(p[41]);
                  m_slots[k].be_mode          = (int)StringToInteger(p[42]);
                  m_slots[k].wall_shield_buf  = StringToDouble(p[43]);
                  m_slots[k].be_stage2_active = (StringToInteger(p[44]) != 0);
                  m_slots[k].pend_bars_left   = (int)StringToInteger(p[45]);
                  m_slots[k].pend_def_wall    = StringToDouble(p[46]);
                  m_slots[k].pend_be_mode     = (int)StringToInteger(p[47]);
                  m_slots[k].pend_wall_buf    = StringToDouble(p[48]);
                 }
              }
           }
        }
      FileClose(h);
     }

   void              ReconcileWithBrokerOnStartup()
     {
      if(MQLInfoInteger(MQL_TESTER))
         return;
      string today_str = DateStr(SafeTime());
      string d_dot = today_str;
      StringReplace(d_dot, "-", ".");
      datetime day_start = StringToTime(d_dot + " 00:00");
      bool hist_ok = HistorySelect(day_start, SafeTime() + 3600);

      for(int k=1; k<=16; k++)
        {
         if(!m_slots[k].enabled)
            continue;
         long slot_magic = m_base_magic + k;

         // 1. Reconcilia PnL Fechado e Trades do Dia pelo Histórico Oficial da Corretora
         if(hist_ok)
           {
            double h_pnl = 0.0;
            int h_tr = 0, h_wins = 0;
            int total_deals = HistoryDealsTotal();
            for(int i=0; i<total_deals; i++)
              {
               ulong dticket = HistoryDealGetTicket(i);
               if(HistoryDealGetString(dticket, DEAL_SYMBOL) == _Symbol &&
                  HistoryDealGetInteger(dticket, DEAL_MAGIC) == slot_magic)
                 {
                  long dentry = HistoryDealGetInteger(dticket, DEAL_ENTRY);
                  if(dentry == DEAL_ENTRY_OUT || dentry == DEAL_ENTRY_INOUT)
                    {
                     double dpnl = HistoryDealGetDouble(dticket, DEAL_PROFIT);
                     h_pnl += dpnl;
                     h_tr += 1;
                     if(dpnl > 0.0)
                        h_wins += 1;
                    }
                 }
              }
            if(h_tr > m_slots[k].trades_today || (h_tr > 0 && MathAbs(m_slots[k].closed_pnl_today_brl) < 0.01))
              {
               m_slots[k].closed_pnl_today_brl = h_pnl;
               m_slots[k].trades_today = h_tr;
               if(m_slots[k].trades_total < h_tr)
                  m_slots[k].trades_total = h_tr;
               if(m_slots[k].wins_total < h_wins)
                  m_slots[k].wins_total = h_wins;
               if(MathAbs(m_slots[k].closed_pnl_total_brl) < MathAbs(h_pnl))
                  m_slots[k].closed_pnl_total_brl = h_pnl;
              }
            if(h_tr > 0 && (k == 15 || k == 16))
               m_slots[k].last_trade_date = today_str;
           }

         // 2. Reconcilia Posições Abertas e Ordens Pendentes em Modo HEDGING
         if(m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
           {
            double actual_lots = 0.0;
            double open_px = 0.0, pos_sl = 0.0, pos_tp = 0.0;
            datetime pos_time = 0;
            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                 {
                  open_px  = m_pos.PriceOpen();
                  pos_sl   = m_pos.StopLoss();
                  pos_tp   = m_pos.TakeProfit();
                  pos_time = m_pos.Time();
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_lots += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_lots -= m_pos.Volume();
                 }
              }

            if(MathAbs(actual_lots) >= 0.99)
              {
               int pos_dir = (actual_lots > 0.0) ? 1 : -1;
               int pos_lots = MathMin(GetMaxBaseLotsForSlot(k), MathMax(1, (int)MathRound(MathAbs(actual_lots) / m_lot_mult)));
               double bid_ref = (pos_dir == 1 && open_px > 0.0) ? Round05(open_px - 0.5) : Round05(open_px);
               if(m_slots[k].dir == pos_dir)
                 {
                  m_slots[k].lots = pos_lots;
                  m_slots[k].real_synced = true;
                  if(m_slots[k].avg_price <= 0.0) m_slots[k].avg_price = bid_ref;
                  if(m_slots[k].p1_entry <= 0.0)  m_slots[k].p1_entry  = bid_ref;
                  if(m_slots[k].curr_sl <= 0.0 && pos_sl > 0.0) m_slots[k].curr_sl = Round05(pos_sl);
                  if(m_slots[k].curr_tp <= 0.0 && pos_tp > 0.0) m_slots[k].curr_tp = Round05(pos_tp);
                 }
               else
                 {
                  // Adota a posição aberta da corretora sem jamais fechá-la no reinício!
                  m_slots[k].dir            = pos_dir;
                  m_slots[k].lots           = pos_lots;
                  m_slots[k].leg_stage      = (pos_lots >= 6) ? 3 : ((pos_lots >= 2) ? 2 : 1);
                  m_slots[k].p1_entry       = bid_ref;
                  m_slots[k].avg_price      = bid_ref;
                  m_slots[k].curr_sl        = (pos_sl > 0.0) ? Round05(pos_sl) : ((pos_dir == 1) ? Round05(bid_ref - 13.5) : Round05(bid_ref + 13.5));
                  m_slots[k].curr_tp        = (pos_tp > 0.0) ? Round05(pos_tp) : ((pos_dir == 1) ? Round05(bid_ref + 24.0) : Round05(bid_ref - 24.0));
                  m_slots[k].init_sl_pts    = MathAbs(bid_ref - m_slots[k].curr_sl);
                  m_slots[k].init_tp_pts    = MathAbs(m_slots[k].curr_tp - bid_ref);
                  m_slots[k].entry_bar_time = pos_time;
                  m_slots[k].real_synced    = true;
                  if(m_slots[k].be_trig <= 0.0)  { m_slots[k].be_trig = (k >= 15) ? 12.5 : 7.0; m_slots[k].be_lock = 1.5; }
                  if(m_slots[k].tr_trig <= 0.0 && k != 11 && k != 13 && k != 14) { m_slots[k].tr_trig = (k >= 15) ? 26.0 : 13.5; m_slots[k].tr_dist = (k >= 15) ? 10.5 : 5.0; }
                  if(m_slots[k].max_hold_bars <= 0) m_slots[k].max_hold_bars = (k >= 15) ? 120 : ((k == 11 || k == 13 || k == 14) ? 26 : 16);
                  if(k == 11) { m_slots[k].step2_dist = 15.0; m_slots[k].lot1 = 1; m_slots[k].lot2 = 2; m_slots[k].tp_avg_pts = 11.0; m_slots[k].max_sl_pts = 22.0; }
                  if(k == 13) { m_slots[k].step2_dist = 16.0; m_slots[k].lot1 = 1; m_slots[k].lot2 = 2; m_slots[k].tp_avg_pts = 11.0; m_slots[k].max_sl_pts = 22.0; }
                  if(k == 14) { m_slots[k].step2_dist = 18.0; m_slots[k].step3_dist = 40.0; m_slots[k].lot1 = 1; m_slots[k].lot2 = 2; m_slots[k].lot3 = 3; m_slots[k].tp_avg_pts = 11.0; m_slots[k].max_sl_pts = 22.0; }
                  if(k == 12) { m_slots[k].pyr_trig = 8.5; m_slots[k].pyr_lock = 2.5; }
                  if(k == 16) m_slots[k].last_trade_date = today_str;
                  PrintFormat("[JUMBA %s] POSICAO ABERTA ADOTADA NO REINICIO | Dir=%d | Lotes=%d | PM=%.1f | SL=%.1f | TP=%.1f",
                              m_slots[k].name, m_slots[k].dir, m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp);
                 }
              }
            else if(m_slots[k].dir != 0)
              {
               // Posição que estava no disco já fechou no servidor enquanto o MT5 estava reiniciando
               ResetSlotPosition(k);
              }

            // 3. Reconcilia Ordens Pendentes Nativas na Corretora
            bool found_ord = false;
            for(int i=OrdersTotal()-1; i>=0; i--)
              {
               if(m_ord.SelectByIndex(i) && m_ord.Symbol() == _Symbol && m_ord.Magic() == slot_magic)
                 {
                  found_ord = true;
                  if(m_slots[k].pend_dir == 0)
                    {
                     ENUM_ORDER_TYPE otype = m_ord.OrderType();
                     m_slots[k].pend_dir      = (otype == ORDER_TYPE_BUY_LIMIT || otype == ORDER_TYPE_BUY_STOP) ? 1 : -1;
                     m_slots[k].pend_type     = (otype == ORDER_TYPE_BUY_LIMIT || otype == ORDER_TYPE_SELL_LIMIT) ? 1 : 2;
                     m_slots[k].pend_price    = Round05(m_ord.PriceOpen());
                     m_slots[k].pend_sl_pts   = (m_ord.StopLoss() > 0.0) ? MathAbs(m_ord.PriceOpen() - m_ord.StopLoss()) : 13.5;
                     m_slots[k].pend_tp_pts   = (m_ord.TakeProfit() > 0.0) ? MathAbs(m_ord.TakeProfit() - m_ord.PriceOpen()) : 24.0;
                     m_slots[k].pend_bar_time = iTime(_Symbol, PERIOD_M5, 0);
                     if(m_slots[k].be_trig <= 0.0) { m_slots[k].be_trig = 7.5; m_slots[k].be_lock = 1.5; m_slots[k].tr_trig = 14.0; m_slots[k].tr_dist = 5.5; m_slots[k].max_hold_bars = 16; }
                     PrintFormat("[JUMBA %s] ORDEM PENDENTE ADOTADA NO REINICIO | Dir=%d @ %.1f",
                                 m_slots[k].name, m_slots[k].pend_dir, m_slots[k].pend_price);
                    }
                  break;
                 }
              }
            if(!found_ord && m_slots[k].pend_dir != 0)
               m_slots[k].pend_dir = 0;
           }
        }
      SaveVirtualStateToDisk();
     }

   void              ResetSlotPosition(int k)
     {
      m_slots[k].dir = 0;
      m_slots[k].lots = 0;
      m_slots[k].leg_stage = 0;
      m_slots[k].p1_entry = 0.0;
      m_slots[k].avg_price = 0.0;
      m_slots[k].curr_sl = 0.0;
      m_slots[k].curr_tp = 0.0;
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
      m_slots[k].be_stage2_active = false;
      m_slots[k].opened_intrabar = false;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = 0;
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_type = 0;
      m_slots[k].pend_price = 0.0;
      m_slots[k].pend_tp_pts = 0.0;
      m_slots[k].pend_sl_pts = 0.0;
      m_slots[k].pend_bar_time = 0;
      m_slots[k].pend_bars_left = 0;
      m_slots[k].pend_def_wall = 0.0;
      m_slots[k].pend_be_mode = 0;
      m_slots[k].pend_wall_buf = 0.0;
      m_slots[k].def_wall = 0.0;
      m_slots[k].be_mode = 0;
      m_slots[k].wall_shield_buf = 0.0;
      m_slots[k].pyr_trig = 0.0;
      m_slots[k].pyr_lock = 0.0;
      m_slots[k].init_sl_pts = 0.0;
      m_slots[k].init_tp_pts = 0.0;
      m_slots[k].real_synced = false;
     }

   double            Round05(double val)
     {
      return MathRound(val * 2.0) / 2.0;
     }

   ENUM_ORDER_TYPE_TIME GetValidOrderTimeType()
     {
      long flags = SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
      if((flags & SYMBOL_EXPIRATION_GTC) != 0)
         return ORDER_TIME_GTC;
      if((flags & SYMBOL_EXPIRATION_DAY) != 0)
         return ORDER_TIME_DAY;
      return ORDER_TIME_GTC;
     }

   string            DateStr(datetime t)
     {
      MqlDateTime dt;
      TimeToStruct(t, dt);
      return StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
     }

   int               TimeMinutes(datetime t)
     {
      MqlDateTime dt;
      TimeToStruct(t, dt);
      return dt.hour * 60 + dt.min;
     }

   bool              WindowOk(int t_min, string wmode)
     {
      if(wmode == "MORNING_09_12")
         return (t_min >= 545 && t_min <= 720);
      if(wmode == "NO_LUNCH")
         return ((t_min >= 545 && t_min <= 735) || (t_min >= 810 && t_min <= 1005));
      if(wmode == "NY_1000_1630")
         return (t_min >= 600 && t_min <= 990);
      if(wmode == "CORE_09_1615")
         return (t_min >= 550 && t_min <= 975);
      if(wmode == "FULL_09_17")
         return (t_min >= 545 && t_min <= 1020);
      return false;
     }

   bool              LoadDailyGexWalls(string target_date)
     {
      if(target_date == m_loaded_date)
         return (ArraySize(m_levels_all) > 0);

      ArrayResize(m_gex_raw, 0);
      ArrayResize(m_levels_all, 0);
      ArrayResize(m_levels_walls, 0);
      m_gamma_flip = 0.0;
      m_max_gamma = 0.0;
      m_min_gamma = 0.0;

      string actual_loaded_date = "";
      // 1. Tenta ler jumba_gex_wdo_daily.csv se não estiver no Strategy Tester
      if(!MQLInfoInteger(MQL_TESTER))
        {
         int h_daily = FileOpen("jumba_gex_wdo_daily.csv", FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
         if(h_daily == INVALID_HANDLE)
            h_daily = FileOpen("jumba_gex_wdo_daily.csv", FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI);
         if(h_daily != INVALID_HANDLE)
           {
            while(!FileIsEnding(h_daily))
              {
               string line = FileReadString(h_daily);
               if(StringLen(line) < 5 || StringFind(line, "session_date") >= 0)
                  continue;
               string parts[];
               int cnt = StringSplit(line, ';', parts);
               if(cnt >= 4)
                 {
                  string s_date = parts[0];
                  if(s_date == target_date)
                    {
                     int n = ArraySize(m_gex_raw);
                     ArrayResize(m_gex_raw, n + 1);
                     m_gex_raw[n].type = parts[1];
                     m_gex_raw[n].price = StringToDouble(parts[2]);
                     m_gex_raw[n].width = (int)StringToInteger(parts[3]);
                    }
                 }
              }
            FileClose(h_daily);
            if(ArraySize(m_gex_raw) > 0)
              {
               m_gex_source = "DAILY_CSV";
               actual_loaded_date = target_date;
              }
           }
        }

      // 2. Busca em jumba_gex_wdo_history.csv
      if(ArraySize(m_gex_raw) == 0)
        {
         int h_hist = FileOpen("jumba_gex_wdo_history.csv", FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
         if(h_hist == INVALID_HANDLE)
            h_hist = FileOpen("jumba_gex_wdo_history.csv", FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI);
         if(h_hist != INVALID_HANDLE)
           {
            string best_date = "";
            while(!FileIsEnding(h_hist))
              {
               string line = FileReadString(h_hist);
               if(StringLen(line) < 5 || StringFind(line, "session_date") >= 0)
                  continue;
               string parts[];
               int cnt = StringSplit(line, ';', parts);
               if(cnt >= 4)
                 {
                  string d = parts[0];
                  bool ok_d = MQLInfoInteger(MQL_TESTER) ? (d == target_date) : (d <= target_date);
                  if(ok_d)
                    {
                     if(d > best_date)
                       {
                        best_date = d;
                        ArrayResize(m_gex_raw, 0);
                       }
                     if(d == best_date)
                       {
                        int n = ArraySize(m_gex_raw);
                        ArrayResize(m_gex_raw, n + 1);
                        m_gex_raw[n].type = parts[1];
                        m_gex_raw[n].price = StringToDouble(parts[2]);
                        m_gex_raw[n].width = (int)StringToInteger(parts[3]);
                       }
                    }
                 }
              }
            FileClose(h_hist);
            if(ArraySize(m_gex_raw) > 0)
              {
               m_gex_source = "HISTORY_CSV (" + best_date + ")";
               actual_loaded_date = best_date;
              }
           }
        }

      // 3. Fallback Cloud Firebase via WebRequest (Apenas em Conta Real/Demo fora do Strategy Tester)
      if(ArraySize(m_gex_raw) == 0 && !MQLInfoInteger(MQL_TESTER))
        {
         char post[], result[];
         string headers;
         string url = "https://wdo-win-dashboard-default-rtdb.firebaseio.com/daily_levels/dol_gex.json";
         int res = WebRequest("GET", url, "", NULL, 4000, post, 0, result, headers);
         if(res == 200)
           {
            string json = CharArrayToString(result);
            ParseFirebaseJson(json);
            if(ArraySize(m_gex_raw) > 0)
              {
               m_gex_source = "FIREBASE_CLOUD";
               actual_loaded_date = target_date;
              }
           }
        }

      for(int i=0; i<ArraySize(m_gex_raw); i++)
        {
         string t = m_gex_raw[i].type;
         double p = m_gex_raw[i].price;
         if(p <= 0.0)
            continue;
         int na = ArraySize(m_levels_all);
         ArrayResize(m_levels_all, na + 1);
         m_levels_all[na] = p;

         if(t == "Wall" || t == "wall")
           {
            int nw = ArraySize(m_levels_walls);
            ArrayResize(m_levels_walls, nw + 1);
            m_levels_walls[nw] = p;
           }
         else if(t == "GammaFlip" || t == "gamma_flip")
            m_gamma_flip = p;
         else if(t == "MaxGamma" || t == "max_gamma")
            m_max_gamma = p;
         else if(t == "MinGamma" || t == "MinGamma")
            m_min_gamma = p;
        }

      ArraySort(m_levels_all);
      ArraySort(m_levels_walls);
      // Evita travar m_loaded_date = target_date as 07h00 antes do pipeline gex_daily gerar o CSV do dia
      if(ArraySize(m_levels_all) > 0)
        {
         if(MQLInfoInteger(MQL_TESTER) || actual_loaded_date == target_date)
            m_loaded_date = target_date;
         else if(actual_loaded_date != "")
            m_loaded_date = actual_loaded_date;
        }

      for(int k=1; k<=16; k++)
        {
         m_slots[k].closed_pnl_today_brl = 0.0;
         m_slots[k].trades_today = 0;
        }

      if(m_draw_levels && !MQLInfoInteger(MQL_OPTIMIZATION))
         DrawLevelsOnChart();
      else if(!MQLInfoInteger(MQL_OPTIMIZATION))
         ObjectsDeleteAll(0, "JUMBA_WDO_GEX_");

      if(!MQLInfoInteger(MQL_TESTER))
         PrintFormat("[JUMBA WDO GEX] %s | Carregadas %d MagicWalls (%d Walls | GammaFlip=%.1f) via %s",
                     _Symbol, ArraySize(m_levels_all), ArraySize(m_levels_walls), m_gamma_flip, m_gex_source);

      return (ArraySize(m_levels_all) > 0);
     }

   void              ParseFirebaseJson(string json)
     {
      int pos = 0;
      while(true)
        {
         int idx_p = StringFind(json, "\"price\":", pos);
         if(idx_p < 0)
            break;
         int idx_end = StringFind(json, "}", idx_p);
         if(idx_end < 0)
            break;
         int idx_start = MathMax(0, idx_p - 80);
         string chunk = StringSubstr(json, idx_start, idx_end - idx_start + 1);

         double price_val = 0.0;
         int p_colon = StringFind(chunk, "\"price\":");
         if(p_colon >= 0)
            price_val = StringToDouble(StringSubstr(chunk, p_colon + 8));

         string type_val = "Wall";
         if(StringFind(chunk, "MidWall") >= 0 || StringFind(chunk, "mid_wall") >= 0)
            type_val = "MidWall";
         else if(StringFind(chunk, "GammaFlip") >= 0 || StringFind(chunk, "gamma_flip") >= 0)
            type_val = "GammaFlip";
         else if(StringFind(chunk, "MaxGamma") >= 0 || StringFind(chunk, "max_gamma") >= 0)
            type_val = "MaxGamma";
         else if(StringFind(chunk, "MinGamma") >= 0 || StringFind(chunk, "min_gamma") >= 0)
            type_val = "MinGamma";

         if(price_val > 2000.0 && price_val < 10000.0)
           {
            int n = ArraySize(m_gex_raw);
            ArrayResize(m_gex_raw, n + 1);
            m_gex_raw[n].type = type_val;
            m_gex_raw[n].price = price_val;
            m_gex_raw[n].width = 2;
           }
         pos = idx_end + 1;
        }
     }

   void              DrawLevelsOnChart()
     {
      ObjectsDeleteAll(0, "JUMBA_WDO_GEX_");
      if(!MQLInfoInteger(MQL_TESTER) && ObjectFind(0, "JUMBA_IND_GEX_HLINE_0") >= 0)
         return;
      for(int i=0; i<ArraySize(m_gex_raw); i++)
        {
         string t = m_gex_raw[i].type;
         double p = m_gex_raw[i].price;
         if(p <= 0.0)
            continue;
         string obj_name = StringFormat("JUMBA_WDO_GEX_%s_%d", t, i);
         ObjectCreate(0, obj_name, OBJ_HLINE, 0, 0, p);
         ObjectSetInteger(0, obj_name, OBJPROP_BACK, true);
         ObjectSetInteger(0, obj_name, OBJPROP_SELECTABLE, false);
         ObjectSetString(0, obj_name, OBJPROP_TOOLTIP, StringFormat("%s @ %.1f (W=%d)", t, p, m_gex_raw[i].width));
         if(t == "Wall" || t == "wall")
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrDarkOrange);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 2);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, STYLE_SOLID);
           }
         else if(t == "MidWall" || t == "mid_wall")
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrDodgerBlue);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 1);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, STYLE_DOT);
           }
         else if(t == "GammaFlip" || t == "gamma_flip")
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrMagenta);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 2);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, STYLE_DASH);
           }
         else
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrMediumSeaGreen);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 2);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, STYLE_SOLID);
           }
        }
      ChartRedraw(0);
     }

   void              RenderHudComment()
     {
      if(!m_show_hud)
         return;
      string hud = "==========================================================\n";
      hud += StringFormat(" JUMBA QUANT WDO GEX + NWE [MIX CAMPEAO] | Data: %s | Fonte: %s\n", m_loaded_date, m_gex_source);
      hud += StringFormat(" Levels: %d (Walls: %d) | GammaFlip: %.1f | NWE50 Slope: %.2f | RSI7: %.1f\n",
                          ArraySize(m_levels_all), ArraySize(m_levels_walls), m_gamma_flip, m_n50_s_1, m_rsi7_1);
      hud += StringFormat(" PnL Dia Acumulado: R$ %.2f | Mult. Lote: %.0fx\n", GetTotalDailyPnLBRL(), m_lot_mult);
      hud += "----------------------------------------------------------\n";
      for(int k=1; k<=16; k++)
        {
         if(!m_slots[k].enabled)
            continue;
         string st = "FLAT";
         if(m_slots[k].dir == 1)
            st = StringFormat("COMPRA %dL @ %.1f (SL %.1f | TP %.1f)", m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp);
         else if(m_slots[k].dir == -1)
            st = StringFormat("VENDA  %dL @ %.1f (SL %.1f | TP %.1f)", m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp);
         else if(m_slots[k].pend_dir != 0)
            st = StringFormat("ORDEM PENDENTE %s @ %.1f", (m_slots[k].pend_type==1?"LIMIT":"STOP"), m_slots[k].pend_price);

         hud += StringFormat(" %-34s | %-36s | Hoje: %d tr (R$ %.0f)\n",
                             m_slots[k].name, st, m_slots[k].trades_today, m_slots[k].closed_pnl_today_brl);
        }
      hud += "==========================================================";
      Comment(hud);
     }

   void              ComputeCausalNWE(const MqlRates &rates[], int total, int lookback, double bw, double mult,
                                      double &c1, double &u1, double &l1, double &s1,
                                      double &c2, double &u2, double &l2, double &s2)
     {
      if(total < lookback + 5)
         return;

      double w[];
      ArrayResize(w, lookback);
      for(int j=0; j<lookback; j++)
         w[j] = MathExp(-((double)(j * j)) / (2.0 * bw * bw));

      double centers[];
      ArrayResize(centers, total);
      for(int t=0; t<total; t++)
        {
         int lim = MathMin(t, lookback - 1);
         double ws = 0.0, wp = 0.0;
         for(int j=0; j<=lim; j++)
           {
            ws += w[j];
            wp += w[j] * rates[t - j].close;
           }
         centers[t] = wp / ws;
        }

      double errs[];
      ArrayResize(errs, total);
      for(int t=0; t<total; t++)
         errs[t] = MathAbs(rates[t].close - centers[t]);

      int last = total - 1;
      int prev = total - 2;

      double mae1 = 0.0;
      int lim1 = MathMin(last, lookback - 1);
      for(int j=0; j<=lim1; j++)
         mae1 += errs[last - j];
      mae1 /= (double)(lim1 + 1);

      double mae2 = 0.0;
      int lim2 = MathMin(prev, lookback - 1);
      for(int j=0; j<=lim2; j++)
         mae2 += errs[prev - j];
      mae2 /= (double)(lim2 + 1);

      c1 = centers[last];
      u1 = c1 + mae1 * mult;
      l1 = c1 - mae1 * mult;
      s1 = centers[last] - centers[prev];

      c2 = centers[prev];
      u2 = c2 + mae2 * mult;
      l2 = c2 - mae2 * mult;
      s2 = (prev >= 1) ? (centers[prev] - centers[prev - 1]) : 0.0;
     }

   void              ComputeRsi7(const MqlRates &rates[], int total, double &r1, double &r2)
     {
      if(total < 20)
        {
         r1 = 50.0;
         r2 = 50.0;
         return;
        }
      int last = total - 1;
      int prev = total - 2;

      double gains1 = 0.0, losses1 = 0.0;
      double gains2 = 0.0, losses2 = 0.0;
      for(int k=0; k<7; k++)
        {
         double d1 = rates[last - k].close - rates[last - k - 1].close;
         if(d1 > 0.0) gains1 += d1; else losses1 -= d1;

         double d2 = rates[prev - k].close - rates[prev - k - 1].close;
         if(d2 > 0.0) gains2 += d2; else losses2 -= d2;
        }
      r1 = (gains1 + losses1 > 1e-9) ? (100.0 * gains1 / (gains1 + losses1)) : 50.0;
      r2 = (gains2 + losses2 > 1e-9) ? (100.0 * gains2 / (gains2 + losses2)) : 50.0;
     }

   void              ComputeWinMetrics(datetime b1_time)
     {
      m_win_ret3_1 = 0.0;
      m_win_z_1 = 0.0;

      double wc[];
      int copied = CopyClose("WIN$N", PERIOD_M5, b1_time, 25, wc);
      if(copied < 25)
         copied = CopyClose("WINZ26", PERIOD_M5, b1_time, 25, wc);
      if(copied < 25)
         return;

      int last = copied - 1;
      if(wc[last - 3] > 0.0)
         m_win_ret3_1 = (wc[last] / wc[last - 3] - 1.0) * 10000.0;

      double rets[20];
      double sum = 0.0;
      for(int k=0; k<20; k++)
        {
         int idx = last - k;
         rets[k] = (wc[idx - 1] > 0.0) ? (wc[idx] / wc[idx - 1] - 1.0) : 0.0;
         sum += rets[k];
        }
      double mean = sum / 20.0;
      double sq = 0.0;
      for(int k=0; k<20; k++)
         sq += (rets[k] - mean) * (rets[k] - mean);
      double std = MathSqrt(sq / 20.0);
      if(std > 1e-9)
         m_win_z_1 = (rets[0] - mean) / std;
     }

   void              FindNearestLevel(const double &levels[], double price, double &min_dist, double &nearest_lvl)
     {
      min_dist = 999999.0;
      nearest_lvl = 0.0;
      int n = ArraySize(levels);
      for(int i=0; i<n; i++)
        {
         double d = MathAbs(levels[i] - price);
         if(d < min_dist)
           {
            min_dist = d;
            nearest_lvl = levels[i];
           }
        }
     }

   void              FindWdoStructuralTargets(double entry_px, int side, double front_run,
                                              double &tp_mid_px, double &tp_main_px)
     {
      int n_all = ArraySize(m_levels_all);
      int n_walls = ArraySize(m_levels_walls);
      double raw_mid = 0.0, raw_main = 0.0;

      if(side == 1)
        {
         int mid_idx_all = -1;
         for(int i=0; i<n_all; i++)
           {
            if(m_levels_all[i] >= entry_px + 7.5)
              {
               raw_mid = m_levels_all[i];
               mid_idx_all = i;
               break;
              }
           }
         if(raw_mid <= 0.0)
            raw_mid = entry_px + 18.0;

         for(int i=0; i<n_walls; i++)
           {
            if(m_levels_walls[i] >= entry_px + 14.0)
              {
               raw_main = m_levels_walls[i];
               break;
              }
           }
         if(raw_main > 0.0)
           {
            if(raw_main <= raw_mid + 3.5)
              {
               if(mid_idx_all >= 0 && (mid_idx_all + 1) < n_all)
                  raw_main = m_levels_all[mid_idx_all + 1];
               else
                  raw_main = raw_mid + 16.0;
              }
           }
         else if(mid_idx_all >= 0 && (mid_idx_all + 1) < n_all)
            raw_main = m_levels_all[mid_idx_all + 1];
         else
            raw_main = raw_mid + 16.0;

         tp_mid_px  = Round05(raw_mid  - front_run);
         tp_main_px = Round05(raw_main - front_run);
        }
      else
        {
         int mid_idx_all = -1;
         for(int i=n_all-1; i>=0; i--)
           {
            if(m_levels_all[i] <= entry_px - 7.5)
              {
               raw_mid = m_levels_all[i];
               mid_idx_all = i;
               break;
              }
           }
         if(raw_mid <= 0.0)
            raw_mid = entry_px - 18.0;

         for(int i=n_walls-1; i>=0; i--)
           {
            if(m_levels_walls[i] <= entry_px - 14.0)
              {
               raw_main = m_levels_walls[i];
               break;
              }
           }
         if(raw_main > 0.0)
           {
            if(raw_main >= raw_mid - 3.5)
              {
               if(mid_idx_all > 0)
                  raw_main = m_levels_all[mid_idx_all - 1];
               else
                  raw_main = raw_mid - 16.0;
              }
           }
         else if(mid_idx_all > 0)
            raw_main = m_levels_all[mid_idx_all - 1];
         else
            raw_main = raw_mid - 16.0;

         tp_mid_px  = Round05(raw_mid  + front_run);
         tp_main_px = Round05(raw_main + front_run);
        }
     }

   double            CalcWdoTargetPts(double entry_px, int side, int tp_type, double orig_tp_pts, double front_run=0.5)
     {
      if(tp_type == 0)
         return orig_tp_pts;
      double tp_mid, tp_main;
      FindWdoStructuralTargets(entry_px, side, front_run, tp_mid, tp_main);
      double target_px = (tp_type == 1) ? tp_mid : tp_main;
      double pts = MathAbs(target_px - entry_px);
      return MathMax(7.0, Round05(pts));
     }

   double            CalcWdoStage1StopPrice(int k)
     {
      int d = m_slots[k].dir;
      if((m_slots[k].be_mode == 1 || m_slots[k].be_mode == 2) && m_slots[k].def_wall > 0.0)
        {
         double buf = (m_slots[k].wall_shield_buf > 0.0) ? m_slots[k].wall_shield_buf : 1.5;
         return (d == 1) ? Round05(m_slots[k].def_wall - buf) : Round05(m_slots[k].def_wall + buf);
        }
      return (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].be_lock) : Round05(m_slots[k].avg_price - m_slots[k].be_lock);
     }

   double            FindWdoNextWallBehind(double entry_px, int dir, double min_d=8.0, double max_d=16.0, double fallback_d=11.0)
     {
      int n = ArraySize(m_levels_all);
      if(dir == 1)
        {
         for(int i=n-1; i>=0; i--)
           {
            double d = entry_px - m_levels_all[i];
            if(d >= min_d && d <= max_d)
               return Round05(d);
           }
        }
      else
        {
         for(int i=0; i<n; i++)
           {
            double d = m_levels_all[i] - entry_px;
            if(d >= min_d && d <= max_d)
               return Round05(d);
           }
        }
      return Round05(fallback_d);
     }

   void              OpenVirtualSingle(int k, int dir, double entry_p, datetime bar_t,
                                       double tp_pts, double sl_pts,
                                       double be_trig, double be_lock,
                                       double tr_trig, double tr_dist,
                                       int max_hold=16, bool is_intrabar=false,
                                       double pyr_trig=0.0, double pyr_lock=1.0,
                                       double def_wall=0.0, int be_mode=0, double wall_buf=0.0)
     {
      double p05 = Round05(entry_p);
      m_slots[k].dir = dir;
      m_slots[k].lots = 1;
      m_slots[k].leg_stage = 1;
      m_slots[k].p1_entry = p05;
      m_slots[k].avg_price = p05;
      m_slots[k].curr_sl = (dir == 1) ? Round05(p05 - sl_pts) : Round05(p05 + sl_pts);
      m_slots[k].curr_tp = (dir == 1) ? Round05(p05 + tp_pts) : Round05(p05 - tp_pts);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
      m_slots[k].be_stage2_active = false;
      m_slots[k].opened_intrabar = is_intrabar;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = bar_t;
      m_slots[k].be_trig = be_trig;
      m_slots[k].be_lock = be_lock;
      m_slots[k].tr_trig = tr_trig;
      m_slots[k].tr_dist = tr_dist;
      m_slots[k].max_hold_bars = max_hold;
      m_slots[k].pyr_trig = pyr_trig;
      m_slots[k].pyr_lock = pyr_lock;
      m_slots[k].init_sl_pts = sl_pts;
      m_slots[k].init_tp_pts = tp_pts;
      m_slots[k].def_wall = def_wall;
      m_slots[k].be_mode = be_mode;
      m_slots[k].wall_shield_buf = wall_buf;
      if(k == 11)
        {
         double s2 = FindWdoNextWallBehind(p05, dir, 8.0, 16.0, 11.0);
         double sl2_pts = 7.0;
         m_slots[k].step2_dist = s2;
         m_slots[k].step3_dist = 0.0;
         m_slots[k].lot1 = 1;
         m_slots[k].lot2 = 2;
         m_slots[k].lot3 = 0;
         m_slots[k].tp_avg_pts = 4.5;
         m_slots[k].max_sl_pts = sl2_pts;
         m_slots[k].init_sl_pts = s2 + sl2_pts;
         m_slots[k].curr_sl = (dir == 1) ? Round05(p05 - (s2 + sl2_pts)) : Round05(p05 + (s2 + sl2_pts));
        }
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_bars_left = 0;
      m_slots[k].real_synced = false;
      SaveVirtualStateToDisk();
     }

   void              OpenVirtualGrid(int k, int dir, double entry_p, datetime bar_t,
                                     double step2, double step3, int l1, int l2, int l3,
                                     double tp_avg, double max_sl, double be_trig, double be_lock=1.5, int max_hold=26)
     {
      double p05 = Round05(entry_p);
      m_slots[k].dir = dir;
      m_slots[k].lots = l1;
      m_slots[k].leg_stage = 1;
      m_slots[k].p1_entry = p05;
      m_slots[k].avg_price = p05;
      double worst_avg_offset = 0.0;
      if(l3 > 0)
         worst_avg_offset = (l2 * step2 + l3 * step3) / (double)(l1 + l2 + l3);
      else if(l2 > 0)
         worst_avg_offset = (l2 * step2) / (double)(l1 + l2);
      double init_sl_dist = MathMax(max_sl, worst_avg_offset + max_sl);
      m_slots[k].curr_sl = (dir == 1) ? Round05(p05 - init_sl_dist) : Round05(p05 + init_sl_dist);

      // No Portfólio Mix Campeão do Dólar, a Perna 1 dos Grids (WDO-11, 13, 14) mira na próxima MidWall Real!
      double p1_tp_pts = CalcWdoTargetPts(p05, dir, 1, tp_avg, 0.5);
      m_slots[k].curr_tp = (dir == 1) ? Round05(p05 + p1_tp_pts) : Round05(p05 - p1_tp_pts);

      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
      m_slots[k].be_stage2_active = false;
      m_slots[k].opened_intrabar = false;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = bar_t;
      m_slots[k].step2_dist = step2;
      m_slots[k].step3_dist = step3;
      m_slots[k].lot1 = l1;
      m_slots[k].lot2 = l2;
      m_slots[k].lot3 = l3;
      m_slots[k].tp_avg_pts = tp_avg;
      m_slots[k].max_sl_pts = max_sl;
      m_slots[k].be_trig = be_trig;
      m_slots[k].be_lock = be_lock;
      m_slots[k].tr_trig = 0.0;
      m_slots[k].tr_dist = 0.0;
      m_slots[k].max_hold_bars = max_hold;
      m_slots[k].pyr_trig = 0.0;
      m_slots[k].init_sl_pts = init_sl_dist;
      m_slots[k].init_tp_pts = p1_tp_pts;
      m_slots[k].def_wall = 0.0;
      m_slots[k].be_mode = 0;
      m_slots[k].wall_shield_buf = 0.0;
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_bars_left = 0;
      m_slots[k].real_synced = false;
      SaveVirtualStateToDisk();
     }

   void              CloseVirtualSlot(int k, double exit_price, string reason)
     {
      if(m_slots[k].dir == 0)
         return;
      double pts = (exit_price - m_slots[k].avg_price) * m_slots[k].dir;
      double pnl_brl = pts * m_slots[k].lots * 10.0 * m_lot_mult; // R$ 10.00 por ponto por mini-contrato WDO
      m_slots[k].closed_pnl_today_brl += pnl_brl;
      m_slots[k].closed_pnl_total_brl += pnl_brl;
      m_slots[k].trades_today += 1;
      m_slots[k].trades_total += 1;
      if(pnl_brl > 0.0)
         m_slots[k].wins_total += 1;

      PrintFormat("[JUMBA %s] FECHADO (%s) | Dir=%d | Lotes=%d | Entrada=%.1f | Saida=%.1f | Pts=%.1f | PnL=R$ %.2f | Acum=R$ %.2f",
                  m_slots[k].name, reason, m_slots[k].dir, m_slots[k].lots,
                  m_slots[k].avg_price, exit_price, pts, pnl_brl, m_slots[k].closed_pnl_total_brl);

      if(!MQLInfoInteger(MQL_OPTIMIZATION))
        {
         string fn = StringFormat("jumba_live_trades_audit_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
         int h = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ|FILE_SHARE_WRITE);
         if(h != INVALID_HANDLE)
           {
            FileSeek(h, 0, SEEK_END);
            long slot_magic = m_base_magic + k;
            string t_str = TimeToString(SafeTime(), TIME_DATE|TIME_SECONDS);
            string line = StringFormat("%s;WDO-%02d;%I64d;%s;%d;%d;%.1f;%.1f;%.2f;%s\n",
                                       t_str, k, slot_magic, _Symbol, m_slots[k].dir, m_slots[k].lots,
                                       m_slots[k].avg_price, exit_price, pnl_brl, reason);
            FileWriteString(h, line);
            FileClose(h);
           }
        }

      ResetSlotPosition(k);
      SaveVirtualStateToDisk();
     }

   double            GetTotalDailyPnLBRL()
     {
      double tot = 0.0;
      double cur_px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      for(int k=1; k<=16; k++)
        {
         tot += m_slots[k].closed_pnl_today_brl;
         if(m_slots[k].dir != 0 && cur_px > 0.0)
           {
            double open_pts = (cur_px - m_slots[k].avg_price) * m_slots[k].dir;
            tot += open_pts * m_slots[k].lots * 10.0 * m_lot_mult;
           }
        }
      return tot;
     }

   void              DeletePendingOrdersForSlot(int k)
     {
      long slot_magic = m_base_magic + k;
      for(int i=OrdersTotal()-1; i>=0; i--)
        {
         if(m_ord.SelectByIndex(i))
           {
            if(m_ord.Symbol() == _Symbol && m_ord.Magic() == slot_magic)
               m_trade.OrderDelete(m_ord.Ticket());
           }
        }
     }

   bool              HasPendingOrderForSlot(int k)
     {
      long slot_magic = m_base_magic + k;
      for(int i=OrdersTotal()-1; i>=0; i--)
        {
         if(m_ord.SelectByIndex(i))
           {
            if(m_ord.Symbol() == _Symbol && m_ord.Magic() == slot_magic)
               return true;
           }
        }
      return false;
     }

   double            GetLastEntryDealPrice(long magic)
     {
      if(!HistorySelect(TimeCurrent() - 600, TimeCurrent() + 60))
         return 0.0;
      int total = HistoryDealsTotal();
      for(int i=total-1; i>=0; i--)
        {
         ulong ticket = HistoryDealGetTicket(i);
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) == _Symbol &&
            HistoryDealGetInteger(ticket, DEAL_MAGIC) == magic &&
            HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_IN)
           {
            return HistoryDealGetDouble(ticket, DEAL_PRICE);
           }
        }
      return 0.0;
     }

   double            GetLastExitDealPrice(long magic, double fallback_px, string &reason_out)
     {
      reason_out = "SL_TP_SERVER";
      if(!HistorySelect(TimeCurrent() - 86400, TimeCurrent() + 60))
         return fallback_px;
      int total = HistoryDealsTotal();
      for(int i=total-1; i>=0; i--)
        {
         ulong ticket = HistoryDealGetTicket(i);
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) == _Symbol &&
            HistoryDealGetInteger(ticket, DEAL_MAGIC) == magic &&
            HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_OUT)
           {
            long r = HistoryDealGetInteger(ticket, DEAL_REASON);
            if(r == DEAL_REASON_SL)
               reason_out = "SL";
            else if(r == DEAL_REASON_TP)
               reason_out = "TP";
            double dp = HistoryDealGetDouble(ticket, DEAL_PRICE);
            long dtype = HistoryDealGetInteger(ticket, DEAL_TYPE);
            if(dtype == DEAL_TYPE_BUY && dp > 0.0)
               return Round05(dp - 0.5);
            return dp;
           }
        }
      return fallback_px;
     }

   void              SyncRealPositionsWithVirtualSlots()
     {
      // Trava Estrutural Absoluta: Conta HEDGING ou EA Individual SEMPRE opera em HEDGING_DIRECT_MAGIC!
      if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || GetSingleActiveSlotId() > 0)
         m_exec_mode = WDO_EXEC_HEDGING_DIRECT_MAGIC;

      if(m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            long slot_magic = m_base_magic + k;
            int max_base = GetMaxBaseLotsForSlot(k);
            if(m_slots[k].lots > max_base)
               m_slots[k].lots = max_base;
            if(m_slots[k].lots < 0)
               m_slots[k].lots = 0;

            double max_slot_vol = MathRound((double)max_base * m_lot_mult);
            double target_signed = MathRound((double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult);
            if(target_signed > max_slot_vol)  target_signed = max_slot_vol;
            if(target_signed < -max_slot_vol) target_signed = -max_slot_vol;

            double actual_signed = 0.0;
            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i))
                 {
                  if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                    {
                     if(m_pos.PositionType() == POSITION_TYPE_BUY)
                        actual_signed += m_pos.Volume();
                     else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                        actual_signed -= m_pos.Volume();
                    }
                 }
              }

            ulong now_ms = GetTickCount64();
            if(!MQLInfoInteger(MQL_TESTER) && m_last_order_ms[k] > 0)
              {
               ulong elapsed = now_ms - m_last_order_ms[k];
               // Enquanto a ordem para este mesmo alvo estiver liquidando na B3 (ate 5s) ou < 1.5s entre ordens, aguarda!
               if(elapsed < 1500 || (elapsed < 5000 && MathAbs(target_signed - m_last_sent_lots[k]) < 0.01))
                  continue;
              }

            if(MathAbs(target_signed) < 0.01 && MathAbs(actual_signed) >= 0.01)
              {
               m_trade.SetExpertMagicNumber(slot_magic);
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = 0.0;
               continue;
              }

            double sl_srv = (m_slots[k].dir == -1 && m_slots[k].curr_sl > 0.0) ? Round05(m_slots[k].curr_sl + 0.5) : m_slots[k].curr_sl;
            double tp_srv = (m_slots[k].dir == -1 && m_slots[k].curr_tp > 0.0) ? Round05(m_slots[k].curr_tp + 0.5) : m_slots[k].curr_tp;

            if((target_signed > 0.0 && actual_signed < -0.01) || (target_signed < 0.0 && actual_signed > 0.01))
              {
               m_trade.SetExpertMagicNumber(slot_magic);
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = 0.0;
               continue;
              }

            double diff = target_signed - actual_signed;
            if(MathAbs(diff) >= 0.99)
              {
               // Circuit Breaker: Nunca adiciona lotes se ja atingiu o teto maximo do slot!
               if(MathAbs(actual_signed) >= max_slot_vol - 0.01 && MathAbs(target_signed) > MathAbs(actual_signed))
                  continue;

               if(!MQLInfoInteger(MQL_TESTER))
                 {
                  if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
                    {
                     if(!m_slots[k].real_synced)
                        ResetSlotPosition(k);
                     continue;
                    }
                  double live_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                  double live_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                  if(!m_slots[k].real_synced && live_bid > 0.0 && live_ask > 0.0)
                    {
                     if(MathAbs(live_bid - m_slots[k].p1_entry) > 2.5)
                       {
                        PrintFormat("[JUMBA %s] Entrada cancelada por atraso/slippage (Sinal=%.1f vs Atual=%.1f)",
                                    m_slots[k].name, m_slots[k].p1_entry, live_bid);
                        ResetSlotPosition(k);
                        continue;
                       }
                     double fill_ref = (m_slots[k].dir == 1) ? Round05(live_ask) : Round05(live_bid);
                     m_slots[k].p1_entry = Round05(live_bid);
                     m_slots[k].avg_price = Round05(live_bid);
                     double sl_d = MathMax(7.0, m_slots[k].init_sl_pts);
                     double tp_d = MathMax(7.0, m_slots[k].init_tp_pts);
                     if(m_slots[k].dir == 1)
                       {
                        m_slots[k].curr_sl = Round05(fill_ref - sl_d);
                        m_slots[k].curr_tp = Round05(fill_ref + tp_d);
                        sl_srv = m_slots[k].curr_sl;
                        tp_srv = m_slots[k].curr_tp;
                       }
                     else
                       {
                        m_slots[k].curr_sl = Round05(fill_ref + sl_d);
                        m_slots[k].curr_tp = Round05(fill_ref - tp_d);
                        sl_srv = Round05(m_slots[k].curr_sl + 0.5);
                        tp_srv = Round05(m_slots[k].curr_tp + 0.5);
                       }
                    }
                 }

               DeletePendingOrdersForSlot(k);
               m_trade.SetExpertMagicNumber(slot_magic);
               double room = MathMax(0.0, max_slot_vol - MathAbs(actual_signed));
               double vol = MathRound(MathMin(MathAbs(diff), room));
               if(vol < 1.0 || vol > max_slot_vol)
                  continue;

               if(!m_guard.AllowOrder(vol, MathAbs(target_signed) < MathAbs(actual_signed)))
                 {
                  if(!m_slots[k].real_synced)
                     ResetSlotPosition(k);
                  continue;
                 }
               bool ok = false;
               if(diff > 0.0)
                  ok = m_trade.Buy(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
               else
                  ok = m_trade.Sell(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);

               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = target_signed;

               if(ok)
                  m_slots[k].real_synced = true;
               else if(!MQLInfoInteger(MQL_TESTER) && !m_slots[k].real_synced)
                  ResetSlotPosition(k);
              }

            if(MathAbs(target_signed) >= 0.99 && MathAbs(actual_signed) >= 0.99)
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                       {
                        double cur_sl = m_pos.StopLoss();
                        double cur_tp = m_pos.TakeProfit();
                        if(MathAbs(cur_sl - sl_srv) >= 0.4 || MathAbs(cur_tp - tp_srv) >= 0.4)
                          {
                           m_trade.SetExpertMagicNumber(slot_magic);
                           m_trade.PositionModify(m_pos.Ticket(), sl_srv, tp_srv);
                          }
                       }
                    }
                 }
              }
           }
        }
      else
        {
         // Modo NETTING (apenas para Conta Netting + EA Portfolio Master unico no grafico)
         if(!MQLInfoInteger(MQL_TESTER) && (GetTickCount64() - m_last_net_sync_ms) < 4000)
            return;

         double target_net = 0.0;
         for(int k=1; k<=16; k++)
           {
            if(m_slots[k].enabled && m_slots[k].dir != 0)
              {
               int c_lots = MathMin(GetMaxBaseLotsForSlot(k), MathMax(0, m_slots[k].lots));
               target_net += (double)(m_slots[k].dir * c_lots) * m_lot_mult;
              }
           }
         double max_port_net = 10.0 * m_lot_mult;
         if(target_net > max_port_net)  target_net = max_port_net;
         if(target_net < -max_port_net) target_net = -max_port_net;
         target_net = MathRound(target_net);

         double actual_net = 0.0;
         for(int i=PositionsTotal()-1; i>=0; i--)
           {
            if(m_pos.SelectByIndex(i))
              {
               if(m_pos.Symbol() == _Symbol)
                 {
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_net += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_net -= m_pos.Volume();
                 }
              }
           }

         double diff = target_net - actual_net;
         if(MathAbs(diff) >= 0.99)
           {
            m_trade.SetExpertMagicNumber(m_base_magic);
            double vol = MathRound(MathMin(MathAbs(diff), 3.0 * m_lot_mult));
            if(vol >= 1.0 && m_guard.AllowOrder(vol, MathAbs(target_net) < MathAbs(actual_net)))
              {
               if(diff > 0.0)
                  m_trade.Buy(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
               else
                  m_trade.Sell(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
               m_last_net_sync_ms = GetTickCount64();
              }
           }
        }
     }

   void              OnTickProcess()
     {
      datetime now = SafeTime();
      string today_str = DateStr(now);
      if(!MQLInfoInteger(MQL_TESTER))
        {
         string loc_str = DateStr(TimeLocal());
         if(loc_str > today_str)
            today_str = loc_str;
        }
      int t_min = TimeMinutes(now);
      if(m_guard.CheckGlobalKill())
        {
         if(m_show_hud)
            Comment("[JUMBA WDO] KILL-SWITCH ATIVO: " + m_guard.Reason());
         return;
        }

      if(!m_state_reconciled && !MQLInfoInteger(MQL_TESTER))
        {
         if(AccountInfoInteger(ACCOUNT_LOGIN) <= 0 || !TerminalInfoInteger(TERMINAL_CONNECTED))
            return;
         LoadVirtualStateFromDisk();
         ReconcileWithBrokerOnStartup();
         m_state_reconciled = true;
         RenderHudComment();
        }

      LoadDailyGexWalls(today_str);

      double last_px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(last_px <= 0.0)
         last_px = SymbolInfoDouble(_Symbol, SYMBOL_LAST);
      if(last_px <= 0.0)
         return;

      datetime curr_bar_time = iTime(_Symbol, PERIOD_M5, 0);
      if(curr_bar_time <= 0)
         return;
      if(m_last_m5_bar_time == 0)
         m_last_m5_bar_time = curr_bar_time;

      if(m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            long slot_magic = m_base_magic + k;

            double actual_lots = 0.0;
            double pos_open_px = 0.0;
            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                 {
                  pos_open_px = m_pos.PriceOpen();
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_lots += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_lots -= m_pos.Volume();
                 }
              }

            if(m_slots[k].dir == 0 && m_slots[k].pend_dir != 0)
              {
               if(MathAbs(actual_lots) >= 0.99)
                 {
                  double fill_px = (m_slots[k].pend_dir == 1 && pos_open_px > 0.0) ? Round05(pos_open_px - 0.5) : ((pos_open_px > 0.0) ? pos_open_px : m_slots[k].pend_price);
                  double pt_save = m_slots[k].pyr_trig;
                  double pl_save = m_slots[k].pyr_lock;
                  OpenVirtualSingle(k, m_slots[k].pend_dir, fill_px, m_slots[k].pend_bar_time,
                                    m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts,
                                    m_slots[k].be_trig, m_slots[k].be_lock,
                                    m_slots[k].tr_trig, m_slots[k].tr_dist,
                                    m_slots[k].max_hold_bars, true, pt_save, pl_save,
                                    m_slots[k].pend_def_wall, m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf);
                  m_slots[k].real_synced = true;
                  m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                  if(k == 16)
                     m_slots[k].last_trade_date = today_str;
                 }
               else if(!HasPendingOrderForSlot(k))
                 {
                  string rsn = "SL_TP_INTRABAR";
                  double deal_px = GetLastExitDealPrice(slot_magic, m_slots[k].pend_price, rsn);
                  if(rsn == "SL" || rsn == "TP")
                    {
                     double pt_save = m_slots[k].pyr_trig;
                     double pl_save = m_slots[k].pyr_lock;
                     OpenVirtualSingle(k, m_slots[k].pend_dir, m_slots[k].pend_price, m_slots[k].pend_bar_time,
                                       m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts,
                                       m_slots[k].be_trig, m_slots[k].be_lock,
                                       m_slots[k].tr_trig, m_slots[k].tr_dist,
                                       m_slots[k].max_hold_bars, true, pt_save, pl_save,
                                       m_slots[k].pend_def_wall, m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf);
                     m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                     if(k == 16)
                        m_slots[k].last_trade_date = today_str;
                     CloseVirtualSlot(k, deal_px, rsn);
                    }
                 }
              }
            else if(m_slots[k].dir != 0 && m_slots[k].real_synced && MathAbs(actual_lots) < 0.01)
              {
               if(!MQLInfoInteger(MQL_TESTER) && m_last_order_ms[k] > 0 && (GetTickCount64() - m_last_order_ms[k]) < 5000)
                  continue;
               string rsn = "SL_TP_SERVER";
               double exit_px = GetLastExitDealPrice(slot_magic, last_px, rsn);
               CloseVirtualSlot(k, exit_px, rsn);
              }
           }
        }

      double total_day_pnl = GetTotalDailyPnLBRL();
      if(t_min >= 1035 || (m_max_daily_loss_brl > 0.0 && total_day_pnl <= -m_max_daily_loss_brl))
        {
         string rsn = (t_min >= 1035) ? "EOD_1715" : "MAX_DAILY_LOSS";
         double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         for(int k=1; k<=16; k++)
           {
            if(m_slots[k].pend_dir != 0)
              {
               DeletePendingOrdersForSlot(k);
               m_slots[k].pend_dir = 0;
               m_slots[k].pend_bars_left = 0;
              }
            if(m_slots[k].dir != 0)
               CloseVirtualSlot(k, px, rsn);
           }
         SyncRealPositionsWithVirtualSlots();
         return;
        }

      if(curr_bar_time != m_last_m5_bar_time)
        {
         OnNewM5Bar(curr_bar_time, today_str);
         m_last_m5_bar_time = curr_bar_time;
        }

      for(int k=1; k<=16; k++)
        {
         if(!m_slots[k].enabled)
            continue;

         if(m_slots[k].dir == 0 && m_slots[k].pend_dir != 0 && m_slots[k].pend_bar_time == curr_bar_time)
           {
            if(m_exec_mode == WDO_EXEC_NETTING_VIRTUAL_SYNC || !HasPendingOrderForSlot(k))
              {
               bool triggered = false;
               if(m_slots[k].pend_type == 1)
                 {
                  if(m_slots[k].pend_dir == 1 && last_px <= m_slots[k].pend_price)
                     triggered = true;
                  else if(m_slots[k].pend_dir == -1 && last_px >= m_slots[k].pend_price)
                     triggered = true;
                 }
               else if(m_slots[k].pend_type == 2)
                 {
                  if(m_slots[k].pend_dir == 1 && last_px >= m_slots[k].pend_price)
                     triggered = true;
                  else if(m_slots[k].pend_dir == -1 && last_px <= m_slots[k].pend_price)
                     triggered = true;
                 }

               if(triggered)
                 {
                  double pt_save = m_slots[k].pyr_trig;
                  double pl_save = m_slots[k].pyr_lock;
                  OpenVirtualSingle(k, m_slots[k].pend_dir, m_slots[k].pend_price, curr_bar_time,
                                    m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts,
                                    m_slots[k].be_trig, m_slots[k].be_lock,
                                    m_slots[k].tr_trig, m_slots[k].tr_dist,
                                    m_slots[k].max_hold_bars, true, pt_save, pl_save,
                                    m_slots[k].pend_def_wall, m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf);
                  m_slots[k].last_entry_bar_time = curr_bar_time;
                  if(k == 16)
                     m_slots[k].last_trade_date = today_str;
                 }
              }
           }

         if(m_slots[k].dir != 0)
           {
            int d = m_slots[k].dir;

            if(k == 11 || k == 13 || k == 14)
              {
               if(m_slots[k].leg_stage == 1 && !m_slots[k].be_active && m_slots[k].lot2 > 0 && m_slots[k].step2_dist > 0.0)
                 {
                  double p2_lvl = (d == 1) ? Round05(m_slots[k].p1_entry - m_slots[k].step2_dist) : Round05(m_slots[k].p1_entry + m_slots[k].step2_dist);
                  if((d == 1 && last_px <= p2_lvl) || (d == -1 && last_px >= p2_lvl))
                    {
                     int new_lots = m_slots[k].lot1 + m_slots[k].lot2;
                     m_slots[k].avg_price = Round05((m_slots[k].p1_entry * m_slots[k].lot1 + p2_lvl * m_slots[k].lot2) / (double)new_lots);
                     m_slots[k].lots = new_lots;
                     m_slots[k].leg_stage = 2;
                     m_slots[k].be_active = false;
                     m_slots[k].max_fav_pts = 0.0;
                     m_slots[k].be_trig = 2.5;
                     m_slots[k].be_lock = 0.5;
                     m_slots[k].be_mode = 0;
                     m_slots[k].curr_tp = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].tp_avg_pts) : Round05(m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                     m_slots[k].curr_sl = (d == 1) ? Round05(p2_lvl - m_slots[k].max_sl_pts) : Round05(p2_lvl + m_slots[k].max_sl_pts);
                     PrintFormat("[JUMBA %s] SMART GRID PERNA 2 NA NEXT_WALL EXECUTADA @ %.1f | Lotes=%d | PM=%.1f | Novo TP=%.1f | Novo SL=%.1f",
                                 m_slots[k].name, p2_lvl, m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_tp, m_slots[k].curr_sl);
                     SaveVirtualStateToDisk();
                    }
                 }
               if(m_slots[k].leg_stage == 2 && m_slots[k].lot3 > 0)
                 {
                  double p3_lvl = (d == 1) ? Round05(m_slots[k].p1_entry - m_slots[k].step3_dist) : Round05(m_slots[k].p1_entry + m_slots[k].step3_dist);
                  if((d == 1 && last_px <= p3_lvl) || (d == -1 && last_px >= p3_lvl))
                    {
                     int new_lots = m_slots[k].lots + m_slots[k].lot3;
                     m_slots[k].avg_price = Round05((m_slots[k].avg_price * m_slots[k].lots + p3_lvl * m_slots[k].lot3) / (double)new_lots);
                     m_slots[k].lots = new_lots;
                     m_slots[k].leg_stage = 3;
                     m_slots[k].be_active = false;
                     m_slots[k].max_fav_pts = 0.0;
                     m_slots[k].curr_tp = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].tp_avg_pts) : Round05(m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                     m_slots[k].curr_sl = (d == 1) ? Round05(m_slots[k].avg_price - m_slots[k].max_sl_pts) : Round05(m_slots[k].avg_price + m_slots[k].max_sl_pts);
                    }
                 }
              }

            if(m_exec_mode == WDO_EXEC_NETTING_VIRTUAL_SYNC)
              {
               if(d == 1)
                 {
                  if(last_px <= m_slots[k].curr_sl) { CloseVirtualSlot(k, m_slots[k].curr_sl, "SL"); continue; }
                  if(last_px >= m_slots[k].curr_tp) { CloseVirtualSlot(k, m_slots[k].curr_tp, "TP"); continue; }
                 }
               else
                 {
                  if(last_px >= m_slots[k].curr_sl) { CloseVirtualSlot(k, m_slots[k].curr_sl, "SL"); continue; }
                  if(last_px <= m_slots[k].curr_tp) { CloseVirtualSlot(k, m_slots[k].curr_tp, "TP"); continue; }
                 }
              }
           }
        }

      SyncRealPositionsWithVirtualSlots();
     }

   //+------------------------------------------------------------------+
   //| Avaliação de Fechamento de Barra M5 (MIX CAMPEÃO WDO-01 A WDO-16)|
   //+------------------------------------------------------------------+
   void              OnNewM5Bar(datetime new_bar_time, string today_str)
     {
      MqlRates rates[];
      int copied = CopyRates(_Symbol, PERIOD_M5, 1, 110, rates);
      if(copied < 60 || ArraySize(m_levels_all) == 0)
         return;

      MqlRates r0[];
      double new_bar_open = (CopyRates(_Symbol, PERIOD_M5, 0, 1, r0) >= 1) ? r0[0].open : rates[copied - 1].close;

      MqlRates b1 = rates[copied - 1];
      string b1_date = DateStr(b1.time);
      int b1_tmin = TimeMinutes(b1.time);
      int new_tmin = TimeMinutes(new_bar_time);

      ComputeCausalNWE(rates, copied, 50, 5.0, 2.0,
                       m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1,
                       m_n50_c_2, m_n50_u_2, m_n50_l_2, m_n50_s_2);
      ComputeCausalNWE(rates, copied, 30, 3.0, 1.6,
                       m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1,
                       m_n30_c_2, m_n30_u_2, m_n30_l_2, m_n30_s_2);
      ComputeRsi7(rates, copied, m_rsi7_1, m_rsi7_2);
      ComputeWinMetrics(b1.time);

      for(int k=1; k<=16; k++)
        {
         // 1. Gerencia ordens pendentes multi-barra (valid_bars=2 nas vagas WDO-03, 06, 08, 09)
         if(m_slots[k].pend_dir != 0)
           {
            m_slots[k].pend_bars_left -= 1;
            if(m_slots[k].pend_bars_left <= 0 || b1_date != today_str || new_tmin >= 1005)
              {
               DeletePendingOrdersForSlot(k);
               m_slots[k].pend_dir = 0;
               m_slots[k].pend_bars_left = 0;
              }
            else
              {
               DeletePendingOrdersForSlot(k);
               ArmPendingOrder(k, m_slots[k].pend_dir, m_slots[k].pend_type, m_slots[k].pend_price, new_bar_time, new_bar_open,
                               m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts, m_slots[k].be_trig, m_slots[k].be_lock,
                               m_slots[k].tr_trig, m_slots[k].tr_dist, m_slots[k].max_hold_bars,
                               m_slots[k].pend_def_wall, m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf,
                               m_slots[k].pend_bars_left);
              }
           }

         // 2. Atualiza BE (BE_ZERO / BE_WALL_SHIELD / BE_WALL_2STAGE), Trailing Stop, Piramidação e Time Stop
         if(m_slots[k].dir != 0)
           {
            int d = m_slots[k].dir;

            if(m_slots[k].opened_intrabar)
              {
               double fav_c = (d == 1) ? (b1.close - m_slots[k].avg_price) : (m_slots[k].avg_price - b1.close);
               if(fav_c > m_slots[k].max_fav_pts)
                  m_slots[k].max_fav_pts = fav_c;
               if(m_slots[k].be_trig > 0.0 && !m_slots[k].be_active && m_slots[k].max_fav_pts >= m_slots[k].be_trig)
                 {
                  double cand_sl = CalcWdoStage1StopPrice(k);
                  if((d == 1 && new_bar_open > cand_sl + 0.5) || (d == -1 && new_bar_open < cand_sl - 0.5))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                     m_slots[k].be_active = true;
                    }
                 }
               if(m_slots[k].be_mode == 2 && !m_slots[k].be_stage2_active && m_slots[k].max_fav_pts >= MathMax(11.5, m_slots[k].be_trig + 4.5))
                 {
                  double cand_sl2 = (d == 1) ? Round05(m_slots[k].avg_price + 2.5) : Round05(m_slots[k].avg_price - 2.5);
                  if((d == 1 && new_bar_open > cand_sl2 + 0.5) || (d == -1 && new_bar_open < cand_sl2 - 0.5))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl2) : MathMin(m_slots[k].curr_sl, cand_sl2);
                     m_slots[k].be_stage2_active = true;
                     m_slots[k].be_active = true;
                    }
                 }
               m_slots[k].opened_intrabar = false;
              }
            else
              {
               m_slots[k].bars_held += 1;

               double fav = (d == 1) ? (b1.high - m_slots[k].avg_price) : (m_slots[k].avg_price - b1.low);
               if(fav > m_slots[k].max_fav_pts)
                  m_slots[k].max_fav_pts = fav;

               // Estágio 1 do Break-Even (BE_ZERO ou BE_WALL_SHIELD / BE_WALL_2STAGE)
               if(m_slots[k].be_trig > 0.0 && !m_slots[k].be_active && m_slots[k].max_fav_pts >= m_slots[k].be_trig)
                 {
                  double cand_sl = CalcWdoStage1StopPrice(k);
                  if((d == 1 && new_bar_open > cand_sl + 0.5) || (d == -1 && new_bar_open < cand_sl - 0.5))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                     m_slots[k].be_active = true;
                    }
                 }

               // Estágio 2 do Break-Even (BE_WALL_2STAGE: avança para avg_price ± 2.5 pts após andar 11.5+ pts)
               if(m_slots[k].be_mode == 2 && !m_slots[k].be_stage2_active && m_slots[k].max_fav_pts >= MathMax(11.5, m_slots[k].be_trig + 4.5))
                 {
                  double cand_sl2 = (d == 1) ? Round05(m_slots[k].avg_price + 2.5) : Round05(m_slots[k].avg_price - 2.5);
                  if((d == 1 && new_bar_open > cand_sl2 + 0.5) || (d == -1 && new_bar_open < cand_sl2 - 0.5))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl2) : MathMin(m_slots[k].curr_sl, cand_sl2);
                     m_slots[k].be_stage2_active = true;
                     m_slots[k].be_active = true;
                    }
                 }

               // Trailing Stop
               if(m_slots[k].tr_trig > 0.0 && m_slots[k].max_fav_pts >= m_slots[k].tr_trig)
                 {
                  double cand_sl = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].max_fav_pts - m_slots[k].tr_dist)
                                            : Round05(m_slots[k].avg_price - m_slots[k].max_fav_pts + m_slots[k].tr_dist);
                  if((d == 1 && new_bar_open > cand_sl + 0.5) || (d == -1 && new_bar_open < cand_sl - 0.5))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                    }
                 }

               // WDO-12: Piramidação no lucro 1+1 lote
               if(k == 12 && m_slots[k].leg_stage == 1 && m_slots[k].pyr_trig > 0.0)
                 {
                  double fav_close = (d == 1) ? (b1.close - m_slots[k].p1_entry) : (m_slots[k].p1_entry - b1.close);
                  if(fav_close >= m_slots[k].pyr_trig)
                    {
                     m_slots[k].avg_price = Round05(0.5 * (m_slots[k].p1_entry + new_bar_open));
                     m_slots[k].lots = 2;
                     m_slots[k].leg_stage = 2;
                     double cand_sl = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].pyr_lock) : Round05(m_slots[k].avg_price - m_slots[k].pyr_lock);
                     if((d == 1 && new_bar_open > cand_sl + 0.5) || (d == -1 && new_bar_open < cand_sl - 0.5))
                        m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                    }
                 }

               if(k <= 15 && m_slots[k].bars_held >= m_slots[k].max_hold_bars)
                 {
                  CloseVirtualSlot(k, new_bar_open, "TIME_STOP");
                  continue;
                 }
              }
           }
        }

      if(b1_date != today_str)
         return;

      if(!MQLInfoInteger(MQL_TESTER))
        {
         if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
            return;
         double live_b = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(live_b > 0.0)
           {
            if(MathAbs(live_b - new_bar_open) > 2.5)
               return;
            new_bar_open = Round05(live_b);
           }
        }

      double d_l, lvl_s, d_h, lvl_r;
      FindNearestLevel(m_levels_all, b1.low,  d_l, lvl_s);
      FindNearestLevel(m_levels_all, b1.high, d_h, lvl_r);
      double dw_l_main, w_s_main, dw_h_main, w_r_main;
      FindNearestLevel(m_levels_walls, b1.low,  dw_l_main, w_s_main);
      FindNearestLevel(m_levels_walls, b1.high, dw_h_main, w_r_main);

      double bw50 = MathMax(1.0, m_n50_u_1 - m_n50_l_1);
      double pos50 = (b1.close - m_n50_l_1) / bw50;
      double bw30 = MathMax(1.0, m_n30_u_1 - m_n30_l_1);
      double pos30 = (b1.close - m_n30_l_1) / bw30;
      double body1 = b1.close - b1.open;
      double mid_b1 = Round05(0.5 * (b1.high + b1.low));
      double tp_calc = 0.0;

      // =====================================================================
      // WDO-01: 3-Pilares (Scalper Híbrido NY + BE_Wall(1.0) + TP_MidWall) | Ret/DD = 4.25
      // =====================================================================
      if(false && m_slots[1].enabled && m_slots[1].dir == 0 && m_slots[1].pend_dir == 0)
        {
         bool ent1 = false;
         if(m_slots[1].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10))
                 {
                  tp_calc = CalcWdoTargetPts(new_bar_open, -1, 1, 18.0);
                  OpenVirtualSingle(1, -1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false, 0.0, 1.0, lvl, 1, 1.0);
                  m_slots[1].last_entry_bar_time = b1.time;
                  ent1 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10))
                 {
                  tp_calc = CalcWdoTargetPts(new_bar_open, 1, 1, 18.0);
                  OpenVirtualSingle(1, 1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false, 0.0, 1.0, lvl, 1, 1.0);
                  m_slots[1].last_entry_bar_time = b1.time;
                  ent1 = true;
                  break;
                 }
              }
           }
         if(!ent1 && WindowOk(new_tmin, "NY_1000_1630"))
           {
            if(pos50 >= 0.65 && d_h <= 3.5 && b1.close < lvl_r && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
              {
               tp_calc = CalcWdoTargetPts(lvl_r, -1, 1, 24.0);
               ArmPendingOrder(1, -1, 1, lvl_r, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_r, 1, 1.0, 1);
              }
            else if(pos50 <= 0.35 && d_l <= 3.5 && b1.close > lvl_s && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
              {
               tp_calc = CalcWdoTargetPts(lvl_s, 1, 1, 24.0);
               ArmPendingOrder(1, 1, 1, lvl_s, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_s, 1, 1.0, 1);
              }
           }
        }

      // =====================================================================
      // WDO-02: 3-Pilares (Scalper CORE + Limit_ExtB1 + BE_2Stage(1.0) + TP_MidWall) | Ret/DD = 4.60
      // =====================================================================
      if(m_slots[2].enabled && m_slots[2].dir == 0 && m_slots[2].pend_dir == 0)
        {
         int sig2 = 0;
         double wall2 = 0.0, sl2 = 13.5, be2 = 7.5, trt2 = 14.5, trd2 = 5.5;
         int mh2 = 16;
         if(m_slots[2].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10) && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip - 2.0))
                 { sig2 = -1; wall2 = lvl; sl2 = 11.0; be2 = 6.5; trt2 = 11.0; trd2 = 4.5; mh2 = 15; break; }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10) && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip + 2.0))
                 { sig2 = 1;  wall2 = lvl; sl2 = 11.0; be2 = 6.5; trt2 = 11.0; trd2 = 4.5; mh2 = 15; break; }
              }
           }
         if(sig2 == 0 && WindowOk(new_tmin, "CORE_09_1615"))
           {
            if(pos50 >= 0.64 && d_h <= 3.5 && b1.close < (lvl_r - 0.5) && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
              { sig2 = -1; wall2 = lvl_r; }
            else if(pos50 <= 0.36 && d_l <= 3.5 && b1.close > (lvl_s + 0.5) && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
              { sig2 = 1;  wall2 = lvl_s; }
           }
         if(sig2 != 0)
           {
            double p2_lim = (sig2 == 1) ? Round05(b1.low + 0.5) : Round05(b1.high - 0.5);
            tp_calc = CalcWdoTargetPts(p2_lim, sig2, 1, 25.0);
            ArmPendingOrder(2, sig2, 1, p2_lim, new_bar_time, new_bar_open, tp_calc, sl2, be2, 1.5, trt2, trd2, mh2, wall2, 2, 1.0, 1);
           }
        }

      // =====================================================================
      // WDO-03: NOVO-WDO-03 (Arbitragem WIN+WDO MainWall | Limit 50%B1(2b) | BE_2Stage(1.5) | TP_MidWall) | Ret/DD = 12.36
      // =====================================================================
      if(m_slots[3].enabled && m_slots[3].dir == 0 && m_slots[3].pend_dir == 0 && WindowOk(b1_tmin, "CORE_09_1615") && ArraySize(m_levels_walls) > 0)
        {
         int sig3 = 0;
         double wall3 = 0.0;
         if(dw_l_main <= 4.0 && pos50 <= 0.36 && (m_win_ret3_1 <= -5.0 || m_win_z_1 <= -0.8) && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip + 8.0))
           { sig3 = 1; wall3 = w_s_main; }
         else if(dw_h_main <= 4.0 && pos50 >= 0.64 && (m_win_ret3_1 >= 5.0 || m_win_z_1 >= 0.8) && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip - 8.0))
           { sig3 = -1; wall3 = w_r_main; }
         if(sig3 != 0)
           {
            tp_calc = CalcWdoTargetPts(mid_b1, sig3, 1, 22.0);
            ArmPendingOrder(3, sig3, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 13.5, 5.0, 16, wall3, 2, 1.5, 2);
           }
        }

      // =====================================================================
      // WDO-04: 3-Pilares MainWall (Limit 50%B1 | BE_2Stage(1.5) | TP_MainWall nas MainWalls) | Ret/DD = 3.94
      // =====================================================================
      if(m_slots[4].enabled && m_slots[4].dir == 0 && m_slots[4].pend_dir == 0 && m_slots[4].trades_today < 1 && WindowOk(new_tmin, "FULL_09_17") && m_gamma_flip > 0.0 && ArraySize(m_levels_walls) > 0)
        {
         if(b1.close > m_gamma_flip + 4.0 && pos50 >= 0.65 && dw_h_main <= 4.0 && b1.close < w_r_main)
           {
            tp_calc = CalcWdoTargetPts(mid_b1, -1, 2, 25.0);
            ArmPendingOrder(4, -1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 14.0, 7.5, 1.5, 15.0, 5.5, 18, w_r_main, 2, 1.5, 1);
           }
         else if(b1.close < m_gamma_flip - 4.0 && pos50 <= 0.35 && dw_l_main <= 4.0 && b1.close > w_s_main)
           {
            tp_calc = CalcWdoTargetPts(mid_b1, 1, 2, 25.0);
            ArmPendingOrder(4, 1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 14.0, 7.5, 1.5, 15.0, 5.5, 18, w_s_main, 2, 1.5, 1);
           }
        }

      // =====================================================================
      // WDO-05: 3-Pilares (Cluster NWE30+NWE50+Wall + Limit_ExtB1 + TP_MidWall) | Ret/DD = 3.78
      // =====================================================================
      if(false && m_slots[5].enabled && m_slots[5].dir == 0 && m_slots[5].pend_dir == 0)
        {
         int sig5 = 0;
         double wall5 = 0.0, sl5 = 13.5, be5 = 7.5, trt5 = 14.0, trd5 = 5.5;
         if(m_slots[5].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n30_s_1 >= 0.15 && m_n50_s_1 >= 0.10 && b1.close < (m_n30_u_1 - bw30 * 0.10))
                 { sig5 = -1; wall5 = lvl; sl5 = 11.0; be5 = 6.5; trt5 = 11.0; trd5 = 4.5; break; }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n30_s_1 <= -0.15 && m_n50_s_1 <= -0.10 && b1.close > (m_n30_l_1 + bw30 * 0.10))
                 { sig5 = 1;  wall5 = lvl; sl5 = 11.0; be5 = 6.5; trt5 = 11.0; trd5 = 4.5; break; }
              }
           }
         if(sig5 == 0 && WindowOk(new_tmin, "CORE_09_1615"))
           {
            if(pos30 >= 0.65 && pos50 >= 0.62 && d_h <= 3.5 && b1.close < lvl_r && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
              { sig5 = -1; wall5 = lvl_r; }
            else if(pos30 <= 0.35 && pos50 <= 0.38 && d_l <= 3.5 && b1.close > lvl_s && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
              { sig5 = 1;  wall5 = lvl_s; }
           }
         if(sig5 != 0)
           {
            double p5_lim = (sig5 == 1) ? Round05(b1.low + 0.5) : Round05(b1.high - 0.5);
            tp_calc = CalcWdoTargetPts(p5_lim, sig5, 1, 24.0);
            ArmPendingOrder(5, sig5, 1, p5_lim, new_bar_time, new_bar_open, tp_calc, sl5, be5, 1.5, trt5, trd5, 16, wall5, 0, 0.0, 1);
           }
        }

      // =====================================================================
      // WDO-06: WF-BRENO-ABSORPTION-WICK (Pavio Exaustao>=2.0p + RSI7 35/65 nas MainWalls | Limit 50%B1(2b) | BE_Wall(1.5) | TP_MidWall)
      // Walk-Forward: IS_PF=2.97 | OOS_PF=1.78 | Last10=+R$420 | WallRank=1/11 | Eleva Port Ret/DD p/ 14.86
      // =====================================================================
      if(m_slots[6].enabled && m_slots[6].dir == 0 && m_slots[6].pend_dir == 0 && m_slots[6].trades_today < 2 && WindowOk(b1_tmin, "CORE_09_1615") && ArraySize(m_levels_walls) > 0)
        {
         int sig6 = 0;
         double wall6 = 0.0;
         double w_bot6 = MathMin(b1.open, b1.close) - b1.low;
         double w_top6 = b1.high - MathMax(b1.open, b1.close);
         if(dw_l_main <= 3.0 && w_bot6 >= 2.0 && m_rsi7_1 <= 35.0 && b1.close > b1.open)
           { sig6 = 1; wall6 = w_s_main; }
         else if(dw_h_main <= 3.0 && w_top6 >= 2.0 && m_rsi7_1 >= 65.0 && b1.close < b1.open)
           { sig6 = -1; wall6 = w_r_main; }
         if(sig6 != 0)
           {
            tp_calc = CalcWdoTargetPts(mid_b1, sig6, 1, 22.0);
            ArmPendingOrder(6, sig6, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 12.5, 6.5, 1.5, 14.5, 5.5, 20, wall6, 1, 1.5, 2);
           }
        }

      // =====================================================================
      // WDO-07: 3-Pilares (Absorção Mkt Wall NY + BE_Wall(1.0) + TP_MidWall) | Ret/DD = 3.64
      // =====================================================================
      if(m_slots[7].enabled && m_slots[7].dir == 0 && m_slots[7].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10))
              {
               tp_calc = CalcWdoTargetPts(new_bar_open, -1, 1, 19.0);
               OpenVirtualSingle(7, -1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false, 0.0, 1.0, lvl, 1, 1.0);
               m_slots[7].last_entry_bar_time = b1.time;
               break;
              }
            if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10))
              {
               tp_calc = CalcWdoTargetPts(new_bar_open, 1, 1, 19.0);
               OpenVirtualSingle(7, 1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false, 0.0, 1.0, lvl, 1, 1.0);
               m_slots[7].last_entry_bar_time = b1.time;
               break;
              }
           }
        }

      // =====================================================================
      // WDO-08: NOVO-WDO-08 (Absorção MainWall+Gamma | Limit 50%B1(2b) | BE_2Stage(1.5) | TP_MainWall) | Ret/DD = 4.43
      // =====================================================================
      if(m_slots[8].enabled && m_slots[8].dir == 0 && m_slots[8].pend_dir == 0 && WindowOk(b1_tmin, "NO_LUNCH") && ArraySize(m_levels_walls) > 0)
        {
         int sig8 = 0;
         double wall8 = 0.0;
         if(dw_l_main <= 3.5 && pos50 <= 0.30 && b1.close > b1.open && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
           { sig8 = 1; wall8 = w_s_main; }
         else if(dw_h_main <= 3.5 && pos50 >= 0.70 && b1.close < b1.open && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
           { sig8 = -1; wall8 = w_r_main; }
         if(sig8 != 0)
           {
            tp_calc = CalcWdoTargetPts(mid_b1, sig8, 2, 25.0);
            ArmPendingOrder(8, sig8, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 13.5, 5.0, 16, wall8, 2, 1.5, 2);
           }
        }

      // =====================================================================
      // WDO-09: NOVO-WDO-09 (Cluster NWE30+50 Wall | Limit Wall+0.5(2b) | BE_2Stage(1.5) | TP_MidWall) | Ret/DD = 4.31
      // =====================================================================
      if(m_slots[9].enabled && m_slots[9].dir == 0 && m_slots[9].pend_dir == 0 && m_slots[9].trades_today < 2 && WindowOk(b1_tmin, "NO_LUNCH"))
        {
         int sig9 = 0;
         double wall9 = 0.0;
         if(d_l <= 5.0 && pos30 <= 0.32 && pos50 <= 0.35 && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip + 5.0))
           { sig9 = 1; wall9 = lvl_s; }
         else if(d_h <= 5.0 && pos30 >= 0.68 && pos50 >= 0.65 && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip - 5.0))
           { sig9 = -1; wall9 = lvl_r; }
         if(sig9 != 0)
           {
            double p9_lim = (sig9 == 1) ? Round05(wall9 + 0.5) : Round05(wall9 - 0.5);
            tp_calc = CalcWdoTargetPts(p9_lim, sig9, 1, 22.0);
            ArmPendingOrder(9, sig9, 1, p9_lim, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 13.5, 5.0, 16, wall9, 2, 1.5, 2);
           }
        }

      // =====================================================================
      // WDO-10: WDO_S2 (Reversão Banda Extrema NWE30 12:00-14:30 + Escudo Mín/Máx Candle ± 1.5pt)
      // 105 Trades | WR = 59.0% | PF = 1.97 | Net = +R$2.490 | MDD = R$255 | Ret/DD = 9.76 (Reduz MDD WDO de R$1.960 p/ R$1.740!)
      // =====================================================================
      if(m_slots[10].enabled && m_slots[10].dir == 0 && m_slots[10].pend_dir == 0 && m_slots[10].trades_today < 3 && b1_tmin >= 720 && b1_tmin <= 870)
        {
         if(m_slots[10].last_entry_bar_time == 0 || (b1.time - m_slots[10].last_entry_bar_time) >= 900)
           {
            double mae30_10 = MathMax(1.2, (m_n30_u_1 - m_n30_c_1) / 1.6);
            double pos_nwe30_10 = (b1.close - m_n30_c_1) / mae30_10;
            double rng10 = MathMax(0.5, b1.high - b1.low);
            double lw10  = MathMin(b1.open, b1.close) - b1.low;
            double uw10  = b1.high - MathMax(b1.open, b1.close);

            if(pos_nwe30_10 <= -0.75 && b1.close >= (b1.low + 0.50 * rng10) && (lw10 >= 0.25 * rng10 || b1.close > b1.open))
              {
               OpenVirtualSingle(10, 1, new_bar_open, new_bar_time, 16.0, 10.0, 5.5, 1.0, 0.0, 0.0, 24, false, 0.0, 1.0, b1.low, 1, 1.5);
               m_slots[10].last_entry_bar_time = b1.time;
              }
            else if(pos_nwe30_10 >= 0.75 && b1.close <= (b1.high - 0.50 * rng10) && (uw10 >= 0.25 * rng10 || b1.close < b1.open))
              {
               OpenVirtualSingle(10, -1, new_bar_open, new_bar_time, 16.0, 10.0, 5.5, 1.0, 0.0, 0.0, 24, false, 0.0, 1.0, b1.high, 1, 1.5);
               m_slots[10].last_entry_bar_time = b1.time;
              }
           }
        }

      // =====================================================================
      // WDO-11: SMART GRID ANCORADO EM WALLS (GammaFlip(±3) + Wall + Limit 50%B1(2b) + Perna 2 na NextWall 1+2L)
      // 173 Trades | Ret/DD = 7.51 | IS_PF = 2.07 | OOS_PF = 1.76 | WallRank = 1/11 (+R$2.168)
      // =====================================================================
      if(m_slots[11].enabled && m_slots[11].dir == 0 && m_slots[11].pend_dir == 0 && m_slots[11].trades_today < 2 && b1_tmin >= 545 && b1_tmin <= 975 && m_gamma_flip > 0.0)
        {
         int sig11 = 0;
         double wall11 = 0.0;
         if(d_l <= 6.0 && b1.close < (m_gamma_flip - 3.0) && pos50 <= 0.42 && b1.close > b1.open)
           { sig11 = 1; wall11 = lvl_s; }
         else if(d_h <= 6.0 && b1.close > (m_gamma_flip + 3.0) && pos50 >= 0.58 && b1.close < b1.open)
           { sig11 = -1; wall11 = lvl_r; }
         if(sig11 != 0)
           {
            double s2_11 = FindWdoNextWallBehind(mid_b1, sig11, 8.0, 16.0, 11.0);
            tp_calc = CalcWdoTargetPts(mid_b1, sig11, 1, 22.0);
            ArmPendingOrder(11, sig11, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, s2_11 + 7.0, 6.0, 1.0, 0.0, 0.0, 20, wall11, 1, 1.0, 2);
           }
        }

      // =====================================================================
      // WDO-12: 3-Pilares (Piramidação no Lucro 1+1L NY + BE_Wall(1.5) + TP_MainWall) | Ret/DD = 3.06
      // =====================================================================
      if(false && m_slots[12].enabled && m_slots[12].dir == 0 && m_slots[12].pend_dir == 0)
        {
         bool ent12 = false;
         if(m_slots[12].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10))
                 {
                  tp_calc = CalcWdoTargetPts(new_bar_open, -1, 2, 24.0);
                  OpenVirtualSingle(12, -1, new_bar_open, new_bar_time, tp_calc, 12.0, 7.0, 1.5, 13.5, 5.0, 16, false, 8.5, 2.5, lvl, 1, 1.5);
                  m_slots[12].last_entry_bar_time = b1.time;
                  ent12 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10))
                 {
                  tp_calc = CalcWdoTargetPts(new_bar_open, 1, 2, 24.0);
                  OpenVirtualSingle(12, 1, new_bar_open, new_bar_time, tp_calc, 12.0, 7.0, 1.5, 13.5, 5.0, 16, false, 8.5, 2.5, lvl, 1, 1.5);
                  m_slots[12].last_entry_bar_time = b1.time;
                  ent12 = true;
                  break;
                 }
              }
           }
         if(!ent12 && WindowOk(new_tmin, "NY_1000_1630") && m_gamma_flip > 0.0)
           {
            if(b1.close > m_gamma_flip + 4.0 && pos50 >= 0.65 && d_h <= 3.5 && b1.close < lvl_r)
              {
               m_slots[12].pyr_trig = 8.5;
               m_slots[12].pyr_lock = 2.5;
               tp_calc = CalcWdoTargetPts(lvl_r, -1, 2, 25.0);
               ArmPendingOrder(12, -1, 1, lvl_r, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_r, 1, 1.5, 1);
              }
            else if(b1.close < m_gamma_flip - 4.0 && pos50 <= 0.35 && d_l <= 3.5 && b1.close > lvl_s)
              {
               m_slots[12].pyr_trig = 8.5;
               m_slots[12].pyr_lock = 2.5;
               tp_calc = CalcWdoTargetPts(lvl_s, 1, 2, 25.0);
               ArmPendingOrder(12, 1, 1, lvl_s, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_s, 1, 1.5, 1);
              }
           }
        }

      // =====================================================================
      // WDO-13: 3-Pilares (Smart Grid 1+2L GammaFlip & Walls + TP_MidWall Real) | Ret/DD = 5.64
      // =====================================================================
      if(false && m_slots[13].enabled && m_slots[13].dir == 0 && m_slots[13].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "FULL_09_17") && m_gamma_flip > 0.0)
        {
         if(b1.close < m_gamma_flip - 5.0 && pos50 <= 0.35 && d_l <= 4.5 && b1.close > b1.open)
           {
            OpenVirtualGrid(13, 1, new_bar_open, new_bar_time, 16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 26);
            m_slots[13].last_entry_bar_time = b1.time;
           }
         else if(b1.close > m_gamma_flip + 5.0 && pos50 >= 0.65 && d_h <= 4.5 && b1.close < b1.open)
           {
            OpenVirtualGrid(13, -1, new_bar_open, new_bar_time, 16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 26);
            m_slots[13].last_entry_bar_time = b1.time;
           }
        }

      // =====================================================================
      // WDO-14: 3-Pilares (Grid Institucional 1+2+3L + TP_MidWall Real) | Ret/DD = 4.62
      // =====================================================================
      if(false && m_slots[14].enabled && m_slots[14].dir == 0 && m_slots[14].last_entry_bar_time != b1.time && b1_tmin >= 545 && b1_tmin <= 930 && m_gamma_flip > 0.0)
        {
         if(b1.close < m_gamma_flip - 5.0 && pos50 <= 0.35 && d_l <= 4.5 && b1.close > b1.open)
           {
            OpenVirtualGrid(14, 1, new_bar_open, new_bar_time, 18.0, 40.0, 1, 2, 3, 11.0, 22.0, 6.5, 1.5, 26);
            m_slots[14].last_entry_bar_time = b1.time;
           }
         else if(b1.close > m_gamma_flip + 5.0 && pos50 >= 0.65 && d_h <= 4.5 && b1.close < b1.open)
           {
            OpenVirtualGrid(14, -1, new_bar_open, new_bar_time, 18.0, 40.0, 1, 2, 3, 11.0, 22.0, 6.5, 1.5, 26);
            m_slots[14].last_entry_bar_time = b1.time;
           }
        }

      // =====================================================================
      // WDO-15: MAINWALL Z30 REVERSAL + CANDLE SHIELD (WDO_PA_MAINWALL_Z30_REV070: Sem Almoco + Limit ExtB1(2b) + Escudo Min/Max Candle + TP_MidWall)
      // 108 Trades (>=100!) | WR = 52.8% | PF = 1.93 | Net = +R$2.575 | MaxDD = R$265 | Ret/DD = 9.72 | WF IS +R$1.300 / OOS +R$1.275
      // =====================================================================
      if(m_slots[15].enabled && m_slots[15].dir == 0 && m_slots[15].pend_dir == 0 && m_slots[15].trades_today < 3 && WindowOk(b1_tmin, "NO_LUNCH") && ArraySize(m_levels_walls) > 0)
        {
         double hb30_15  = MathMax(1.0, 0.5 * bw30);
         double z30_c_15 = (b1.close - m_n30_c_1) / hb30_15;
         double z30_l_15 = (b1.low   - m_n30_c_1) / hb30_15;
         double z30_h_15 = (b1.high  - m_n30_c_1) / hb30_15;
         bool gf_b15     = (m_gamma_flip <= 0.0) || (b1.close < m_gamma_flip + 6.0);
         bool gf_s15     = (m_gamma_flip <= 0.0) || (b1.close > m_gamma_flip - 6.0);

         int sig15 = 0;
         if(dw_l_main <= 4.5 && b1.close >= (w_s_main - 0.5) && (z30_c_15 <= -0.70 || z30_l_15 <= -0.90) && b1.close > b1.open && gf_b15)
            sig15 = 1;
         else if(dw_h_main <= 4.5 && b1.close <= (w_r_main + 0.5) && (z30_c_15 >= 0.70 || z30_h_15 >= 0.90) && b1.close < b1.open && gf_s15)
            sig15 = -1;

         if(sig15 != 0)
           {
            double p15_lim   = (sig15 == 1) ? Round05(b1.low + 0.5) : Round05(b1.high - 0.5);
            double c_shld_15 = (sig15 == 1) ? b1.low : b1.high; // Escudo na Minima/Maxima do Candle de Gatilho!
            tp_calc = CalcWdoTargetPts(p15_lim, sig15, 1, 14.0);
            ArmPendingOrder(15, sig15, 1, p15_lim, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 0.0, 0.0, 16, c_shld_15, 1, 1.5, 2);
           }
        }

      // =====================================================================
      // WDO-16: 3-Pilares MainWall (Posicional EOD MainWalls + Limit 50%B1 + BE_Wall(1.5) + TP_MidWall) | Ret/DD = 11.22
      // =====================================================================
      if(m_slots[16].enabled && m_slots[16].dir == 0 && m_slots[16].pend_dir == 0 && m_slots[16].last_trade_date != today_str && new_tmin >= 550 && new_tmin <= 840 && ArraySize(m_levels_walls) > 0)
        {
         if(pos50 >= 0.65 && dw_h_main <= 4.0 && b1.close < w_r_main && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
           {
            tp_calc = CalcWdoTargetPts(mid_b1, -1, 1, 65.0);
            ArmPendingOrder(16, -1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 20.0, 11.5, 2.0, 26.0, 10.5, 120, w_r_main, 1, 1.5, 1);
           }
         else if(pos50 <= 0.35 && dw_l_main <= 4.0 && b1.close > w_s_main && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
           {
            tp_calc = CalcWdoTargetPts(mid_b1, 1, 1, 65.0);
            ArmPendingOrder(16, 1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 20.0, 11.5, 2.0, 26.0, 10.5, 120, w_s_main, 1, 1.5, 1);
           }
        }

      if(!MQLInfoInteger(MQL_OPTIMIZATION))
        {
         SaveVirtualStateToDisk();
         RenderHudComment();
        }
     }

   void              ArmPendingOrder(int k, int dir, int ptype, double price, datetime bar_t, double new_bar_open,
                                     double tp_pts, double sl_pts, double be_trig, double be_lock,
                                     double tr_trig, double tr_dist, int max_hold=16,
                                     double def_wall=0.0, int be_mode=0, double wall_buf=0.0, int valid_bars=1)
     {
      double p05 = Round05(price);

      if(ptype == 1 && dir == 1 && new_bar_open < p05)
         return;
      if(ptype == 1 && dir == -1 && new_bar_open > p05)
         return;
      if(ptype == 2 && dir == 1 && new_bar_open > p05)
         return;
      if(ptype == 2 && dir == -1 && new_bar_open < p05)
         return;

      m_slots[k].pend_dir = dir;
      m_slots[k].pend_type = ptype;
      m_slots[k].pend_price = p05;
      m_slots[k].pend_bar_time = bar_t;
      m_slots[k].pend_tp_pts = tp_pts;
      m_slots[k].pend_sl_pts = sl_pts;
      m_slots[k].be_trig = be_trig;
      m_slots[k].be_lock = be_lock;
      m_slots[k].tr_trig = tr_trig;
      m_slots[k].tr_dist = tr_dist;
      m_slots[k].max_hold_bars = max_hold;
      m_slots[k].pend_def_wall = def_wall;
      m_slots[k].pend_be_mode = be_mode;
      m_slots[k].pend_wall_buf = wall_buf;
      m_slots[k].pend_bars_left = valid_bars;

      if(m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double ord_p = (dir == 1) ? Round05(p05 + 0.5) : p05;

         if((ptype == 1 && dir == 1 && ask > 0.0 && ask <= ord_p) ||
            (ptype == 1 && dir == -1 && bid > 0.0 && bid >= ord_p) ||
            (ptype == 2 && dir == 1 && ask > 0.0 && ask >= ord_p) ||
            (ptype == 2 && dir == -1 && bid > 0.0 && bid <= ord_p))
           {
            double pt_save = m_slots[k].pyr_trig;
            double pl_save = m_slots[k].pyr_lock;
            OpenVirtualSingle(k, dir, p05, bar_t, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, true, pt_save, pl_save, def_wall, be_mode, wall_buf);
            m_slots[k].last_entry_bar_time = bar_t;
            if(k == 16)
               m_slots[k].last_trade_date = DateStr(bar_t);
            return;
           }

         long slot_magic = m_base_magic + k;
         DeletePendingOrdersForSlot(k);
         m_trade.SetExpertMagicNumber(slot_magic);

         double vol = MathRound(1.0 * m_lot_mult);
         if(!m_guard.AllowOrder(vol))
            return;
         double sl_p = (dir == 1) ? Round05(p05 - sl_pts) : Round05(p05 + sl_pts + 0.5);
         double tp_p = (dir == 1) ? Round05(p05 + tp_pts) : Round05(p05 - tp_pts + 0.5);
         ENUM_ORDER_TYPE_TIME ttype = GetValidOrderTimeType();

         if(ptype == 1 && dir == 1)
            m_trade.BuyLimit(vol, ord_p, _Symbol, sl_p, tp_p, ttype, 0, m_slots[k].name);
         else if(ptype == 1 && dir == -1)
            m_trade.SellLimit(vol, ord_p, _Symbol, sl_p, tp_p, ttype, 0, m_slots[k].name);
         else if(ptype == 2 && dir == 1)
            m_trade.BuyStop(vol, ord_p, _Symbol, sl_p, tp_p, ttype, 0, m_slots[k].name);
         else if(ptype == 2 && dir == -1)
            m_trade.SellStop(vol, ord_p, _Symbol, sl_p, tp_p, ttype, 0, m_slots[k].name);
        }
      SaveVirtualStateToDisk();
     }
  };
//+------------------------------------------------------------------+
