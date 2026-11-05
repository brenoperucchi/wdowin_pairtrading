//+------------------------------------------------------------------+
//|                                          Jumba_GEX_NWE_Core.mqh |
//|        Motor Institucional GEX MagicWalls + NWE para MT5 (WIN$N) |
//|   Suporta: 16 Estratégias Auditadas, Virtual Position Manager    |
//|   (Netting & Hedging), Leitura Híbrida (Common\Files + Firebase) |
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property link      "https://wdo-win-dashboard-default-rtdb.firebaseio.com"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Jumba_SafetyGuard.mqh>

enum ENUM_PORTFOLIO_PRESET
  {
   PRESET_PORT_01_COMPLETO = 0, // PORT-01 (Ret/DD 29.54 | EST 04+07+09+10+11+13+14+15)
   PRESET_PORT_03_SHARPE   = 1, // PORT-03 (Sharpe 8.15  | EST 01+04+08+11+13+14+15+16)
   PRESET_LEVE_01_R2_986   = 2, // LEVE-01 (Sem EST-14   | EST 04+06+08+09+11+12+15+16)
   PRESET_LEVE_03_PROFIT   = 3, // LEVE-03 (Sem EST-14   | EST 03+04+08+09+11+13+15+16)
   PRESET_CUSTOM_MANUAL    = 4, // Personalizado (Usar chaves individuais Enable_EST01..16)
   PRESET_SINGLE_ROBOT     = 5, // Robô Individual (Apenas 1 Estratégia Ativa)
   PRESET_TODAS_16_ATIVAS  = 6  // TODAS AS 16 ESTRATÉGIAS (EST-01 a EST-16 Juntas | R$ 48.334 | Ret/DD 27.89)
  };

enum ENUM_EXECUTION_MODE
  {
   EXEC_NETTING_VIRTUAL_SYNC = 0, // Netting B3: Virtualiza cada robô e sincroniza posição líquida
   EXEC_HEDGING_DIRECT_MAGIC = 1  // Hedging / Individual: Envia ordens isoladas por MagicNumber
  };

struct SGexLevel
  {
   string            type;
   double            price;
   int               width;
  };

struct SVirtualSlot
  {
   int               id;              // 1..16
   string            name;
   bool              enabled;
   int               dir;             // 0=Flat, 1=Long, -1=Short
   int               lots;            // Current active lots (in base units)
   int               leg_stage;       // 1, 2, or 3 (for Grids and Pyramiding)
   double            p1_entry;        // Initial entry price
   double            avg_price;       // Volume-weighted average price
   double            curr_sl;         // Current Stop Loss price
   double            curr_tp;         // Current Take Profit price
   double            max_fav_pts;     // Maximum favorable excursion in points
   bool              be_active;       // Breakeven Stage 1 activated flag
   bool              be_stage2_active;// Breakeven Stage 2 activated flag
   bool              opened_intrabar; // True if opened via Limit/Stop during current M5 bar
   bool              real_synced;     // True once real position is open on MT5 server
   int               bars_held;       // M5 bars held since entry
   datetime          entry_bar_time;  // Timestamp of M5 bar when position opened
   datetime          last_entry_bar_time; // Prevents double entry on same M5 bar
   string            last_trade_date; // For EOD strategies (1 trade/day limit)
   // Structural Wall-Shield BE & Partial Exit fields
   double            def_wall;        // Defending Wall coordinate
   int               be_mode;         // 0=BE_ZERO, 1=BE_WALL_SHIELD, 2=BE_TWO_STAGE_WALLS
   double            wall_buf;        // Buffer behind Wall (15 or 25 pts)
   double            raw_mid_lvl;     // MidWall coordinate for Stage 2 & Partial
   double            tp1_px;          // Partial exit TP1 coordinate
   bool              partial_mode;    // True if 50% partial exit at MidWall is enabled
   bool              partial_done;    // True once 50% partial exit was executed
   // Pending Order State (for Limit/Stop strategies armed for M5 bar(s))
   int               pend_dir;        // 0=None, 1=Buy, -1=Sell
   int               pend_type;       // 0=None, 1=Limit, 2=Stop
   double            pend_price;      // Trigger price (rounded to 5 pts)
   double            pend_tp_pts;     // TP distance in pts for pending order
   double            pend_sl_pts;     // SL distance in pts for pending order
   datetime          pend_bar_time;   // M5 bar open time when armed/updated
   int               pend_bars_left;  // Remaining M5 bars for pending order validity (1 or 2)
   bool              pend_rolling_stop;// True if Rolling Stop updates on next M5 bar
   int               pend_init_lots;  // Initial base lots when pending order triggers (1 or 2)
   double            pend_def_wall;
   int               pend_be_mode;
   double            pend_wall_buf;
   double            pend_raw_mid_lvl;
   double            pend_tp1_px;
   bool              pend_partial_mode;
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
   double            init_sl_pts;
   double            init_tp_pts;
   double            closed_pnl_today_brl;
   int               trades_today;
  };

