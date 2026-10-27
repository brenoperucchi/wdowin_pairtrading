//+------------------------------------------------------------------+
//|                                           Jumba_NWE_Envelope.mq5 |
//|     Indicador Visual Causal Nadaraya-Watson Envelope (50 e 30)   |
//+------------------------------------------------------------------+
#property copyright "Jumba Quant / Antigravity"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 5
#property indicator_plots   5

#property indicator_label1  "NWE50 Upper"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrCrimson
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

#property indicator_label2  "NWE50 Center"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrGold
#property indicator_style2  STYLE_DOT
#property indicator_width2  1

#property indicator_label3  "NWE50 Lower"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDodgerBlue
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

#property indicator_label4  "NWE30 Upper"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrOrangeRed
#property indicator_style4  STYLE_DOT
#property indicator_width4  1

#property indicator_label5  "NWE30 Lower"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrDeepSkyBlue
#property indicator_style5  STYLE_DOT
#property indicator_width5  1

input int    InpLookback50 = 50;   // NWE Principal: Lookback (Barras)
input double InpBandwidth50= 5.0;  // NWE Principal: Bandwidth (h)
input double InpMult50     = 2.0;  // NWE Principal: Multiplicador MAE
input int    InpLookback30 = 30;   // NWE Rápido: Lookback (Barras)
input double InpBandwidth30= 3.0;  // NWE Rápido: Bandwidth (h)
input double InpMult30     = 1.6;  // NWE Rápido: Multiplicador MAE
input int    InpMaxBars    = 1500; // Máximo de Barras Calculadas no Histórico

double BufU50[], BufC50[], BufL50[], BufU30[], BufL30[];
double W50[], W30[];

int OnInit()
  {
   SetIndexBuffer(0, BufU50, INDICATOR_DATA);
   SetIndexBuffer(1, BufC50, INDICATOR_DATA);
   SetIndexBuffer(2, BufL50, INDICATOR_DATA);
   SetIndexBuffer(3, BufU30, INDICATOR_DATA);
   SetIndexBuffer(4, BufL30, INDICATOR_DATA);

   ArrayResize(W50, InpLookback50);
   for(int k=0; k<InpLookback50; k++)
      W50[k] = MathExp(-((double)(k * k)) / (2.0 * InpBandwidth50 * InpBandwidth50));

   ArrayResize(W30, InpLookback30);
   for(int k=0; k<InpLookback30; k++)
      W30[k] = MathExp(-((double)(k * k)) / (2.0 * InpBandwidth30 * InpBandwidth30));

   IndicatorSetString(INDICATOR_SHORTNAME, "Jumba NWE Envelope (50 & 30)");
   return(INIT_SUCCEEDED);
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
   if(rates_total < InpLookback50 + 5)
      return(0);

   int start_bar = MathMax(0, rates_total - InpMaxBars);
   if(prev_calculated > start_bar + 5)
      start_bar = prev_calculated - 2;

   for(int i=0; i<start_bar && prev_calculated == 0; i++)
     {
      BufU50[i] = EMPTY_VALUE;
      BufC50[i] = EMPTY_VALUE;
      BufL50[i] = EMPTY_VALUE;
      BufU30[i] = EMPTY_VALUE;
      BufL30[i] = EMPTY_VALUE;
     }

   for(int t=start_bar; t<rates_total; t++)
     {
      // Causal NWE 50
      int l50 = MathMin(t, InpLookback50 - 1);
      double num50 = 0.0, den50 = 0.0;
      for(int k=0; k<=l50; k++)
        {
         num50 += W50[k] * close[t - k];
         den50 += W50[k];
        }
      BufC50[t] = (den50 > 0.0) ? (num50 / den50) : close[t];

      double sum_err50 = 0.0;
      for(int k=0; k<=l50; k++)
        {
         double c_tk = (BufC50[t - k] != EMPTY_VALUE && BufC50[t - k] > 0.0) ? BufC50[t - k] : close[t - k];
         sum_err50 += MathAbs(close[t - k] - c_tk);
        }
      double mae50 = sum_err50 / (double)(l50 + 1);
      BufU50[t] = BufC50[t] + mae50 * InpMult50;
      BufL50[t] = BufC50[t] - mae50 * InpMult50;

      // Causal NWE 30
      int l30 = MathMin(t, InpLookback30 - 1);
      double num30 = 0.0, den30 = 0.0;
      for(int k=0; k<=l30; k++)
        {
         num30 += W30[k] * close[t - k];
         den30 += W30[k];
        }
      double c30 = (den30 > 0.0) ? (num30 / den30) : close[t];

      double sum_err30 = 0.0;
      for(int k=0; k<=l30; k++)
        {
         double c_tk = (BufC50[t - k] != EMPTY_VALUE && BufC50[t - k] > 0.0) ? BufC50[t - k] : close[t - k];
         sum_err30 += MathAbs(close[t - k] - c_tk);
        }
      double mae30 = sum_err30 / (double)(l30 + 1);
      BufU30[t] = c30 + mae30 * InpMult30;
      BufL30[t] = c30 - mae30 * InpMult30;
     }

   return(rates_total);
  }
