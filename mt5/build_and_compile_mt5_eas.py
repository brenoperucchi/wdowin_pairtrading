import os
import shutil
import subprocess

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
MT5_PROJ_DIR = os.path.join(PROJECT_ROOT, "mt5")
MT5_INC_DIR = os.path.join(MT5_PROJ_DIR, "Include")
MT5_EXP_DIR = os.path.join(MT5_PROJ_DIR, "Experts", "Jumba_GEX_NWE")

os.makedirs(MT5_INC_DIR, exist_ok=True)
os.makedirs(MT5_EXP_DIR, exist_ok=True)

# 1. Patch gex/engine/main.py cleanly if not already patched
main_py_path = os.path.join(PROJECT_ROOT, "gex", "engine", "main.py")
with open(main_py_path, "r", encoding="utf-8") as f:
    main_txt = f.read()

if "export_to_mt5_common" not in main_txt:
    anchor = '    print("\\n" + "=" * 50)\n    print("  Pipeline concluido com sucesso!")'
    hook_code = '''    # 8. Export to MT5 Common\\Files + Firebase Backup
    print("\\n[8/8] Exportando MagicWalls para MetaTrader 5 (Common\\\\Files + Firebase)...")
    try:
        from .mt5_exporter import export_to_mt5_common
        export_to_mt5_common(walls=walls, ref_date=trading_date, current_win=current_win)
    except Exception as e:
        print(f"      Aviso: Falha ao exportar para MT5 Common\\\\Files ({e})")
    try:
        push_walls_to_firebase(walls)
    except Exception as e:
        print(f"      Aviso: Falha ao publicar no Firebase ({e})")

'''
    if anchor in main_txt:
        main_txt = main_txt.replace(anchor, hook_code + anchor, 1)
        with open(main_py_path, "w", encoding="utf-8") as f:
            f.write(main_txt)
        print("[OK] Patched gex/engine/main.py with Step [8/8] MT5 Common\\Files + Firebase export!")

