//+------------------------------------------------------------------+
//|                                     Jumba_GEX_MagicWalls_Ind.mq5 |
//|   Indicador Visual das MagicWalls Diárias + Histórico (20 Dias)  |
//|   Plota a marcação calculada de cada dia exatamente sobre o dia  |
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property version   "3.10"
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_type1   DRAW_NONE

input int  InpHistoryDays    = 0;    // Dias de Histórico p/ Plotar (0 = TODO o histórico disponível)
input bool InpShowWallLabels = true; // Mostrar Tooltip c/ Data e Preço nas Linhas

double DummyBuf[];
string g_last_date = "";

struct SIndGexItem
  {
   string            date;
   string            type;
   double            price;
   int               width;
  };

bool IsWdoChart()
  {
   string s = _Symbol;
   StringToUpper(s);
   return (StringFind(s, "WDO") >= 0 || StringFind(s, "DOL") >= 0);
  }

string GetDateStr(datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
  }

datetime DateToSessionTime(string d_iso, string hhmm)
  {
   string d_dot = d_iso;
   StringReplace(d_dot, "-", ".");
   return StringToTime(d_dot + " " + hhmm);
  }

int OnInit()
  {
   SetIndexBuffer(0, DummyBuf, INDICATOR_CALCULATIONS);
   IndicatorSetString(INDICATOR_SHORTNAME, "Jumba GEX MagicWalls (ALL)");
   datetime t_ref = TimeCurrent();
   if(t_ref <= 0)
      t_ref = TimeTradeServer();
   if(t_ref <= 0)
      t_ref = TimeLocal();
   string d_str = GetDateStr(t_ref);
   DrawHistoryWalls(d_str);
   g_last_date = d_str;
   ChartRedraw(0);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, "JUMBA_IND_GEX_");
  }

void AddUniqueDate(string &dates[], string d)
  {
   int n = ArraySize(dates);
   for(int i=0; i<n; i++)
      if(dates[i] == d)
         return;
   ArrayResize(dates, n + 1);
   dates[n] = d;
  }