class CJumbaGexNweEngine
  {
private:
   CTrade            m_trade;
   CPositionInfo     m_pos;
   ulong             m_base_magic;
   int               m_single_id;
   ENUM_EXECUTION_MODE m_exec_mode;
   CJumbaSafetyGuard m_guard;      // Kill-switch anti-loop (volume, exposicao, taxa de ordens)
   double            m_lot_mult;
   double            m_max_daily_loss_brl;
   bool              m_draw_levels;
   string            m_wdo_symbol;

   string            m_loaded_date;
   string            m_gex_source;
   SGexLevel         m_gex_raw[];
   double            m_levels_all[];
   double            m_levels_walls[];
   double            m_gamma_flip;
   double            m_max_gamma;
   double            m_min_gamma;

   // Causal Indicator Values at closed bar [1] and prior closed bar [2]
   datetime          m_last_m5_bar_time;
   bool              m_state_reconciled;
   ulong             m_last_order_ms[17];
   double            m_last_sent_lots[17];
   ulong             m_last_net_sync_ms;
   double            m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1;
   double            m_n50_c_2, m_n50_u_2, m_n50_l_2, m_n50_s_2;
   double            m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1;
   double            m_n30_c_2, m_n30_u_2, m_n30_l_2, m_n30_s_2;
   double            m_rsi7_1,  m_rsi7_2;
   double            m_wdo_ret3_1, m_wdo_z_1;
   double            m_day_high_morning, m_day_low_morning;
   string            m_morning_date;

   SVirtualSlot      m_slots[17]; // Index 1..16

public:
                     CJumbaGexNweEngine()
     {
      m_base_magic = 88000;
      m_single_id = 0;
      m_exec_mode = EXEC_HEDGING_DIRECT_MAGIC;
      m_lot_mult = 1.0;
      m_max_daily_loss_brl = 2500.0;
      m_draw_levels = true;
      m_wdo_symbol = "WDO$N";
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
      m_day_high_morning = 0.0;
      m_day_low_morning = 9999999.0;
      m_morning_date = "";
     }

   void              Init(ulong base_magic, ENUM_EXECUTION_MODE exec_mode, double lot_mult, double max_daily_loss_brl, bool draw_levels, string wdo_sym="WDO$N")
     {
      m_base_magic = base_magic;
      m_single_id = 0;
      m_exec_mode = exec_mode;
      m_lot_mult = MathMin(10.0, MathMax(1.0, MathRound(lot_mult)));
      m_last_net_sync_ms = 0;
      for(int k=0; k<=16; k++)
        {
         m_last_order_ms[k] = 0;
         m_last_sent_lots[k] = 0.0;
        }
      m_max_daily_loss_brl = max_daily_loss_brl;
      m_draw_levels = draw_levels;
      m_wdo_symbol = wdo_sym;
      m_trade.SetExpertMagicNumber(m_base_magic);
      m_trade.SetDeviationInPoints(50);
      m_trade.SetTypeFillingBySymbol(_Symbol);

      string names[17] =
        {
         "",
         "EST-01 [3Pil BE_Wall25+MainW] Scalper NY",
         "EST-02 [3Pil Lim50%B1+MainW] Scalper Full",
         "EST-03 [DESATIVADO WF] Clone EST-01",
         "EST-04 [WDO Reteste220+BE2Stg+MidW] Limit",
         "EST-05 [DESATIVADO WF] Cluster NWE",
         "EST-06 [3Pil StopB1+BE_W15+MainW] Slope",
         "EST-07 [3Pil BE_Wall15] Breakout Mom NY",
         "EST-08 [3Pil TP_MainW] Breakout Core",
         "EST-09 [DESATIVADO WF] Clone EST-01",
         "EST-10 [DESATIVADO WF] WallsOnly GF",
         "EST-11 [DESATIVADO <100tr] StopB1(2b)+MidW",
         "EST-12 [3Pil TP_MainW] Piramidacao 1+1L",
         "EST-13 [SmartGrid CrossWDO+NextWall 1+2L]",
         "EST-14 [SmartGrid Wick25+NextWall 1+2L]",
         "EST-15 [SmartGrid Z30_Rev+NextWall 1+2L]",
         "EST-16 [SmartGrid SpringZ30+NextWall 1+2L]"
        };

      for(int k=1; k<=16; k++)
        {
         m_slots[k].id = k;
         m_slots[k].name = names[k];
         m_slots[k].enabled = false;
         ResetSlotPosition(k);
         m_slots[k].last_entry_bar_time = 0;
         m_slots[k].last_trade_date = "";
         m_slots[k].closed_pnl_today_brl = 0.0;
         m_slots[k].trades_today = 0;
        }
     }

   void              ConfigurePreset(ENUM_PORTFOLIO_PRESET preset, int single_id,
                                     bool e01, bool e02, bool e03, bool e04,
                                     bool e05, bool e06, bool e07, bool e08,
                                     bool e09, bool e10, bool e11, bool e12,
                                     bool e13, bool e14, bool e15, bool e16)
     {
      m_single_id = (preset == PRESET_SINGLE_ROBOT) ? single_id : 0;
      for(int k=1; k<=16; k++)
         m_slots[k].enabled = false;

      if(preset == PRESET_PORT_01_COMPLETO)
        {
         m_slots[4].enabled = true;  m_slots[7].enabled = true;
         m_slots[9].enabled = true;  m_slots[10].enabled = true;
         m_slots[11].enabled = true; m_slots[13].enabled = true;
         m_slots[14].enabled = true; m_slots[15].enabled = true;
        }
      else if(preset == PRESET_PORT_03_SHARPE)
        {
         m_slots[1].enabled = true;  m_slots[4].enabled = true;
         m_slots[8].enabled = true;  m_slots[11].enabled = true;
         m_slots[13].enabled = true; m_slots[14].enabled = true;
         m_slots[15].enabled = true; m_slots[16].enabled = true;
        }
      else if(preset == PRESET_LEVE_01_R2_986)
        {
         m_slots[4].enabled = true;  m_slots[6].enabled = true;
         m_slots[8].enabled = true;  m_slots[9].enabled = true;
         m_slots[11].enabled = true; m_slots[12].enabled = true;
         m_slots[15].enabled = true; m_slots[16].enabled = true;
        }
      else if(preset == PRESET_LEVE_03_PROFIT)
        {
         m_slots[3].enabled = true;  m_slots[4].enabled = true;
         m_slots[8].enabled = true;  m_slots[9].enabled = true;
         m_slots[11].enabled = true; m_slots[13].enabled = true;
         m_slots[15].enabled = true; m_slots[16].enabled = true;
        }
      else if(preset == PRESET_SINGLE_ROBOT)
        {
         if(single_id >= 1 && single_id <= 16)
            m_slots[single_id].enabled = true;
        }
      else if(preset == PRESET_TODAS_16_ATIVAS)
        {
         for(int k=1; k<=16; k++)
            m_slots[k].enabled = true;
        }
      else
        {
         m_slots[1].enabled = e01;  m_slots[2].enabled = e02;
         m_slots[3].enabled = e03;  m_slots[4].enabled = e04;
         m_slots[5].enabled = e05;  m_slots[6].enabled = e06;
         m_slots[7].enabled = e07;  m_slots[8].enabled = e08;
         m_slots[9].enabled = e09;  m_slots[10].enabled = e10;
         m_slots[11].enabled = e11; m_slots[12].enabled = e12;
         m_slots[13].enabled = e13; m_slots[14].enabled = e14;
         m_slots[15].enabled = e15; m_slots[16].enabled = e16;
        }
      // Auditoria Walk-Forward + Minimo 100 Trades (Nov/2026): Desativa slots <100tr ou reprovados (3, 5, 9, 10, 11); EST-13..16 sao SmartGrids >=100tr aprovados!
      m_slots[3].enabled  = false;
      m_slots[5].enabled  = false;
      m_slots[9].enabled  = false;
      m_slots[10].enabled = false;
      m_slots[11].enabled = false;

      int guard_slots = 0;
      for(int gk=1; gk<=16; gk++)
         if(m_slots[gk].enabled) guard_slots++;
      m_guard.Configure("JUMBA WIN", (long)m_base_magic, m_lot_mult, guard_slots);
      m_guard.CheckAccountMode(m_single_id > 0 || GetSingleActiveSlotId() > 0);

      long acc_margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(acc_margin_mode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || m_single_id > 0 || GetSingleActiveSlotId() > 0)
        {
         if(m_exec_mode != EXEC_HEDGING_DIRECT_MAGIC)
            Print("[JUMBA WIN] Trava de Seguranca: Forcando EXEC_HEDGING_DIRECT_MAGIC (Conta Hedging ou Robo Individual).");
         m_exec_mode = EXEC_HEDGING_DIRECT_MAGIC;
        }
      else if(acc_margin_mode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && m_exec_mode == EXEC_HEDGING_DIRECT_MAGIC)
        {
         Print("[JUMBA WIN] Conta NETTING detectada na corretora. Alternando automaticamente para EXEC_NETTING_VIRTUAL_SYNC.");
         m_exec_mode = EXEC_NETTING_VIRTUAL_SYNC;
        }

      if(!MQLInfoInteger(MQL_TESTER))
        {
         GlobalVariablesDeleteAll("JUMBA_LOTS_");
         GlobalVariablesDeleteAll("JUMBA_TIME_");
        }

      m_state_reconciled = MQLInfoInteger(MQL_TESTER) ? true : false;
      if(!MQLInfoInteger(MQL_TESTER))
        {
         SymbolSelect("WINZ26", true);
         if(StringFind(_Symbol, "$") >= 0)
            ChartSetSymbolPeriod(0, "WINZ26", PERIOD_M5);
         else if(_Period != PERIOD_M5)
            ChartSetSymbolPeriod(0, _Symbol, PERIOD_M5);
         SymbolSelect(_Symbol, true);
         SymbolSelect(m_wdo_symbol, true);
         SymbolSelect("WDOX26", true);
         SymbolSelect("WDOZ26", true);
         MqlRates r_init[];
         if(CopyRates(_Symbol, PERIOD_M5, 0, 2, r_init) >= 2)
            m_last_m5_bar_time = r_init[1].time;
         ChartSetInteger(0, CHART_SCALEFIX, false);
         string init_date = DateStr(SafeTime());
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
         ObjectsDeleteAll(0, "JUMBA_GEX_");
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
      if(m_single_id > 0)
         return m_single_id;
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
      if(k >= 13 && k <= 16)
         return 3; // SmartGrid 1+2 lotes
      if(k == 11 || k == 12)
         return 2; // Piramidacao 1+1 lotes
      return 1;    // Demais estrategias operam estritamente 1 lote base
     }

   string            StateFileName()
     {
      ulong file_magic = m_base_magic + (ulong)m_single_id;
      return StringFormat("jumba_state_%I64d_%s_%I64u.csv", AccountInfoInteger(ACCOUNT_LOGIN), _Symbol, file_magic);
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
            "%d;%d;%d;%d;%.2f;%.2f;%.2f;%.2f;%.2f;%d;%d;%I64d;%s;%.2f;%d;%.2f;%.2f;%d;%d;%d;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%d;%.2f;%d;%.2f;%.2f;%.2f;%d;%d;%d;%I64d;%d;%d;%.2f;%.2f;%.2f;%I64d;%d;%d;%d;%.2f;%d;%.2f;%.2f;%.2f;%d\n",
            k, m_slots[k].dir, m_slots[k].lots, m_slots[k].leg_stage,
            m_slots[k].p1_entry, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp,
            m_slots[k].max_fav_pts, (m_slots[k].be_active ? 1 : 0), m_slots[k].bars_held,
            (long)m_slots[k].entry_bar_time, m_slots[k].last_trade_date,
            m_slots[k].closed_pnl_today_brl, m_slots[k].trades_today,
            m_slots[k].step2_dist, m_slots[k].step3_dist,
            m_slots[k].lot1, m_slots[k].lot2, m_slots[k].lot3,
            m_slots[k].tp_avg_pts, m_slots[k].max_sl_pts,
            m_slots[k].be_trig, m_slots[k].be_lock, m_slots[k].tr_trig, m_slots[k].tr_dist,
            m_slots[k].max_hold_bars,
            m_slots[k].def_wall, m_slots[k].be_mode, m_slots[k].wall_buf,
            m_slots[k].raw_mid_lvl, m_slots[k].tp1_px,
            (m_slots[k].partial_mode ? 1 : 0), (m_slots[k].partial_done ? 1 : 0),
            (m_slots[k].be_stage2_active ? 1 : 0),
            (long)m_slots[k].last_entry_bar_time,
            m_slots[k].pend_dir, m_slots[k].pend_type, m_slots[k].pend_price,
            m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts, (long)m_slots[k].pend_bar_time,
            m_slots[k].pend_bars_left, (m_slots[k].pend_rolling_stop ? 1 : 0),
            m_slots[k].pend_init_lots, m_slots[k].pend_def_wall, m_slots[k].pend_be_mode,
            m_slots[k].pend_wall_buf, m_slots[k].pend_raw_mid_lvl, m_slots[k].pend_tp1_px,
            (m_slots[k].pend_partial_mode ? 1 : 0)
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
        {
         string legacy_name = StringFormat("jumba_state_%I64d_%s.csv", AccountInfoInteger(ACCOUNT_LOGIN), _Symbol);
         h = FileOpen(legacy_name, FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
        }
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
         if(cnt >= 27)
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
               m_slots[k].last_trade_date      = p[12];
               m_slots[k].closed_pnl_today_brl = StringToDouble(p[13]);
               m_slots[k].trades_today         = (int)StringToInteger(p[14]);
               m_slots[k].step2_dist           = StringToDouble(p[15]);
               m_slots[k].step3_dist           = StringToDouble(p[16]);
               m_slots[k].lot1                 = (int)StringToInteger(p[17]);
               m_slots[k].lot2                 = (int)StringToInteger(p[18]);
               m_slots[k].lot3                 = (int)StringToInteger(p[19]);
               m_slots[k].tp_avg_pts           = StringToDouble(p[20]);
               m_slots[k].max_sl_pts           = StringToDouble(p[21]);
               m_slots[k].be_trig              = StringToDouble(p[22]);
               m_slots[k].be_lock              = StringToDouble(p[23]);
               m_slots[k].tr_trig              = StringToDouble(p[24]);
               m_slots[k].tr_dist              = StringToDouble(p[25]);
               m_slots[k].max_hold_bars        = (int)StringToInteger(p[26]);
               if(cnt >= 35)
                 {
                  m_slots[k].def_wall         = StringToDouble(p[27]);
                  m_slots[k].be_mode          = (int)StringToInteger(p[28]);
                  m_slots[k].wall_buf         = StringToDouble(p[29]);
                  m_slots[k].raw_mid_lvl      = StringToDouble(p[30]);
                  m_slots[k].tp1_px           = StringToDouble(p[31]);
                  m_slots[k].partial_mode     = (StringToInteger(p[32]) != 0);
                  m_slots[k].partial_done     = (StringToInteger(p[33]) != 0);
                  m_slots[k].be_stage2_active = (StringToInteger(p[34]) != 0);
                 }
               if(cnt >= 51)
                 {
                  m_slots[k].last_entry_bar_time = (datetime)StringToInteger(p[35]);
                  m_slots[k].pend_dir            = (int)StringToInteger(p[36]);
                  m_slots[k].pend_type           = (int)StringToInteger(p[37]);
                  m_slots[k].pend_price          = StringToDouble(p[38]);
                  m_slots[k].pend_tp_pts         = StringToDouble(p[39]);
                  m_slots[k].pend_sl_pts         = StringToDouble(p[40]);
                  m_slots[k].pend_bar_time       = (datetime)StringToInteger(p[41]);
                  m_slots[k].pend_bars_left      = (int)StringToInteger(p[42]);
                  m_slots[k].pend_rolling_stop   = (StringToInteger(p[43]) != 0);
                  m_slots[k].pend_init_lots      = (int)StringToInteger(p[44]);
                  m_slots[k].pend_def_wall       = StringToDouble(p[45]);
                  m_slots[k].pend_be_mode        = (int)StringToInteger(p[46]);
                  m_slots[k].pend_wall_buf       = StringToDouble(p[47]);
                  m_slots[k].pend_raw_mid_lvl    = StringToDouble(p[48]);
                  m_slots[k].pend_tp1_px         = StringToDouble(p[49]);
                  m_slots[k].pend_partial_mode   = (StringToInteger(p[50]) != 0);
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
         ulong slot_magic = m_base_magic + (ulong)k;

         // 1. Reconcilia PnL Fechado e Trades do Dia pelo Histórico Oficial da Corretora
         if(hist_ok)
           {
            double h_pnl = 0.0;
            int h_tr = 0;
            int total_deals = HistoryDealsTotal();
            for(int i=0; i<total_deals; i++)
              {
               ulong dticket = HistoryDealGetTicket(i);
               if(HistoryDealGetString(dticket, DEAL_SYMBOL) == _Symbol &&
                  (ulong)HistoryDealGetInteger(dticket, DEAL_MAGIC) == slot_magic)
                 {
                  long dentry = HistoryDealGetInteger(dticket, DEAL_ENTRY);
                  if(dentry == DEAL_ENTRY_OUT || dentry == DEAL_ENTRY_INOUT)
                    {
                     h_pnl += HistoryDealGetDouble(dticket, DEAL_PROFIT);
                     h_tr += 1;
                    }
                 }
              }
            if(h_tr > m_slots[k].trades_today || (h_tr > 0 && MathAbs(m_slots[k].closed_pnl_today_brl) < 0.01))
              {
               m_slots[k].closed_pnl_today_brl = h_pnl;
               m_slots[k].trades_today = h_tr;
              }
            if(h_tr > 0 && k == 15)
               m_slots[k].last_trade_date = today_str;
           }

         // 2. Reconcilia Posições Abertas e Ordens Pendentes em Modo HEDGING
         if(m_exec_mode == EXEC_HEDGING_DIRECT_MAGIC)
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
               double bid_ref = (pos_dir == 1 && open_px > 0.0) ? Round5(open_px - 5.0) : Round5(open_px);
               if(m_slots[k].dir == pos_dir)
                 {
                  m_slots[k].lots = pos_lots;
                  m_slots[k].real_synced = true;
                  if(m_slots[k].avg_price <= 0.0) m_slots[k].avg_price = bid_ref;
                  if(m_slots[k].p1_entry <= 0.0)  m_slots[k].p1_entry  = bid_ref;
                  if(m_slots[k].curr_sl <= 0.0 && pos_sl > 0.0) m_slots[k].curr_sl = Round5(pos_sl);
                  if(m_slots[k].curr_tp <= 0.0 && pos_tp > 0.0) m_slots[k].curr_tp = Round5(pos_tp);
                 }
               else
                 {
                  // Adota a posição aberta da corretora sem jamais fechá-la no reinício!
                  m_slots[k].dir            = pos_dir;
                  m_slots[k].lots           = pos_lots;
                  m_slots[k].leg_stage      = 1;
                  m_slots[k].p1_entry       = bid_ref;
                  m_slots[k].avg_price      = bid_ref;
                  m_slots[k].curr_sl        = (pos_sl > 0.0) ? Round5(pos_sl) : ((pos_dir == 1) ? Round5(bid_ref - 230.0) : Round5(bid_ref + 230.0));
                  m_slots[k].curr_tp        = (pos_tp > 0.0) ? Round5(pos_tp) : ((pos_dir == 1) ? Round5(bid_ref + 450.0) : Round5(bid_ref - 450.0));
                  m_slots[k].init_sl_pts    = MathAbs(bid_ref - m_slots[k].curr_sl);
                  m_slots[k].init_tp_pts    = MathAbs(m_slots[k].curr_tp - bid_ref);
                  m_slots[k].entry_bar_time = pos_time;
                  m_slots[k].real_synced    = true;
                  if(m_slots[k].be_trig <= 0.0)  { m_slots[k].be_trig = 150.0; m_slots[k].be_lock = 25.0; }
                  if(m_slots[k].tr_trig <= 0.0)  { m_slots[k].tr_trig = 280.0; m_slots[k].tr_dist = 110.0; }
                  if(m_slots[k].max_hold_bars <= 0) m_slots[k].max_hold_bars = (k == 15) ? 120 : 18;
                  if(k == 15) m_slots[k].last_trade_date = today_str;
                  PrintFormat("[JUMBA %s] POSICAO ABERTA ADOTADA NO REINICIO | Dir=%d | Lotes=%d | PM=%.0f | SL=%.0f | TP=%.0f",
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
               ulong ord_ticket = OrderGetTicket(i);
               if(ord_ticket > 0 && OrderGetString(ORDER_SYMBOL) == _Symbol && (ulong)OrderGetInteger(ORDER_MAGIC) == slot_magic)
                 {
                  found_ord = true;
                  if(m_slots[k].pend_dir == 0)
                    {
                     ENUM_ORDER_TYPE otype = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
                     double op = OrderGetDouble(ORDER_PRICE_OPEN);
                     double osl = OrderGetDouble(ORDER_SL);
                     double otp = OrderGetDouble(ORDER_TP);
                     double ovol = OrderGetDouble(ORDER_VOLUME_INITIAL);
                     m_slots[k].pend_dir       = (otype == ORDER_TYPE_BUY_LIMIT || otype == ORDER_TYPE_BUY_STOP) ? 1 : -1;
                     m_slots[k].pend_type      = (otype == ORDER_TYPE_BUY_LIMIT || otype == ORDER_TYPE_SELL_LIMIT) ? 1 : 2;
                     m_slots[k].pend_price     = Round5(op);
                     m_slots[k].pend_sl_pts    = (osl > 0.0) ? MathAbs(op - osl) : 230.0;
                     m_slots[k].pend_tp_pts    = (otp > 0.0) ? MathAbs(otp - op) : 450.0;
                     m_slots[k].pend_bar_time  = iTime(_Symbol, PERIOD_M5, 0);
                     m_slots[k].pend_bars_left = 1;
                     m_slots[k].pend_init_lots = MathMax(1, (int)MathRound(ovol / m_lot_mult));
                     if(m_slots[k].be_trig <= 0.0) { m_slots[k].be_trig = 150.0; m_slots[k].be_lock = 25.0; m_slots[k].max_hold_bars = 18; }
                     PrintFormat("[JUMBA %s] ORDEM PENDENTE ADOTADA NO REINICIO | Dir=%d @ %.0f",
                                 m_slots[k].name, m_slots[k].pend_dir, m_slots[k].pend_price);
                    }
                  break;
                 }
              }
            if(!found_ord && m_slots[k].pend_dir != 0)
              {
               m_slots[k].pend_dir = 0;
               m_slots[k].pend_bars_left = 0;
              }
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
      m_slots[k].real_synced = false;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = 0;
      m_slots[k].def_wall = 0.0;
      m_slots[k].be_mode = 0;
      m_slots[k].wall_buf = 0.0;
      m_slots[k].raw_mid_lvl = 0.0;
      m_slots[k].tp1_px = 0.0;
      m_slots[k].partial_mode = false;
      m_slots[k].partial_done = false;
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_type = 0;
      m_slots[k].pend_price = 0.0;
      m_slots[k].pend_tp_pts = 0.0;
      m_slots[k].pend_sl_pts = 0.0;
      m_slots[k].pend_bar_time = 0;
      m_slots[k].pend_bars_left = 0;
      m_slots[k].pend_rolling_stop = false;
      m_slots[k].pend_init_lots = 1;
      m_slots[k].pend_def_wall = 0.0;
      m_slots[k].pend_be_mode = 0;
      m_slots[k].pend_wall_buf = 0.0;
      m_slots[k].pend_raw_mid_lvl = 0.0;
      m_slots[k].pend_tp1_px = 0.0;
      m_slots[k].pend_partial_mode = false;
      m_slots[k].init_sl_pts = 0.0;
      m_slots[k].init_tp_pts = 0.0;
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
         return ((t_min >= 545 && t_min <= 735) || (t_min >= 810 && t_min <= 990));
      if(wmode == "NY_1000_1630")
         return (t_min >= 600 && t_min <= 990);
      if(wmode == "CORE_09_1615")
         return (t_min >= 550 && t_min <= 975);
      if(wmode == "FULL_09_17")
         return (t_min >= 545 && t_min <= 1020);
      return false;
     }

   //+------------------------------------------------------------------+
   //| Carregamento Híbrido Diário das MagicWalls (Common\Files + Cloud)|
   //+------------------------------------------------------------------+
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
      // 1. Tenta ler jumba_gex_win_daily.csv em Common\Files se for a data de hoje
      int h_daily = FileOpen("jumba_gex_win_daily.csv", FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(h_daily != INVALID_HANDLE)
        {
         while(!FileIsEnding(h_daily))
           {
            string line = FileReadString(h_daily);
            if(StringLen(line) < 5 || StringFind(line, "session_date") >= 0)
               continue;
            string parts[];
            int cnt = StringSplit(line, ';', parts);
            if(cnt >= 5)
              {
               string s_date = parts[0];
               string r_date = parts[1];
               if(!MQLInfoInteger(MQL_TESTER) && s_date == target_date)
                 {
                  int n = ArraySize(m_gex_raw);
                  ArrayResize(m_gex_raw, n + 1);
                  m_gex_raw[n].type = parts[2];
                  m_gex_raw[n].price = StringToDouble(parts[3]);
                  m_gex_raw[n].width = (int)StringToInteger(parts[4]);
                 }
              }
           }
         FileClose(h_daily);
         if(ArraySize(m_gex_raw) > 0)
           {
            m_gex_source = "COMMON_DAILY_CSV";
            actual_loaded_date = target_date;
           }
        }

      // 2. Se não achou no daily (ex: Strategy Tester histórico ou virada de dia), busca em jumba_gex_win_history.csv
      if(ArraySize(m_gex_raw) == 0)
        {
         int h_hist = FileOpen("jumba_gex_win_history.csv", FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
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
               m_gex_source = "COMMON_HISTORY_CSV (" + best_date + ")";
               actual_loaded_date = best_date;
              }
           }
        }

      // 3. Fallback Cloud Firebase via WebRequest (Apenas em Conta Real/Demo fora do Strategy Tester)
      if(ArraySize(m_gex_raw) == 0 && !MQLInfoInteger(MQL_TESTER))
        {
         char post[], result[];
         string headers;
         string url = "https://wdo-win-dashboard-default-rtdb.firebaseio.com/daily_levels/win_gex.json";
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

      // Classificar níveis em m_levels_all, m_levels_walls e GammaFlip/Max/Min
      for(int i=0; i<ArraySize(m_gex_raw); i++)
        {
         string t = m_gex_raw[i].type;
         double p = m_gex_raw[i].price;
         if(p <= 0.0)
            continue;
         if(t == "Wall" || t == "wall")
           {
            int nw = ArraySize(m_levels_walls);
            ArrayResize(m_levels_walls, nw + 1);
            m_levels_walls[nw] = p;

            int na = ArraySize(m_levels_all);
            ArrayResize(m_levels_all, na + 1);
            m_levels_all[na] = p;
           }
         else if(t == "MidWall" || t == "mid_wall")
           {
            int na = ArraySize(m_levels_all);
            ArrayResize(m_levels_all, na + 1);
            m_levels_all[na] = p;
           }
         else if(t == "GammaFlip" || t == "gamma_flip")
            m_gamma_flip = p;
         else if(t == "MaxGamma" || t == "max_gamma")
            m_max_gamma = p;
         else if(t == "MinGamma" || t == "min_gamma")
            m_min_gamma = p;
        }

      ArraySort(m_levels_all);
      ArraySort(m_levels_walls);
      // Evita travar m_loaded_date = target_date as 07h00 antes do pipeline gex_daily gerar o CSV do dia
      if(MQLInfoInteger(MQL_TESTER) || actual_loaded_date == target_date)
         m_loaded_date = target_date;
      else if(actual_loaded_date != "")
         m_loaded_date = actual_loaded_date;

      // Reset daily PnL counters on new day
      for(int k=1; k<=16; k++)
        {
         m_slots[k].closed_pnl_today_brl = 0.0;
         m_slots[k].trades_today = 0;
        }

      if(m_draw_levels && !MQLInfoInteger(MQL_OPTIMIZATION))
         DrawLevelsOnChart();
      else if(!MQLInfoInteger(MQL_OPTIMIZATION))
         ObjectsDeleteAll(0, "JUMBA_GEX_");

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
         int idx_start = idx_p - 80;
         if(idx_start < 0)
            idx_start = 0;
         string chunk = StringSubstr(json, idx_start, idx_end - idx_start + 1);

         double price_val = 0.0;
         int p_colon = StringFind(chunk, "\"price\":");
         if(p_colon >= 0)
           {
            string sub_p = StringSubstr(chunk, p_colon + 8);
            price_val = StringToDouble(sub_p);
           }

         string type_val = "Wall";
         if(StringFind(chunk, "MidWall") >= 0 || StringFind(chunk, "mid_wall") >= 0)
            type_val = "MidWall";
         else if(StringFind(chunk, "GammaFlip") >= 0 || StringFind(chunk, "gamma_flip") >= 0)
            type_val = "GammaFlip";
         else if(StringFind(chunk, "MaxGamma") >= 0 || StringFind(chunk, "max_gamma") >= 0)
            type_val = "MaxGamma";
         else if(StringFind(chunk, "MinGamma") >= 0 || StringFind(chunk, "min_gamma") >= 0)
            type_val = "MinGamma";

         if(price_val > 10000.0)
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
      ObjectsDeleteAll(0, "JUMBA_GEX_");
      // Se o indicador visual Jumba_GEX_MagicWalls_Ind já está desenhando as linhas HLINE no gráfico ao vivo, evita duplicar objetos
      if(!MQLInfoInteger(MQL_TESTER) && ObjectFind(0, "JUMBA_IND_GEX_HLINE_0") >= 0)
         return;
      for(int i=0; i<ArraySize(m_gex_raw); i++)
        {
         string obj_name = StringFormat("JUMBA_GEX_%s_%d", m_gex_raw[i].type, i);
         double p = m_gex_raw[i].price;
         string d_dot = m_loaded_date;
         StringReplace(d_dot, "-", ".");
         datetime t1 = StringToTime(d_dot + " 09:00");
         datetime t2 = StringToTime(d_dot + " 18:20");
         ObjectCreate(0, obj_name, OBJ_TREND, 0, t1, p, t2, p);
         ObjectSetInteger(0, obj_name, OBJPROP_RAY_LEFT, false);
         ObjectSetInteger(0, obj_name, OBJPROP_RAY_RIGHT, true);
         ObjectSetInteger(0, obj_name, OBJPROP_BACK, true);
         string t = m_gex_raw[i].type;
         if(t == "Wall")
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrDarkOrange);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 2);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, STYLE_SOLID);
           }
         else if(t == "MidWall")
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrDodgerBlue);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 1);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, STYLE_DOT);
           }
         else if(t == "GammaFlip")
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrMagenta);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 2);
            ObjectSetInteger(0, obj_name, OBJPROP_STYLE, STYLE_DASH);
           }
         else
           {
            ObjectSetInteger(0, obj_name, OBJPROP_COLOR, clrMediumSeaGreen);
            ObjectSetInteger(0, obj_name, OBJPROP_WIDTH, 2);
           }
        }
     }

   //+------------------------------------------------------------------+
   //| Cálculo Causal do Nadaraya-Watson Envelope + RSI(7) + WDO        |
   //+------------------------------------------------------------------+
   void              ComputeCausalNWE(const MqlRates &rates[], int total_bars, int lookback, double bw, double mult,
                                      double &c_curr, double &u_curr, double &l_curr, double &s_curr,
                                      double &c_prev, double &u_prev, double &l_prev, double &s_prev)
     {
      // rates[] está ordenado de forma cronológica (0 = mais antigo, total_bars-1 = última barra fechada [1])
      int idx_curr = total_bars - 1;
      int idx_prev = total_bars - 2;
      double centers[];
      ArrayResize(centers, total_bars);

      double w[];
      ArrayResize(w, lookback);
      for(int k=0; k<lookback; k++)
         w[k] = MathExp(-((double)(k * k)) / (2.0 * bw * bw));

      int start_t = MathMax(0, total_bars - lookback - 4);
      for(int t=0; t<total_bars; t++)
        {
         if(t < start_t - lookback)
           {
            centers[t] = rates[t].close;
            continue;
           }
         int l_idx = MathMin(t, lookback - 1);
         double num = 0.0, den = 0.0;
         for(int k=0; k<=l_idx; k++)
           {
            num += w[k] * rates[t - k].close;
            den += w[k];
           }
         centers[t] = (den > 0.0) ? (num / den) : rates[t].close;
        }

      // MAE causal para idx_curr e idx_prev
      int l_c = MathMin(idx_curr, lookback - 1);
      double sum_err_c = 0.0;
      for(int k=0; k<=l_c; k++)
         sum_err_c += MathAbs(rates[idx_curr - k].close - centers[idx_curr - k]);
      double mae_c = sum_err_c / (double)(l_c + 1);

      int l_p = MathMin(idx_prev, lookback - 1);
      double sum_err_p = 0.0;
      for(int k=0; k<=l_p; k++)
         sum_err_p += MathAbs(rates[idx_prev - k].close - centers[idx_prev - k]);
      double mae_p = sum_err_p / (double)(l_p + 1);

      c_curr = centers[idx_curr];
      u_curr = c_curr + mae_c * mult;
      l_curr = c_curr - mae_c * mult;
      s_curr = centers[idx_curr] - centers[idx_curr - 1];

      c_prev = centers[idx_prev];
      u_prev = c_prev + mae_p * mult;
      l_prev = c_prev - mae_p * mult;
      s_prev = (idx_prev >= 1) ? (centers[idx_prev] - centers[idx_prev - 1]) : 0.0;
     }

   void              ComputeRsi7(const MqlRates &rates[], int total_bars, double &rsi_curr, double &rsi_prev)
     {
      rsi_curr = 50.0;
      rsi_prev = 50.0;
      if(total_bars < 10)
         return;
      int idx_c = total_bars - 1;
      int idx_p = total_bars - 2;

      double up_c = 0.0, dn_c = 0.0;
      for(int k=0; k<7; k++)
        {
         double diff = rates[idx_c - k].close - rates[idx_c - k - 1].close;
         if(diff > 0) up_c += diff;
         else         dn_c += (-diff);
        }
      up_c /= 7.0; dn_c /= 7.0;
      rsi_curr = (dn_c <= 1e-9) ? 100.0 : (100.0 - 100.0 / (1.0 + up_c / dn_c));

      double up_p = 0.0, dn_p = 0.0;
      for(int k=0; k<7; k++)
        {
         double diff = rates[idx_p - k].close - rates[idx_p - k - 1].close;
         if(diff > 0) up_p += diff;
         else         dn_p += (-diff);
        }
      up_p /= 7.0; dn_p /= 7.0;
      rsi_prev = (dn_p <= 1e-9) ? 100.0 : (100.0 - 100.0 / (1.0 + up_p / dn_p));
     }

   void              ComputeWdoMetrics()
     {
      m_wdo_ret3_1 = 0.0;
      m_wdo_z_1 = 0.0;
      double wdo_c[];
      int copied = CopyClose(m_wdo_symbol, PERIOD_M5, 1, 25, wdo_c);
      if(copied < 25) copied = CopyClose("WDOX26", PERIOD_M5, 1, 25, wdo_c);
      if(copied < 25) copied = CopyClose("WDOZ26", PERIOD_M5, 1, 25, wdo_c);
      if(copied < 25) copied = CopyClose("WDO$N",  PERIOD_M5, 1, 25, wdo_c);
      if(copied < 25)
         return;
      int last = copied - 1;
      if(wdo_c[last - 3] > 0.0)
         m_wdo_ret3_1 = (wdo_c[last] / wdo_c[last - 3] - 1.0) * 10000.0;

      double rets[20];
      double sum_r = 0.0;
      for(int k=0; k<20; k++)
        {
         int idx = last - k;
         rets[k] = (wdo_c[idx - 1] > 0.0) ? (wdo_c[idx] / wdo_c[idx - 1] - 1.0) : 0.0;
         sum_r += rets[k];
        }
      double mean_r = sum_r / 20.0;
      double var_r = 0.0;
      for(int k=0; k<20; k++)
         var_r += (rets[k] - mean_r) * (rets[k] - mean_r);
      double std_r = MathSqrt(var_r / 20.0);
      if(std_r > 1e-9)
         m_wdo_z_1 = (rets[0] - mean_r) / std_r;
     }

   void              FindNearestLevel(const double &lvls[], double price, double &min_dist, double &nearest_lvl)
     {
      min_dist = 999999.0;
      nearest_lvl = 0.0;
      int n = ArraySize(lvls);
      for(int i=0; i<n; i++)
        {
         double d = MathAbs(lvls[i] - price);
         if(d < min_dist)
           {
            min_dist = d;
            nearest_lvl = lvls[i];
           }
        }
     }

   //+------------------------------------------------------------------+
   //| Gerenciamento de Posição Virtual e Sincronização com MT5         |
   //+------------------------------------------------------------------+
   double            Round5(double val)
     {
      return MathRound(val / 5.0) * 5.0;
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

   void              DeletePendingOrdersForSlot(int k)
     {
      if(m_exec_mode != EXEC_HEDGING_DIRECT_MAGIC)
         return;
      ulong slot_magic = m_base_magic + (ulong)k;
      for(int i=OrdersTotal()-1; i>=0; i--)
        {
         ulong ord_ticket = OrderGetTicket(i);
         if(ord_ticket > 0 && OrderGetString(ORDER_SYMBOL) == _Symbol && (ulong)OrderGetInteger(ORDER_MAGIC) == slot_magic)
            m_trade.OrderDelete(ord_ticket);
        }
     }

   bool              HasPendingOrderForSlot(int k)
     {
      ulong slot_magic = m_base_magic + (ulong)k;
      for(int i=OrdersTotal()-1; i>=0; i--)
        {
         ulong ord_ticket = OrderGetTicket(i);
         if(ord_ticket > 0 && OrderGetString(ORDER_SYMBOL) == _Symbol && (ulong)OrderGetInteger(ORDER_MAGIC) == slot_magic)
            return true;
        }
      return false;
     }

   double            GetLastExitDealPrice(ulong slot_magic, double fallback_px, string &reason)
     {
      reason = "SL_TP_SERVER";
      if(!HistorySelect(TimeCurrent() - 86400, TimeCurrent() + 60))
         return fallback_px;
      int total = HistoryDealsTotal();
      for(int i=total-1; i>=0; i--)
        {
         ulong dticket = HistoryDealGetTicket(i);
         if(dticket > 0 && HistoryDealGetString(dticket, DEAL_SYMBOL) == _Symbol && (ulong)HistoryDealGetInteger(dticket, DEAL_MAGIC) == slot_magic)
           {
            long entry = HistoryDealGetInteger(dticket, DEAL_ENTRY);
            if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_INOUT)
              {
               double px = HistoryDealGetDouble(dticket, DEAL_PRICE);
               long d_rsn = HistoryDealGetInteger(dticket, DEAL_REASON);
               if(d_rsn == DEAL_REASON_SL)
                  reason = "SL";
               else if(d_rsn == DEAL_REASON_TP)
                  reason = "TP";
               if(px > 0.0)
                  return px;
              }
           }
        }
      return fallback_px;
     }

   //+------------------------------------------------------------------+
   //| Localiza Coordenadas Reais das Próximas MidWall e Main Wall      |
   //+------------------------------------------------------------------+
   void              FindStructuralTargets(double entry_px, int side, double front_run,
                                           double &tp_mid_px, double &tp_main_px,
                                           double &raw_mid_lvl, double &raw_main_lvl)
     {
      int n_all = ArraySize(m_levels_all);
      int n_walls = ArraySize(m_levels_walls);

      if(side == 1)
        {
         raw_mid_lvl = 0.0;
         int mid_idx_all = -1;
         for(int i=0; i<n_all; i++)
           {
            if(m_levels_all[i] >= entry_px + 135.0)
              {
               raw_mid_lvl = m_levels_all[i];
               mid_idx_all = i;
               break;
              }
           }
         if(raw_mid_lvl <= 0.0)
            raw_mid_lvl = entry_px + 460.0;

         raw_main_lvl = 0.0;
         for(int i=0; i<n_walls; i++)
           {
            if(m_levels_walls[i] >= entry_px + 300.0 && m_levels_walls[i] > raw_mid_lvl + 80.0)
              {
               raw_main_lvl = m_levels_walls[i];
               break;
              }
           }
         if(raw_main_lvl <= 0.0)
           {
            if(mid_idx_all >= 0 && (mid_idx_all + 1) < n_all && m_levels_all[mid_idx_all + 1] > raw_mid_lvl + 80.0)
               raw_main_lvl = m_levels_all[mid_idx_all + 1];
            else
               raw_main_lvl = raw_mid_lvl + 480.0;
           }

         tp_mid_px  = Round5(raw_mid_lvl  - front_run);
         tp_main_px = Round5(raw_main_lvl - front_run);
        }
      else
        {
         raw_mid_lvl = 0.0;
         int mid_idx_all = -1;
         for(int i=n_all-1; i>=0; i--)
           {
            if(m_levels_all[i] <= entry_px - 135.0)
              {
               raw_mid_lvl = m_levels_all[i];
               mid_idx_all = i;
               break;
              }
           }
         if(raw_mid_lvl <= 0.0)
            raw_mid_lvl = entry_px - 460.0;

         raw_main_lvl = 0.0;
         for(int i=n_walls-1; i>=0; i--)
           {
            if(m_levels_walls[i] <= entry_px - 300.0 && m_levels_walls[i] < raw_mid_lvl - 80.0)
              {
               raw_main_lvl = m_levels_walls[i];
               break;
              }
           }
         if(raw_main_lvl <= 0.0)
           {
            if(mid_idx_all > 0 && m_levels_all[mid_idx_all - 1] < raw_mid_lvl - 80.0)
               raw_main_lvl = m_levels_all[mid_idx_all - 1];
            else
               raw_main_lvl = raw_mid_lvl - 480.0;
           }

         tp_mid_px  = Round5(raw_mid_lvl  + front_run);
         tp_main_px = Round5(raw_main_lvl + front_run);
        }
     }

   double            CalcTargetPts(double entry_px, int dir, int tp_type, double tp_orig_pts,
                                   double &out_raw_mid, double &out_tp1_px)
     {
      double tp_mid, tp_main, raw_mid, raw_main;
      FindStructuralTargets(entry_px, dir, 20.0, tp_mid, tp_main, raw_mid, raw_main);
      out_raw_mid = raw_mid;
      out_tp1_px  = tp_mid;
      if(tp_type == 1) // TP_MIDWALL
         return MathMax(140.0, MathAbs(tp_mid - entry_px));
      if(tp_type == 2 || tp_type == 3) // TP_MAIN_WALL or TP_PARTIAL_MID_MAIN
         return MathMax(240.0, MathAbs(tp_main - entry_px));
      return tp_orig_pts;
     }

   double            CalcStage1StopPrice(int k)
     {
      int d = m_slots[k].dir;
      double avg_p = m_slots[k].avg_price;
      double cur_sl = m_slots[k].curr_sl;
      if(m_slots[k].be_mode == 0 || m_slots[k].def_wall <= 0.0)
         return (d == 1) ? Round5(avg_p + m_slots[k].be_lock) : Round5(avg_p - m_slots[k].be_lock);

      // BE_WALL_SHIELD / BE_TWO_STAGE_WALLS (Estágio 1): protege logo atrás da Wall (def_wall ∓ wall_buf)
      if(d == 1)
        {
         double sh1 = Round5(m_slots[k].def_wall - m_slots[k].wall_buf);
         sh1 = MathMax(cur_sl, MathMin(sh1, avg_p + 10.0));
         sh1 = MathMax(sh1, Round5(avg_p - 90.0));
         return sh1;
        }
      else
        {
         double sh1 = Round5(m_slots[k].def_wall + m_slots[k].wall_buf);
         sh1 = MathMin(cur_sl, MathMax(sh1, avg_p - 10.0));
         sh1 = MathMin(sh1, Round5(avg_p + 90.0));
         return sh1;
        }
     }

   double            CalcStage2StopPrice(int k, double ref_close)
     {
      int d = m_slots[k].dir;
      double avg_p = m_slots[k].avg_price;
      double raw_mid = m_slots[k].raw_mid_lvl;
      double buf = m_slots[k].wall_buf;
      if(d == 1)
        {
         if(raw_mid > 0.0 && ref_close > raw_mid + 10.0)
            return MathMax(Round5(avg_p + m_slots[k].be_lock), Round5(raw_mid - buf));
         return Round5(avg_p + m_slots[k].be_lock);
        }
      else
        {
         if(raw_mid > 0.0 && ref_close < raw_mid - 10.0)
            return MathMin(Round5(avg_p - m_slots[k].be_lock), Round5(raw_mid + buf));
         return Round5(avg_p - m_slots[k].be_lock);
        }
     }

   void              ExecutePartialExitVirtual(int k, double partial_px, double ref_open_or_px)
     {
      if(m_slots[k].dir == 0 || m_slots[k].partial_done || m_slots[k].lots < 2)
         return;
      int closed_lots = m_slots[k].lots / 2;
      double pts_leg1 = (partial_px - m_slots[k].avg_price) * (double)m_slots[k].dir - 10.0;
      double pnl_brl = pts_leg1 * (double)closed_lots * m_lot_mult * 0.20;
      m_slots[k].closed_pnl_today_brl += pnl_brl;
      m_slots[k].lots -= closed_lots;
      m_slots[k].partial_done = true;

      // Protege o lote remanescente no Estágio 1 (atrás da Wall de entrada)
      double cand_sl = CalcStage1StopPrice(k);
      if((m_slots[k].dir == 1 && ref_open_or_px > cand_sl + 5.0) || (m_slots[k].dir == -1 && ref_open_or_px < cand_sl - 5.0))
        {
         m_slots[k].curr_sl = (m_slots[k].dir == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
         m_slots[k].be_active = true;
        }
      PrintFormat("[JUMBA %s] SAIDA PARCIAL 50%% NA MIDWALL @ %.0f | Lotes Restantes=%d | Novo SL=%.0f | PnL Parcial=R$ %.2f",
                  m_slots[k].name, partial_px, m_slots[k].lots, m_slots[k].curr_sl, pnl_brl);
      SaveVirtualStateToDisk();
     }

   double            FindNextWallBehind(double entry_px, int dir, double min_d=140.0, double max_d=280.0, double fallback_d=190.0)
     {
      int n = ArraySize(m_levels_all);
      if(dir == 1)
        {
         for(int i=n-1; i>=0; i--)
           {
            double d = entry_px - m_levels_all[i];
            if(d >= min_d && d <= max_d)
               return Round5(d);
           }
        }
      else
        {
         for(int i=0; i<n; i++)
           {
            double d = m_levels_all[i] - entry_px;
            if(d >= min_d && d <= max_d)
               return Round5(d);
           }
        }
      return Round5(fallback_d);
     }

   void              OpenVirtualSingle(int k, int dir, double entry_p, datetime bar_t,
                                       double tp_pts, double sl_pts, double be_trig, double be_lock,
                                       double tr_trig, double tr_dist, int max_hold=15, bool is_intrabar=false,
                                       int init_lots=1, double def_wall=0.0, int be_mode=0, double wall_buf=0.0,
                                       double raw_mid_lvl=0.0, double tp1_px=0.0, bool partial_mode=false)
     {
      double p5 = Round5(entry_p);
      m_slots[k].dir = dir;
      m_slots[k].lots = MathMax(1, init_lots);
      m_slots[k].leg_stage = 1;
      m_slots[k].p1_entry = p5;
      m_slots[k].avg_price = p5;
      m_slots[k].curr_sl = (dir == 1) ? Round5(p5 - sl_pts) : Round5(p5 + sl_pts);
      m_slots[k].curr_tp = (dir == 1) ? Round5(p5 + tp_pts) : Round5(p5 - tp_pts);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
      m_slots[k].be_stage2_active = false;
      m_slots[k].opened_intrabar = is_intrabar;
      m_slots[k].real_synced = false;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = bar_t;
      m_slots[k].be_trig = be_trig;
      m_slots[k].be_lock = be_lock;
      m_slots[k].tr_trig = tr_trig;
      m_slots[k].tr_dist = tr_dist;
      m_slots[k].max_hold_bars = max_hold;
      m_slots[k].init_sl_pts = sl_pts;
      m_slots[k].init_tp_pts = tp_pts;
      m_slots[k].def_wall = def_wall;
      m_slots[k].be_mode = be_mode;
      m_slots[k].wall_buf = wall_buf;
      m_slots[k].raw_mid_lvl = raw_mid_lvl;
      m_slots[k].tp1_px = tp1_px;
      m_slots[k].partial_mode = partial_mode;
      m_slots[k].partial_done = false;
      if(k >= 13 && k <= 16)
        {
         double s2 = FindNextWallBehind(p5, dir, 140.0, 280.0, 190.0);
         double sl2_pts = 175.0;
         m_slots[k].step2_dist = s2;
         m_slots[k].step3_dist = 0.0;
         m_slots[k].lot1 = 1;
         m_slots[k].lot2 = 2;
         m_slots[k].lot3 = 0;
         m_slots[k].tp_avg_pts = 170.0;
         m_slots[k].max_sl_pts = sl2_pts;
         m_slots[k].init_sl_pts = s2 + sl2_pts;
         m_slots[k].curr_sl = (dir == 1) ? Round5(p5 - (s2 + sl2_pts)) : Round5(p5 + (s2 + sl2_pts));
        }
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_bars_left = 0;
      SaveVirtualStateToDisk();
     }

   void              OpenVirtualGrid(int k, int dir, double entry_p, datetime bar_t,
                                     double step2, double step3, int l1, int l2, int l3,
                                     double tp_avg, double max_sl, double be_avg_trig, double be_avg_lock=25.0, int max_hold=28)
     {
      double p5 = Round5(entry_p);
      m_slots[k].dir = dir;
      m_slots[k].lots = l1;
      m_slots[k].leg_stage = 1;
      m_slots[k].p1_entry = p5;
      m_slots[k].avg_price = p5;
      double worst_avg_off = 0.0;
      if(l3 > 0)
         worst_avg_off = (l2 * step2 + l3 * step3) / (double)(l1 + l2 + l3);
      else if(l2 > 0)
         worst_avg_off = (l2 * step2) / (double)(l1 + l2);
      double init_sl_dist = (k >= 13 && k <= 16) ? MathMax(max_sl, worst_avg_off + max_sl) : max_sl;
      m_slots[k].curr_sl = (dir == 1) ? Round5(p5 - init_sl_dist) : Round5(p5 + init_sl_dist);
      m_slots[k].curr_tp = (dir == 1) ? Round5(p5 + tp_avg) : Round5(p5 - tp_avg);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
      m_slots[k].be_stage2_active = false;
      m_slots[k].opened_intrabar = false;
      m_slots[k].real_synced = false;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = bar_t;
      m_slots[k].step2_dist = step2;
      m_slots[k].step3_dist = step3;
      m_slots[k].lot1 = l1;
      m_slots[k].lot2 = l2;
      m_slots[k].lot3 = l3;
      m_slots[k].tp_avg_pts = tp_avg;
      m_slots[k].max_sl_pts = max_sl;
      m_slots[k].be_trig = be_avg_trig;
      m_slots[k].be_lock = be_avg_lock;
      m_slots[k].tr_trig = 0.0;
      m_slots[k].tr_dist = 0.0;
      m_slots[k].max_hold_bars = max_hold;
      m_slots[k].init_sl_pts = init_sl_dist;
      m_slots[k].init_tp_pts = tp_avg;
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_bars_left = 0;
      SaveVirtualStateToDisk();
     }

   void              AppendWinTradeAudit(int k, double exit_price, double pnl_brl, string reason)
     {
      if(MQLInfoInteger(MQL_OPTIMIZATION))
         return;
      string fn = StringFormat("jumba_live_trades_audit_%I64d.csv", AccountInfoInteger(ACCOUNT_LOGIN));
      int h = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ|FILE_SHARE_WRITE);
      if(h == INVALID_HANDLE)
         return;
      FileSeek(h, 0, SEEK_END);
      ulong slot_magic = m_base_magic + (ulong)k;
      string t_str = TimeToString(SafeTime(), TIME_DATE|TIME_SECONDS);
      string line = StringFormat("%s;EST-%02d;%I64u;%s;%d;%d;%.1f;%.1f;%.2f;%s\n",
                                 t_str, k, slot_magic, _Symbol, m_slots[k].dir, m_slots[k].lots,
                                 m_slots[k].avg_price, exit_price, pnl_brl, reason);
      FileWriteString(h, line);
      FileClose(h);
     }

   void              CloseVirtualSlot(int k, double exit_price, string reason)
     {
      if(m_slots[k].dir == 0)
         return;
      double pts_per_lot = (exit_price - m_slots[k].avg_price) * (double)m_slots[k].dir - 10.0;
      double pnl_brl = pts_per_lot * (double)m_slots[k].lots * m_lot_mult * 0.20;
      m_slots[k].closed_pnl_today_brl += pnl_brl;
      m_slots[k].trades_today += 1;
      PrintFormat("[JUMBA %s] FECHADO (%s) | Dir=%d | Lotes=%d | PM=%.0f -> Saida=%.0f | PnL=R$ %.2f",
                  m_slots[k].name, reason, m_slots[k].dir, m_slots[k].lots, m_slots[k].avg_price, exit_price, pnl_brl);
      AppendWinTradeAudit(k, exit_price, pnl_brl, reason);
      ResetSlotPosition(k);
      SaveVirtualStateToDisk();
     }

   double            GetTotalDailyPnLBRL()
     {
      double total = 0.0;
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      for(int k=1; k<=16; k++)
        {
         total += m_slots[k].closed_pnl_today_brl;
         if(m_slots[k].dir != 0 && bid > 0.0)
           {
            double open_pts = (bid - m_slots[k].avg_price) * (double)m_slots[k].dir;
            total += open_pts * (double)m_slots[k].lots * m_lot_mult * 0.20;
           }
        }
      return total;
     }

   //+------------------------------------------------------------------+
   //| Sincroniza os Slots Virtuais com Ordens Reais no MetaTrader 5    |
   //+------------------------------------------------------------------+
   void              SyncRealPositionsWithVirtualSlots()
     {
      // Trava Estrutural Absoluta: Conta HEDGING ou EA Individual SEMPRE opera em EXEC_HEDGING_DIRECT_MAGIC!
      if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || m_single_id > 0 || GetSingleActiveSlotId() > 0)
         m_exec_mode = EXEC_HEDGING_DIRECT_MAGIC;

      if(m_exec_mode == EXEC_NETTING_VIRTUAL_SYNC)
        {
         if(!MQLInfoInteger(MQL_TESTER) && (GetTickCount64() - m_last_net_sync_ms) < 4000)
            return;

         double target_net_lots = 0.0;
         for(int k=1; k<=16; k++)
           {
            if(m_slots[k].enabled && m_slots[k].dir != 0)
              {
               int c_lots = MathMin(GetMaxBaseLotsForSlot(k), MathMax(0, m_slots[k].lots));
               target_net_lots += (double)(m_slots[k].dir * c_lots) * m_lot_mult;
              }
           }
         double max_port_net = 12.0 * m_lot_mult;
         if(target_net_lots > max_port_net)  target_net_lots = max_port_net;
         if(target_net_lots < -max_port_net) target_net_lots = -max_port_net;
         target_net_lots = MathRound(target_net_lots);

         double actual_net_lots = 0.0;
         for(int i=PositionsTotal()-1; i>=0; i--)
           {
            if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol)
              {
               if(m_pos.PositionType() == POSITION_TYPE_BUY)
                  actual_net_lots += m_pos.Volume();
               else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                  actual_net_lots -= m_pos.Volume();
              }
           }

         double diff = target_net_lots - actual_net_lots;
         if(MathAbs(diff) >= 0.99)
           {
            m_trade.SetExpertMagicNumber(m_base_magic);
            double vol = MathRound(MathMin(MathAbs(diff), 3.0 * m_lot_mult));
            if(vol >= 1.0 && m_guard.AllowOrder(vol, MathAbs(target_net_lots) < MathAbs(actual_net_lots)))
              {
               if(diff > 0.0)
                  m_trade.Buy(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
               else
                  m_trade.Sell(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
               m_last_net_sync_ms = GetTickCount64();
               SaveVirtualStateToDisk();
              }
           }

         if(!MQLInfoInteger(MQL_TESTER) && MathAbs(target_net_lots) >= 0.99 && PositionSelect(_Symbol))
           {
            int net_dir = (target_net_lots > 0.0) ? 1 : -1;
            int open_cnt = 0;
            double worst_sl = 0.0;
            double best_tp  = 0.0;
            for(int k=1; k<=16; k++)
              {
               if(m_slots[k].enabled && m_slots[k].dir == net_dir && m_slots[k].curr_sl > 0.0)
                 {
                  open_cnt++;
                  if(net_dir == 1)
                    {
                     if(worst_sl == 0.0 || m_slots[k].curr_sl < worst_sl) worst_sl = m_slots[k].curr_sl;
                     if(best_tp == 0.0  || m_slots[k].curr_tp > best_tp)  best_tp  = m_slots[k].curr_tp;
                    }
                  else
                    {
                     if(worst_sl == 0.0 || m_slots[k].curr_sl > worst_sl) worst_sl = m_slots[k].curr_sl;
                     if(best_tp == 0.0  || m_slots[k].curr_tp < best_tp)  best_tp  = m_slots[k].curr_tp;
                    }
                 }
              }
            if(worst_sl > 0.0)
              {
               double pad = (open_cnt == 1) ? 0.0 : 25.0;
               double srv_sl = (net_dir == 1) ? Round5(worst_sl - pad) : Round5(worst_sl + pad);
               double srv_tp = (open_cnt == 1 && best_tp > 0.0 && !m_slots[m_single_id > 0 ? m_single_id : 1].partial_mode) ? Round5(best_tp) : 0.0;
               double cur_srv_sl = PositionGetDouble(POSITION_SL);
               double cur_srv_tp = PositionGetDouble(POSITION_TP);
               if(MathAbs(cur_srv_sl - srv_sl) >= 5.0 || MathAbs(cur_srv_tp - srv_tp) >= 5.0)
                  m_trade.PositionModify(_Symbol, srv_sl, srv_tp);
              }
           }
        }
      else
        {
         // EXEC_HEDGING_DIRECT_MAGIC: Cada slot k gerencia sua posição com MagicNumber = m_base_magic + k
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            ulong slot_magic = m_base_magic + (ulong)k;
            int max_base = GetMaxBaseLotsForSlot(k);
            if(m_slots[k].lots > max_base)
               m_slots[k].lots = max_base;
            if(m_slots[k].lots < 0)
               m_slots[k].lots = 0;

            double max_slot_vol = MathRound((double)max_base * m_lot_mult);
            double target_lots = MathRound((double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult);
            if(target_lots > max_slot_vol)  target_lots = max_slot_vol;
            if(target_lots < -max_slot_vol) target_lots = -max_slot_vol;

            double actual_lots = 0.0;
            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                 {
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_lots += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_lots -= m_pos.Volume();
                 }
              }

            ulong now_ms = GetTickCount64();
            if(!MQLInfoInteger(MQL_TESTER) && m_last_order_ms[k] > 0)
              {
               ulong elapsed = now_ms - m_last_order_ms[k];
               if(elapsed < 1500 || (elapsed < 5000 && MathAbs(target_lots - m_last_sent_lots[k]) < 0.01))
                  continue;
              }

            if(target_lots == 0.0 && MathAbs(actual_lots) >= 0.99)
              {
               m_trade.SetExpertMagicNumber(slot_magic);
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                     m_trade.PositionClose(m_pos.Ticket());
                 }
               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = 0.0;
               continue;
              }
            else if(MathAbs(target_lots - actual_lots) >= 0.99)
              {
               if(target_lots * actual_lots < 0.0)
                 {
                  m_trade.SetExpertMagicNumber(slot_magic);
                  for(int i=PositionsTotal()-1; i>=0; i--)
                    {
                     if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                  m_last_order_ms[k] = GetTickCount64();
                  m_last_sent_lots[k] = 0.0;
                  continue;
                 }

               // Circuit Breaker: Nunca adiciona lotes se ja atingiu o teto maximo do slot!
               if(MathAbs(actual_lots) >= max_slot_vol - 0.01 && MathAbs(target_lots) > MathAbs(actual_lots))
                  continue;

               double delta = target_lots - actual_lots;
               double sl_srv = (m_slots[k].curr_sl > 0.0) ? Round5(m_slots[k].curr_sl) : 0.0;
               double tp_srv = (m_slots[k].curr_tp > 0.0) ? Round5(m_slots[k].curr_tp) : 0.0;
               if(!MQLInfoInteger(MQL_TESTER))
                 {
                  if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
                    {
                     if(!m_slots[k].real_synced)
                       {
                        ResetSlotPosition(k);
                        SaveVirtualStateToDisk();
                       }
                     continue;
                    }
                  double live_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                  double live_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                  if(!m_slots[k].real_synced && live_bid > 0.0 && live_ask > 0.0)
                    {
                     if(MathAbs(live_bid - m_slots[k].p1_entry) > 150.0)
                       {
                        PrintFormat("[JUMBA %s] Entrada cancelada por atraso/slippage (Sinal=%.0f vs Atual=%.0f)",
                                    m_slots[k].name, m_slots[k].p1_entry, live_bid);
                        ResetSlotPosition(k);
                        SaveVirtualStateToDisk();
                        continue;
                       }
                     double fill_ref = (m_slots[k].dir == 1) ? Round5(live_ask) : Round5(live_bid);
                     m_slots[k].p1_entry = Round5(live_bid);
                     m_slots[k].avg_price = Round5(live_bid);
                     double sl_d = MathMax(200.0, m_slots[k].init_sl_pts);
                     double tp_d = MathMax(160.0, m_slots[k].init_tp_pts);
                     m_slots[k].curr_sl = (m_slots[k].dir == 1) ? Round5(fill_ref - sl_d) : Round5(fill_ref + sl_d);
                     m_slots[k].curr_tp = (m_slots[k].dir == 1) ? Round5(fill_ref + tp_d) : Round5(fill_ref - tp_d);
                     sl_srv = m_slots[k].curr_sl;
                     tp_srv = m_slots[k].curr_tp;
                    }
                 }
               DeletePendingOrdersForSlot(k);
               m_trade.SetExpertMagicNumber(slot_magic);
               bool sent = false;
               // Se for reducao parcial de posicao existente no mesmo sentido, usa PositionClosePartial
               if(actual_lots != 0.0 && MathAbs(target_lots) < MathAbs(actual_lots) && target_lots * actual_lots > 0.0)
                 {
                  double vol_reduce = MathRound(MathAbs(delta));
                  for(int i=PositionsTotal()-1; i>=0 && vol_reduce >= 0.99; i--)
                    {
                     if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                       {
                        double pv = m_pos.Volume();
                        if(pv <= vol_reduce + 0.01)
                          {
                           if(m_trade.PositionClose(m_pos.Ticket()))
                             {
                              vol_reduce -= pv;
                              sent = true;
                             }
                          }
                        else
                          {
                           if(m_trade.PositionClosePartial(m_pos.Ticket(), vol_reduce))
                             {
                              vol_reduce = 0.0;
                              sent = true;
                             }
                          }
                       }
                    }
                 }
               else
                 {
                  double room = MathMax(0.0, max_slot_vol - MathAbs(actual_lots));
                  double vol = MathRound(MathMin(MathAbs(delta), room));
                  if(vol < 1.0 || vol > max_slot_vol)
                     continue;
                  if(!m_guard.AllowOrder(vol))
                     continue;
                  if(delta > 0.0)
                     sent = m_trade.Buy(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
                  else if(delta < 0.0)
                     sent = m_trade.Sell(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
                 }

               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = target_lots;

               if(sent)
                 {
                  m_slots[k].real_synced = true;
                 }
               else if(!MQLInfoInteger(MQL_TESTER) && !m_slots[k].real_synced)
                 {
                  ResetSlotPosition(k);
                 }
               SaveVirtualStateToDisk();
              }

            // Sincroniza SL e TP físicos no servidor para todos os tickets deste MagicNumber
            if(MathAbs(target_lots) >= 0.99 && MathAbs(actual_lots) >= 0.99 && m_slots[k].curr_sl > 0.0)
              {
               double sl_srv = Round5(m_slots[k].curr_sl);
               double tp_srv = (m_slots[k].curr_tp > 0.0) ? Round5(m_slots[k].curr_tp) : 0.0;
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                    {
                     m_slots[k].real_synced = true;
                     if(MathAbs(m_pos.StopLoss() - sl_srv) >= 5.0 || MathAbs(m_pos.TakeProfit() - tp_srv) >= 5.0)
                        m_trade.PositionModify(m_pos.Ticket(), sl_srv, tp_srv);
                    }
                 }
              }
           }
        }
     }

   //+------------------------------------------------------------------+
   //| Processamento Tick a Tick (Ordens Nativas + Saídas SL/TP/Parcial)|
   //+------------------------------------------------------------------+
   void              OnTickProcess()
     {
      if(!m_state_reconciled && !MQLInfoInteger(MQL_TESTER))
        {
         if(AccountInfoInteger(ACCOUNT_LOGIN) <= 0 || !TerminalInfoInteger(TERMINAL_CONNECTED))
            return;
         LoadVirtualStateFromDisk();
         ReconcileWithBrokerOnStartup();
         m_state_reconciled = true;
         RenderHudComment();
        }

      MqlRates r_curr[];
      if(CopyRates(_Symbol, PERIOD_M5, 0, 2, r_curr) < 2)
         return;

      datetime curr_bar_time = r_curr[1].time;
      if(m_last_m5_bar_time == 0)
         m_last_m5_bar_time = curr_bar_time;
      string today_str = DateStr(curr_bar_time);
      if(!MQLInfoInteger(MQL_TESTER))
        {
         string loc_str = DateStr(TimeLocal());
         if(loc_str > today_str)
            today_str = loc_str;
        }
      int t_min = TimeMinutes(SafeTime());
      if(m_guard.CheckGlobalKill())
        {
         Comment("[JUMBA WIN] KILL-SWITCH ATIVO: " + m_guard.Reason());
         return;
        }

      LoadDailyGexWalls(today_str);

      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double last_px = SymbolInfoDouble(_Symbol, SYMBOL_LAST);
      if(last_px <= 0.0)
         last_px = bid;

      // 0. Em modo HEDGING, verifica primeiro se alguma ordem pendente nativa executou ou se algum SL/TP nativo fechou no servidor!
      if(m_exec_mode == EXEC_HEDGING_DIRECT_MAGIC)
        {
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            ulong slot_magic = m_base_magic + (ulong)k;
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

            // A. Ordem Pendente Nativa (Limit/Stop) acabou de executar no servidor MT5!
            if(m_slots[k].dir == 0 && m_slots[k].pend_dir != 0)
              {
               if(MathAbs(actual_lots) >= 0.99)
                 {
                  double fill_px = (m_slots[k].pend_dir == 1 && pos_open_px > 0.0) ? Round5(pos_open_px - 5.0) : ((pos_open_px > 0.0) ? pos_open_px : m_slots[k].pend_price);
                  OpenVirtualSingle(k, m_slots[k].pend_dir, fill_px, m_slots[k].pend_bar_time,
                                    m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts,
                                    m_slots[k].be_trig, m_slots[k].be_lock,
                                    m_slots[k].tr_trig, m_slots[k].tr_dist,
                                    m_slots[k].max_hold_bars, true,
                                    m_slots[k].pend_init_lots, m_slots[k].pend_def_wall,
                                    m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf,
                                    m_slots[k].pend_raw_mid_lvl, m_slots[k].pend_tp1_px,
                                    m_slots[k].pend_partial_mode);
                  m_slots[k].real_synced = true;
                  m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                  // EST-15 agora permite ate 3 trades/dia
                  PrintFormat("[JUMBA %s] ORDEM PENDENTE NATIVA EXECUTADA | Dir=%d | Lotes=%d @ %.0f",
                              m_slots[k].name, m_slots[k].dir, m_slots[k].lots, m_slots[k].avg_price);
                 }
               else if(!HasPendingOrderForSlot(k))
                 {
                  string rsn = "SL_TP_INTRABAR";
                  double deal_px = GetLastExitDealPrice(slot_magic, m_slots[k].pend_price, rsn);
                  if(rsn == "SL" || rsn == "TP")
                    {
                     OpenVirtualSingle(k, m_slots[k].pend_dir, m_slots[k].pend_price, m_slots[k].pend_bar_time,
                                       m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts,
                                       m_slots[k].be_trig, m_slots[k].be_lock,
                                       m_slots[k].tr_trig, m_slots[k].tr_dist,
                                       m_slots[k].max_hold_bars, true,
                                       m_slots[k].pend_init_lots, m_slots[k].pend_def_wall,
                                       m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf,
                                       m_slots[k].pend_raw_mid_lvl, m_slots[k].pend_tp1_px,
                                       m_slots[k].pend_partial_mode);
                     m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                     // EST-15 agora permite ate 3 trades/dia
                     CloseVirtualSlot(k, deal_px, rsn);
                    }
                 }
              }
            // B. Posição Aberta foi encerrada nativamente pelo SL ou TP no Servidor da Corretora / Tester!
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

      // Trava de Perda Máxima Diária ou Encerramento de Fim de Dia (17h15 = 1035 min)
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

      // 1. Verifica se abriu uma nova barra M5 -> Avalia fechamento da barra anterior, atualiza BE/Trail e arma sinais!
      if(curr_bar_time != m_last_m5_bar_time)
        {
         OnNewM5Bar(curr_bar_time, today_str);
         m_last_m5_bar_time = curr_bar_time;
        }

      // 2. Monitoramento Intrabar (Disparo pendente em Netting, Saída Parcial 50% na MidWall e Saídas SL/TP em Netting)
      for(int k=1; k<=16; k++)
        {
         if(!m_slots[k].enabled)
            continue;

         // A. Disparo de Ordens Pendentes em Netting (ou fallback se ordem pendente nativa não pôde ser apregoada)
         if(m_slots[k].dir == 0 && m_slots[k].pend_dir != 0 && m_slots[k].pend_bar_time == curr_bar_time)
           {
            if(m_exec_mode == EXEC_NETTING_VIRTUAL_SYNC || !HasPendingOrderForSlot(k))
              {
               bool triggered = false;
               if(m_slots[k].pend_type == 1) // LIMIT
                 {
                  if(m_slots[k].pend_dir == 1 && last_px <= m_slots[k].pend_price)
                     triggered = true;
                  else if(m_slots[k].pend_dir == -1 && last_px >= m_slots[k].pend_price)
                     triggered = true;
                 }
               else if(m_slots[k].pend_type == 2) // STOP
                 {
                  if(m_slots[k].pend_dir == 1 && last_px >= m_slots[k].pend_price)
                     triggered = true;
                  else if(m_slots[k].pend_dir == -1 && last_px <= m_slots[k].pend_price)
                     triggered = true;
                 }

               if(triggered)
                 {
                  OpenVirtualSingle(k, m_slots[k].pend_dir, m_slots[k].pend_price, curr_bar_time,
                                    m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts,
                                    m_slots[k].be_trig, m_slots[k].be_lock,
                                    m_slots[k].tr_trig, m_slots[k].tr_dist,
                                    m_slots[k].max_hold_bars, true,
                                    m_slots[k].pend_init_lots, m_slots[k].pend_def_wall,
                                    m_slots[k].pend_be_mode, m_slots[k].pend_wall_buf,
                                    m_slots[k].pend_raw_mid_lvl, m_slots[k].pend_tp1_px,
                                    m_slots[k].pend_partial_mode);
                  m_slots[k].last_entry_bar_time = curr_bar_time;
                  // EST-15 agora permite ate 3 trades/dia
                  PrintFormat("[JUMBA %s] ORDEM PENDENTE EXECUTADA | Dir=%d | Lotes=%d @ %.0f",
                              m_slots[k].name, m_slots[k].dir, m_slots[k].lots, m_slots[k].avg_price);
                 }
              }
           }

         // B. Gerenciamento de Posição Aberta (Saída Parcial na MidWall + Saídas Virtuais em Netting)
         if(m_slots[k].dir != 0)
           {
            int d = m_slots[k].dir;

            // Smart Grid Ancorado na Proxima Wall (EST-13 e EST-14: Perna 2 de +2 lotes na 2a Wall GEX)
            if((k >= 13 && k <= 16) && m_slots[k].leg_stage == 1 && !m_slots[k].be_active && m_slots[k].lot2 > 0 && m_slots[k].step2_dist > 0.0)
              {
               double p2_lvl = (d == 1) ? Round5(m_slots[k].p1_entry - m_slots[k].step2_dist) : Round5(m_slots[k].p1_entry + m_slots[k].step2_dist);
               if((d == 1 && last_px <= p2_lvl) || (d == -1 && last_px >= p2_lvl))
                 {
                  int new_lots = m_slots[k].lot1 + m_slots[k].lot2;
                  m_slots[k].avg_price = Round5((m_slots[k].p1_entry * m_slots[k].lot1 + p2_lvl * m_slots[k].lot2) / (double)new_lots);
                  m_slots[k].lots = new_lots;
                  m_slots[k].leg_stage = 2;
                  m_slots[k].be_active = false;
                  m_slots[k].max_fav_pts = 0.0;
                  m_slots[k].be_trig = 90.0;
                  m_slots[k].be_lock = 15.0;
                  m_slots[k].be_mode = 0;
                  m_slots[k].curr_tp = (d == 1) ? Round5(m_slots[k].avg_price + m_slots[k].tp_avg_pts) : Round5(m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                  m_slots[k].curr_sl = (d == 1) ? Round5(p2_lvl - m_slots[k].max_sl_pts) : Round5(p2_lvl + m_slots[k].max_sl_pts);
                  PrintFormat("[JUMBA %s] SMART GRID PERNA 2 NA NEXT_WALL EXECUTADA @ %.0f | Lotes=%d | PM=%.0f | Novo TP=%.0f | Novo SL=%.0f",
                              m_slots[k].name, p2_lvl, m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_tp, m_slots[k].curr_sl);
                  SaveVirtualStateToDisk();
                 }
              }

            // Verifica Saída Parcial de 50% na MidWall (ex: EST-16 NOVO-3 com 2 lotes)
            if(m_slots[k].partial_mode && !m_slots[k].partial_done && m_slots[k].lots >= 2 && m_slots[k].tp1_px > 0.0)
              {
               if((d == 1 && last_px >= m_slots[k].tp1_px) || (d == -1 && last_px <= m_slots[k].tp1_px))
                  ExecutePartialExitVirtual(k, m_slots[k].tp1_px, last_px);
              }

            // Em modo NETTING (onde não há SL/TP individual por ticket no servidor), fecha virtualmente por last_px
            if(m_exec_mode == EXEC_NETTING_VIRTUAL_SYNC)
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
   //| Avaliação de Fechamento de Barra M5 (MIX CAMPEÃO EST-01 A EST-16)|
   //+------------------------------------------------------------------+
   void              OnNewM5Bar(datetime new_bar_time, string today_str)
     {
      MqlRates rates[];
      int copied = CopyRates(_Symbol, PERIOD_M5, 1, 110, rates);
      if(copied < 60 || ArraySize(m_levels_all) == 0)
         return;

      MqlRates r0[];
      double new_bar_open = (CopyRates(_Symbol, PERIOD_M5, 0, 1, r0) >= 1) ? r0[0].open : rates[copied - 1].close;

      // Barra que acabou de fechar é rates[copied-1], e a anterior a ela é rates[copied-2]
      MqlRates b1 = rates[copied - 1];
      MqlRates b2 = rates[copied - 2];
      string b1_date = DateStr(b1.time);
      int b1_tmin = TimeMinutes(b1.time);
      int new_tmin = TimeMinutes(new_bar_time);

      // Calcula NWE(50, 5.0, 2.0), NWE(30, 3.0, 1.6), RSI(7) e WDO
      ComputeCausalNWE(rates, copied, 50, 5.0, 2.0,
                       m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1,
                       m_n50_c_2, m_n50_u_2, m_n50_l_2, m_n50_s_2);
      ComputeCausalNWE(rates, copied, 30, 3.0, 1.6,
                       m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1,
                       m_n30_c_2, m_n30_u_2, m_n30_l_2, m_n30_s_2);
      ComputeRsi7(rates, copied, m_rsi7_1, m_rsi7_2);
      ComputeWdoMetrics();

      double d_l, lvl_s, d_h, lvl_r;
      FindNearestLevel(m_levels_all, b1.low,  d_l, lvl_s);
      FindNearestLevel(m_levels_all, b1.high, d_h, lvl_r);
      double dw_l_main, w_s_main, dw_h_main, w_r_main;
      FindNearestLevel(m_levels_walls, b1.low,  dw_l_main, w_s_main);
      FindNearestLevel(m_levels_walls, b1.high, dw_h_main, w_r_main);

      // 1. Gerencia ordens pendentes multi-barra (valid_bars=2 e Rolling Stop) e atualiza BE / Trailing / Time Stop!
      for(int k=1; k<=16; k++)
        {
         if(m_slots[k].pend_dir != 0)
           {
            m_slots[k].pend_bars_left -= 1;
            if(m_slots[k].pend_bars_left <= 0 || b1_date != today_str || new_tmin > 1000)
              {
               DeletePendingOrdersForSlot(k);
               m_slots[k].pend_dir = 0;
               m_slots[k].pend_bars_left = 0;
              }
            else
              {
               // Mantém por mais 1 barra (valid_bars=2); se for Rolling Stop, atualiza gatilho para a nova High[1]/Low[1]!
               DeletePendingOrdersForSlot(k);
               double next_trig = m_slots[k].pend_price;
               if(m_slots[k].pend_rolling_stop)
                 {
                  if(m_slots[k].pend_dir == 1 && b1.low >= m_slots[k].pend_def_wall - 60.0)
                    {
                     double cand_stop = Round5(b1.high + 15.0);
                     if(cand_stop < next_trig && (cand_stop - m_slots[k].pend_def_wall) <= 135.0)
                        next_trig = cand_stop;
                    }
                  else if(m_slots[k].pend_dir == -1 && b1.high <= m_slots[k].pend_def_wall + 60.0)
                    {
                     double cand_stop = Round5(b1.low - 15.0);
                     if(cand_stop > next_trig && (m_slots[k].pend_def_wall - cand_stop) <= 135.0)
                        next_trig = cand_stop;
                    }
                 }
               double raw_m = m_slots[k].pend_raw_mid_lvl, tp1_p = m_slots[k].pend_tp1_px;
               int tp_t = m_slots[k].pend_partial_mode ? 3 : 1;
               double new_tp_pts = (k >= 13 && k <= 16) ? m_slots[k].pend_tp_pts : CalcTargetPts(next_trig, m_slots[k].pend_dir, tp_t, m_slots[k].pend_tp_pts, raw_m, tp1_p);
               ArmPendingOrder(k, m_slots[k].pend_dir, m_slots[k].pend_type, next_trig, new_bar_time, new_bar_open,
                               new_tp_pts, m_slots[k].pend_sl_pts, m_slots[k].be_trig, m_slots[k].be_lock,
                               m_slots[k].tr_trig, m_slots[k].tr_dist, m_slots[k].max_hold_bars,
                               m_slots[k].pend_init_lots, m_slots[k].pend_def_wall, m_slots[k].pend_be_mode,
                               m_slots[k].pend_wall_buf, raw_m, tp1_p, m_slots[k].pend_partial_mode,
                               m_slots[k].pend_bars_left, m_slots[k].pend_rolling_stop);
              }
           }

         if(m_slots[k].dir != 0)
           {
            int d = m_slots[k].dir;

            // Verifica se a barra b1 atingiu o TP1 parcial na MidWall (caso ainda não tenha executado intrabar)
            if(m_slots[k].partial_mode && !m_slots[k].partial_done && m_slots[k].lots >= 2 && m_slots[k].tp1_px > 0.0)
              {
               if((d == 1 && b1.high >= m_slots[k].tp1_px) || (d == -1 && b1.low <= m_slots[k].tp1_px))
                  ExecutePartialExitVirtual(k, m_slots[k].tp1_px, new_bar_open);
              }

            if(m_slots[k].opened_intrabar)
              {
               double fav_c = (d == 1) ? (b1.close - m_slots[k].avg_price) : (m_slots[k].avg_price - b1.close);
               if(fav_c > m_slots[k].max_fav_pts)
                  m_slots[k].max_fav_pts = fav_c;
               if(m_slots[k].be_trig > 0.0 && !m_slots[k].be_active && m_slots[k].max_fav_pts >= m_slots[k].be_trig)
                 {
                  double cand_sl = CalcStage1StopPrice(k);
                  if((d == 1 && new_bar_open > cand_sl + 5.0) || (d == -1 && new_bar_open < cand_sl - 5.0))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                     m_slots[k].be_active = true;
                    }
                 }
               if(m_slots[k].be_mode == 2 && !m_slots[k].be_stage2_active)
                 {
                  bool crossed_mid = (m_slots[k].raw_mid_lvl > 0.0) && ((d == 1 && b1.close > m_slots[k].raw_mid_lvl + 10.0) || (d == -1 && b1.close < m_slots[k].raw_mid_lvl - 10.0));
                  if(m_slots[k].max_fav_pts >= 240.0 || crossed_mid)
                    {
                     double cand_sl2 = CalcStage2StopPrice(k, b1.close);
                     if((d == 1 && new_bar_open > cand_sl2 + 5.0) || (d == -1 && new_bar_open < cand_sl2 - 5.0))
                       {
                        m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl2) : MathMin(m_slots[k].curr_sl, cand_sl2);
                        m_slots[k].be_stage2_active = true;
                        m_slots[k].be_active = true;
                       }
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

               // Estágio 1 do Break-Even (BE_ZERO ou BE_WALL_SHIELD / BE_TWO_STAGE_WALLS)
               if(m_slots[k].be_trig > 0.0 && !m_slots[k].be_active && m_slots[k].max_fav_pts >= m_slots[k].be_trig)
                 {
                  double cand_sl = CalcStage1StopPrice(k);
                  if((d == 1 && new_bar_open > cand_sl + 5.0) || (d == -1 && new_bar_open < cand_sl - 5.0))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                     m_slots[k].be_active = true;
                    }
                 }

               // Estágio 2 do Break-Even (BE_TWO_STAGE_WALLS: trava atrás da MidWall ou no BE+lock)
               if(m_slots[k].be_mode == 2 && !m_slots[k].be_stage2_active)
                 {
                  bool crossed_mid = (m_slots[k].raw_mid_lvl > 0.0) && ((d == 1 && b1.close > m_slots[k].raw_mid_lvl + 10.0) || (d == -1 && b1.close < m_slots[k].raw_mid_lvl - 10.0));
                  if(m_slots[k].max_fav_pts >= 240.0 || crossed_mid)
                    {
                     double cand_sl2 = CalcStage2StopPrice(k, b1.close);
                     if((d == 1 && new_bar_open > cand_sl2 + 5.0) || (d == -1 && new_bar_open < cand_sl2 - 5.0))
                       {
                        m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl2) : MathMin(m_slots[k].curr_sl, cand_sl2);
                        m_slots[k].be_stage2_active = true;
                        m_slots[k].be_active = true;
                       }
                    }
                 }

               // Trailing Stop
               if(m_slots[k].tr_trig > 0.0 && m_slots[k].max_fav_pts >= m_slots[k].tr_trig)
                 {
                  double cand_sl = (d == 1) ? Round5(m_slots[k].avg_price + m_slots[k].max_fav_pts - m_slots[k].tr_dist)
                                            : Round5(m_slots[k].avg_price - m_slots[k].max_fav_pts + m_slots[k].tr_dist);
                  if((d == 1 && new_bar_open > cand_sl + 5.0) || (d == -1 && new_bar_open < cand_sl - 5.0))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                    }
                 }

               // EST-12: Piramidação no Fechamento se lucro no fechamento >= +110 pts
               if(k == 12 && m_slots[k].leg_stage == 1)
                 {
                  double fav_close = (d == 1) ? (b1.close - m_slots[k].p1_entry) : (m_slots[k].p1_entry - b1.close);
                  if(fav_close >= 110.0)
                    {
                     m_slots[k].avg_price = Round5(0.5 * (m_slots[k].p1_entry + new_bar_open));
                     m_slots[k].lots = 2;
                     m_slots[k].leg_stage = 2;
                     double cand_sl = (d == 1) ? Round5(m_slots[k].avg_price + 25.0) : Round5(m_slots[k].avg_price - 25.0);
                     if((d == 1 && new_bar_open > cand_sl + 5.0) || (d == -1 && new_bar_open < cand_sl - 5.0))
                        m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                     PrintFormat("[JUMBA %s] PIRAMIDACAO +1 LOTE NO LUCRO ATIVADA @ %.0f | Novo Stop Protegido=%.0f",
                                 m_slots[k].name, new_bar_open, m_slots[k].curr_sl);
                    }
                 }

               // Time Stop (EST-15 segura até 17h15; demais encerram após max_hold_bars)
               if(m_slots[k].bars_held >= m_slots[k].max_hold_bars)
                 {
                  CloseVirtualSlot(k, new_bar_open, "TIME_STOP");
                  continue;
                 }
              }
           }
        }

      // Se estamos na mesma sessão, avalia sinais para as estratégias que estão FLAT
      if(b1_date != today_str)
         return;

      if(!MQLInfoInteger(MQL_TESTER))
        {
         if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
            return;
         double live_b = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(live_b > 0.0)
           {
            if(MathAbs(live_b - new_bar_open) > 150.0)
               return;
            new_bar_open = Round5(live_b);
           }
        }

      double bw50 = MathMax(1.0, m_n50_u_1 - m_n50_l_1);
      double bw30 = MathMax(1.0, m_n30_u_1 - m_n30_l_1);
      double pos50 = (b1.close - m_n50_l_1) / bw50;
      double pos30 = (b1.close - m_n30_l_1) / bw30;
      double body1 = b1.close - b1.open;
      double rng1 = MathMax(1.0, b1.high - b1.low);
      double mid_b1 = Round5(0.5 * (b1.high + b1.low));
      bool c_buy  = (b1.close > b1.open && (b1.close - b1.low) >= 0.5 * rng1);
      bool c_sell = (b1.close < b1.open && (b1.high - b1.close) >= 0.5 * rng1);
      double raw_mid, tp1_px, tp_calc;

      // =====================================================================
      // EST-01: 3-Pilares (Sinal Original NY + BE_Wall_Shield(25) + TP_MainWall) | Ret/DD = 6.90
      // =====================================================================
      if(m_slots[1].enabled && m_slots[1].dir == 0 && m_slots[1].pend_dir == 0)
        {
         bool ent1 = false;
         if(m_slots[1].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
           {
            if(d_l <= 60.0 && (b1.close - lvl_s >= -25.0) && (b1.close - lvl_s <= 75.0) && b1.close <= (m_n50_l_1 + bw50 * 0.22) && m_rsi7_1 <= 35.0 && c_buy && m_n50_s_1 >= -12.0)
              {
               tp_calc = CalcTargetPts(new_bar_open, 1, 2, 550.0, raw_mid, tp1_px);
               OpenVirtualSingle(1, 1, new_bar_open, new_bar_time, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false, 1, lvl_s, 1, 25.0, raw_mid, tp1_px, false);
               m_slots[1].last_entry_bar_time = b1.time;
               ent1 = true;
              }
            else if(d_h <= 60.0 && (lvl_r - b1.close >= -25.0) && (lvl_r - b1.close <= 75.0) && b1.close >= (m_n50_u_1 - bw50 * 0.22) && m_rsi7_1 >= 65.0 && c_sell && m_n50_s_1 <= 12.0)
              {
               tp_calc = CalcTargetPts(new_bar_open, -1, 2, 550.0, raw_mid, tp1_px);
               OpenVirtualSingle(1, -1, new_bar_open, new_bar_time, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false, 1, lvl_r, 1, 25.0, raw_mid, tp1_px, false);
               m_slots[1].last_entry_bar_time = b1.time;
               ent1 = true;
              }
            if(!ent1)
              {
               for(int i=0; i<ArraySize(m_levels_all); i++)
                 {
                  double lvl = m_levels_all[i];
                  if(b1.open <= lvl + 12.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 85.0 && body1 >= 55.0 && m_n50_s_1 >= 4.5 && b1.close < (m_n50_u_1 - bw50 * 0.15))
                    {
                     tp_calc = CalcTargetPts(new_bar_open, 1, 2, 550.0, raw_mid, tp1_px);
                     OpenVirtualSingle(1, 1, new_bar_open, new_bar_time, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false, 1, lvl, 1, 25.0, raw_mid, tp1_px, false);
                     m_slots[1].last_entry_bar_time = b1.time;
                     ent1 = true;
                     break;
                    }
                  if(b1.open >= lvl - 12.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 85.0 && (-body1) >= 55.0 && m_n50_s_1 <= -4.5 && b1.close > (m_n50_l_1 + bw50 * 0.15))
                    {
                     tp_calc = CalcTargetPts(new_bar_open, -1, 2, 550.0, raw_mid, tp1_px);
                     OpenVirtualSingle(1, -1, new_bar_open, new_bar_time, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false, 1, lvl, 1, 25.0, raw_mid, tp1_px, false);
                     m_slots[1].last_entry_bar_time = b1.time;
                     ent1 = true;
                     break;
                    }
                 }
              }
           }
         if(!ent1 && WindowOk(new_tmin, "NY_1000_1630"))
           {
            if(m_n50_s_1 >= 6.0 && b1.close <= (m_n50_c_1 + bw50 * 0.18) && d_l <= 55.0 && b1.close > lvl_s)
              {
               tp_calc = CalcTargetPts(lvl_s, 1, 2, 500.0, raw_mid, tp1_px);
               ArmPendingOrder(1, 1, 1, lvl_s, new_bar_time, new_bar_open, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 15, 1, lvl_s, 1, 25.0, raw_mid, tp1_px, false, 1, false);
              }
            else if(m_n50_s_1 <= -6.0 && b1.close >= (m_n50_c_1 - bw50 * 0.18) && d_h <= 55.0 && b1.close < lvl_r)
              {
               tp_calc = CalcTargetPts(lvl_r, -1, 2, 500.0, raw_mid, tp1_px);
               ArmPendingOrder(1, -1, 1, lvl_r, new_bar_time, new_bar_open, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 15, 1, lvl_r, 1, 25.0, raw_mid, tp1_px, false, 1, false);
              }
           }
        }

      // =====================================================================
      // EST-02: 3-Pilares (Sinal Original DiaTodo + Limit 50% Barra[1] + TP_MainWall) | Ret/DD = 3.80
      // =====================================================================
      if(m_slots[2].enabled && m_slots[2].dir == 0 && m_slots[2].pend_dir == 0)
        {
         int sig2 = 0;
         double wall2 = 0.0;
         if(WindowOk(b1_tmin, "FULL_09_17"))
           {
            if(d_l <= 60.0 && (b1.close - lvl_s >= -25.0) && (b1.close - lvl_s <= 75.0) && b1.close <= (m_n50_l_1 + bw50 * 0.22) && m_rsi7_1 <= 35.0 && c_buy && m_n50_s_1 >= -12.0)
              { sig2 = 1; wall2 = lvl_s; }
            else if(d_h <= 60.0 && (lvl_r - b1.close >= -25.0) && (lvl_r - b1.close <= 75.0) && b1.close >= (m_n50_u_1 - bw50 * 0.22) && m_rsi7_1 >= 65.0 && c_sell && m_n50_s_1 <= 12.0)
              { sig2 = -1; wall2 = lvl_r; }
           }
         if(sig2 == 0 && WindowOk(new_tmin, "CORE_09_1615"))
           {
            if(m_n50_s_1 >= 6.0 && b1.close <= (m_n50_c_1 + bw50 * 0.18) && d_l <= 55.0 && b1.close > (lvl_s + 10.0))
              { sig2 = 1; wall2 = lvl_s; }
            else if(m_n50_s_1 <= -6.0 && b1.close >= (m_n50_c_1 - bw50 * 0.18) && d_h <= 55.0 && b1.close < (lvl_r - 10.0))
              { sig2 = -1; wall2 = lvl_r; }
           }
         if(sig2 != 0)
           {
            tp_calc = CalcTargetPts(mid_b1, sig2, 2, 500.0, raw_mid, tp1_px);
            ArmPendingOrder(2, sig2, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 15, 1, wall2, 0, 0.0, raw_mid, tp1_px, false, 1, false);
           }
        }

      // =====================================================================
      // EST-03: MANTIDO ORIGINAL (Arbitragem Cambial Confluência WIN+WDO na Wall) | Ret/DD = 6.68
      // =====================================================================
      if(false && m_slots[3].enabled && m_slots[3].dir == 0 && m_slots[3].pend_dir == 0)
        {
         bool ent3 = false;
         if(m_slots[3].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 12.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 85.0 && body1 >= 50.0 && m_n50_s_1 >= 4.0 && b1.close < (m_n50_u_1 - bw50 * 0.15) && (m_wdo_ret3_1 <= 2.0 || m_wdo_z_1 <= 0.0))
                 {
                  OpenVirtualSingle(3, 1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
                  m_slots[3].last_entry_bar_time = b1.time;
                  ent3 = true;
                  break;
                 }
               if(b1.open >= lvl - 12.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 85.0 && (-body1) >= 50.0 && m_n50_s_1 <= -4.0 && b1.close > (m_n50_l_1 + bw50 * 0.15) && (m_wdo_ret3_1 >= -2.0 || m_wdo_z_1 >= 0.0))
                 {
                  OpenVirtualSingle(3, -1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
                  m_slots[3].last_entry_bar_time = b1.time;
                  ent3 = true;
                  break;
                 }
              }
           }
         if(!ent3 && WindowOk(new_tmin, "FULL_09_17"))
           {
            if(m_n50_s_1 >= 8.0 && (m_wdo_ret3_1 <= 2.0 || m_wdo_z_1 <= 0.2) && d_l <= 55.0 && b1.close > lvl_s && b1.close <= (m_n50_c_1 + bw50 * 0.20))
               ArmPendingOrder(3, 1, 1, lvl_s, new_bar_time, new_bar_open, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
            else if(m_n50_s_1 <= -8.0 && (m_wdo_ret3_1 >= -2.0 || m_wdo_z_1 >= -0.2) && d_h <= 55.0 && b1.close < lvl_r && b1.close >= (m_n50_c_1 - bw50 * 0.20))
               ArmPendingOrder(3, -1, 1, lvl_r, new_bar_time, new_bar_open, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
           }
        }

      // =====================================================================
      // EST-04: Matriz WDO (Reteste 220p(off-5) + BE_2Stage_177k(15) + TP_MidWall) | Ret/DD = 4.88
      // =====================================================================
      if(m_slots[4].enabled && m_slots[4].dir == 0 && m_slots[4].pend_dir == 0 && WindowOk(new_tmin, "FULL_09_17"))
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 12.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 220.0 && body1 >= 45.0 && m_n50_s_1 >= 5.5)
              {
               if((m_gamma_flip <= 0.0 || b1.close >= m_gamma_flip) && pos50 < 0.85)
                 {
                  double p4 = Round5(lvl - 5.0);
                  tp_calc = CalcTargetPts(p4, 1, 1, 520.0, raw_mid, tp1_px);
                  ArmPendingOrder(4, 1, 1, p4, new_bar_time, new_bar_open, tp_calc, 240.0, 150.0, 45.0, 330.0, 120.0, 16, 1, lvl, 2, 15.0, raw_mid, tp1_px, false, 1, false);
                  break;
                 }
              }
            if(b1.open >= lvl - 12.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 220.0 && (-body1) >= 45.0 && m_n50_s_1 <= -5.5)
              {
               if((m_gamma_flip <= 0.0 || b1.close <= m_gamma_flip) && pos50 > 0.15)
                 {
                  double p4 = Round5(lvl + 5.0);
                  tp_calc = CalcTargetPts(p4, -1, 1, 520.0, raw_mid, tp1_px);
                  ArmPendingOrder(4, -1, 1, p4, new_bar_time, new_bar_open, tp_calc, 240.0, 150.0, 45.0, 330.0, 120.0, 16, 1, lvl, 2, 15.0, raw_mid, tp1_px, false, 1, false);
                  break;
                 }
              }
           }
        }

      // =====================================================================
      // EST-05: 3-Pilares (Cluster NWE30+50 + Limit Extremo Barra[1] + TP_MainWall) | Ret/DD = 6.57
      // =====================================================================
      if(false && m_slots[5].enabled && m_slots[5].dir == 0 && m_slots[5].pend_dir == 0)
        {
         int sig5 = 0;
         double wall5 = 0.0;
         if(WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 12.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 90.0 && body1 >= 45.0 && m_n30_s_1 >= 5.0 && m_n50_s_1 >= 4.0 && b1.close < (m_n30_u_1 - bw30 * 0.15))
                 { sig5 = 1; wall5 = lvl; break; }
               if(b1.open >= lvl - 12.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 90.0 && (-body1) >= 45.0 && m_n30_s_1 <= -5.0 && m_n50_s_1 <= -4.0 && b1.close > (m_n30_l_1 + bw30 * 0.15))
                 { sig5 = -1; wall5 = lvl; break; }
              }
           }
         if(sig5 == 0 && WindowOk(new_tmin, "CORE_09_1615"))
           {
            if(m_n30_s_1 >= 6.0 && m_n50_s_1 >= 6.0 && b1.close <= (m_n30_c_1 + bw30 * 0.20) && d_l <= 50.0 && b1.close > lvl_s)
              { sig5 = 1; wall5 = lvl_s; }
            else if(m_n30_s_1 <= -6.0 && m_n50_s_1 <= -6.0 && b1.close >= (m_n30_c_1 - bw30 * 0.20) && d_h <= 50.0 && b1.close < lvl_r)
              { sig5 = -1; wall5 = lvl_r; }
           }
         if(sig5 != 0)
           {
            double p5_lim = (sig5 == 1) ? Round5(b1.low + 5.0) : Round5(b1.high - 5.0);
            tp_calc = CalcTargetPts(p5_lim, sig5, 2, 500.0, raw_mid, tp1_px);
            ArmPendingOrder(5, sig5, 1, p5_lim, new_bar_time, new_bar_open, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 16, 1, wall5, 0, 0.0, raw_mid, tp1_px, false, 1, false);
           }
        }

      // =====================================================================
      // EST-06: 3-Pilares (Stop Barra[1] + BE_Wall_Shield(15) + TP_MainWall) | Ret/DD = 5.99
      // =====================================================================
      if(m_slots[6].enabled && m_slots[6].dir == 0 && m_slots[6].pend_dir == 0 && WindowOk(new_tmin, "CORE_09_1615"))
        {
         int sig6 = 0;
         double wall6 = 0.0;
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 10.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 95.0 && body1 >= 42.0 && m_n50_s_1 >= 5.5 && b1.close < (m_n50_u_1 - bw50 * 0.15))
              { sig6 = 1; wall6 = lvl; break; }
            if(b1.open >= lvl - 10.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 95.0 && (-body1) >= 42.0 && m_n50_s_1 <= -5.5 && b1.close > (m_n50_l_1 + bw50 * 0.15))
              { sig6 = -1; wall6 = lvl; break; }
           }
         if(sig6 == 0)
           {
            if(m_n50_s_1 >= 8.0 && b1.close <= (m_n50_c_1 + bw50 * 0.20) && d_l <= 55.0 && b1.close > lvl_s)
              { sig6 = 1; wall6 = lvl_s; }
            else if(m_n50_s_1 <= -8.0 && b1.close >= (m_n50_c_1 - bw50 * 0.20) && d_h <= 55.0 && b1.close < lvl_r)
              { sig6 = -1; wall6 = lvl_r; }
           }
         if(sig6 != 0)
           {
            double p6_stp = (sig6 == 1) ? Round5(b1.high + 5.0) : Round5(b1.low - 5.0);
            tp_calc = CalcTargetPts(p6_stp, sig6, 2, 550.0, raw_mid, tp1_px);
            ArmPendingOrder(6, sig6, 2, p6_stp, new_bar_time, new_bar_open, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 16, 1, wall6, 1, 15.0, raw_mid, tp1_px, false, 1, false);
           }
        }

      // =====================================================================
      // EST-07 (3-Pilares: BE_Wall(15) + TP_Original | Ret/DD = 6.91) &
      // EST-08 (3-Pilares: TP_MainWall Real | Ret/DD = 5.40)
      // =====================================================================
      for(int bo_id=7; bo_id<=8; bo_id++)
        {
         if(!m_slots[bo_id].enabled || m_slots[bo_id].dir != 0 || m_slots[bo_id].last_entry_bar_time == b1.time)
            continue;
         string wm_bo = (bo_id == 7) ? "NY_1000_1630" : "CORE_09_1615";
         double min_bd = (bo_id == 7) ? 65.0 : 50.0;
         double tp_b   = (bo_id == 7) ? 650.0 : 400.0;
         double sl_b   = (bo_id == 7) ? 260.0 : 220.0;
         double be_b   = (bo_id == 7) ? 160.0 : 140.0;
         double tr_t   = (bo_id == 7) ? 350.0 : 250.0;
         double tr_d   = (bo_id == 7) ? 120.0 : 100.0;
         int    bm_b   = (bo_id == 7) ? 1 : 0;      // EST-07 usa BE_WALL_SHIELD(15); EST-08 usa BE_ZERO
         double buf_b  = (bo_id == 7) ? 15.0 : 0.0;
         int    tpt_b  = (bo_id == 7) ? 0 : 2;      // EST-07 usa TP_Original (650); EST-08 usa TP_MAIN_WALL

         if(WindowOk(b1_tmin, wm_bo))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 15.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 90.0 && body1 >= min_bd && m_n50_s_1 >= 4.0)
                 {
                  if(b1.close < (m_n50_u_1 - bw50 * 0.15))
                    {
                     tp_calc = CalcTargetPts(new_bar_open, 1, tpt_b, tp_b, raw_mid, tp1_px);
                     OpenVirtualSingle(bo_id, 1, new_bar_open, new_bar_time, tp_calc, sl_b, be_b, 20.0, tr_t, tr_d, 16, false, 1, lvl, bm_b, buf_b, raw_mid, tp1_px, false);
                     m_slots[bo_id].last_entry_bar_time = b1.time;
                     break;
                    }
                 }
               if(b1.open >= lvl - 15.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 90.0 && (-body1) >= min_bd && m_n50_s_1 <= -4.0)
                 {
                  if(b1.close > (m_n50_l_1 + bw50 * 0.15))
                    {
                     tp_calc = CalcTargetPts(new_bar_open, -1, tpt_b, tp_b, raw_mid, tp1_px);
                     OpenVirtualSingle(bo_id, -1, new_bar_open, new_bar_time, tp_calc, sl_b, be_b, 20.0, tr_t, tr_d, 16, false, 1, lvl, bm_b, buf_b, raw_mid, tp1_px, false);
                     m_slots[bo_id].last_entry_bar_time = b1.time;
                     break;
                    }
                 }
              }
           }
        }

      // =====================================================================
      // EST-09: MANTIDO ORIGINAL (Breakout Stop & Limit Wall NY) | Ret/DD = 4.53
      // =====================================================================
      if(false && m_slots[9].enabled && m_slots[9].dir == 0 && m_slots[9].pend_dir == 0 && WindowOk(new_tmin, "NY_1000_1630"))
        {
         bool armed9 = false;
         if(m_n30_s_1 >= 5.0 && b1.close > b1.open && body1 >= 35.0 && b1.close < (m_n30_u_1 - bw30 * 0.20))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(lvl >= b1.close - 5.0 && (lvl - b1.close) <= 55.0)
                 {
                  double stp_p = MathMax(lvl + 10.0, b1.high + 5.0);
                  ArmPendingOrder(9, 1, 2, stp_p, new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
                  armed9 = true;
                  break;
                 }
              }
           }
         if(!armed9 && m_n30_s_1 <= -5.0 && b1.close < b1.open && (-body1) >= 35.0 && b1.close > (m_n30_l_1 + bw30 * 0.20))
           {
            for(int i=ArraySize(m_levels_all)-1; i>=0; i--)
              {
               double lvl = m_levels_all[i];
               if(lvl <= b1.close + 5.0 && (b1.close - lvl) <= 55.0)
                 {
                  double stp_p = MathMin(lvl - 10.0, b1.low - 5.0);
                  ArmPendingOrder(9, -1, 2, stp_p, new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
                  armed9 = true;
                  break;
                 }
              }
           }
         if(!armed9)
           {
            if(m_n50_s_1 >= 6.5 && d_l <= 55.0 && b1.close > lvl_s && b1.close <= (m_n50_c_1 + bw50 * 0.20))
               ArmPendingOrder(9, 1, 1, lvl_s, new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
            else if(m_n50_s_1 <= -6.5 && d_h <= 55.0 && b1.close < lvl_r && b1.close >= (m_n50_c_1 - bw50 * 0.20))
               ArmPendingOrder(9, -1, 1, lvl_r, new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
           }
        }

      // =====================================================================
      // EST-10: Matriz WDO (MainWalls Only pos50+GammaFlip + BE_177k(240/45)) | Ret/DD = 5.20
      // =====================================================================
      if(false && m_slots[10].enabled && m_slots[10].dir == 0 && m_slots[10].pend_dir == 0 && WindowOk(new_tmin, "CORE_09_1615") && ArraySize(m_levels_walls) > 0)
        {
         bool armed10 = false;
         if(m_n30_s_1 >= 4.0 && b1.close > b1.open && body1 >= 35.0 && pos30 < 0.85 && (m_gamma_flip <= 0.0 || b1.close >= m_gamma_flip))
           {
            for(int i=0; i<ArraySize(m_levels_walls); i++)
              {
               double w = m_levels_walls[i];
               if(w >= b1.close - 10.0 && (w - b1.close) <= 70.0)
                 {
                  ArmPendingOrder(10, 1, 2, MathMax(w + 15.0, b1.high + 5.0), new_bar_time, new_bar_open, 600.0, 250.0, 240.0, 45.0, 340.0, 120.0, 16, 1, w, 0, 0.0, 0.0, 0.0, false, 1, false);
                  armed10 = true;
                  break;
                 }
              }
           }
         if(!armed10 && m_n30_s_1 <= -4.0 && b1.close < b1.open && (-body1) >= 35.0 && pos30 > 0.15 && (m_gamma_flip <= 0.0 || b1.close <= m_gamma_flip))
           {
            for(int i=ArraySize(m_levels_walls)-1; i>=0; i--)
              {
               double w = m_levels_walls[i];
               if(w <= b1.close + 10.0 && (b1.close - w) <= 70.0)
                 {
                  ArmPendingOrder(10, -1, 2, MathMin(w - 15.0, b1.low - 5.0), new_bar_time, new_bar_open, 600.0, 250.0, 240.0, 45.0, 340.0, 120.0, 16, 1, w, 0, 0.0, 0.0, 0.0, false, 1, false);
                  armed10 = true;
                  break;
                 }
              }
           }
         if(!armed10)
           {
            if(dw_l_main <= 70.0 && b1.close > (w_s_main + 10.0) && ((m_n50_s_1 >= 4.5 && pos50 <= 0.65) || (pos50 <= 0.35 && m_n50_s_1 >= -2.0)) && (m_gamma_flip <= 0.0 || b1.close >= m_gamma_flip))
               ArmPendingOrder(10, 1, 1, w_s_main + 10.0, new_bar_time, new_bar_open, 600.0, 250.0, 240.0, 45.0, 340.0, 120.0, 16, 1, w_s_main, 0, 0.0, 0.0, 0.0, false, 1, false);
            else if(dw_h_main <= 70.0 && b1.close < (w_r_main - 10.0) && ((m_n50_s_1 <= -4.5 && pos50 >= 0.35) || (pos50 >= 0.65 && m_n50_s_1 <= 2.0)) && (m_gamma_flip <= 0.0 || b1.close <= m_gamma_flip))
               ArmPendingOrder(10, -1, 1, w_r_main - 10.0, new_bar_time, new_bar_open, 600.0, 250.0, 240.0, 45.0, 340.0, 120.0, 16, 1, w_r_main, 0, 0.0, 0.0, 0.0, false, 1, false);
           }
        }

      // =====================================================================
      // Sinais Base compartilhados pelos 4 Novos Achados (NOVO-1 a NOVO-4)
      // =====================================================================
      bool touched_supp = (d_l <= 65.0) && (b1.close >= lvl_s - 35.0) && ((b1.close - lvl_s) <= 95.0);
      bool touched_res  = (d_h <= 65.0) && (b1.close <= lvl_r + 35.0) && ((lvl_r - b1.close) <= 95.0);

      bool hyb_buy  = touched_supp && ((b1.close <= m_n50_l_1 + bw50 * 0.25 && m_rsi7_1 <= 38.0) || (m_n50_s_1 >= 8.0 && b1.close <= m_n50_c_1 + bw50 * 0.15 && b1.close > lvl_s));
      bool hyb_sell = touched_res  && ((b1.close >= m_n50_u_1 - bw50 * 0.25 && m_rsi7_1 >= 62.0) || (m_n50_s_1 <= -8.0 && b1.close >= m_n50_c_1 - bw50 * 0.15 && b1.close < lvl_r));

      bool slp_buy  = touched_supp && (m_n50_s_1 >= 7.0) && (b1.close <= m_n50_c_1 + bw50 * 0.15) && (b1.close > lvl_s);
      bool slp_sell = touched_res  && (m_n50_s_1 <= -7.0) && (b1.close >= m_n50_c_1 - bw50 * 0.15) && (b1.close < lvl_r);

      // =====================================================================
      // EST-11: NOVO-4 (Stop Barra[1](2b) Híbrido + BE_Wall(25) + TP_MidWall | 2 Lotes) | Ret/DD = 3.00
      // =====================================================================
      if(m_slots[11].enabled && m_slots[11].dir == 0 && m_slots[11].pend_dir == 0 && b1_tmin >= 550 && b1_tmin <= 990)
        {
         if(hyb_buy && (b1.high + 15.0 - lvl_s) <= 135.0)
           {
            double trig11 = Round5(b1.high + 15.0);
            tp_calc = CalcTargetPts(trig11, 1, 1, 450.0, raw_mid, tp1_px);
            ArmPendingOrder(11, 1, 2, trig11, new_bar_time, new_bar_open, tp_calc, 230.0, 130.0, 20.0, 0.0, 0.0, 18, 2, lvl_s, 1, 25.0, raw_mid, tp1_px, false, 2, false);
           }
         else if(hyb_sell && (lvl_r - (b1.low - 15.0)) <= 135.0)
           {
            double trig11 = Round5(b1.low - 15.0);
            tp_calc = CalcTargetPts(trig11, -1, 1, 450.0, raw_mid, tp1_px);
            ArmPendingOrder(11, -1, 2, trig11, new_bar_time, new_bar_open, tp_calc, 230.0, 130.0, 20.0, 0.0, 0.0, 18, 2, lvl_r, 1, 25.0, raw_mid, tp1_px, false, 2, false);
           }
        }

      // =====================================================================
      // EST-12: 3-Pilares (Piramidação no Lucro 1+1L NY + TP_MainWall Real) | Ret/DD = 4.47
      // =====================================================================
      if(m_slots[12].enabled && m_slots[12].dir == 0 && m_slots[12].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 15.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 90.0 && body1 >= 55.0 && m_n50_s_1 >= 4.0 && b1.close < (m_n50_u_1 - bw50 * 0.15))
              {
               tp_calc = CalcTargetPts(new_bar_open, 1, 2, 550.0, raw_mid, tp1_px);
               OpenVirtualSingle(12, 1, new_bar_open, new_bar_time, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 18, false, 1, lvl, 0, 0.0, raw_mid, tp1_px, false);
               m_slots[12].last_entry_bar_time = b1.time;
               break;
              }
            if(b1.open >= lvl - 15.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 90.0 && (-body1) >= 55.0 && m_n50_s_1 <= -4.0 && b1.close > (m_n50_l_1 + bw50 * 0.15))
              {
               tp_calc = CalcTargetPts(new_bar_open, -1, 2, 550.0, raw_mid, tp1_px);
               OpenVirtualSingle(12, -1, new_bar_open, new_bar_time, tp_calc, 240.0, 150.0, 20.0, 300.0, 110.0, 18, false, 1, lvl, 0, 0.0, raw_mid, tp1_px, false);
               m_slots[12].last_entry_bar_time = b1.time;
               break;
              }
           }
        }

      // =====================================================================
      // EST-13: SMART GRID ANCORADO EM WALLS (Cross WDO_Z + Wall + Limit 50%B1(2b) + Perna 2 na NextWall 1+2L)
      // 116 Trades | Ret/DD = 10.65 | IS_PF = 3.19 | OOS_PF = 2.61 | WallRank = 1/11 (+R$1.686)
      // =====================================================================
      if(m_slots[13].enabled && m_slots[13].dir == 0 && m_slots[13].pend_dir == 0 && m_slots[13].trades_today < 5 && b1_tmin >= 545 && b1_tmin <= 975)
        {
         int sig13 = 0;
         double wall13 = 0.0;
         if(d_l <= 80.0 && pos50 <= 0.45 && m_wdo_z_1 <= 0.35 && b1.close > lvl_s && b1.close > b1.open)
           { sig13 = 1; wall13 = lvl_s; }
         else if(d_h <= 80.0 && pos50 >= 0.55 && m_wdo_z_1 >= -0.35 && b1.close < lvl_r && b1.close < b1.open)
           { sig13 = -1; wall13 = lvl_r; }
         if(sig13 != 0)
           {
            double s2_13 = FindNextWallBehind(mid_b1, sig13, 140.0, 280.0, 190.0);
            tp_calc = MathMin(220.0, CalcTargetPts(mid_b1, sig13, 1, 220.0, raw_mid, tp1_px));
            ArmPendingOrder(13, sig13, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, s2_13 + 175.0, 130.0, 20.0, 0.0, 0.0, 18, 1, wall13, 1, 20.0, raw_mid, tp1_px, false, 2, false);
           }
        }

      // =====================================================================
      // EST-14: SMART GRID ANCORADO EM WALLS (Defesa Pavio>=25p na Wall + Limit 50%B1(2b) + Perna 2 na NextWall 1+2L)
      // 241 Trades | Ret/DD = 7.96 | IS_PF = 2.06 | OOS_PF = 1.55 | WallRank = 3/11 (+R$1.856)
      // =====================================================================
      if(m_slots[14].enabled && m_slots[14].dir == 0 && m_slots[14].pend_dir == 0 && m_slots[14].trades_today < 3 && b1_tmin >= 545 && b1_tmin <= 1005)
        {
         int sig14 = 0;
         double wall14 = 0.0;
         double w_bot14 = MathMin(b1.open, b1.close) - b1.low;
         double w_top14 = b1.high - MathMax(b1.open, b1.close);
         if(d_l <= 75.0 && w_bot14 >= 25.0 && pos50 <= 0.48 && b1.close >= b1.open && b1.close > (lvl_s - 15.0))
           { sig14 = 1; wall14 = lvl_s; }
         else if(d_h <= 75.0 && w_top14 >= 25.0 && pos50 >= 0.52 && b1.close <= b1.open && b1.close < (lvl_r + 15.0))
           { sig14 = -1; wall14 = lvl_r; }
         if(sig14 != 0)
           {
            double s2_14 = FindNextWallBehind(mid_b1, sig14, 140.0, 280.0, 190.0);
            tp_calc = MathMin(220.0, CalcTargetPts(mid_b1, sig14, 1, 220.0, raw_mid, tp1_px));
            ArmPendingOrder(14, sig14, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, s2_14 + 175.0, 130.0, 20.0, 0.0, 0.0, 18, 1, wall14, 1, 20.0, raw_mid, tp1_px, false, 2, false);
           }
        }

      // =====================================================================
      // EST-15: SMART GRID Z30 REVERSAL WALL (WIN_SG_Z30_REV_WALL: Candle Z30 Fora NWE30 + Wall + Limit 50%B1(2b) + NextWall 1+2L)
      // 278 Trades (>=100!) | WR = 82.4% | PF = 1.76 | Net = +R$5.005 | MaxDD = R$545 | Ret/DD = 9.18 | 6/6 Meses | WF IS/OOS Aprovado
      // =====================================================================
      double hb30_w  = MathMax(10.0, 0.5 * bw30);
      double z30_c_w = (b1.close - m_n30_c_1) / hb30_w;
      double z30_l_w = (b1.low   - m_n30_c_1) / hb30_w;
      double z30_h_w = (b1.high  - m_n30_c_1) / hb30_w;
      double lw_b1   = MathMin(b1.open, b1.close) - b1.low;
      double uw_b1   = b1.high - MathMax(b1.open, b1.close);
      bool rev_b_w   = (b1.close >= b1.low  + 0.45 * rng1) && (lw_b1 >= 0.22 * rng1 || b1.close > b1.open);
      bool rev_s_w   = (b1.close <= b1.high - 0.45 * rng1) && (uw_b1 >= 0.22 * rng1 || b1.close < b1.open);
      bool gf_b_w    = (m_gamma_flip <= 0.0) || (b1.close < m_gamma_flip + 400.0);
      bool gf_s_w    = (m_gamma_flip <= 0.0) || (b1.close > m_gamma_flip - 400.0);

      if(m_slots[15].enabled && m_slots[15].dir == 0 && m_slots[15].pend_dir == 0 && m_slots[15].trades_today < 3 && b1_tmin >= 555 && b1_tmin <= 975)
        {
         int sig15 = 0;
         double wall15 = 0.0;
         if(d_l <= 110.0 && (z30_c_w <= -0.60 || z30_l_w <= -0.80) && rev_b_w && b1.close > (lvl_s - 20.0) && gf_b_w)
           { sig15 = 1; wall15 = lvl_s; }
         else if(d_h <= 110.0 && (z30_c_w >= 0.60 || z30_h_w >= 0.80) && rev_s_w && b1.close < (lvl_r + 20.0) && gf_s_w)
           { sig15 = -1; wall15 = lvl_r; }
         if(sig15 != 0)
           {
            double s2_15 = FindNextWallBehind(mid_b1, sig15, 140.0, 280.0, 190.0);
            tp_calc = MathMin(220.0, CalcTargetPts(mid_b1, sig15, 1, 220.0, raw_mid, tp1_px));
            ArmPendingOrder(15, sig15, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, s2_15 + 175.0, 130.0, 20.0, 0.0, 0.0, 18, 1, wall15, 1, 20.0, raw_mid, tp1_px, false, 2, false);
           }
        }

      // =====================================================================
      // EST-16: SMART GRID SPRING Z30 WALL (WIN_SG_SPRING_Z30_WALL: Falso Rompimento Wall + Exaustao NWE30 + Limit 50%B1(2b) + NextWall 1+2L)
      // 199 Trades (>=100!) | WR = 83.9% | PF = 2.17 | Net = +R$4.781 | MaxDD = R$809 | Ret/DD = 5.91 | 6/6 Meses | WF IS/OOS Aprovado
      // =====================================================================
      if(m_slots[16].enabled && m_slots[16].dir == 0 && m_slots[16].pend_dir == 0 && m_slots[16].trades_today < 3 && b1_tmin >= 555 && b1_tmin <= 975)
        {
         int sig16 = 0;
         double wall16 = 0.0;
         if(b1.low <= (lvl_s + 20.0) && b1.close >= lvl_s && d_l <= 105.0 && (z30_l_w <= -0.45 || pos30 <= 0.30) && b1.close > b1.open && gf_b_w)
           { sig16 = 1; wall16 = lvl_s; }
         else if(b1.high >= (lvl_r - 20.0) && b1.close <= lvl_r && d_h <= 105.0 && (z30_h_w >= 0.45 || pos30 >= 0.70) && b1.close < b1.open && gf_s_w)
           { sig16 = -1; wall16 = lvl_r; }
         if(sig16 != 0)
           {
            double s2_16 = FindNextWallBehind(mid_b1, sig16, 140.0, 280.0, 190.0);
            tp_calc = MathMin(220.0, CalcTargetPts(mid_b1, sig16, 1, 220.0, raw_mid, tp1_px));
            ArmPendingOrder(16, sig16, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, s2_16 + 175.0, 130.0, 20.0, 0.0, 0.0, 18, 1, wall16, 1, 20.0, raw_mid, tp1_px, false, 2, false);
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
                                     double tr_trig, double tr_dist, int max_hold=15,
                                     int init_lots=1, double def_wall=0.0, int be_mode=0, double wall_buf=0.0,
                                     double raw_mid_lvl=0.0, double tp1_px=0.0, bool partial_mode=false,
                                     int valid_bars=1, bool rolling_stop=false)
     {
      double p5 = Round5(price);

      // Filtro de Abertura da Nova Barra (não arma Limit se abriu com gap além do preço, nem Stop se abriu além do Stop)
      if(ptype == 1 && dir == 1 && new_bar_open < p5)
         return;
      if(ptype == 1 && dir == -1 && new_bar_open > p5)
         return;
      if(ptype == 2 && dir == 1 && new_bar_open > p5)
         return;
      if(ptype == 2 && dir == -1 && new_bar_open < p5)
         return;

      m_slots[k].pend_dir          = dir;
      m_slots[k].pend_type         = ptype; // 1=Limit, 2=Stop
      m_slots[k].pend_price        = p5;
      m_slots[k].pend_bar_time     = bar_t;
      m_slots[k].pend_tp_pts       = tp_pts;
      m_slots[k].pend_sl_pts       = sl_pts;
      m_slots[k].pend_bars_left    = MathMax(1, valid_bars);
      m_slots[k].pend_rolling_stop = rolling_stop;
      m_slots[k].pend_init_lots    = MathMax(1, init_lots);
      m_slots[k].pend_def_wall     = def_wall;
      m_slots[k].pend_be_mode      = be_mode;
      m_slots[k].pend_wall_buf     = wall_buf;
      m_slots[k].pend_raw_mid_lvl  = raw_mid_lvl;
      m_slots[k].pend_tp1_px       = tp1_px;
      m_slots[k].pend_partial_mode = partial_mode;
      m_slots[k].be_trig           = be_trig;
      m_slots[k].be_lock           = be_lock;
      m_slots[k].tr_trig           = tr_trig;
      m_slots[k].tr_dist           = tr_dist;
      m_slots[k].max_hold_bars     = max_hold;

      // Em Modo Hedging, envia Ordem Pendente Nativa (BuyLimit/SellLimit/BuyStop/SellStop) com SL/TP já anexados no servidor!
      if(m_exec_mode == EXEC_HEDGING_DIRECT_MAGIC)
        {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double ord_p = (dir == 1) ? Round5(p5 + 5.0) : p5;

         // Se na abertura da barra o preço atual já está exatamente no nível da ordem Limit/Stop, executa imediatamente!
         if((ptype == 1 && dir == 1 && ask > 0.0 && ask <= ord_p) ||
            (ptype == 1 && dir == -1 && bid > 0.0 && bid >= ord_p) ||
            (ptype == 2 && dir == 1 && ask > 0.0 && ask >= ord_p) ||
            (ptype == 2 && dir == -1 && bid > 0.0 && bid <= ord_p))
           {
            OpenVirtualSingle(k, dir, p5, bar_t, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, true,
                              init_lots, def_wall, be_mode, wall_buf, raw_mid_lvl, tp1_px, partial_mode);
            m_slots[k].last_entry_bar_time = bar_t;
            if(k == 15)
               m_slots[k].last_trade_date = DateStr(bar_t);
            return;
           }

         ulong slot_magic = m_base_magic + (ulong)k;
         DeletePendingOrdersForSlot(k);
         m_trade.SetExpertMagicNumber(slot_magic);
         double vol = MathRound((double)MathMin(GetMaxBaseLotsForSlot(k), MathMax(1, init_lots)) * m_lot_mult);
         if(!m_guard.AllowOrder(vol))
            return;
         double sl_srv = (dir == 1) ? Round5(p5 - sl_pts) : Round5(p5 + sl_pts);
         double tp_srv = (dir == 1) ? Round5(p5 + tp_pts) : Round5(p5 - tp_pts);
         ENUM_ORDER_TYPE_TIME ttype = GetValidOrderTimeType();

         if(ptype == 1 && dir == 1)
            m_trade.BuyLimit(vol, ord_p, _Symbol, sl_srv, tp_srv, ttype, 0, m_slots[k].name);
         else if(ptype == 1 && dir == -1)
            m_trade.SellLimit(vol, ord_p, _Symbol, sl_srv, tp_srv, ttype, 0, m_slots[k].name);
         else if(ptype == 2 && dir == 1)
            m_trade.BuyStop(vol, ord_p, _Symbol, sl_srv, tp_srv, ttype, 0, m_slots[k].name);
         else if(ptype == 2 && dir == -1)
            m_trade.SellStop(vol, ord_p, _Symbol, sl_srv, tp_srv, ttype, 0, m_slots[k].name);
        }
      SaveVirtualStateToDisk();
     }

   void              RenderHudComment()
     {
      string hud = "==========================================================\n";
      hud += StringFormat(" JUMBA QUANT GEX + NWE [MIX CAMPEAO] | Data: %s | Fonte: %s\n", m_loaded_date, m_gex_source);
      hud += StringFormat(" Levels: %d (Walls: %d) | GammaFlip: %.0f | NWE50 Slope: %.1f | RSI7: %.1f\n",
                          ArraySize(m_levels_all), ArraySize(m_levels_walls), m_gamma_flip, m_n50_s_1, m_rsi7_1);
      hud += StringFormat(" PnL Dia Acumulado: R$ %.2f | Mult. Lote: %.0fx\n", GetTotalDailyPnLBRL(), m_lot_mult);
      hud += "----------------------------------------------------------\n";
      for(int k=1; k<=16; k++)
        {
         if(!m_slots[k].enabled)
            continue;
         string st = "FLAT";
         if(m_slots[k].dir == 1)
            st = StringFormat("COMPRA %dL @ %.0f (SL %.0f | TP %.0f)", m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp);
         else if(m_slots[k].dir == -1)
            st = StringFormat("VENDA  %dL @ %.0f (SL %.0f | TP %.0f)", m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp);
         else if(m_slots[k].pend_dir != 0)
            st = StringFormat("ORDEM PENDENTE %s %dL @ %.0f", (m_slots[k].pend_type==1?"LIMIT":"STOP"), m_slots[k].pend_init_lots, m_slots[k].pend_price);

         hud += StringFormat(" %-44s | %-36s | Hoje: %d tr (R$ %.0f)\n",
                             m_slots[k].name, st, m_slots[k].trades_today, m_slots[k].closed_pnl_today_brl);
        }
      hud += "==========================================================";
      Comment(hud);
     }
  };