# 2. Write Jumba_GEX_NWE_Core.mqh
core_mqh = r"""//+------------------------------------------------------------------+
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
   int               bars_held;       // M5 bars held since entry
   datetime          entry_bar_time;  // Timestamp of M5 bar when position opened
   string            last_trade_date; // For EOD strategies (1 trade/day limit)
   // Pending Order State (for Limit/Stop strategies armed for the current M5 bar)
   int               pend_dir;        // 0=None, 1=Buy, -1=Sell
   int               pend_type;       // 0=None, 1=Limit, 2=Stop
   double            pend_price;      // Trigger price
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
      m_exec_mode = EXEC_NETTING_VIRTUAL_SYNC;
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
         "EST-09 [Breakout Stop] Aceleracao Wall",
         "EST-10 [Breakout Stop] Stop Wick",
         "EST-11 [Grid Pullback Tendencia] 1+2L",
         "EST-12 [Piramidacao no Lucro] 1+1L",
         "EST-13 [Smart Grid RSI+BE] 1+2L",
         "EST-14 [Grid Institucional] 1+2+3L",
         "EST-15 [Posicional EOD] Breakout",
         "EST-16 [Posicional EOD] Extreme Fade"
        };

      for(int k=1; k<=16; k++)
        {
         m_slots[k].id = k;
         m_slots[k].name = names[k];
         m_slots[k].enabled = false;
         ResetSlotPosition(k);
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
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = 0;
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_type = 0;
      m_slots[k].pend_price = 0.0;
      m_slots[k].pend_bar_time = 0;
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
      if(target_date == m_loaded_date && ArraySize(m_levels_all) > 0)
         return true;

      ArrayResize(m_gex_raw, 0);
      ArrayResize(m_levels_all, 0);
      ArrayResize(m_levels_walls, 0);
      m_gamma_flip = 0.0;
      m_max_gamma = 0.0;
      m_min_gamma = 0.0;

      // 1. Tenta ler jumba_gex_win_daily.csv em Common\Files se for a data de hoje
      int h_daily = FileOpen("jumba_gex_win_daily.csv", FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
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
               if(s_date == target_date || r_date == target_date)
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
         int h_hist = FileOpen("jumba_gex_win_history.csv", FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
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
                  if(d <= target_date)
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
         ObjectCreate(0, obj_name, OBJ_HLINE, 0, 0, p);
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
   void              OpenVirtualSingle(int k, int dir, double entry_p, datetime bar_t,
                                       double tp_pts, double sl_pts, double be_trig, double be_lock,
                                       double tr_trig, double tr_dist, int max_hold=16)
     {
      m_slots[k].dir = dir;
      m_slots[k].lots = 1;
      m_slots[k].leg_stage = 1;
      m_slots[k].p1_entry = entry_p;
      m_slots[k].avg_price = entry_p;
      m_slots[k].curr_sl = (dir == 1) ? (entry_p - sl_pts) : (entry_p + sl_pts);
      m_slots[k].curr_tp = (dir == 1) ? (entry_p + tp_pts) : (entry_p - tp_pts);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = bar_t;
      m_slots[k].be_trig = be_trig;
      m_slots[k].be_lock = be_lock;
      m_slots[k].tr_trig = tr_trig;
      m_slots[k].tr_dist = tr_dist;
      m_slots[k].max_hold_bars = max_hold;
      m_slots[k].pend_dir = 0;
     }

   void              OpenVirtualGrid(int k, int dir, double entry_p, datetime bar_t,
                                     double step2, double step3, int l1, int l2, int l3,
                                     double tp_avg, double max_sl, double be_avg_trig)
     {
      m_slots[k].dir = dir;
      m_slots[k].lots = l1;
      m_slots[k].leg_stage = 1;
      m_slots[k].p1_entry = entry_p;
      m_slots[k].avg_price = entry_p;
      m_slots[k].curr_sl = (dir == 1) ? (entry_p - max_sl) : (entry_p + max_sl);
      m_slots[k].curr_tp = (dir == 1) ? (entry_p + tp_avg) : (entry_p - tp_avg);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
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
      m_slots[k].be_lock = 20.0;
      m_slots[k].max_hold_bars = 28;
      m_slots[k].pend_dir = 0;
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
         // Soma a posição líquida desejada de todos os slots ativos
         double target_net_lots = 0.0;
         for(int k=1; k<=16; k++)
           {
            if(m_slots[k].enabled && m_slots[k].dir != 0)
               target_net_lots += (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
           }

         // Verifica posição líquida atual no ativo _Symbol
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
               // Se inverteu de lado, fecha primeiro
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
               m_trade.SetExpertMagicNumber(slot_magic);
               if(delta > 0.0)
                  m_trade.Buy(MathRound(delta), _Symbol, 0.0, 0.0, 0.0, m_slots[k].name);
               else if(delta < 0.0)
                  m_trade.Sell(MathRound(-delta), _Symbol, 0.0, 0.0, 0.0, m_slots[k].name);
              }
           }
        }
     }

   //+------------------------------------------------------------------+
   //| Processamento Tick a Tick (Saídas TP/SL/BE/Trail + Ordens Limit) |
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

      // Trava de Perda Máxima Diária ou Encerramento de Fim de Dia (17h15 = 1035 min)
      double total_day_pnl = GetTotalDailyPnLBRL();
      if(t_min >= 1035 || (m_max_daily_loss_brl > 0.0 && total_day_pnl <= -m_max_daily_loss_brl))
        {
         string rsn = (t_min >= 1035) ? "EOD_1715" : "MAX_DAILY_LOSS";
         double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         for(int k=1; k<=16; k++)
           {
            m_slots[k].pend_dir = 0;
            if(m_slots[k].dir != 0)
               CloseVirtualSlot(k, px, rsn);
           }
         SyncRealPositionsWithVirtualSlots();
         return;
        }

      // 1. Verifica se abriu uma nova barra M5 -> Avalia fechamento da barra anterior e arma sinais!
      if(curr_bar_time != m_last_m5_bar_time)
        {
         OnNewM5Bar(curr_bar_time, today_str);
         m_last_m5_bar_time = curr_bar_time;
        }

      // 2. Monitora em Tempo Real (Tick a Tick) Preço Atual para Ordens Pendentes (Limit/Stop) e Saídas (SL/TP/Grid/BE/Trail)
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double last_px = SymbolInfoDouble(_Symbol, SYMBOL_LAST);
      if(last_px <= 0.0)
         last_px = bid;

      for(int k=1; k<=16; k++)
        {
         if(!m_slots[k].enabled)
            continue;

         // A. Disparo de Ordens Pendentes (Limit / Stop) armadas para a barra M5 atual
         if(m_slots[k].dir == 0 && m_slots[k].pend_dir != 0 && m_slots[k].pend_bar_time == curr_bar_time)
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
                                 m_slots[k].curr_tp, m_slots[k].curr_sl,
                                 m_slots[k].be_trig, m_slots[k].be_lock,
                                 m_slots[k].tr_trig, m_slots[k].tr_dist, 16);
               PrintFormat("[JUMBA %s] ORDEM PENDENTE EXECUTADA | Dir=%d @ %.0f", m_slots[k].name, m_slots[k].dir, m_slots[k].avg_price);
              }
           }

         // B. Gerenciamento de Posição Aberta Tick-a-Tick
         if(m_slots[k].dir != 0)
           {
            int d = m_slots[k].dir;
            // Verifica Stop Loss e Take Profit
            if(d == 1)
              {
               if(last_px <= m_slots[k].curr_sl)
                 {
                  CloseVirtualSlot(k, m_slots[k].curr_sl, "SL");
                  continue;
                 }
               if(last_px >= m_slots[k].curr_tp)
                 {
                  CloseVirtualSlot(k, m_slots[k].curr_tp, "TP");
                  continue;
                 }
              }
            else
              {
               if(last_px >= m_slots[k].curr_sl)
                 {
                  CloseVirtualSlot(k, m_slots[k].curr_sl, "SL");
                  continue;
                 }
               if(last_px <= m_slots[k].curr_tp)
                 {
                  CloseVirtualSlot(k, m_slots[k].curr_tp, "TP");
                  continue;
                 }
              }

            // Verifica Adição de Lotes de Grid (EST-11, EST-13, EST-14)
            if(k == 11 || k == 13 || k == 14)
              {
               if(m_slots[k].leg_stage == 1 && m_slots[k].lot2 > 0)
                 {
                  double p2_lvl = (d == 1) ? (m_slots[k].p1_entry - m_slots[k].step2_dist) : (m_slots[k].p1_entry + m_slots[k].step2_dist);
                  if((d == 1 && last_px <= p2_lvl) || (d == -1 && last_px >= p2_lvl))
                    {
                     int new_lots = m_slots[k].lot1 + m_slots[k].lot2;
                     m_slots[k].avg_price = (m_slots[k].p1_entry * m_slots[k].lot1 + p2_lvl * m_slots[k].lot2) / (double)new_lots;
                     m_slots[k].lots = new_lots;
                     m_slots[k].leg_stage = 2;
                     m_slots[k].curr_tp = (d == 1) ? (m_slots[k].avg_price + m_slots[k].tp_avg_pts) : (m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                     PrintFormat("[JUMBA %s] GRID PERNA 2 ATIVADA | Total Lotes=%d | Novo PM=%.0f | Novo TP=%.0f",
                                 m_slots[k].name, m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_tp);
                    }
                 }
               else if(m_slots[k].leg_stage == 2 && m_slots[k].lot3 > 0)
                 {
                  double p3_lvl = (d == 1) ? (m_slots[k].p1_entry - m_slots[k].step3_dist) : (m_slots[k].p1_entry + m_slots[k].step3_dist);
                  if((d == 1 && last_px <= p3_lvl) || (d == -1 && last_px >= p3_lvl))
                    {
                     int new_lots = m_slots[k].lots + m_slots[k].lot3;
                     m_slots[k].avg_price = (m_slots[k].avg_price * m_slots[k].lots + p3_lvl * m_slots[k].lot3) / (double)new_lots;
                     m_slots[k].lots = new_lots;
                     m_slots[k].leg_stage = 3;
                     m_slots[k].curr_tp = (d == 1) ? (m_slots[k].avg_price + m_slots[k].tp_avg_pts) : (m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                     PrintFormat("[JUMBA %s] GRID PERNA 3 ATIVADA | Total Lotes=%d | Novo PM=%.0f | Novo TP=%.0f",
                                 m_slots[k].name, m_slots[k].lots, m_slots[k].avg_price, m_slots[k].curr_tp);
                    }
                 }
              }

            // Atualiza Breakeven e Trailing Stop
            double fav = (d == 1) ? (last_px - m_slots[k].avg_price) : (m_slots[k].avg_price - last_px);
            if(fav > m_slots[k].max_fav_pts)
               m_slots[k].max_fav_pts = fav;

            if(m_slots[k].be_trig > 0.0 && !m_slots[k].be_active && m_slots[k].max_fav_pts >= m_slots[k].be_trig)
              {
               if(d == 1)
                  m_slots[k].curr_sl = MathMax(m_slots[k].curr_sl, m_slots[k].avg_price + m_slots[k].be_lock);
               else
                  m_slots[k].curr_sl = MathMin(m_slots[k].curr_sl, m_slots[k].avg_price - m_slots[k].be_lock);
               m_slots[k].be_active = true;
              }

            if(m_slots[k].tr_trig > 0.0 && m_slots[k].max_fav_pts >= m_slots[k].tr_trig)
              {
               if(d == 1)
                  m_slots[k].curr_sl = MathMax(m_slots[k].curr_sl, m_slots[k].avg_price + m_slots[k].max_fav_pts - m_slots[k].tr_dist);
               else
                  m_slots[k].curr_sl = MathMin(m_slots[k].curr_sl, m_slots[k].avg_price - m_slots[k].max_fav_pts + m_slots[k].tr_dist);
              }
           }
        }

      SyncRealPositionsWithVirtualSlots();
     }

   //+------------------------------------------------------------------+
   //| Avaliação de Fechamento de Barra M5 (Sinais Market/Limit/Stop)   |
   //+------------------------------------------------------------------+
   void              OnNewM5Bar(datetime new_bar_time, string today_str)
     {
      MqlRates rates[];
      int copied = CopyRates(_Symbol, PERIOD_M5, 1, 110, rates);
      if(copied < 60 || ArraySize(m_levels_all) == 0)
         return;

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

      // 1. Atualiza contador de barras das posições abertas, Time Stop e Piramidação no Fechamento (EST-12)
      for(int k=1; k<=16; k++)
        {
         m_slots[k].pend_dir = 0; // Limpa ordens pendentes expiradas da barra anterior
         if(m_slots[k].dir != 0)
           {
            m_slots[k].bars_held += 1;

            // EST-12: Piramidação no Fechamento se lucro no fechamento >= +110 pts
            if(k == 12 && m_slots[k].leg_stage == 1)
              {
               double fav_close = (m_slots[k].dir == 1) ? (b1.close - m_slots[k].p1_entry) : (m_slots[k].p1_entry - b1.close);
               if(fav_close >= 110.0)
                 {
                  m_slots[k].avg_price = 0.5 * (m_slots[k].p1_entry + b1.close);
                  m_slots[k].lots = 2;
                  m_slots[k].leg_stage = 2;
                  m_slots[k].curr_sl = (m_slots[k].dir == 1) ? (m_slots[k].avg_price + 20.0) : (m_slots[k].avg_price - 20.0);
                  PrintFormat("[JUMBA %s] PIRAMIDACAO +1 LOTE NO LUCRO ATIVADA @ %.0f | Novo Stop Protegido=%.0f",
                              m_slots[k].name, b1.close, m_slots[k].curr_sl);
                 }
              }

            // Time Stop (exceto EOD 15 e 16 que seguram até 17h15)
            if(k <= 14 && m_slots[k].bars_held >= m_slots[k].max_hold_bars)
               CloseVirtualSlot(k, b1.close, "TIME_STOP");
           }
        }

      // Se estamos na mesma sessão, avalia sinais para as estratégias que estão FLAT
      if(b1_date != today_str)
         return;

      double d_l, lvl_s, d_h, lvl_r;
      FindNearestLevel(m_levels_all, b1.low,  d_l, lvl_s);
      FindNearestLevel(m_levels_all, b1.high, d_h, lvl_r);
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
         double slp_m  = (sc_id == 1) ? 9.0 : 7.0;
         double l_off  = (sc_id == 1) ? 0.0 : 10.0;

         // Perna Market (Rejeição fechada na barra b1)
         if(WindowOk(b1_tmin, wm_rej))
           {
            if(d_l <= 65.0 && (b1.close - lvl_s >= -30.0) && (b1.close - lvl_s <= 80.0) && b1.close <= (m_n50_l_1 + bw50 * 0.22) && m_rsi7_1 <= 35.0)
              {
               OpenVirtualSingle(sc_id, 1, b1.close, new_bar_time, 400.0, 220.0, 140.0, 20.0, 250.0, 100.0, 16);
               continue;
              }
            else if(d_h <= 65.0 && (lvl_r - b1.close >= -30.0) && (lvl_r - b1.close <= 80.0) && b1.close >= (m_n50_u_1 - bw50 * 0.22) && m_rsi7_1 >= 65.0)
              {
               OpenVirtualSingle(sc_id, -1, b1.close, new_bar_time, 400.0, 220.0, 140.0, 20.0, 250.0, 100.0, 16);
               continue;
              }
           }
         // Perna Limit (Armada para a nova barra se b1 tocou Wall em tendência forte)
         if(WindowOk(new_tmin, wm_lim))
           {
            if(m_n50_s_1 >= slp_m && d_l <= 45.0 && b1.close > lvl_s + l_off)
               ArmPendingOrder(sc_id, 1, 1, lvl_s + l_off, new_bar_time, 400.0, 220.0, 140.0, 20.0, 250.0, 100.0);
            else if(m_n50_s_1 <= -slp_m && d_h <= 45.0 && b1.close < lvl_r - l_off)
               ArmPendingOrder(sc_id, -1, 1, lvl_r - l_off, new_bar_time, 400.0, 220.0, 140.0, 20.0, 250.0, 100.0);
           }
        }

      // --- EST-03: Scalper Cambial Confluência WIN+WDO na Wall ---
      if(m_slots[3].enabled && m_slots[3].dir == 0 && WindowOk(b1_tmin, "FULL_09_17"))
        {
         if(d_l <= 65.0 && (b1.close - lvl_s >= -35.0) && (b1.close - lvl_s <= 80.0) && b1.close <= (m_n50_l_1 + bw50 * 0.22) && m_rsi7_1 <= 36.0)
           {
            if(m_wdo_ret3_1 <= 3.0 || m_wdo_z_1 <= -0.35)
               OpenVirtualSingle(3, 1, b1.close, new_bar_time, 650.0, 260.0, 160.0, 20.0, 350.0, 120.0, 16);
           }
         else if(d_h <= 65.0 && (lvl_r - b1.close >= -35.0) && (lvl_r - b1.close <= 80.0) && b1.close >= (m_n50_u_1 - bw50 * 0.22) && m_rsi7_1 >= 64.0)
           {
            if(m_wdo_ret3_1 >= -3.0 || m_wdo_z_1 >= 0.35)
               OpenVirtualSingle(3, -1, b1.close, new_bar_time, 650.0, 260.0, 160.0, 20.0, 350.0, 120.0, 16);
           }
        }

      // --- EST-04: Pullback Limit Reteste de Wall Rompida c/ GammaFlip ---
      if(m_slots[4].enabled && m_slots[4].dir == 0 && WindowOk(new_tmin, "FULL_09_17"))
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if(b1.open <= lvl + 5.0 && b1.close > lvl + 15.0 && (b1.close - lvl) <= 95.0 && body1 >= 45.0 && m_n50_s_1 >= 6.0)
              {
               if((m_gamma_flip <= 0.0 || b1.close >= m_gamma_flip) && b1.close < (m_n50_u_1 - bw50 * 0.15))
                 {
                  ArmPendingOrder(4, 1, 1, lvl, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0);
                  break;
                 }
              }
            if(b1.open >= lvl - 5.0 && b1.close < lvl - 15.0 && (lvl - b1.close) <= 95.0 && (-body1) >= 45.0 && m_n50_s_1 <= -6.0)
              {
               if((m_gamma_flip <= 0.0 || b1.close <= m_gamma_flip) && b1.close > (m_n50_l_1 + bw50 * 0.15))
                 {
                  ArmPendingOrder(4, -1, 1, lvl, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0);
                  break;
                 }
              }
           }
        }

      // --- EST-05: Pullback Cluster NWE Center + Wall + Reteste (Sem Almoço) ---
      if(m_slots[5].enabled && m_slots[5].dir == 0 && WindowOk(b1_tmin, "NO_LUNCH"))
        {
         bool entered5 = false;
         if(m_n30_s_1 >= 4.5 && d_l <= 45.0 && MathAbs(lvl_s - m_n30_c_1) <= 90.0 && b1.close > lvl_s && b1.close > b1.open && body1 >= 25.0)
           {
            OpenVirtualSingle(5, 1, b1.close, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
            entered5 = true;
           }
         else if(m_n30_s_1 <= -4.5 && d_h <= 45.0 && MathAbs(lvl_r - m_n30_c_1) <= 90.0 && b1.close < lvl_r && b1.close < b1.open && (-body1) >= 25.0)
           {
            OpenVirtualSingle(5, -1, b1.close, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16);
            entered5 = true;
           }
         if(!entered5 && WindowOk(new_tmin, "NO_LUNCH"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 5.0 && b1.close > lvl + 15.0 && (b1.close - lvl) <= 95.0 && body1 >= 45.0 && m_n50_s_1 >= 6.0 && b1.close < (m_n50_u_1 - bw50 * 0.15))
                 {
                  ArmPendingOrder(5, 1, 1, lvl, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0);
                  break;
                 }
               if(b1.open >= lvl - 5.0 && b1.close < lvl - 15.0 && (lvl - b1.close) <= 95.0 && (-body1) >= 45.0 && m_n50_s_1 <= -6.0 && b1.close > (m_n50_l_1 + bw50 * 0.15))
                 {
                  ArmPendingOrder(5, -1, 1, lvl, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0);
                  break;
                 }
              }
           }
        }

      // --- EST-06: Pullback Limit Ordem Limit na Wall c/ Slope NWE (09h-16h15) ---
      if(m_slots[6].enabled && m_slots[6].dir == 0 && WindowOk(new_tmin, "CORE_09_1615"))
        {
         if(m_n50_s_1 >= 9.0 && d_l <= 45.0 && b1.close > lvl_s)
            ArmPendingOrder(6, 1, 1, lvl_s, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0);
         else if(m_n50_s_1 <= -9.0 && d_h <= 45.0 && b1.close < lvl_r)
            ArmPendingOrder(6, -1, 1, lvl_r, new_bar_time, 500.0, 240.0, 150.0, 20.0, 300.0, 110.0);
        }

      // --- EST-07 & EST-08: Breakout Mkt Momentum Wall c/ Espaço NWE ---
      for(int bo_id=7; bo_id<=8; bo_id++)
        {
         if(!m_slots[bo_id].enabled || m_slots[bo_id].dir != 0)
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
               if(b1.open <= lvl + 10.0 && b1.close > lvl + 12.0 && (b1.close - lvl) <= 95.0 && body1 >= min_bd && m_n50_s_1 >= 4.0)
                 {
                  if(b1.close < (m_n50_u_1 - bw50 * 0.15) && m_rsi7_1 < 74.0)
                    {
                     OpenVirtualSingle(bo_id, 1, b1.close, new_bar_time, tp_b, sl_b, be_b, 20.0, tr_t, tr_d, 16);
                     break;
                    }
                 }
               if(b1.open >= lvl - 10.0 && b1.close < lvl - 12.0 && (lvl - b1.close) <= 95.0 && (-body1) >= min_bd && m_n50_s_1 <= -4.0)
                 {
                  if(b1.close > (m_n50_l_1 + bw50 * 0.15) && m_rsi7_1 > 26.0)
                    {
                     OpenVirtualSingle(bo_id, -1, b1.close, new_bar_time, tp_b, sl_b, be_b, 20.0, tr_t, tr_d, 16);
                     break;
                    }
                 }
              }
           }
        }

      // --- EST-09: Breakout Stop Aceleração Buy/Sell Stop na Wall (NY) ---
      if(m_slots[9].enabled && m_slots[9].dir == 0 && WindowOk(new_tmin, "NY_1000_1630"))
        {
         for(int i=0; i<ArraySize(m_levels_all); i++)
           {
            double lvl = m_levels_all[i];
            if((lvl - b1.close > 0.0) && (lvl - b1.close <= 55.0) && m_n30_s_1 >= 5.0 && b1.close > b1.open && lvl < (m_n30_u_1 - bw30 * 0.20))
              {
               ArmPendingOrder(9, 1, 2, lvl + 10.0, new_bar_time, 650.0, 260.0, 160.0, 20.0, 350.0, 120.0);
               break;
              }
            if((b1.close - lvl > 0.0) && (b1.close - lvl <= 55.0) && m_n30_s_1 <= -5.0 && b1.close < b1.open && lvl > (m_n30_l_1 + bw30 * 0.20))
              {
               ArmPendingOrder(9, -1, 2, lvl - 10.0, new_bar_time, 650.0, 260.0, 160.0, 20.0, 350.0, 120.0);
               break;
              }
           }
        }

      // --- EST-10: Breakout Stop Wick Pavio na Wall (Sem Almoço) ---
      if(m_slots[10].enabled && m_slots[10].dir == 0 && WindowOk(new_tmin, "NO_LUNCH") && rng1 <= 260.0)
        {
         double d_lc, lvl_sc;
         FindNearestLevel(m_levels_all, b1.close, d_lc, lvl_sc);
         if((d_l <= 55.0 || d_lc <= 55.0) && ((b1.close - b1.low) / rng1 >= 0.40) && m_rsi7_1 <= 42.0)
            ArmPendingOrder(10, 1, 2, b1.high + 5.0, new_bar_time, 650.0, 260.0, 160.0, 20.0, 350.0, 120.0);
         else if((d_h <= 55.0 || d_lc <= 55.0) && ((b1.high - b1.close) / rng1 >= 0.40) && m_rsi7_1 >= 58.0)
            ArmPendingOrder(10, -1, 2, b1.low - 5.0, new_bar_time, 650.0, 260.0, 160.0, 20.0, 350.0, 120.0);
        }

      // --- EST-11: Grid Pullback Tendência 1+2 Lotes a Favor do NWE (Sem Almoço) ---
      if(m_slots[11].enabled && m_slots[11].dir == 0 && WindowOk(b1_tmin, "NO_LUNCH"))
        {
         if(m_n50_s_1 >= 3.0 && d_l <= 55.0 && (b1.close - lvl_s >= -30.0) && (b1.close - lvl_s <= 80.0) && b1.close < (m_n50_u_1 - bw50 * 0.15) && m_rsi7_1 <= 48.0)
            OpenVirtualGrid(11, 1, b1.close, new_bar_time, 450.0, 900.0, 1, 2, 0, 280.0, 650.0, 150.0);
         else if(m_n50_s_1 <= -3.0 && d_h <= 55.0 && (lvl_r - b1.close >= -30.0) && (lvl_r - b1.close <= 80.0) && b1.close > (m_n50_l_1 + bw50 * 0.15) && m_rsi7_1 >= 52.0)
            OpenVirtualGrid(11, -1, b1.close, new_bar_time, 450.0, 900.0, 1, 2, 0, 280.0, 650.0, 150.0);
        }

      // --- EST-12: Piramidação no Lucro 1+1 Lote Anti-Martingale (NY 10h-16h30) ---
      if(m_slots[12].enabled && m_slots[12].dir == 0 && WindowOk(b1_tmin, "NY_1000_1630"))
        {
         if(d_l <= 65.0 && (b1.close - lvl_s >= -35.0) && (b1.close - lvl_s <= 80.0) && b1.close <= (m_n50_l_1 + bw50 * 0.22) && m_rsi7_1 <= 36.0)
            OpenVirtualSingle(12, 1, b1.close, new_bar_time, 450.0, 220.0, 0.0, 0.0, 0.0, 0.0, 18);
         else if(d_h <= 65.0 && (lvl_r - b1.close >= -35.0) && (lvl_r - b1.close <= 80.0) && b1.close >= (m_n50_u_1 - bw50 * 0.22) && m_rsi7_1 >= 64.0)
            OpenVirtualSingle(12, -1, b1.close, new_bar_time, 450.0, 220.0, 0.0, 0.0, 0.0, 0.0, 18);
        }

      // --- EST-13: Smart Grid RSI+BE 1+2 Lotes Curto c/ Breakeven (Sem Almoço) ---
      if(m_slots[13].enabled && m_slots[13].dir == 0 && WindowOk(b1_tmin, "NO_LUNCH"))
        {
         if(d_l <= 65.0 && (b1.close - lvl_s >= -35.0) && (b1.close - lvl_s <= 80.0) && b1.close <= (m_n50_l_1 + bw50 * 0.25) && m_rsi7_1 <= 38.0)
            OpenVirtualGrid(13, 1, b1.close, new_bar_time, 380.0, 760.0, 1, 2, 0, 250.0, 620.0, 140.0);
         else if(d_h <= 65.0 && (lvl_r - b1.close >= -35.0) && (lvl_r - b1.close <= 80.0) && b1.close >= (m_n50_u_1 - bw50 * 0.25) && m_rsi7_1 >= 62.0)
            OpenVirtualGrid(13, -1, b1.close, new_bar_time, 380.0, 760.0, 1, 2, 0, 250.0, 620.0, 140.0);
        }

      // --- EST-14: Grid Institucional Wall->MidWall->Wall (1+2+3 Lotes) ---
      if(m_slots[14].enabled && m_slots[14].dir == 0 && b1_tmin >= 550 && b1_tmin <= 960 && ArraySize(m_levels_walls) > 0)
        {
         double dw_l, w_s, dw_h, w_r;
         FindNearestLevel(m_levels_walls, b1.low,  dw_l, w_s);
         FindNearestLevel(m_levels_walls, b1.high, dw_h, w_r);
         if(dw_l <= 60.0 && b1.close > w_s && (b1.close - w_s) <= 80.0 && b1.close <= (m_n50_l_1 + bw50 * 0.25))
            OpenVirtualGrid(14, 1, b1.close, new_bar_time, 507.0, 1014.0, 1, 2, 3, 320.0, 800.0, 0.0);
         else if(dw_h <= 60.0 && b1.close < w_r && (w_r - b1.close) <= 80.0 && b1.close >= (m_n50_u_1 - bw50 * 0.25))
            OpenVirtualGrid(14, -1, b1.close, new_bar_time, 507.0, 1014.0, 1, 2, 3, 320.0, 800.0, 0.0);
        }

      // --- EST-15: Posicional EOD Breakout Matinal (09h05-11h00 -> 17h15) ---
      if(m_slots[15].enabled && m_slots[15].dir == 0 && m_slots[15].last_trade_date != b1_date && b1_tmin >= 545 && b1_tmin <= 660)
        {
         for(int i=0; i<ArraySize(m_levels_walls); i++)
           {
            double w = m_levels_walls[i];
            if(b1.open <= w && b1.close > w + 15.0 && (b1.close - w) <= 120.0 && m_n50_s_1 > 5.0)
              {
               OpenVirtualSingle(15, 1, b1.close, new_bar_time, 1500.0, 450.0, 350.0, 20.0, 0.0, 0.0, 120);
               m_slots[15].last_trade_date = b1_date;
               break;
              }
            if(b1.open >= w && b1.close < w - 15.0 && (w - b1.close) <= 120.0 && m_n50_s_1 < -5.0)
              {
               OpenVirtualSingle(15, -1, b1.close, new_bar_time, 1500.0, 450.0, 350.0, 20.0, 0.0, 0.0, 120);
               m_slots[15].last_trade_date = b1_date;
               break;
              }
           }
        }

      // --- EST-16: Posicional EOD Extreme Fade Matinal (09h05-11h00 -> 17h15) ---
      if(m_slots[16].enabled && m_slots[16].dir == 0 && m_slots[16].last_trade_date != b1_date && b1_tmin >= 545 && b1_tmin <= 660 && ArraySize(m_levels_walls) > 0)
        {
         double dw_l, w_s, dw_h, w_r;
         FindNearestLevel(m_levels_walls, b1.low,  dw_l, w_s);
         FindNearestLevel(m_levels_walls, b1.high, dw_h, w_r);
         if(b1.low <= m_day_low_morning + 10.0 && dw_l <= 50.0 && b1.close <= m_n50_l_1 && b1.close > b1.open)
           {
            OpenVirtualSingle(16, 1, b1.close, new_bar_time, 2500.0, 600.0, 0.0, 0.0, 0.0, 0.0, 120);
            m_slots[16].last_trade_date = b1_date;
           }
         else if(b1.high >= m_day_high_morning - 10.0 && dw_h <= 50.0 && b1.close >= m_n50_u_1 && b1.close < b1.open)
           {
            OpenVirtualSingle(16, -1, b1.close, new_bar_time, 2500.0, 600.0, 0.0, 0.0, 0.0, 0.0, 120);
            m_slots[16].last_trade_date = b1_date;
           }
        }

      if(!MQLInfoInteger(MQL_OPTIMIZATION))
         RenderHudComment();
     }

   void              ArmPendingOrder(int k, int dir, int ptype, double price, datetime bar_t,
                                     double tp_pts, double sl_pts, double be_trig, double be_lock,
                                     double tr_trig, double tr_dist)
     {
      m_slots[k].pend_dir = dir;
      m_slots[k].pend_type = ptype; // 1=Limit, 2=Stop
      m_slots[k].pend_price = price;
      m_slots[k].pend_bar_time = bar_t;
      m_slots[k].curr_tp = tp_pts;
      m_slots[k].curr_sl = sl_pts;
      m_slots[k].be_trig = be_trig;
      m_slots[k].be_lock = be_lock;
      m_slots[k].tr_trig = tr_trig;
      m_slots[k].tr_dist = tr_dist;
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
"""