void DrawHistoryWalls(string target_date)
  {
   ObjectsDeleteAll(0, "JUMBA_IND_GEX_");
   // Remove eventuais OBJ_HLINE infinitas antigas do EA para não poluir os 20 dias para trás
   ObjectsDeleteAll(0, "JUMBA_GEX_");
   ObjectsDeleteAll(0, "JUMBA_WDO_GEX_");

   bool is_wdo = IsWdoChart();
   string daily_csv = is_wdo ? "jumba_gex_wdo_daily.csv" : "jumba_gex_win_daily.csv";
   string hist_csv  = is_wdo ? "jumba_gex_wdo_history.csv" : "jumba_gex_win_history.csv";

   SIndGexItem items[];
   string all_dates[];

   // 1. Lê o histórico completo (jumba_gex_*_history.csv) com FILE_SHARE_READ
   int hh = FileOpen(hist_csv, FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(hh == INVALID_HANDLE)
      hh = FileOpen(hist_csv, FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI);
   if(hh != INVALID_HANDLE)
     {
      while(!FileIsEnding(hh))
        {
         string line = FileReadString(hh);
         if(StringLen(line) < 5 || StringFind(line, "session_date") >= 0)
            continue;
         string parts[];
         int cnt = StringSplit(line, ';', parts);
         if(cnt >= 4)
           {
            string d = parts[0];
            if(d <= target_date)
              {
               int n = ArraySize(items);
               ArrayResize(items, n + 1);
               items[n].date  = d;
               items[n].type  = parts[1];
               items[n].price = StringToDouble(parts[2]);
               items[n].width = (int)StringToInteger(parts[3]);
               AddUniqueDate(all_dates, d);
              }
           }
        }
      FileClose(hh);
     }

   // 2. Complementa com jumba_gex_*_daily.csv caso a data do daily ainda não esteja no history
   int hd = FileOpen(daily_csv, FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(hd == INVALID_HANDLE)
      hd = FileOpen(daily_csv, FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_TXT|FILE_ANSI);
   if(hd != INVALID_HANDLE)
     {
      string daily_added_date = "";
      bool already_in_hist = false;
      while(!FileIsEnding(hd))
        {
         string line = FileReadString(hd);
         if(StringLen(line) < 5 || StringFind(line, "session_date") >= 0)
            continue;
         string parts[];
         int cnt = StringSplit(line, ';', parts);
         string d = "";
         string tp = "";
         double pr = 0.0;
         int wd = 1;
         if(cnt >= 5)
           {
            d  = parts[0];
            tp = parts[2];
            pr = StringToDouble(parts[3]);
            wd = (int)StringToInteger(parts[4]);
           }
         else if(cnt == 4)
           {
            d  = parts[0];
            tp = parts[1];
            pr = StringToDouble(parts[2]);
            wd = (int)StringToInteger(parts[3]);
           }
         if(d != "" && d <= target_date)
           {
            if(daily_added_date == "")
              {
               daily_added_date = d;
               for(int i=0; i<ArraySize(all_dates); i++)
                  if(all_dates[i] == d)
                     already_in_hist = true;
              }
            if(!already_in_hist && d == daily_added_date)
              {
               int n = ArraySize(items);
               ArrayResize(items, n + 1);
               items[n].date  = d;
               items[n].type  = tp;
               items[n].price = pr;
               items[n].width = wd;
               AddUniqueDate(all_dates, d);
              }
           }
        }
      FileClose(hd);
     }

   int total_dates = ArraySize(all_dates);
   if(total_dates == 0)
      return;

   // Plota SEMPRE 100% de todo o histórico disponível (todos os pregões desde Maio/2026)
   int start_idx = 0;
   string first_date = all_dates[start_idx];
   string last_date  = all_dates[total_dates - 1];

   int obj_idx = 0;
   for(int i=0; i<ArraySize(items); i++)
     {
      string d = items[i].date;
      if(d < first_date)
         continue;

      bool is_latest_day = (d == last_date);
      CreateDaySegment(obj_idx++, d, items[i].type, items[i].price, items[i].width, is_wdo, is_latest_day);
     }
   PrintFormat("[JUMBA IND GEX v3.20] %s | Plotados %d niveis em %d pregoes (%s ate %s)",
               _Symbol, obj_idx, total_dates, first_date, last_date);
  }

void CreateDaySegment(int idx, string d_iso, string wtype, double price, int width, bool is_wdo, bool is_latest_day)
  {
   if(price <= 0.0)
      return;
   datetime t1 = DateToSessionTime(d_iso, "09:00");
   datetime t2 = DateToSessionTime(d_iso, "18:20");
   if(t1 <= 0 || t2 <= 0)
      return;

   string name = StringFormat("JUMBA_IND_GEX_%s_%s_%d", d_iso, wtype, idx);
   ObjectCreate(0, name, OBJ_TREND, 0, t1, price, t2, price);
   ObjectSetInteger(0, name, OBJPROP_RAY_LEFT, false);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, is_latest_day);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);

   if(InpShowWallLabels)
     {
      string tip = is_wdo ? StringFormat("[%s] %s @ %.1f (W=%d)", d_iso, wtype, price, width)
                          : StringFormat("[%s] %s @ %.0f (W=%d)", d_iso, wtype, price, width);
      ObjectSetString(0, name, OBJPROP_TOOLTIP, tip);
     }

   if(wtype == "Wall")
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrDarkOrange);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, is_latest_day ? 2 : 1);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
     }
   else if(wtype == "MidWall")
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrDodgerBlue);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DOT);
     }
   else if(wtype == "GammaFlip")
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrMagenta);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
     }
   else
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrMediumSeaGreen);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
     }
  }

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   if(rates_total < 1)
      return(0);
   string d_str = GetDateStr(time[rates_total - 1]);
   if(!MQLInfoInteger(MQL_TESTER))
     {
      string d_loc = GetDateStr(TimeLocal());
      if(d_loc > d_str)
         d_str = d_loc;
     }
   if(d_str != g_last_date)
     {
      DrawHistoryWalls(d_str);
      g_last_date = d_str;
     }
   return(rates_total);
  }
