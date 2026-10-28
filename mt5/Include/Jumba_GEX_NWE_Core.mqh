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
   bool              be_active;       // Breakeven activated flag
   bool              opened_intrabar; // True if opened via Limit/Stop during current M5 bar
   bool              real_synced;     // True once real position is open on MT5 server
   int               bars_held;       // M5 bars held since entry
   datetime          entry_bar_time;  // Timestamp of M5 bar when position opened
   datetime          last_entry_bar_time; // Prevents double entry on same M5 bar
   string            last_trade_date; // For EOD strategies (1 trade/day limit)
   // Pending Order State (for Limit/Stop strategies armed for the current M5 bar)
   int               pend_dir;        // 0=None, 1=Buy, -1=Sell
   int               pend_type;       // 0=None, 1=Limit, 2=Stop
   double            pend_price;      // Trigger price (rounded to 5 pts)
   double            pend_tp_pts;     // TP distance in pts for pending order
   double            pend_sl_pts;     // SL distance in pts for pending order
   datetime          pend_bar_time;   // Valid only during this M5 bar open time
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
   ENUM_EXECUTION_MODE m_exec_mode;
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
      m_exec_mode = EXEC_HEDGING_DIRECT_MAGIC;
      m_lot_mult = 1.0;
      m_max_daily_loss_brl = 2500.0;
      m_draw_levels = true;
      m_wdo_symbol = "WDO$N";
      m_loaded_date = "";
      m_gex_source = "NONE";
      m_last_m5_bar_time = 0;
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
      m_exec_mode = exec_mode;
      m_lot_mult = MathMax(1.0, MathRound(lot_mult));
      m_max_daily_loss_brl = max_daily_loss_brl;
      m_draw_levels = draw_levels;
      m_wdo_symbol = wdo_sym;
      m_trade.SetExpertMagicNumber(m_base_magic);
      m_trade.SetDeviationInPoints(50);
      m_trade.SetTypeFillingBySymbol(_Symbol);

      string names[17] =
        {
         "",
         "EST-01 [Scalper Limit+Mkt] Hibrido NY",
         "EST-02 [Scalper Limit+Mkt] Dia Todo",
         "EST-03 [Scalper Cambial] WIN+WDO Wall",
         "EST-04 [Pullback Limit] Reteste Wall",
         "EST-05 [Pullback Cluster] NWE+Wall",
         "EST-06 [Pullback Limit] Limit Slope",
         "EST-07 [Breakout Mkt] Momentum NY",
         "EST-08 [Breakout Mkt] Rapido Core",
         "EST-09 [Breakout Stop+Lim] Acel Wall",
         "EST-10 [Walls Only] Stop+Limit Wall",
         "EST-11 [Grid Pullback Tendencia] 1+2L",
         "EST-12 [Piramidacao no Lucro] 1+1L",
         "EST-13 [Walls Only] Smart Grid 1+2L",
         "EST-14 [Walls Only] Grid Inst 1+2+3L",
         "EST-15 [Posicional EOD] Breakout",
         "EST-16 [Posicional EOD] Stop Wall"
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
      for(int k=1; k<=16; k++)
         m_slots[k].enabled = false;

      if(preset == PRESET_PORT_01_COMPLETO)
        {
         // EST-04 + EST-07 + EST-09 + EST-10 + EST-11 + EST-13 + EST-14 + EST-15
         m_slots[4].enabled = true;  m_slots[7].enabled = true;
         m_slots[9].enabled = true;  m_slots[10].enabled = true;
         m_slots[11].enabled = true; m_slots[13].enabled = true;
         m_slots[14].enabled = true; m_slots[15].enabled = true;
        }
      else if(preset == PRESET_PORT_03_SHARPE)
        {
         // EST-01 + EST-04 + EST-08 + EST-11 + EST-13 + EST-14 + EST-15 + EST-16
         m_slots[1].enabled = true;  m_slots[4].enabled = true;
         m_slots[8].enabled = true;  m_slots[11].enabled = true;
         m_slots[13].enabled = true; m_slots[14].enabled = true;
         m_slots[15].enabled = true; m_slots[16].enabled = true;
        }
      else if(preset == PRESET_LEVE_01_R2_986)
        {
         // EST-04 + EST-06 + EST-08 + EST-09 + EST-11 + EST-12 + EST-15 + EST-16
         m_slots[4].enabled = true;  m_slots[6].enabled = true;
         m_slots[8].enabled = true;  m_slots[9].enabled = true;
         m_slots[11].enabled = true; m_slots[12].enabled = true;
         m_slots[15].enabled = true; m_slots[16].enabled = true;
        }
      else if(preset == PRESET_LEVE_03_PROFIT)
        {
         // EST-03 + EST-04 + EST-08 + EST-09 + EST-11 + EST-13 + EST-15 + EST-16
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
         LoadDailyGexWalls(DateStr(TimeCurrent()));
         LoadVirtualStateFromDisk();
         RenderHudComment();
        }
     }

   string            StateFileName()
     {
      return StringFormat("jumba_state_%I64d_%s.csv", AccountInfoInteger(ACCOUNT_LOGIN), _Symbol);
     }

   void              SaveVirtualStateToDisk()
     {
      if(MQLInfoInteger(MQL_TESTER))
         return;
      int h = FileOpen(StateFileName(), FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(h == INVALID_HANDLE)
         return;
      string today = DateStr(TimeCurrent());
      FileWriteString(h, today + "\n");
      for(int k=1; k<=16; k++)
        {
         string line = StringFormat(
            "%d;%d;%d;%d;%.2f;%.2f;%.2f;%.2f;%.2f;%d;%d;%I64d;%s;%.2f;%d;%.2f;%.2f;%d;%d;%d;%.2f;%.2f;%.2f;%.2f;%.2f;%.2f;%d\n",
            k, m_slots[k].dir, m_slots[k].lots, m_slots[k].leg_stage,
            m_slots[k].p1_entry, m_slots[k].avg_price, m_slots[k].curr_sl, m_slots[k].curr_tp,
            m_slots[k].max_fav_pts, (m_slots[k].be_active ? 1 : 0), m_slots[k].bars_held,
            (long)m_slots[k].entry_bar_time, m_slots[k].last_trade_date,
            m_slots[k].closed_pnl_today_brl, m_slots[k].trades_today,
            m_slots[k].step2_dist, m_slots[k].step3_dist,
            m_slots[k].lot1, m_slots[k].lot2, m_slots[k].lot3,
            m_slots[k].tp_avg_pts, m_slots[k].max_sl_pts,
            m_slots[k].be_trig, m_slots[k].be_lock, m_slots[k].tr_trig, m_slots[k].tr_dist,
            m_slots[k].max_hold_bars
         );
         FileWriteString(h, line);
        }
      FileClose(h);
     }

   void              LoadVirtualStateFromDisk()
     {
      if(MQLInfoInteger(MQL_TESTER))
         return;
      int h = FileOpen(StateFileName(), FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(h == INVALID_HANDLE)
         return;
      string saved_date = FileReadString(h);
      StringReplace(saved_date, "\r", "");
      StringReplace(saved_date, "\n", "");
      string today = DateStr(TimeCurrent());
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
               m_slots[k].lots                 = (int)StringToInteger(p[2]);
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
              }
           }
        }
      FileClose(h);
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
      m_slots[k].opened_intrabar = false;
      m_slots[k].real_synced = false;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = 0;
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_type = 0;
      m_slots[k].pend_price = 0.0;
      m_slots[k].pend_tp_pts = 0.0;
      m_slots[k].pend_sl_pts = 0.0;
      m_slots[k].pend_bar_time = 0;
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
            m_gex_source = "COMMON_DAILY_CSV";
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
               m_gex_source = "COMMON_HISTORY_CSV (" + best_date + ")";
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
               m_gex_source = "FIREBASE_CLOUD";
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
      m_loaded_date = target_date;

      // Reset daily PnL counters on new day
      for(int k=1; k<=16; k++)
        {
         m_slots[k].closed_pnl_today_brl = 0.0;
         m_slots[k].trades_today = 0;
        }

      if(m_draw_levels && !MQLInfoInteger(MQL_OPTIMIZATION))
         DrawLevelsOnChart();

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

   void              OpenVirtualSingle(int k, int dir, double entry_p, datetime bar_t,
                                       double tp_pts, double sl_pts, double be_trig, double be_lock,
                                       double tr_trig, double tr_dist, int max_hold=15, bool is_intrabar=false)
     {
      double p5 = Round5(entry_p);
      m_slots[k].dir = dir;
      m_slots[k].lots = 1;
      m_slots[k].leg_stage = 1;
      m_slots[k].p1_entry = p5;
      m_slots[k].avg_price = p5;
      m_slots[k].curr_sl = (dir == 1) ? Round5(p5 - sl_pts) : Round5(p5 + sl_pts);
      m_slots[k].curr_tp = (dir == 1) ? Round5(p5 + tp_pts) : Round5(p5 - tp_pts);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
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
      m_slots[k].pend_dir = 0;
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
      double init_sl_dist = (k == 13 || k == 14) ? MathMax(max_sl, worst_avg_off + max_sl) : max_sl;
      m_slots[k].curr_sl = (dir == 1) ? Round5(p5 - init_sl_dist) : Round5(p5 + init_sl_dist);
      m_slots[k].curr_tp = (dir == 1) ? Round5(p5 + tp_avg) : Round5(p5 - tp_avg);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
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
      SaveVirtualStateToDisk();
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
      if(m_exec_mode == EXEC_NETTING_VIRTUAL_SYNC)
        {
         double target_net_lots = 0.0;
         if(MQLInfoInteger(MQL_TESTER))
           {
            for(int k=1; k<=16; k++)
              {
               if(m_slots[k].enabled)
                  target_net_lots += (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
              }
           }
         else
           {
            datetime now_loc = TimeLocal();
            for(int k=1; k<=16; k++)
              {
               string gv_lots = StringFormat("JUMBA_LOTS_%s_%d", _Symbol, k);
               string gv_time = StringFormat("JUMBA_TIME_%s_%d", _Symbol, k);
               if(m_slots[k].enabled)
                 {
                  double my_l = (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
                  GlobalVariableSet(gv_lots, my_l);
                  GlobalVariableSet(gv_time, (double)now_loc);
                  target_net_lots += my_l;
                 }
               else if(GlobalVariableCheck(gv_time) && (now_loc - (datetime)GlobalVariableGet(gv_time)) <= 90)
                 {
                  target_net_lots += GlobalVariableGet(gv_lots);
                 }
              }
           }
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
            if(diff > 0.0)
               m_trade.Buy(MathRound(diff), _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
            else
               m_trade.Sell(MathRound(-diff), _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
            SaveVirtualStateToDisk();
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
               double srv_tp = (open_cnt == 1 && best_tp > 0.0) ? Round5(best_tp) : 0.0;
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
            double target_lots = (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
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

            if(target_lots == 0.0 && MathAbs(actual_lots) >= 0.99)
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                     m_trade.PositionClose(m_pos.Ticket());
                 }
              }
            else if(MathAbs(target_lots - actual_lots) >= 0.99)
              {
               if(target_lots * actual_lots < 0.0)
                 {
                  for(int i=PositionsTotal()-1; i>=0; i--)
                    {
                     if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                  actual_lots = 0.0;
                 }
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
                     double tp_d = MathMax(250.0, m_slots[k].init_tp_pts);
                     m_slots[k].curr_sl = (m_slots[k].dir == 1) ? Round5(fill_ref - sl_d) : Round5(fill_ref + sl_d);
                     m_slots[k].curr_tp = (m_slots[k].dir == 1) ? Round5(fill_ref + tp_d) : Round5(fill_ref - tp_d);
                     sl_srv = m_slots[k].curr_sl;
                     tp_srv = m_slots[k].curr_tp;
                    }
                 }
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
               else if(delta > 0.0)
                  sent = m_trade.Buy(MathRound(delta), _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
               else if(delta < 0.0)
                  sent = m_trade.Sell(MathRound(-delta), _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
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
            if(MathAbs(target_lots) >= 0.99 && m_slots[k].curr_sl > 0.0)
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
   //| Processamento Tick a Tick (Ordens Nativas + Saídas SL/TP/Grid)   |
   //+------------------------------------------------------------------+
   void              OnTickProcess()
     {
      MqlRates r_curr[];
      if(CopyRates(_Symbol, PERIOD_M5, 0, 2, r_curr) < 2)
         return;

      datetime curr_bar_time = r_curr[1].time;
      string today_str = DateStr(curr_bar_time);
      int t_min = TimeMinutes(TimeCurrent());

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
                                    m_slots[k].max_hold_bars, true);
                  m_slots[k].real_synced = true;
                  m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                  if(k == 15 || k == 16)
                     m_slots[k].last_trade_date = today_str;
                  PrintFormat("[JUMBA %s] ORDEM PENDENTE NATIVA EXECUTADA | Dir=%d @ %.0f", m_slots[k].name, m_slots[k].dir, m_slots[k].avg_price);
                 }
               else if(!HasPendingOrderForSlot(k))
                 {
                  // Em modo OHLC 1 min, se a ordem pendente executou e já bateu SL/TP dentro do mesmo salto de tick
                  string rsn = "SL_TP_INTRABAR";
                  double deal_px = GetLastExitDealPrice(slot_magic, m_slots[k].pend_price, rsn);
                  if(rsn == "SL" || rsn == "TP")
                    {
                     OpenVirtualSingle(k, m_slots[k].pend_dir, m_slots[k].pend_price, m_slots[k].pend_bar_time,
                                       m_slots[k].pend_tp_pts, m_slots[k].pend_sl_pts,
                                       m_slots[k].be_trig, m_slots[k].be_lock,
                                       m_slots[k].tr_trig, m_slots[k].tr_dist,
                                       m_slots[k].max_hold_bars, true);
                     m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                     if(k == 15 || k == 16)
                        m_slots[k].last_trade_date = today_str;
                     CloseVirtualSlot(k, deal_px, rsn);
                    }
                 }
              }
            // B. Posição Aberta foi encerrada nativamente pelo SL ou TP no Servidor da Corretora / Tester!
            else if(m_slots[k].dir != 0 && m_slots[k].real_synced && MathAbs(actual_lots) < 0.01)
              {
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
         SyncRealPositionsWithVirtualSlots();
        }

      // 2. Monitoramento Intrabar (Fallback p/ Netting e Adição de Lotes de Grid EST-11, EST-13, EST-14)
      for(int k=1; k<=16; k++)
        {
         if(!m_slots[k].enabled)
            continue;

         // A. Disparo de Ordens Pendentes em Netting (ou fallback se ordem pendente nativa não pôde ser apregoada por distância mínima)
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
                                    m_slots[k].max_hold_bars, true);
                  m_slots[k].last_entry_bar_time = curr_bar_time;
                  if(k == 15 || k == 16)
                     m_slots[k].last_trade_date = today_str;
                  PrintFormat("[JUMBA %s] ORDEM PENDENTE EXECUTADA | Dir=%d @ %.0f", m_slots[k].name, m_slots[k].dir, m_slots[k].avg_price);
                 }
              }
           }

         // B. Gerenciamento de Posição Aberta
         if(m_slots[k].dir != 0)
           {
            int d = m_slots[k].dir;

            // Verifica Adição de Lotes de Grid (EST-11, EST-13, EST-14) ANTES do Hard SL
            if(k == 11 || k == 13 || k == 14)
              {
               if(m_slots[k].leg_stage == 1 && m_slots[k].lot2 > 0)
                 {
                  double p2_lvl = (d == 1) ? (m_slots[k].p1_entry - m_slots[k].step2_dist) : (m_slots[k].p1_entry + m_slots[k].step2_dist);
                  if((d == 1 && last_px <= p2_lvl) || (d == -1 && last_px >= p2_lvl))
                    {
                     int new_lots = m_slots[k].lot1 + m_slots[k].lot2;
                     m_slots[k].avg_price = Round5((m_slots[k].p1_entry * m_slots[k].lot1 + p2_lvl * m_slots[k].lot2) / (double)new_lots);
                     m_slots[k].lots = new_lots;
                     m_slots[k].leg_stage = 2;
                     m_slots[k].be_active = false;
                     m_slots[k].max_fav_pts = 0.0;
                     m_slots[k].curr_tp = (d == 1) ? Round5(m_slots[k].avg_price + m_slots[k].tp_avg_pts) : Round5(m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                     m_slots[k].curr_sl = (d == 1) ? Round5(m_slots[k].avg_price - m_slots[k].max_sl_pts) : Round5(m_slots[k].avg_price + m_slots[k].max_sl_pts);
                     PrintFormat("[JUMBA %s] GRID PERNA 2 ATIVADA | Total Lotes=%d | Novo PM=%.0f | Novo TP=%.0f | Novo SL=%.0f",
                                 m_slots[k].name, m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_tp, m_slots[k].curr_sl);
                    }
                 }
               if(m_slots[k].leg_stage == 2 && m_slots[k].lot3 > 0)
                 {
                  double p3_lvl = (d == 1) ? (m_slots[k].p1_entry - m_slots[k].step3_dist) : (m_slots[k].p1_entry + m_slots[k].step3_dist);
                  if((d == 1 && last_px <= p3_lvl) || (d == -1 && last_px >= p3_lvl))
                    {
                     int new_lots = m_slots[k].lots + m_slots[k].lot3;
                     m_slots[k].avg_price = Round5((m_slots[k].avg_price * m_slots[k].lots + p3_lvl * m_slots[k].lot3) / (double)new_lots);
                     m_slots[k].lots = new_lots;
                     m_slots[k].leg_stage = 3;
                     m_slots[k].be_active = false;
                     m_slots[k].max_fav_pts = 0.0;
                     m_slots[k].curr_tp = (d == 1) ? Round5(m_slots[k].avg_price + m_slots[k].tp_avg_pts) : Round5(m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                     m_slots[k].curr_sl = (d == 1) ? Round5(m_slots[k].avg_price - m_slots[k].max_sl_pts) : Round5(m_slots[k].avg_price + m_slots[k].max_sl_pts);
                     PrintFormat("[JUMBA %s] GRID PERNA 3 ATIVADA | Total Lotes=%d | Novo PM=%.0f | Novo TP=%.0f | Novo SL=%.0f",
                                 m_slots[k].name, m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_tp, m_slots[k].curr_sl);
                    }
                 }
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
   //| Avaliação de Fechamento de Barra M5 (BE/Trail + Sinais Mkt/Lim)  |
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

      // Atualiza máxima e mínima da manhã (09h00 - 11h00) para a EST-16 Extreme Fade
      if(m_morning_date != b1_date)
        {
         m_morning_date = b1_date;
         m_day_high_morning = b1.high;
         m_day_low_morning = b1.low;
        }
      else if(b1_tmin <= 660)
        {
         if(b1.high > m_day_high_morning) m_day_high_morning = b1.high;
         if(b1.low  < m_day_low_morning)  m_day_low_morning  = b1.low;
        }

      // Calcula NWE(50, 5.0, 2.0), NWE(30, 3.0, 1.6), RSI(7) e WDO
      ComputeCausalNWE(rates, copied, 50, 5.0, 2.0,
                       m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1,
                       m_n50_c_2, m_n50_u_2, m_n50_l_2, m_n50_s_2);
      ComputeCausalNWE(rates, copied, 30, 3.0, 1.6,
                       m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1,
                       m_n30_c_2, m_n30_u_2, m_n30_l_2, m_n30_s_2);
      ComputeRsi7(rates, copied, m_rsi7_1, m_rsi7_2);
      ComputeWdoMetrics();

      double cur_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double cur_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      // 1. Limpa ordens pendentes da barra anterior e atualiza BE / Trailing Stop / Time Stop no fechamento da barra M5 b1!
      for(int k=1; k<=16; k++)
        {
         if(m_slots[k].pend_dir != 0)
           {
            DeletePendingOrdersForSlot(k);
            m_slots[k].pend_dir = 0;
           }

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
                  double cand_sl = (d == 1) ? Round5(m_slots[k].avg_price + m_slots[k].be_lock) : Round5(m_slots[k].avg_price - m_slots[k].be_lock);
                  if((d == 1 && new_bar_open > cand_sl + 5.0) || (d == -1 && new_bar_open < cand_sl - 5.0))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
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

               if(m_slots[k].be_trig > 0.0 && !m_slots[k].be_active && m_slots[k].max_fav_pts >= m_slots[k].be_trig)
                 {
                  double cand_sl = (d == 1) ? Round5(m_slots[k].avg_price + m_slots[k].be_lock) : Round5(m_slots[k].avg_price - m_slots[k].be_lock);
                  if((d == 1 && new_bar_open > cand_sl + 5.0) || (d == -1 && new_bar_open < cand_sl - 5.0))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                     m_slots[k].be_active = true;
                    }
                 }

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

               // Time Stop (exceto EOD 15 e 16 que seguram até 17h15)
               if(k <= 14 && m_slots[k].bars_held >= m_slots[k].max_hold_bars)
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

      double d_l, lvl_s, d_h, lvl_r;
      FindNearestLevel(m_levels_all, b1.low,  d_l, lvl_s);
      FindNearestLevel(m_levels_all, b1.high, d_h, lvl_r);
      double dw_l_main, w_s_main, dw_h_main, w_r_main;
      FindNearestLevel(m_levels_walls, b1.low,  dw_l_main, w_s_main);
      FindNearestLevel(m_levels_walls, b1.high, dw_h_main, w_r_main);
      double bw50 = m_n50_u_1 - m_n50_l_1;
      double bw30 = m_n30_u_1 - m_n30_l_1;
      double body1 = b1.close - b1.open;
      double rng1 = MathMax(1.0, b1.high - b1.low);

      // --- EST-01 & EST-02: Scalper Híbrido Limit + Market ---
      for(int sc_id=1; sc_id<=2; sc_id++)
        {
         if(!m_slots[sc_id].enabled || m_slots[sc_id].dir != 0)
            continue;
         string wm_rej = (sc_id == 1) ? "NY_1000_1630" : "FULL_09_17";
         string wm_lim = (sc_id == 1) ? "NY_1000_1630" : "CORE_09_1615";
         double l_off  = (sc_id == 1) ? 0.0 : 10.0;
         bool c_buy  = (b1.close > b1.open && (b1.close - b1.low) >= 0.5 * rng1);
         bool c_sell = (b1.close < b1.open && (b1.high - b1.close) >= 0.5 * rng1);

         if(m_slots[sc_id].last_entry_bar_time != b1.time && WindowOk(b1_tmin, wm_rej))
           {
            if(d_l <= 60.0 && (b1.close - lvl_s >= -25.0) && (b1.close - lvl_s <= 75.0) && b1.close <= (m_n50_l_1 + bw50 * 0.22) && m_rsi7_1 <= 35.0 && c_buy && m_n50_s_1 >= -12.0)
              {
               OpenVirtualSingle(sc_id, 1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
               m_slots[sc_id].last_entry_bar_time = b1.time;
               continue;
              }
            else if(d_h <= 60.0 && (lvl_r - b1.close >= -25.0) && (lvl_r - b1.close <= 75.0) && b1.close >= (m_n50_u_1 - bw50 * 0.22) && m_rsi7_1 >= 65.0 && c_sell && m_n50_s_1 <= 12.0)
              {
               OpenVirtualSingle(sc_id, -1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
               m_slots[sc_id].last_entry_bar_time = b1.time;
               continue;
              }
            if(sc_id == 1)
              {
               bool ent_imp = false;
               for(int i=0; i<ArraySize(m_levels_all); i++)
                 {
                  double lvl = m_levels_all[i];
                  if(b1.open <= lvl + 12.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 85.0 && body1 >= 55.0 && m_n50_s_1 >= 4.5 && b1.close < (m_n50_u_1 - bw50 * 0.15))
                    {
                     OpenVirtualSingle(1, 1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
                     m_slots[1].last_entry_bar_time = b1.time;
                     ent_imp = true;
                     break;
                    }
                  if(b1.open >= lvl - 12.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 85.0 && (-body1) >= 55.0 && m_n50_s_1 <= -4.5 && b1.close > (m_n50_l_1 + bw50 * 0.15))
                    {
                     OpenVirtualSingle(1, -1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
                     m_slots[1].last_entry_bar_time = b1.time;
                     ent_imp = true;
                     break;
                    }
                 }
               if(ent_imp)
                  continue;
              }
           }
         if(WindowOk(new_tmin, wm_lim))
           {
            if(m_n50_s_1 >= 6.0 && b1.close <= (m_n50_c_1 + bw50 * 0.18) && d_l <= 55.0 && b1.close > (lvl_s + l_off))
               ArmPendingOrder(sc_id, 1, 1, lvl_s + l_off, new_bar_time, new_bar_open, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15);
            else if(m_n50_s_1 <= -6.0 && b1.close >= (m_n50_c_1 - bw50 * 0.18) && d_h <= 55.0 && b1.close < (lvl_r - l_off))
               ArmPendingOrder(sc_id, -1, 1, lvl_r - l_off, new_bar_time, new_bar_open, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15);
           }
        }

      // --- EST-03: Arbitragem Cambial Confluência WIN+WDO na Wall ---
      if(m_slots[3].enabled && m_slots[3].dir == 0)
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

      // --- EST-04: Pullback Limit Reteste de Wall Rompida c/ GammaFlip ---
      if(m_slots[4].enabled && m_slots[4].dir == 0 && WindowOk(new_tmin, "FULL_09_17"))
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 10.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 95.0 && body1 >= 45.0 && m_n50_s_1 >= 6.0)
              {
               if((m_gamma_flip <= 0.0 || b1.close >= m_gamma_flip) && b1.close < (m_n50_u_1 - bw50 * 0.15))
                 {
                  ArmPendingOrder(4, 1, 1, lvl, new_bar_time, new_bar_open, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
                  break;
                 }
              }
            if(b1.open >= lvl - 10.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 95.0 && (-body1) >= 45.0 && m_n50_s_1 <= -6.0)
              {
               if((m_gamma_flip <= 0.0 || b1.close <= m_gamma_flip) && b1.close > (m_n50_l_1 + bw50 * 0.15))
                 {
                  ArmPendingOrder(4, -1, 1, lvl, new_bar_time, new_bar_open, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
                  break;
                 }
              }
           }
        }

      // --- EST-05: Pullback Cluster NWE30 + NWE50 + Wall ---
      if(m_slots[5].enabled && m_slots[5].dir == 0)
        {
         bool entered5 = false;
         if(m_slots[5].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 12.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 90.0 && body1 >= 45.0 && m_n30_s_1 >= 5.0 && m_n50_s_1 >= 4.0 && b1.close < (m_n30_u_1 - bw30 * 0.15))
                 {
                  OpenVirtualSingle(5, 1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
                  m_slots[5].last_entry_bar_time = b1.time;
                  entered5 = true;
                  break;
                 }
               if(b1.open >= lvl - 12.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 90.0 && (-body1) >= 45.0 && m_n30_s_1 <= -5.0 && m_n50_s_1 <= -4.0 && b1.close > (m_n30_l_1 + bw30 * 0.15))
                 {
                  OpenVirtualSingle(5, -1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16, false);
                  m_slots[5].last_entry_bar_time = b1.time;
                  entered5 = true;
                  break;
                 }
              }
           }
         if(!entered5 && WindowOk(new_tmin, "CORE_09_1615"))
           {
            if(m_n30_s_1 >= 6.0 && m_n50_s_1 >= 6.0 && b1.close <= (m_n30_c_1 + bw30 * 0.20) && d_l <= 50.0 && b1.close > lvl_s)
               ArmPendingOrder(5, 1, 1, lvl_s, new_bar_time, new_bar_open, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
            else if(m_n30_s_1 <= -6.0 && m_n50_s_1 <= -6.0 && b1.close >= (m_n30_c_1 - bw30 * 0.20) && d_h <= 50.0 && b1.close < lvl_r)
               ArmPendingOrder(5, -1, 1, lvl_r, new_bar_time, new_bar_open, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
           }
        }

      // --- EST-06: Pullback Limit Ordem Limit na Wall c/ Slope NWE + Reteste (09h-16h15) ---
      if(m_slots[6].enabled && m_slots[6].dir == 0 && WindowOk(new_tmin, "CORE_09_1615"))
        {
         bool armed6 = false;
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 10.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 95.0 && body1 >= 42.0 && m_n50_s_1 >= 5.5 && b1.close < (m_n50_u_1 - bw50 * 0.15))
              {
               ArmPendingOrder(6, 1, 1, lvl, new_bar_time, new_bar_open, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
               armed6 = true;
               break;
              }
            if(b1.open >= lvl - 10.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 95.0 && (-body1) >= 42.0 && m_n50_s_1 <= -5.5 && b1.close > (m_n50_l_1 + bw50 * 0.15))
              {
               ArmPendingOrder(6, -1, 1, lvl, new_bar_time, new_bar_open, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
               armed6 = true;
               break;
              }
           }
         if(!armed6)
           {
            if(m_n50_s_1 >= 8.0 && b1.close <= (m_n50_c_1 + bw50 * 0.20) && d_l <= 55.0 && b1.close > lvl_s)
               ArmPendingOrder(6, 1, 1, lvl_s, new_bar_time, new_bar_open, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15);
            else if(m_n50_s_1 <= -8.0 && b1.close >= (m_n50_c_1 - bw50 * 0.20) && d_h <= 55.0 && b1.close < lvl_r)
               ArmPendingOrder(6, -1, 1, lvl_r, new_bar_time, new_bar_open, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15);
           }
        }

      // --- EST-07 & EST-08: Breakout Mkt Momentum Wall c/ Espaço NWE ---
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

         if(WindowOk(b1_tmin, wm_bo))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 15.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 90.0 && body1 >= min_bd && m_n50_s_1 >= 4.0)
                 {
                  if(b1.close < (m_n50_u_1 - bw50 * 0.15))
                    {
                     OpenVirtualSingle(bo_id, 1, new_bar_open, new_bar_time, tp_b, sl_b, be_b, 20.0, tr_t, tr_d, 16, false);
                     m_slots[bo_id].last_entry_bar_time = b1.time;
                     break;
                    }
                 }
               if(b1.open >= lvl - 15.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 90.0 && (-body1) >= min_bd && m_n50_s_1 <= -4.0)
                 {
                  if(b1.close > (m_n50_l_1 + bw50 * 0.15))
                    {
                     OpenVirtualSingle(bo_id, -1, new_bar_open, new_bar_time, tp_b, sl_b, be_b, 20.0, tr_t, tr_d, 16, false);
                     m_slots[bo_id].last_entry_bar_time = b1.time;
                     break;
                    }
                 }
              }
           }
        }

      // --- EST-09: Breakout Stop & Limit Wall (NY Session - All Levels) ---
      if(m_slots[9].enabled && m_slots[9].dir == 0 && WindowOk(new_tmin, "NY_1000_1630"))
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

      // --- EST-10: Stop & Limit SÓ NAS WALLS PRINCIPAIS (CORE 09h-16h15) ---
      if(m_slots[10].enabled && m_slots[10].dir == 0 && WindowOk(new_tmin, "CORE_09_1615") && ArraySize(m_levels_walls) > 0)
        {
         bool armed10 = false;
         if(m_n30_s_1 >= 4.5 && b1.close > b1.open && body1 >= 35.0 && b1.close < (m_n30_u_1 - bw30 * 0.18))
           {
            for(int i=0; i<ArraySize(m_levels_walls); i++)
              {
               double w = m_levels_walls[i];
               if(w >= b1.close - 5.0 && (w - b1.close) <= 55.0)
                 {
                  ArmPendingOrder(10, 1, 2, MathMax(w + 10.0, b1.high + 5.0), new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
                  armed10 = true;
                  break;
                 }
              }
           }
         if(!armed10 && m_n30_s_1 <= -4.5 && b1.close < b1.open && (-body1) >= 35.0 && b1.close > (m_n30_l_1 + bw30 * 0.18))
           {
            for(int i=ArraySize(m_levels_walls)-1; i>=0; i--)
              {
               double w = m_levels_walls[i];
               if(w <= b1.close + 5.0 && (b1.close - w) <= 55.0)
                 {
                  ArmPendingOrder(10, -1, 2, MathMin(w - 10.0, b1.low - 5.0), new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
                  armed10 = true;
                  break;
                 }
              }
           }
         if(!armed10)
           {
            if(m_n50_s_1 >= 5.5 && dw_l_main <= 60.0 && b1.close > w_s_main && b1.close <= (m_n50_c_1 + bw50 * 0.22))
               ArmPendingOrder(10, 1, 1, w_s_main, new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
            else if(m_n50_s_1 <= -5.5 && dw_h_main <= 60.0 && b1.close < w_r_main && b1.close >= (m_n50_c_1 - bw50 * 0.22))
               ArmPendingOrder(10, -1, 1, w_r_main, new_bar_time, new_bar_open, 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16);
           }
        }

      // --- EST-11: Grid Pullback Tendência 1+2 Lotes a Favor do NWE (Sem Almoço) ---
      if(m_slots[11].enabled && m_slots[11].dir == 0 && m_slots[11].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NO_LUNCH"))
        {
         if(m_n50_s_1 >= 3.0 && b1.close < (m_n50_u_1 - bw50 * 0.15) && d_l <= 55.0 && (b1.close - lvl_s >= -10.0) && (b1.close - lvl_s <= 85.0) && b1.close > b1.open)
           {
            OpenVirtualGrid(11, 1, new_bar_open, new_bar_time, 450.0, 900.0, 1, 2, 0, 280.0, 650.0, 150.0, 25.0, 24);
            m_slots[11].last_entry_bar_time = b1.time;
           }
         else if(m_n50_s_1 <= -3.0 && b1.close > (m_n50_l_1 + bw50 * 0.15) && d_h <= 55.0 && (lvl_r - b1.close >= -10.0) && (lvl_r - b1.close <= 85.0) && b1.close < b1.open)
           {
            OpenVirtualGrid(11, -1, new_bar_open, new_bar_time, 450.0, 900.0, 1, 2, 0, 280.0, 650.0, 150.0, 25.0, 24);
            m_slots[11].last_entry_bar_time = b1.time;
           }
        }

      // --- EST-12: Piramidação no Lucro 1+1 Lote Anti-Martingale (NY 10h-16h30) ---
      if(m_slots[12].enabled && m_slots[12].dir == 0 && m_slots[12].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 15.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 90.0 && body1 >= 55.0 && m_n50_s_1 >= 4.0 && b1.close < (m_n50_u_1 - bw50 * 0.15))
              {
               OpenVirtualSingle(12, 1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 18, false);
               m_slots[12].last_entry_bar_time = b1.time;
               break;
              }
            if(b1.open >= lvl - 15.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 90.0 && (-body1) >= 55.0 && m_n50_s_1 <= -4.0 && b1.close > (m_n50_l_1 + bw50 * 0.15))
              {
               OpenVirtualSingle(12, -1, new_bar_open, new_bar_time, 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 18, false);
               m_slots[12].last_entry_bar_time = b1.time;
               break;
              }
           }
        }

      // --- EST-13: Smart Grid 1+2 Lotes SÓ NAS WALLS PRINCIPAIS (FULL 09h-17h) ---
      if(m_slots[13].enabled && m_slots[13].dir == 0 && m_slots[13].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "FULL_09_17") && ArraySize(m_levels_walls) > 0)
        {
         if(m_n50_s_1 >= 2.0 && b1.close < (m_n50_u_1 - bw50 * 0.12) && dw_l_main <= 65.0 && (b1.close - w_s_main >= -15.0) && (b1.close - w_s_main <= 90.0) && b1.close > b1.open)
           {
            OpenVirtualGrid(13, 1, new_bar_open, new_bar_time, 507.0, 1014.0, 1, 2, 0, 280.0, 700.0, 150.0, 25.0, 26);
            m_slots[13].last_entry_bar_time = b1.time;
           }
         else if(m_n50_s_1 <= -2.0 && b1.close > (m_n50_l_1 + bw50 * 0.12) && dw_h_main <= 65.0 && (w_r_main - b1.close >= -15.0) && (w_r_main - b1.close <= 90.0) && b1.close < b1.open)
           {
            OpenVirtualGrid(13, -1, new_bar_open, new_bar_time, 507.0, 1014.0, 1, 2, 0, 280.0, 700.0, 150.0, 25.0, 26);
            m_slots[13].last_entry_bar_time = b1.time;
           }
        }

      // --- EST-14: Grid Institucional Wall->MidWall->Wall (1+2+3 Lotes SÓ NAS WALLS PRINCIPAIS) ---
      if(m_slots[14].enabled && m_slots[14].dir == 0 && m_slots[14].last_entry_bar_time != b1.time && b1_tmin >= 545 && b1_tmin <= 930 && ArraySize(m_levels_walls) > 0)
        {
         if(m_n50_s_1 >= 1.5 && b1.close < (m_n50_u_1 - bw50 * 0.15) && dw_l_main <= 65.0 && (b1.close - w_s_main >= -20.0) && (b1.close - w_s_main <= 85.0) && b1.close > b1.open)
           {
            OpenVirtualGrid(14, 1, new_bar_open, new_bar_time, 507.0, 1014.0, 1, 2, 3, 280.0, 650.0, 150.0, 25.0, 28);
            m_slots[14].last_entry_bar_time = b1.time;
           }
         else if(m_n50_s_1 <= -1.5 && b1.close > (m_n50_l_1 + bw50 * 0.15) && dw_h_main <= 65.0 && (w_r_main - b1.close >= -20.0) && (w_r_main - b1.close <= 85.0) && b1.close < b1.open)
           {
            OpenVirtualGrid(14, -1, new_bar_open, new_bar_time, 507.0, 1014.0, 1, 2, 3, 280.0, 650.0, 150.0, 25.0, 28);
            m_slots[14].last_entry_bar_time = b1.time;
           }
        }

      // --- EST-15: Posicional EOD Breakout Matinal (09h05-13h00 -> 17h15) ---
      if(m_slots[15].enabled && m_slots[15].dir == 0 && m_slots[15].last_trade_date != b1_date && b1_tmin >= 545 && b1_tmin <= 780)
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 12.0 && b1.close > lvl + 15.0 && (b1.close - lvl) <= 95.0 && body1 >= 50.0 && m_n50_s_1 >= 5.0 && b1.close < (m_n50_u_1 - bw50 * 0.15))
              {
               OpenVirtualSingle(15, 1, new_bar_open, new_bar_time, 1500.0, 450.0, 300.0, 25.0, 600.0, 250.0, 120, false);
               m_slots[15].last_trade_date = b1_date;
               m_slots[15].last_entry_bar_time = b1.time;
               break;
              }
            if(b1.open >= lvl - 12.0 && b1.close < lvl - 15.0 && (lvl - b1.close) <= 95.0 && (-body1) >= 50.0 && m_n50_s_1 <= -5.0 && b1.close > (m_n50_l_1 + bw50 * 0.15))
              {
               OpenVirtualSingle(15, -1, new_bar_open, new_bar_time, 1500.0, 450.0, 300.0, 25.0, 600.0, 250.0, 120, false);
               m_slots[15].last_trade_date = b1_date;
               m_slots[15].last_entry_bar_time = b1.time;
               break;
              }
           }
        }

      // --- EST-16: Posicional EOD Stop Wall (09h10-14h00 -> 17h15) ---
      if(m_slots[16].enabled && m_slots[16].dir == 0 && m_slots[16].last_trade_date != b1_date && new_tmin >= 550 && new_tmin <= 840)
        {
         bool armed16 = false;
         if(m_n30_s_1 >= 5.0 && b1.close > b1.open && body1 >= 40.0 && b1.close < (m_n30_u_1 - bw30 * 0.20))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(lvl >= b1.close - 5.0 && (lvl - b1.close) <= 55.0)
                 {
                  ArmPendingOrder(16, 1, 2, MathMax(lvl + 10.0, b1.high + 5.0), new_bar_time, new_bar_open, 1500.0, 400.0, 260.0, 25.0, 500.0, 200.0, 120);
                  armed16 = true;
                  break;
                 }
              }
           }
         if(!armed16 && m_n30_s_1 <= -5.0 && b1.close < b1.open && (-body1) >= 40.0 && b1.close > (m_n30_l_1 + bw30 * 0.20))
           {
            for(int i=ArraySize(m_levels_all)-1; i>=0; i--)
              {
               double lvl = m_levels_all[i];
               if(lvl <= b1.close + 5.0 && (b1.close - lvl) <= 55.0)
                 {
                  ArmPendingOrder(16, -1, 2, MathMin(lvl - 10.0, b1.low - 5.0), new_bar_time, new_bar_open, 1500.0, 400.0, 260.0, 25.0, 500.0, 200.0, 120);
                  break;
                 }
              }
           }
        }

      if(!MQLInfoInteger(MQL_OPTIMIZATION))
         RenderHudComment();
     }

   void              ArmPendingOrder(int k, int dir, int ptype, double price, datetime bar_t, double new_bar_open,
                                     double tp_pts, double sl_pts, double be_trig, double be_lock,
                                     double tr_trig, double tr_dist, int max_hold=15)
     {
      double p5 = Round5(price);

      // Filtro de Abertura da Nova Barra (idêntico ao Python: não arma Limit se abriu com gap além do preço, nem Stop se abriu além do Stop)
      if(ptype == 1 && dir == 1 && new_bar_open < p5)
         return;
      if(ptype == 1 && dir == -1 && new_bar_open > p5)
         return;
      if(ptype == 2 && dir == 1 && new_bar_open > p5)
         return;
      if(ptype == 2 && dir == -1 && new_bar_open < p5)
         return;

      m_slots[k].pend_dir = dir;
      m_slots[k].pend_type = ptype; // 1=Limit, 2=Stop
      m_slots[k].pend_price = p5;
      m_slots[k].pend_bar_time = bar_t;
      m_slots[k].pend_tp_pts = tp_pts;
      m_slots[k].pend_sl_pts = sl_pts;
      m_slots[k].be_trig = be_trig;
      m_slots[k].be_lock = be_lock;
      m_slots[k].tr_trig = tr_trig;
      m_slots[k].tr_dist = tr_dist;
      m_slots[k].max_hold_bars = max_hold;

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
            OpenVirtualSingle(k, dir, p5, bar_t, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, true);
            m_slots[k].last_entry_bar_time = bar_t;
            if(k == 15 || k == 16)
               m_slots[k].last_trade_date = DateStr(bar_t);
            return;
           }

         ulong slot_magic = m_base_magic + (ulong)k;
         m_trade.SetExpertMagicNumber(slot_magic);
         double vol = MathRound(1.0 * m_lot_mult);
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
     }

   void              RenderHudComment()
     {
      string hud = "==========================================================\n";
      hud += StringFormat(" JUMBA QUANT GEX + NWE | Data: %s | Fonte: %s\n", m_loaded_date, m_gex_source);
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
            st = StringFormat("ORDEM PENDENTE %s @ %.0f", (m_slots[k].pend_type==1?"LIMIT":"STOP"), m_slots[k].pend_price);

         hud += StringFormat(" %-38s | %-34s | Hoje: %d tr (R$ %.0f)\n",
                             m_slots[k].name, st, m_slots[k].trades_today, m_slots[k].closed_pnl_today_brl);
        }
      hud += "==========================================================";
      Comment(hud);
     }
  };