core_path = os.path.join(MT5_INC_DIR, "Jumba_GEX_NWE_Core.mqh")
with open(core_path, "w", encoding="utf-8-sig") as f:
    f.write(core_mqh)

# 3. Write Jumba_GEX_NWE_Portfolio_Master.mq5
master_mq5 = r"""//+------------------------------------------------------------------+
//|                               Jumba_GEX_NWE_Portfolio_Master.mq5 |
//|     EA Mestre Unificado de Portfólio GEX MagicWalls + NWE (WIN)  |
//|     Inclui Presets PORT-01, PORT-03, LEVE-01, LEVE-03 e Custom   |
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property version   "1.00"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input group "=== 1. SELECAO DO PORTFOLIO & EXECUCAO ==="
input ENUM_PORTFOLIO_PRESET InpPreset         = PRESET_PORT_01_COMPLETO; // Preset de Portfólio (8 Estratégias Corr < 0.40)
input ENUM_EXECUTION_MODE   InpExecMode       = EXEC_NETTING_VIRTUAL_SYNC; // Modo de Execução (Netting B3 ou Hedging)
input double                InpLotMultiplier  = 1.0;    // Multiplicador de Lotes (1.0 = Lote Base do Backtest)
input double                InpMaxDailyLoss   = 2500.0; // Trava de Perda Máxima Diária do Portfólio (R$)
input ulong                 InpBaseMagic      = 88000;  // Magic Number Base
input bool                  InpDrawLevels     = true;   // Desenhar MagicWalls no Gráfico
input string                InpWdoSymbol      = "WDO$N"; // Símbolo do Dólar (p/ EST-03)

input group "=== 2. CHAVES INDIVIDUAIS (USADAS NO MODO PRESET_CUSTOM_MANUAL) ==="
input bool Enable_EST01_Scalper_NY            = false;
input bool Enable_EST02_Scalper_Full          = false;
input bool Enable_EST03_Scalper_WDO           = false;
input bool Enable_EST04_Pullback_Retest       = true;
input bool Enable_EST05_Pullback_Cluster      = false;
input bool Enable_EST06_Pullback_LimitSlope   = false;
input bool Enable_EST07_Breakout_NY           = true;
input bool Enable_EST08_Breakout_Core         = false;
input bool Enable_EST09_Breakout_StopWall     = true;
input bool Enable_EST10_Breakout_StopWick     = true;
input bool Enable_EST11_Grid_TrendPullback    = true;
input bool Enable_EST12_Pyramid_Profit11      = false;
input bool Enable_EST13_SmartGrid_RSI         = true;
input bool Enable_EST14_Grid_Institucional    = true;
input bool Enable_EST15_EOD_Breakout          = true;
input bool Enable_EST16_EOD_ExtremeFade       = false;

CJumbaGexNweEngine g_engine;

int OnInit()
  {
   g_engine.Init(InpBaseMagic, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      InpPreset, 0,
      Enable_EST01_Scalper_NY, Enable_EST02_Scalper_Full, Enable_EST03_Scalper_WDO, Enable_EST04_Pullback_Retest,
      Enable_EST05_Pullback_Cluster, Enable_EST06_Pullback_LimitSlope, Enable_EST07_Breakout_NY, Enable_EST08_Breakout_Core,
      Enable_EST09_Breakout_StopWall, Enable_EST10_Breakout_StopWick, Enable_EST11_Grid_TrendPullback, Enable_EST12_Pyramid_Profit11,
      Enable_EST13_SmartGrid_RSI, Enable_EST14_Grid_Institucional, Enable_EST15_EOD_Breakout, Enable_EST16_EOD_ExtremeFade
   );
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   Comment("");
  }

void OnTick()
  {
   g_engine.OnTickProcess();
  }
"""

