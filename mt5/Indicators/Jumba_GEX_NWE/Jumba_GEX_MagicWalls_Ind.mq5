//+------------------------------------------------------------------+
//|                                     Jumba_GEX_MagicWalls_Ind.mq5 |
//|   Indicador Visual Standalone das MagicWalls Diárias (Common)    |
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_type1   DRAW_NONE

input bool InpShowWallLabels = true; // Mostrar Rótulos das Walls no Gráfico

double DummyBuf[];
string g_last_date = "";

int OnInit()
  {
   SetIndexBuffer(0, DummyBuf, INDICATOR_CALCULATIONS);
   IndicatorSetString(INDICATOR_SHORTNAME, "Jumba GEX MagicWalls");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, "JUMBA_IND_GEX_");
  }

void DrawDailyWalls(string target_date)
  {
   ObjectsDeleteAll(0, "JUMBA_IND_GEX_");
   int idx = 0;

   // 1. Tenta ler jumba_gex_win_daily.csv em Common\Files
   int h = FileOpen("jumba_gex_win_daily.csv", FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   bool found = false;
   if(h != INVALID_HANDLE)
     {
      while(!FileIsEnding(h))
        {
         string line = FileReadString(h);
         if(StringLen(line) < 5 || StringFind(line, "session_date") >= 0)
            continue;
         string parts[];
         if(StringSplit(line, ';', parts) >= 5)
           {
            if(parts[0] == target_date || parts[1] == target_date)
              {
               CreateWallLine(idx++, parts[2], StringToDouble(parts[3]), (int)StringToInteger(parts[4]));
               found = true;
              }
           }
        }
      FileClose(h);
     }

   // 2. Fallback: jumba_gex_win_history.csv (última data <= target_date)
   if(!found)
     {
      int hh = FileOpen("jumba_gex_win_history.csv", FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(hh != INVALID_HANDLE)
        {
         string best_d = "";
         string types[];
         double prices[];
         int widths[];
         while(!FileIsEnding(hh))
           {
            string line = FileReadString(hh);
            if(StringLen(line) < 5 || StringFind(line, "session_date") >= 0)
               continue;
            string parts[];
            if(StringSplit(line, ';', parts) >= 4)
              {
               string d = parts[0];
               if(d <= target_date)
                 {
                  if(d > best_d)
                    {
                     best_d = d;
                     ArrayResize(types, 0);
                     ArrayResize(prices, 0);
                     ArrayResize(widths, 0);
                    }
                  if(d == best_d)
                    {
                     int n = ArraySize(types);
                     ArrayResize(types, n + 1);
                     ArrayResize(prices, n + 1);
                     ArrayResize(widths, n + 1);
                     types[n] = parts[1];
                     prices[n] = StringToDouble(parts[2]);
                     widths[n] = (int)StringToInteger(parts[3]);
                    }
                 }
              }
           }
         FileClose(hh);
         for(int k=0; k<ArraySize(types); k++)
            CreateWallLine(idx++, types[k], prices[k], widths[k]);
        }
     }
  }

void CreateWallLine(int idx, string wtype, double price, int width)
  {
   if(price <= 0.0)
      return;
   string name = StringFormat("JUMBA_IND_GEX_%s_%d", wtype, idx);
   ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, StringFormat("%s @ %.0f (W=%d)", wtype, price, width));
   if(wtype == "Wall")
     {
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrDarkOrange);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
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
   MqlDateTime dt;
   TimeToStruct(time[rates_total - 1], dt);
   string d_str = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
   if(d_str != g_last_date)
     {
      DrawDailyWalls(d_str);
      g_last_date = d_str;
     }
   return(rates_total);
  }
