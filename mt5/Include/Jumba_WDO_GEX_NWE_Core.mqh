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
   bool              be_active;           // Break-Even já ativado?
   bool              opened_intrabar;     // Abriu via ordem pendente intrabar na barra atual?
   int               bars_held;           // Barras M5 completas em posição
   datetime          entry_bar_time;      // Timestamp da barra M5 da entrada
   datetime          last_entry_bar_time; // Evita reentrada na mesma barra M5
   string            last_trade_date;     // Usado nas EOD 15 e 16 (1 trade/dia)

   // Ordem Pendente Virtual / Nativa (1 barra M5 de validade)
   int               pend_dir;            // 0=None, 1=Buy, -1=Sell
   int               pend_type;           // 1=Limit, 2=Stop
   double            pend_price;
   double            pend_tp_pts;
   double            pend_sl_pts;
   datetime          pend_bar_time;

   // Parâmetros de Gerenciamento Dinâmico do Trade Ativo
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
      m_lot_mult = MathMax(1.0, MathRound(lot_mult));
      m_max_daily_loss_brl = max_daily_loss_brl;
      m_draw_levels = draw_levels;
      m_show_hud = show_hud;
      m_exec_mode = exec_mode;

      long acc_margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(acc_margin_mode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         Print("[JUMBA WDO] Conta NETTING detectada na corretora. Alternando automaticamente para WDO_EXEC_NETTING_VIRTUAL_SYNC.");
         m_exec_mode = WDO_EXEC_NETTING_VIRTUAL_SYNC;
        }

      m_trade.SetExpertMagicNumber(m_base_magic);
      m_trade.SetDeviationInPoints(100);
      m_trade.SetTypeFillingBySymbol(_Symbol);

      string names[17] =
        {
         "",
         "WDO-01 Scalper Hibrido NY",
         "WDO-02 Scalper Hibrido CORE",
         "WDO-03 Arbitragem WIN+WDO Wall",
         "WDO-04 Limit Wall c/ GammaFlip",
         "WDO-05 Cluster NWE30+NWE50+Wall",
         "WDO-06 Limit Wall Rejeicao NWE50",
         "WDO-07 Absorcao Mkt Wall NY",
         "WDO-08 Absorcao Mkt Wall CORE",
         "WDO-09 Stop & Limit Wall NY",
         "WDO-10 Stop & Limit Main Walls",
         "WDO-11 Grid 1+2 Absorcao NWE",
         "WDO-12 Piramidacao 1+1 Lucro NY",
         "WDO-13 Smart Grid 1+2 GammaFlip",
         "WDO-14 Grid 1+2+3 Institucional",
         "WDO-15 Posicional EOD Matinal",
         "WDO-16 Posicional EOD Limit Wall"
        };

      bool en[17];
      en[0]=false;
      en[1]=e1;  en[2]=e2;  en[3]=e3;  en[4]=e4;
      en[5]=e5;  en[6]=e6;  en[7]=e7;  en[8]=e8;
      en[9]=e9;  en[10]=e10; en[11]=e11; en[12]=e12;
      en[13]=e13; en[14]=e14; en[15]=e15; en[16]=e16;

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

      SymbolSelect("WIN$N", true);
      SymbolSelect("WINZ26", true);

      if(!MQLInfoInteger(MQL_TESTER))
        {
         SymbolSelect("WDOX26", true);
         SymbolSelect("WDOZ26", true);
         SymbolSelect(_Symbol, true);
         m_last_m5_bar_time = iTime(_Symbol, PERIOD_M5, 0);
         datetime t_ref = TimeCurrent();
         if(t_ref <= 0)
            t_ref = TimeTradeServer();
         if(t_ref <= 0)
            t_ref = TimeLocal();
         LoadDailyGexWalls(DateStr(t_ref));
         RenderHudComment();
         ChartRedraw(0);
        }
     }

   void              Deinit()
     {
      if(m_draw_levels)
         ObjectsDeleteAll(0, "JUMBA_WDO_GEX_");
      if(m_show_hud)
         Comment("");
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
      m_slots[k].bars_held = 0;
      m_slots[k].entry_bar_time = 0;
      m_slots[k].pend_dir = 0;
      m_slots[k].pend_type = 0;
      m_slots[k].pend_price = 0.0;
      m_slots[k].pend_tp_pts = 0.0;
      m_slots[k].pend_sl_pts = 0.0;
      m_slots[k].pend_bar_time = 0;
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
               m_gex_source = "DAILY_CSV";
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
               m_gex_source = "HISTORY_CSV (" + best_date + ")";
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
               m_gex_source = "FIREBASE_CLOUD";
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
      if(ArraySize(m_levels_all) > 0)
         m_loaded_date = target_date;

      for(int k=1; k<=16; k++)
        {
         m_slots[k].closed_pnl_today_brl = 0.0;
         m_slots[k].trades_today = 0;
        }

      if(m_draw_levels && !MQLInfoInteger(MQL_OPTIMIZATION))
         DrawLevelsOnChart();

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
      for(int i=0; i<ArraySize(m_gex_raw); i++)
        {
         string obj_name = StringFormat("JUMBA_WDO_GEX_%s_%d", m_gex_raw[i].type, i);
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

   void              RenderHudComment()
     {
      if(!m_show_hud)
         return;
      string hud = "==========================================================\n";
      hud += StringFormat(" JUMBA QUANT WDO GEX + NWE | Data: %s | Fonte: %s\n", m_loaded_date, m_gex_source);
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
      for(int k=0; k<14; k++)
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

   void              OpenVirtualSingle(int k, int dir, double entry_p, datetime bar_t,
                                       double tp_pts, double sl_pts,
                                       double be_trig, double be_lock,
                                       double tr_trig, double tr_dist,
                                       int max_hold=16, bool is_intrabar=false,
                                       double pyr_trig=0.0, double pyr_lock=1.0)
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
      m_slots[k].pend_dir = 0;
      m_slots[k].real_synced = false;
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
      m_slots[k].curr_tp = (dir == 1) ? Round05(p05 + tp_avg) : Round05(p05 - tp_avg);
      m_slots[k].max_fav_pts = 0.0;
      m_slots[k].be_active = false;
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
      m_slots[k].init_tp_pts = tp_avg;
      m_slots[k].pend_dir = 0;
      m_slots[k].real_synced = false;
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

      ResetSlotPosition(k);
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
      if(m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            long slot_magic = m_base_magic + k;
            double target_signed = m_slots[k].dir * m_slots[k].lots * m_lot_mult;

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

            if(MathAbs(target_signed) < 0.01 && MathAbs(actual_signed) >= 0.01)
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               continue;
              }

            double sl_srv = (m_slots[k].dir == -1 && m_slots[k].curr_sl > 0.0) ? Round05(m_slots[k].curr_sl + 0.5) : m_slots[k].curr_sl;
            double tp_srv = (m_slots[k].dir == -1 && m_slots[k].curr_tp > 0.0) ? Round05(m_slots[k].curr_tp + 0.5) : m_slots[k].curr_tp;

            if((target_signed > 0.0 && actual_signed < -0.01) || (target_signed < 0.0 && actual_signed > 0.01))
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               actual_signed = 0.0;
              }

            double diff = target_signed - actual_signed;
            if(MathAbs(diff) >= 0.99)
              {
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
                     if(MathAbs(live_bid - m_slots[k].p1_entry) > 2.0)
                       {
                        PrintFormat("[JUMBA %s] Entrada cancelada por atraso/slippage (Sinal=%.1f vs Atual=%.1f)",
                                    m_slots[k].name, m_slots[k].p1_entry, live_bid);
                        ResetSlotPosition(k);
                        continue;
                       }
                     double fill_ref = (m_slots[k].dir == 1) ? Round05(live_ask) : Round05(live_bid);
                     m_slots[k].p1_entry = Round05(live_bid);
                     m_slots[k].avg_price = Round05(live_bid);
                     double sl_d = MathMax(11.0, m_slots[k].init_sl_pts);
                     double tp_d = MathMax(11.0, m_slots[k].init_tp_pts);
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

               m_trade.SetExpertMagicNumber(slot_magic);
               double vol = MathRound(MathAbs(diff));
               bool ok = false;
               if(diff > 0.0)
                  ok = m_trade.Buy(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
               else
                  ok = m_trade.Sell(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);

               if(ok)
                  m_slots[k].real_synced = true;
               else if(!MQLInfoInteger(MQL_TESTER) && !m_slots[k].real_synced)
                  ResetSlotPosition(k);
              }

            if(MathAbs(target_signed) >= 0.99)
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
         double target_net = 0.0;
         for(int k=1; k<=16; k++)
           {
            if(m_slots[k].enabled && m_slots[k].dir != 0)
               target_net += m_slots[k].dir * m_slots[k].lots * m_lot_mult;
           }

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
            double vol = MathRound(MathAbs(diff));
            if(diff > 0.0)
               m_trade.Buy(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
            else
               m_trade.Sell(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
           }
        }
     }

   void              OnTickProcess()
     {
      datetime now = TimeCurrent();
      string today_str = DateStr(now);
      int t_min = TimeMinutes(now);

      LoadDailyGexWalls(today_str);

      double last_px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(last_px <= 0.0)
         last_px = SymbolInfoDouble(_Symbol, SYMBOL_LAST);
      if(last_px <= 0.0)
         return;

      datetime curr_bar_time = iTime(_Symbol, PERIOD_M5, 0);

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
                                    m_slots[k].max_hold_bars, true, pt_save, pl_save);
                  m_slots[k].real_synced = true;
                  m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                  if(k == 15 || k == 16)
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
                                       m_slots[k].max_hold_bars, true, pt_save, pl_save);
                     m_slots[k].last_entry_bar_time = m_slots[k].pend_bar_time;
                     if(k == 15 || k == 16)
                        m_slots[k].last_trade_date = today_str;
                     CloseVirtualSlot(k, deal_px, rsn);
                    }
                 }
              }
            else if(m_slots[k].dir != 0 && m_slots[k].real_synced && MathAbs(actual_lots) < 0.01)
              {
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
         SyncRealPositionsWithVirtualSlots();
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
                                    m_slots[k].max_hold_bars, true, pt_save, pl_save);
                  m_slots[k].last_entry_bar_time = curr_bar_time;
                  if(k == 15 || k == 16)
                     m_slots[k].last_trade_date = today_str;
                 }
              }
           }

         if(m_slots[k].dir != 0)
           {
            int d = m_slots[k].dir;

            if(k == 11 || k == 13 || k == 14)
              {
               if(m_slots[k].leg_stage == 1 && m_slots[k].lot2 > 0)
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
                     m_slots[k].curr_tp = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].tp_avg_pts) : Round05(m_slots[k].avg_price - m_slots[k].tp_avg_pts);
                     m_slots[k].curr_sl = (d == 1) ? Round05(m_slots[k].avg_price - m_slots[k].max_sl_pts) : Round05(m_slots[k].avg_price + m_slots[k].max_sl_pts);
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
                  double cand_sl = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].be_lock) : Round05(m_slots[k].avg_price - m_slots[k].be_lock);
                  if((d == 1 && new_bar_open > cand_sl + 0.5) || (d == -1 && new_bar_open < cand_sl - 0.5))
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
                  double cand_sl = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].be_lock) : Round05(m_slots[k].avg_price - m_slots[k].be_lock);
                  if((d == 1 && new_bar_open > cand_sl + 0.5) || (d == -1 && new_bar_open < cand_sl - 0.5))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                     m_slots[k].be_active = true;
                    }
                 }

               if(m_slots[k].tr_trig > 0.0 && m_slots[k].max_fav_pts >= m_slots[k].tr_trig)
                 {
                  double cand_sl = (d == 1) ? Round05(m_slots[k].avg_price + m_slots[k].max_fav_pts - m_slots[k].tr_dist)
                                            : Round05(m_slots[k].avg_price - m_slots[k].max_fav_pts + m_slots[k].tr_dist);
                  if((d == 1 && new_bar_open > cand_sl + 0.5) || (d == -1 && new_bar_open < cand_sl - 0.5))
                    {
                     m_slots[k].curr_sl = (d == 1) ? MathMax(m_slots[k].curr_sl, cand_sl) : MathMin(m_slots[k].curr_sl, cand_sl);
                    }
                 }

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

               if(k <= 14 && m_slots[k].bars_held >= m_slots[k].max_hold_bars)
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

      // --- WDO-01: Scalper Híbrido NY (Market Absorption + Limit Wall c/ GammaFlip, 10h00-16h30) ---
      if(m_slots[1].enabled && m_slots[1].dir == 0)
        {
         bool ent1 = false;
         if(m_slots[1].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10))
                 {
                  OpenVirtualSingle(1, -1, new_bar_open, new_bar_time, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false);
                  m_slots[1].last_entry_bar_time = b1.time;
                  ent1 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10))
                 {
                  OpenVirtualSingle(1, 1, new_bar_open, new_bar_time, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false);
                  m_slots[1].last_entry_bar_time = b1.time;
                  ent1 = true;
                  break;
                 }
              }
           }
         if(!ent1 && WindowOk(new_tmin, "NY_1000_1630"))
           {
            if(pos50 >= 0.65 && d_h <= 3.5 && b1.close < lvl_r && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
               ArmPendingOrder(1, -1, 1, lvl_r, new_bar_time, new_bar_open, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16);
            else if(pos50 <= 0.35 && d_l <= 3.5 && b1.close > lvl_s && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
               ArmPendingOrder(1, 1, 1, lvl_s, new_bar_time, new_bar_open, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16);
           }
        }

      // --- WDO-02: Scalper Híbrido CORE (Market Absorption + Limit Wall c/ Offset 0.5 pt, 09h10-16h15) ---
      if(m_slots[2].enabled && m_slots[2].dir == 0)
        {
         bool ent2 = false;
         if(m_slots[2].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10) && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip - 2.0))
                 {
                  OpenVirtualSingle(2, -1, new_bar_open, new_bar_time, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false);
                  m_slots[2].last_entry_bar_time = b1.time;
                  ent2 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10) && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip + 2.0))
                 {
                  OpenVirtualSingle(2, 1, new_bar_open, new_bar_time, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false);
                  m_slots[2].last_entry_bar_time = b1.time;
                  ent2 = true;
                  break;
                 }
              }
           }
         if(!ent2 && WindowOk(new_tmin, "CORE_09_1615"))
           {
            if(pos50 >= 0.64 && d_h <= 3.5 && b1.close < (lvl_r - 0.5) && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
               ArmPendingOrder(2, -1, 1, lvl_r - 0.5, new_bar_time, new_bar_open, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16);
            else if(pos50 <= 0.36 && d_l <= 3.5 && b1.close > (lvl_s + 0.5) && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
               ArmPendingOrder(2, 1, 1, lvl_s + 0.5, new_bar_time, new_bar_open, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16);
           }
        }

      // --- WDO-03: Arbitragem Cross-Asset WIN$N + WDO$N na Wall ---
      if(m_slots[3].enabled && m_slots[3].dir == 0)
        {
         bool ent3 = false;
         if(m_slots[3].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 1.5 && (m_win_ret3_1 >= -8.0 || m_win_z_1 >= -1.2))
                 {
                  OpenVirtualSingle(3, -1, new_bar_open, new_bar_time, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16, false);
                  m_slots[3].last_entry_bar_time = b1.time;
                  ent3 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 1.5 && (m_win_ret3_1 <= 8.0 || m_win_z_1 <= 1.2))
                 {
                  OpenVirtualSingle(3, 1, new_bar_open, new_bar_time, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16, false);
                  m_slots[3].last_entry_bar_time = b1.time;
                  ent3 = true;
                  break;
                 }
              }
           }
         if(!ent3 && WindowOk(new_tmin, "FULL_09_17"))
           {
            if(pos50 >= 0.65 && (m_win_ret3_1 >= 8.0 || m_win_z_1 >= 1.2) && d_h <= 3.5 && b1.close < lvl_r)
               ArmPendingOrder(3, -1, 1, lvl_r, new_bar_time, new_bar_open, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16);
            else if(pos50 <= 0.35 && (m_win_ret3_1 <= -8.0 || m_win_z_1 <= -1.2) && d_l <= 3.5 && b1.close > lvl_s)
               ArmPendingOrder(3, 1, 1, lvl_s, new_bar_time, new_bar_open, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16);
           }
        }

      // --- WDO-04: Limit Reteste de Wall c/ Regime GammaFlip (09h05-17h00) ---
      if(m_slots[4].enabled && m_slots[4].dir == 0 && WindowOk(new_tmin, "FULL_09_17") && m_gamma_flip > 0.0)
        {
         if(b1.close > m_gamma_flip + 4.0 && pos50 >= 0.65 && d_h <= 3.5 && b1.close < lvl_r)
            ArmPendingOrder(4, -1, 1, lvl_r, new_bar_time, new_bar_open, 25.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18);
         else if(b1.close < m_gamma_flip - 4.0 && pos50 <= 0.35 && d_l <= 3.5 && b1.close > lvl_s)
            ArmPendingOrder(4, 1, 1, lvl_s, new_bar_time, new_bar_open, 25.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18);
        }

      // --- WDO-05: Cluster NWE30 + NWE50 + Wall (09h10-16h15) ---
      if(m_slots[5].enabled && m_slots[5].dir == 0)
        {
         bool ent5 = false;
         if(m_slots[5].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "CORE_09_1615"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n30_s_1 >= 0.15 && m_n50_s_1 >= 0.10 && b1.close < (m_n30_u_1 - bw30 * 0.10))
                 {
                  OpenVirtualSingle(5, -1, new_bar_open, new_bar_time, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 16, false);
                  m_slots[5].last_entry_bar_time = b1.time;
                  ent5 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n30_s_1 <= -0.15 && m_n50_s_1 <= -0.10 && b1.close > (m_n30_l_1 + bw30 * 0.10))
                 {
                  OpenVirtualSingle(5, 1, new_bar_open, new_bar_time, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 16, false);
                  m_slots[5].last_entry_bar_time = b1.time;
                  ent5 = true;
                  break;
                 }
              }
           }
         if(!ent5 && WindowOk(new_tmin, "CORE_09_1615"))
           {
            if(pos30 >= 0.65 && pos50 >= 0.62 && d_h <= 3.5 && b1.close < lvl_r && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
               ArmPendingOrder(5, -1, 1, lvl_r, new_bar_time, new_bar_open, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16);
            else if(pos30 <= 0.35 && pos50 <= 0.38 && d_l <= 3.5 && b1.close > lvl_s && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
               ArmPendingOrder(5, 1, 1, lvl_s, new_bar_time, new_bar_open, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16);
           }
        }

      // --- WDO-06: Limit Ordem na Wall c/ Rejeição + NWE50 (09h05-17h00) ---
      if(m_slots[6].enabled && m_slots[6].dir == 0 && WindowOk(new_tmin, "FULL_09_17"))
        {
         if(pos50 >= 0.62 && d_h <= 3.5 && b1.close < lvl_r && (b1.close < b1.open || (m_gamma_flip > 0.0 && b1.close > m_gamma_flip)))
            ArmPendingOrder(6, -1, 1, lvl_r, new_bar_time, new_bar_open, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16);
         else if(pos50 <= 0.38 && d_l <= 3.5 && b1.close > lvl_s && (b1.close > b1.open || (m_gamma_flip > 0.0 && b1.close < m_gamma_flip)))
            ArmPendingOrder(6, 1, 1, lvl_s, new_bar_time, new_bar_open, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16);
        }

      // --- WDO-07 & WDO-08: Absorção Institucional Market na Wall (NY & CORE) ---
      for(int bo_id=7; bo_id<=8; bo_id++)
        {
         if(!m_slots[bo_id].enabled || m_slots[bo_id].dir != 0 || m_slots[bo_id].last_entry_bar_time == b1.time)
            continue;
         string wm_bo = (bo_id == 7) ? "NY_1000_1630" : "CORE_09_1615";
         double tp_b  = (bo_id == 7) ? 19.0 : 18.0;
         if(WindowOk(b1_tmin, wm_bo))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10))
                 {
                  OpenVirtualSingle(bo_id, -1, new_bar_open, new_bar_time, tp_b, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false);
                  m_slots[bo_id].last_entry_bar_time = b1.time;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10))
                 {
                  OpenVirtualSingle(bo_id, 1, new_bar_open, new_bar_time, tp_b, 11.0, 6.5, 1.5, 11.0, 4.5, 15, false);
                  m_slots[bo_id].last_entry_bar_time = b1.time;
                  break;
                 }
              }
           }
        }

      // --- WDO-09: Stop & Limit Reversão na Wall (NY Session - Todos os Níveis) ---
      if(m_slots[9].enabled && m_slots[9].dir == 0 && WindowOk(new_tmin, "NY_1000_1630"))
        {
         if(pos30 <= 0.28 && d_l <= 4.0 && b1.close > b1.open && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip + 10.0))
            ArmPendingOrder(9, 1, 2, b1.high + 0.5, new_bar_time, new_bar_open, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16);
         else if(pos30 >= 0.72 && d_h <= 4.0 && b1.close < b1.open && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip - 10.0))
            ArmPendingOrder(9, -1, 2, b1.low - 0.5, new_bar_time, new_bar_open, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16);
         else if(pos50 <= 0.35 && d_l <= 4.0 && b1.close > lvl_s && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
            ArmPendingOrder(9, 1, 1, lvl_s, new_bar_time, new_bar_open, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16);
         else if(pos50 >= 0.65 && d_h <= 4.0 && b1.close < lvl_r && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
            ArmPendingOrder(9, -1, 1, lvl_r, new_bar_time, new_bar_open, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16);
        }

      // --- WDO-10: Stop & Limit SÓ NAS WALLS PRINCIPAIS + GammaFlip (CORE 09h10-16h15) ---
      if(m_slots[10].enabled && m_slots[10].dir == 0 && WindowOk(new_tmin, "CORE_09_1615") && ArraySize(m_levels_walls) > 0)
        {
         if(dw_h_main <= 6.0 && pos50 >= 0.65 && b1.close < w_r_main && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
            ArmPendingOrder(10, -1, 1, w_r_main, new_bar_time, new_bar_open, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18);
         else if(dw_l_main <= 6.0 && pos50 <= 0.35 && b1.close > w_s_main && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
            ArmPendingOrder(10, 1, 1, w_s_main, new_bar_time, new_bar_open, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18);
         else if(m_gamma_flip > 0.0 && b1.close > m_gamma_flip + 5.0 && pos50 >= 0.70 && d_h <= 3.5 && b1.close < lvl_r)
            ArmPendingOrder(10, -1, 1, lvl_r, new_bar_time, new_bar_open, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18);
         else if(m_gamma_flip > 0.0 && b1.close < m_gamma_flip - 5.0 && pos50 <= 0.30 && d_l <= 3.5 && b1.close > lvl_s)
            ArmPendingOrder(10, 1, 1, lvl_s, new_bar_time, new_bar_open, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18);
        }

      // --- WDO-11: Grid Pullback / Absorção 1+2 Lotes no NWE (Sem Almoço) ---
      if(m_slots[11].enabled && m_slots[11].dir == 0 && m_slots[11].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NO_LUNCH"))
        {
         if(pos50 <= 0.25 && d_l <= 4.0 && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip + 15.0))
           {
            OpenVirtualGrid(11, 1, new_bar_open, new_bar_time, 16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 24);
            m_slots[11].last_entry_bar_time = b1.time;
           }
         else if(pos50 >= 0.75 && d_h <= 4.0 && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip - 15.0))
           {
            OpenVirtualGrid(11, -1, new_bar_open, new_bar_time, 16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 24);
            m_slots[11].last_entry_bar_time = b1.time;
           }
        }

      // --- WDO-12: Piramidação no Lucro 1+1 Lote Anti-Martingale (NY 10h00-16h30) ---
      if(m_slots[12].enabled && m_slots[12].dir == 0)
        {
         bool ent12 = false;
         if(m_slots[12].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "NY_1000_1630"))
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && m_n50_s_1 >= 0.15 && b1.close < (m_n50_u_1 - bw50 * 0.10))
                 {
                  OpenVirtualSingle(12, -1, new_bar_open, new_bar_time, 24.0, 12.0, 7.0, 1.5, 13.5, 5.0, 16, false, 8.5, 2.5);
                  m_slots[12].last_entry_bar_time = b1.time;
                  ent12 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && m_n50_s_1 <= -0.15 && b1.close > (m_n50_l_1 + bw50 * 0.10))
                 {
                  OpenVirtualSingle(12, 1, new_bar_open, new_bar_time, 24.0, 12.0, 7.0, 1.5, 13.5, 5.0, 16, false, 8.5, 2.5);
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
               ArmPendingOrder(12, -1, 1, lvl_r, new_bar_time, new_bar_open, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16);
              }
            else if(b1.close < m_gamma_flip - 4.0 && pos50 <= 0.35 && d_l <= 3.5 && b1.close > lvl_s)
              {
               m_slots[12].pyr_trig = 8.5;
               m_slots[12].pyr_lock = 2.5;
               ArmPendingOrder(12, 1, 1, lvl_s, new_bar_time, new_bar_open, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16);
              }
           }
        }

      // --- WDO-13: Smart Grid 1+2 Lotes Equilíbrio GammaFlip & Walls (FULL 09h05-17h00) ---
      if(m_slots[13].enabled && m_slots[13].dir == 0 && m_slots[13].last_entry_bar_time != b1.time && WindowOk(b1_tmin, "FULL_09_17") && m_gamma_flip > 0.0)
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

      // --- WDO-14: Grid Institucional 3 Estágios (1+2+3 Lotes Wall->MidWall->Wall, 09h05-15h30) ---
      if(m_slots[14].enabled && m_slots[14].dir == 0 && m_slots[14].last_entry_bar_time != b1.time && b1_tmin >= 545 && b1_tmin <= 930 && m_gamma_flip > 0.0)
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

      // --- WDO-15: Posicional EOD Absorção Matinal na Wall (09h05-13h30 -> 17h15) ---
      if(m_slots[15].enabled && m_slots[15].dir == 0 && m_slots[15].last_trade_date != today_str)
        {
         bool ent15 = false;
         if(b1_tmin >= 545 && b1_tmin <= 780)
           {
            for(int i=0; i<ArraySize(m_levels_all); i++)
              {
               double lvl = m_levels_all[i];
               if(b1.open <= lvl + 0.5 && b1.close > lvl + 0.5 && (b1.close - lvl) <= 4.5 && body1 >= 2.0 && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
                 {
                  OpenVirtualSingle(15, -1, new_bar_open, new_bar_time, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, false);
                  m_slots[15].last_trade_date = b1_date;
                  m_slots[15].last_entry_bar_time = b1.time;
                  ent15 = true;
                  break;
                 }
               if(b1.open >= lvl - 0.5 && b1.close < lvl - 0.5 && (lvl - b1.close) <= 4.5 && (-body1) >= 2.0 && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
                 {
                  OpenVirtualSingle(15, 1, new_bar_open, new_bar_time, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, false);
                  m_slots[15].last_trade_date = b1_date;
                  m_slots[15].last_entry_bar_time = b1.time;
                  ent15 = true;
                  break;
                 }
              }
           }
         if(!ent15 && new_tmin >= 550 && new_tmin <= 810)
           {
            if(pos50 >= 0.65 && d_h <= 3.5 && b1.close < lvl_r && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
               ArmPendingOrder(15, -1, 1, lvl_r, new_bar_time, new_bar_open, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120);
            else if(pos50 <= 0.35 && d_l <= 3.5 && b1.close > lvl_s && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
               ArmPendingOrder(15, 1, 1, lvl_s, new_bar_time, new_bar_open, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120);
           }
        }

      // --- WDO-16: Posicional EOD Limit Equilíbrio Wall c/ GammaFlip (09h10-14h00 -> 17h15) ---
      if(m_slots[16].enabled && m_slots[16].dir == 0 && m_slots[16].last_trade_date != today_str && new_tmin >= 550 && new_tmin <= 840)
        {
         if(pos50 >= 0.68 && d_h <= 3.5 && b1.close < lvl_r && (m_gamma_flip <= 0.0 || b1.close > m_gamma_flip))
            ArmPendingOrder(16, -1, 1, lvl_r, new_bar_time, new_bar_open, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120);
         else if(pos50 <= 0.32 && d_l <= 3.5 && b1.close > lvl_s && (m_gamma_flip <= 0.0 || b1.close < m_gamma_flip))
            ArmPendingOrder(16, 1, 1, lvl_s, new_bar_time, new_bar_open, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120);
        }

      if(!MQLInfoInteger(MQL_OPTIMIZATION))
         RenderHudComment();
     }

   void              ArmPendingOrder(int k, int dir, int ptype, double price, datetime bar_t, double new_bar_open,
                                     double tp_pts, double sl_pts, double be_trig, double be_lock,
                                     double tr_trig, double tr_dist, int max_hold=16)
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
            OpenVirtualSingle(k, dir, p05, bar_t, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, true, pt_save, pl_save);
            m_slots[k].last_entry_bar_time = bar_t;
            if(k == 15 || k == 16)
               m_slots[k].last_trade_date = DateStr(bar_t);
            return;
           }

         long slot_magic = m_base_magic + k;
         DeletePendingOrdersForSlot(k);
         m_trade.SetExpertMagicNumber(slot_magic);

         double vol = MathRound(1.0 * m_lot_mult);
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
     }
  };
//+------------------------------------------------------------------+