master_path = os.path.join(MT5_EXP_DIR, "Jumba_GEX_NWE_Portfolio_Master.mq5")
with open(master_path, "w", encoding="utf-8-sig") as f:
    f.write(master_mq5)

# 4. Generate all 16 Individual Strategy .mq5 files
indiv_specs = [
    (1,  "Jumba_EST01_Scalper_Hibrido_NY",       88001, "EST-01 [Scalper Limit+Mkt] Hibrido NY (10h-16h30)"),
    (2,  "Jumba_EST02_Scalper_Hibrido_DiaTodo",  88002, "EST-02 [Scalper Limit+Mkt] Dia Todo (09h-17h)"),
    (3,  "Jumba_EST03_Scalper_Cambial_WDO",      88003, "EST-03 [Scalper Cambial] Confluencia WIN+WDO"),
    (4,  "Jumba_EST04_Pullback_Reteste_Wall",    88004, "EST-04 [Pullback Limit] Reteste de Wall Rompida"),
    (5,  "Jumba_EST05_Pullback_Cluster_NWE",     88005, "EST-05 [Pullback Cluster] NWE Center + Wall"),
    (6,  "Jumba_EST06_Pullback_Limit_Slope",     88006, "EST-06 [Pullback Limit] Ordem Limit na Wall c/ Slope"),
    (7,  "Jumba_EST07_Breakout_Momentum_NY",     88007, "EST-07 [Breakout Mkt] Momentum Wall NY"),
    (8,  "Jumba_EST08_Breakout_Rapido_Core",     88008, "EST-08 [Breakout Mkt] Momentum Rapido Core"),
    (9,  "Jumba_EST09_Breakout_Stop_Wall",       88009, "EST-09 [Breakout Stop] Aceleracao Buy/Sell Stop Wall"),
    (10, "Jumba_EST10_Breakout_Stop_Wick",       88010, "EST-10 [Breakout Stop] Stop Wick Pavio na Wall"),
    (11, "Jumba_EST11_Grid_Pullback_Tendencia",  88011, "EST-11 [Grid Pullback Tendencia] 1+2 Lotes NWE"),
    (12, "Jumba_EST12_Piramidacao_Lucro_11L",    88012, "EST-12 [Piramidacao no Lucro] 1+1 Lote Anti-Martingale"),
    (13, "Jumba_EST13_SmartGrid_RSI_BE",         88013, "EST-13 [Smart Grid RSI+BE] 1+2 Lotes Curto"),
    (14, "Jumba_EST14_Grid_Institucional_123L",  88014, "EST-14 [Grid Institucional] Wall->MidWall->Wall 1+2+3L"),
    (15, "Jumba_EST15_Posicional_EOD_Breakout",  88015, "EST-15 [Posicional EOD] Breakout Matinal -> 17h15"),
    (16, "Jumba_EST16_Posicional_EOD_Fade",      88016, "EST-16 [Posicional EOD] Extreme Fade Matinal -> 17h15"),
]

