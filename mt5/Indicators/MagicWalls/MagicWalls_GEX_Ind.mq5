//+------------------------------------------------------------------+
//|                                     MagicWalls_GEX_Ind.mq5 |
//|   Indicador Visual das MagicWalls Diarias (WIN e WDO Automatico) |
//+------------------------------------------------------------------+
#property copyright "Magic Walls"
#property version   "3.30"
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_type1   DRAW_NONE

input int  InpHistoryDays    = 0;    // Dias de Historico (0 = Todos + HLINE no Dia Atual)
input bool InpShowWallLabels = true; // Mostrar Rótulos e Preço no Eixo Direito

double DummyBuf[];
string g_last_date = "";
long   g_last_daily_mtime = 0;

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

void AddUniqueDate(string &dates[], string d)
  {
   int n = ArraySize(dates);
   for(int i=0; i<n; i++)
      if(dates[i] == d)
         return;
   ArrayResize(dates, n + 1);
   dates[n] = d;
  }

int OnInit()
  {
   SetIndexBuffer(0, DummyBuf, INDICATOR_CALCULATIONS);
   IndicatorSetString(INDICATOR_SHORTNAME, "Magic Walls GEX (WIN/WDO)");
   ChartSetInteger(0, CHART_SCALEFIX, false);
   datetime t_ref = TimeCurrent();
   if(t_ref <= 0)
      t_ref = TimeTradeServer();
   if(t_ref <= 0)
      t_ref = TimeLocal();
   string d_str = GetDateStr(t_ref);
   string drawn = DrawDailyWalls(d_str);
   if(drawn != "")
      g_last_date = drawn;
   ChartRedraw(0);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, "MW_IND_GEX_");
  }

void StyleWallObject(string name, string wtype, double price, int width, bool is_wdo, string d_iso)
  {
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   if(InpShowWallLabels)
     {
      string tip = is_wdo ? StringFormat("[%s] %s @ %.1f (W=%d)", d_iso, wtype, price, width)
                          : StringFormat("[%s] %s @ %.0f (W=%d)", d_iso, wtype, price, width);
      ObjectSetString(0, name, OBJPROP_TOOLTIP, tip);
     }
   if(wtype == "Wall" || wtype == "wall")
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrDarkOrange);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
     }
   else if(wtype == "MidWall" || wtype == "mid_wall")
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrDodgerBlue);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DOT);
     }
   else if(wtype == "GammaFlip" || wtype == "gamma_flip")
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

string DrawDailyWalls(string target_date)
  {
   ObjectsDeleteAll(0, "MW_IND_GEX_");

   bool is_wdo = IsWdoChart();
   string daily_csv = is_wdo ? "magicwalls_gex_wdo_daily.csv" : "magicwalls_gex_win_daily.csv";
   string hist_csv  = is_wdo ? "magicwalls_gex_wdo_history.csv" : "magicwalls_gex_win_history.csv";

   g_last_daily_mtime = FileGetInteger(daily_csv, FILE_MODIFY_DATE, true);

   SIndGexItem items[];
   string all_dates[];

   // 1. Le historico
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

   // 2. Complementa com daily_csv
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
      return "";

   string last_date = all_dates[total_dates - 1];
   int idx = 0;

   // Para o dia atual (last_date), desenha OBJ_HLINE (exibe etiqueta de preco na direita e NUNCA achata a escala vertical do grafico!)
   for(int i=0; i<ArraySize(items); i++)
     {
      if(items[i].date != last_date)
         continue;
      if(items[i].price <= 0.0)
         continue;
      string name = StringFormat("MW_IND_GEX_HLINE_%s_%d", items[i].type, idx++);
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, items[i].price);
      StyleWallObject(name, items[i].type, items[i].price, items[i].width, is_wdo, items[i].date);
     }
   ChartRedraw(0);
   return last_date;
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
   long cur_mtime = g_last_daily_mtime;
   if(!MQLInfoInteger(MQL_TESTER))
     {
      string d_loc = GetDateStr(TimeLocal());
      if(d_loc > d_str)
         d_str = d_loc;
      string daily_csv = IsWdoChart() ? "magicwalls_gex_wdo_daily.csv" : "magicwalls_gex_win_daily.csv";
      cur_mtime = FileGetInteger(daily_csv, FILE_MODIFY_DATE, true);
     }
   if(d_str != g_last_date || cur_mtime != g_last_daily_mtime)
     {
      string drawn = DrawDailyWalls(d_str);
      if(drawn != "")
         g_last_date = drawn;
     }
   return(rates_total);
  }