for sid, fname, magic, desc in indiv_specs:
    indiv_code = f"""//+------------------------------------------------------------------+
//| {fname}.mq5
//| {desc}
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property description "{desc}"
#property version   "1.00"
#property strict

#include <Jumba_GEX_NWE_Core.mqh>

input ENUM_EXECUTION_MODE InpExecMode      = EXEC_HEDGING_DIRECT_MAGIC; // Modo de Execução
input double              InpLotMultiplier = 1.0;    // Multiplicador de Lotes
input double              InpMaxDailyLoss  = 1000.0; // Perda Máxima Diária Individual (R$)
input ulong               InpMagicNumber   = {magic}; // Magic Number Base
input bool                InpDrawLevels    = true;   // Desenhar MagicWalls no Gráfico
input string              InpWdoSymbol     = "WDO$N"; // Símbolo do Dólar (se usado)

CJumbaGexNweEngine g_engine;

int OnInit()
  {{
   g_engine.Init(InpMagicNumber - {sid}, InpExecMode, InpLotMultiplier, InpMaxDailyLoss, InpDrawLevels, InpWdoSymbol);
   g_engine.ConfigurePreset(
      PRESET_SINGLE_ROBOT, {sid},
      false,false,false,false,false,false,false,false,
      false,false,false,false,false,false,false,false
   );
   return(INIT_SUCCEEDED);
  }}

void OnDeinit(const int reason)
  {{
   Comment("");
  }}

void OnTick()
  {{
   g_engine.OnTickProcess();
  }}
"""
    with open(os.path.join(MT5_EXP_DIR, f"{fname}.mq5"), "w", encoding="utf-8-sig") as f:
        f.write(indiv_code)

# 5. Copy to MT5 Data Folder and Compile with metaeditor64.exe
TERM_DATA = r"C:\Users\ryzen\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\MQL5"
TERM_INC  = os.path.join(TERM_DATA, "Include")
TERM_EXP  = os.path.join(TERM_DATA, "Experts", "Jumba_GEX_NWE")
os.makedirs(TERM_INC, exist_ok=True)
os.makedirs(TERM_EXP, exist_ok=True)

shutil.copy2(core_path, os.path.join(TERM_INC, "Jumba_GEX_NWE_Core.mqh"))

METAEDITOR = r"C:\Program Files\MetaTrader 5 EXNESS\metaeditor64.exe"
mq5_files = sorted([f for f in os.listdir(MT5_EXP_DIR) if f.endswith(".mq5")])

compiled_ok = 0
for mq5 in mq5_files:
    src = os.path.join(MT5_EXP_DIR, mq5)
    dst = os.path.join(TERM_EXP, mq5)
    shutil.copy2(src, dst)
    log_file = dst.replace(".mq5", ".log")
    if os.path.exists(log_file):
        os.remove(log_file)
    cmd = [METAEDITOR, f'/compile:{dst}', f'/inc:{TERM_DATA}', f'/log:{log_file}']
    subprocess.run(cmd, check=False)
    ex5_dst = dst.replace(".mq5", ".ex5")
    ex5_src = src.replace(".mq5", ".ex5")
    if os.path.exists(ex5_dst):
        shutil.copy2(ex5_dst, ex5_src)
        compiled_ok += 1
        print(f"[COMPILED OK] {os.path.basename(ex5_src)} ({os.path.getsize(ex5_src):,} bytes)")
    else:
        print(f"[COMPILE FAILED] {mq5}")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-16", errors="ignore") as lf:
                print(lf.read())

print(f"\nTotal .ex5 compiled successfully: {compiled_ok}/{len(mq5_files)}")
