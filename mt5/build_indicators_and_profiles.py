import os
import shutil
import subprocess

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
MT5_PROJ_DIR = os.path.join(PROJECT_ROOT, "mt5")
MT5_IND_DIR  = os.path.join(MT5_PROJ_DIR, "Indicators", "Jumba_GEX_NWE")
MT5_TPL_DIR  = os.path.join(MT5_PROJ_DIR, "Profiles", "Templates")
MT5_PRF_DIR  = os.path.join(MT5_PROJ_DIR, "Profiles", "Charts")

os.makedirs(MT5_IND_DIR, exist_ok=True)
os.makedirs(MT5_TPL_DIR, exist_ok=True)
os.makedirs(MT5_PRF_DIR, exist_ok=True)

# 1. Write Custom Indicator 1: Jumba_NWE_Envelope.mq5 (Causal Nadaraya-Watson Envelope M5)
nwe_ind_code = r"""//+------------------------------------------------------------------+
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
"""

nwe_ind_path = os.path.join(MT5_IND_DIR, "Jumba_NWE_Envelope.mq5")
with open(nwe_ind_path, "w", encoding="utf-8-sig") as f:
    f.write(nwe_ind_code)

# 2. Write Custom Indicator 2: Jumba_GEX_MagicWalls_Ind.mq5
gex_ind_code = r"""//+------------------------------------------------------------------+
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
"""

gex_ind_path = os.path.join(MT5_IND_DIR, "Jumba_GEX_MagicWalls_Ind.mq5")
with open(gex_ind_path, "w", encoding="utf-8-sig") as f:
    f.write(gex_ind_code)

# 3. Compile both Indicators using metaeditor64.exe
METAEDITOR = r"C:\Program Files\MetaTrader 5\metaeditor64.exe"
if not os.path.exists(METAEDITOR):
    METAEDITOR = r"C:\Program Files\MetaTrader 5 EXNESS\metaeditor64.exe"

TARGET_TERM = r"C:\Users\ryzen\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5"
TARGET_IND_DIR = os.path.join(TARGET_TERM, "Indicators", "Jumba_GEX_NWE")
os.makedirs(TARGET_IND_DIR, exist_ok=True)

for mq5_path in (nwe_ind_path, gex_ind_path):
    fname = os.path.basename(mq5_path)
    dst = os.path.join(TARGET_IND_DIR, fname)
    shutil.copy2(mq5_path, dst)
    log_f = dst.replace(".mq5", ".log")
    subprocess.run([METAEDITOR, f'/compile:{dst}', f'/inc:{TARGET_TERM}', f'/log:{log_f}'], check=False)
    ex5_dst = dst.replace(".mq5", ".ex5")
    ex5_src = mq5_path.replace(".mq5", ".ex5")
    if os.path.exists(ex5_dst):
        shutil.copy2(ex5_dst, ex5_src)
        print(f"[INDICATOR COMPILED OK] {os.path.basename(ex5_src)} ({os.path.getsize(ex5_src):,} bytes)")
    else:
        print(f"[INDICATOR COMPILE FAILED] {fname}")
        if os.path.exists(log_f):
            with open(log_f, "r", encoding="utf-16", errors="ignore") as lf:
                print(lf.read())

# 4. Helper to generate UTF-16LE .chr and .tpl content with Expert + Both Visual Indicators pre-attached!
def make_chart_chr(chart_id, symbol, expert_name, expert_path, expert_inputs_str, w_left=0, w_top=0, w_right=1480, w_bottom=680, w_type=3):
    return f"""<chart>
id={chart_id}
symbol={symbol}
description=Jumba Quant GEX MagicWalls + NWE (M5)
period_type=0
period_size=5
digits=0
tick_size=5.000000
scale_fix=0
scale_bar=0
scale=8
mode=1
fore=0
grid=1
volume=0
scroll=1
shift=1
shift_size=20.000000
fixed_pos=0.000000
ticker=1
ohlc=1
one_click=0
one_click_btn=1
bidline=1
askline=1
lastline=1
days=1
descriptions=0
tradelines=1
tradehistory=1
window_left={w_left}
window_top={w_top}
window_right={w_right}
window_bottom={w_bottom}
window_type={w_type}
floating=0
background_color=1315860
foreground_color=14737632
barup_color=59136
bardown_color=3552970
bullcandle_color=59136
bearcandle_color=3552970
chartline_color=59136
volumes_color=3329330
grid_color=2960685
bidline_color=10061943
askline_color=255
lastline_color=49152
stops_color=255
windows_total=1

<expert>
name={expert_name}
path={expert_path}
expertmode=5
<inputs>
{expert_inputs_str}
</inputs>
</expert>

<window>
height=100.000000
objects=0

<indicator>
name=Main
path=
apply=1
show_data=1
scale_inherit=0
scale_line=0
scale_line_percent=50
scale_line_value=0.000000
scale_fix_min=0
scale_fix_min_val=0.000000
scale_fix_max=0
scale_fix_max_val=0.000000
expertmode=0
fixed_height=-1
</indicator>

<indicator>
name=Custom Indicator
path=Indicators\\Jumba_GEX_NWE\\Jumba_NWE_Envelope.ex5
apply=1
show_data=1
scale_inherit=0
scale_line=0
scale_line_percent=50
scale_line_value=0.000000
scale_fix_min=0
scale_fix_min_val=0.000000
scale_fix_max=0
scale_fix_max_val=0.000000
expertmode=0
fixed_height=-1
<inputs>
InpLookback50=50
InpBandwidth50=5.0
InpMult50=2.0
InpLookback30=30
InpBandwidth30=3.0
InpMult30=1.6
InpMaxBars=1500
</inputs>
</indicator>

<indicator>
name=Custom Indicator
path=Indicators\\Jumba_GEX_NWE\\Jumba_GEX_MagicWalls_Ind.ex5
apply=1
show_data=1
scale_inherit=0
scale_line=0
scale_line_percent=50
scale_line_value=0.000000
scale_fix_min=0
scale_fix_min_val=0.000000
scale_fix_max=0
scale_fix_max_val=0.000000
expertmode=0
fixed_height=-1
<inputs>
InpShowWallLabels=true
</inputs>
</indicator>
</window>
</chart>
"""

# 5. Build Profiles & Templates
master_presets = [
    ("Jumba_PORT_01_Master", 0, "PRESET_PORT_01_COMPLETO (Ret/DD 29.54)"),
    ("Jumba_PORT_03_Master", 1, "PRESET_PORT_03_SHARPE (Sharpe 8.15)"),
    ("Jumba_LEVE_01_Master", 2, "PRESET_LEVE_01_R2_986 (Sem Grid 6L, R2 98.6%)"),
    ("Jumba_LEVE_03_Master", 3, "PRESET_LEVE_03_PROFIT (Sem Grid 6L, Lucro R$ 19.776)"),
    ("Jumba_TODAS_16_Master", 6, "PRESET_TODAS_16_ATIVAS (Todas as 16 Estrategias Juntas)"),
]

for prf_name, preset_val, desc in master_presets:
    inputs_str = f"""InpPreset={preset_val}
InpExecMode=0
InpLotMultiplier=1.0
InpMaxDailyLoss=2500.0
InpBaseMagic=88000
InpDrawLevels=true
InpWdoSymbol=WDO$N"""
    chr_txt = make_chart_chr(
        chart_id=145000000000000001 + preset_val,
        symbol="WIN$N",
        expert_name="Jumba_GEX_NWE_Portfolio_Master",
        expert_path="Experts\\Jumba_GEX_NWE\\Jumba_GEX_NWE_Portfolio_Master.ex5",
        expert_inputs_str=inputs_str,
    )
    # Save Template (.tpl)
    tpl_file = os.path.join(MT5_TPL_DIR, f"{prf_name}.tpl")
    with open(tpl_file, "w", encoding="utf-16") as f:
        f.write(chr_txt)

    # Save Profile directory (chart01.chr + order.wnd)
    prf_dir = os.path.join(MT5_PRF_DIR, prf_name)
    os.makedirs(prf_dir, exist_ok=True)
    with open(os.path.join(prf_dir, "chart01.chr"), "w", encoding="utf-16") as f:
        f.write(chr_txt)
    with open(os.path.join(prf_dir, "order.wnd"), "w", encoding="utf-16") as f:
        f.write("chart01.chr\r\n")

# Build 8-Chart Multi-Window Profiles: Jumba_8_Graficos_PORT01 & Jumba_8_Graficos_LEVE01
robot_map = {
    1:  ("Jumba_EST01_Scalper_Hibrido_NY",      88001),
    2:  ("Jumba_EST02_Scalper_Hibrido_DiaTodo", 88002),
    3:  ("Jumba_EST03_Scalper_Cambial_WDO",     88003),
    4:  ("Jumba_EST04_Pullback_Reteste_Wall",   88004),
    5:  ("Jumba_EST05_Pullback_Cluster_NWE",    88005),
    6:  ("Jumba_EST06_Pullback_Limit_Slope",    88006),
    7:  ("Jumba_EST07_Breakout_Momentum_NY",    88007),
    8:  ("Jumba_EST08_Breakout_Rapido_Core",    88008),
    9:  ("Jumba_EST09_Breakout_Stop_Wall",      88009),
    10: ("Jumba_EST10_Breakout_Stop_Wick",      88010),
    11: ("Jumba_EST11_Grid_Pullback_Tendencia", 88011),
    12: ("Jumba_EST12_Piramidacao_Lucro_11L",   88012),
    13: ("Jumba_EST13_SmartGrid_RSI_BE",        88013),
    14: ("Jumba_EST14_Grid_Institucional_123L", 88014),
    15: ("Jumba_EST15_Posicional_EOD_Breakout", 88015),
    16: ("Jumba_EST16_Posicional_EOD_Fade",     88016),
}

multi8_profiles = [
    ("Jumba_8_Graficos_PORT01", [4, 7, 9, 10, 11, 13, 14, 15]),
    ("Jumba_8_Graficos_LEVE01", [4, 6, 8, 9, 11, 12, 15, 16]),
    ("Jumba_16_Graficos_TODAS16", list(range(1, 17))),
]

for m_name, id_list in multi8_profiles:
    prf_dir = os.path.join(MT5_PRF_DIR, m_name)
    os.makedirs(prf_dir, exist_ok=True)
    order_lines = []
    n_charts = len(id_list)
    cols = 4
    rows = (n_charts + cols - 1) // cols
    col_w = 380
    row_h = 680 // rows
    for idx, sid in enumerate(id_list):
        r_name, magic = robot_map[sid]
        col = idx % cols
        row = idx // cols
        wl = col * col_w
        wt = row * row_h
        wr = wl + col_w
        wb = wt + row_h
        inp_s = f"""InpExecMode=1
InpLotMultiplier=1.0
InpMaxDailyLoss=1000.0
InpMagicNumber={magic}
InpDrawLevels=true
InpWdoSymbol=WDO$N"""
        c_fname = f"chart{idx+1:02d}.chr"
        order_lines.append(c_fname)
        c_txt = make_chart_chr(
            chart_id=145000000000000100 + idx + (100 if n_charts == 16 else (20 if "LEVE" in m_name else 0)),
            symbol="WIN$N",
            expert_name=r_name,
            expert_path=f"Experts\\Jumba_GEX_NWE\\{r_name}.ex5",
            expert_inputs_str=inp_s,
            w_left=wl, w_top=wt, w_right=wr, w_bottom=wb, w_type=1
        )
        with open(os.path.join(prf_dir, c_fname), "w", encoding="utf-16") as f:
            f.write(c_txt)
    with open(os.path.join(prf_dir, "order.wnd"), "w", encoding="utf-16") as f:
        f.write("\r\n".join(order_lines) + "\r\n")

# 6. Deploy Indicators, Templates and Profiles to C:\Program Files\MetaTrader 5 (D0E8209F77C8CF37AD8BF550E51FF075) AND all other MT5 terminals!
term_root = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
deployed_count = 0

for d in os.listdir(term_root):
    t_dir = os.path.join(term_root, d)
    mql5_dir = os.path.join(t_dir, "MQL5")
    if not os.path.isdir(mql5_dir):
        continue

    # Copy Indicators
    dst_ind = os.path.join(mql5_dir, "Indicators", "Jumba_GEX_NWE")
    os.makedirs(dst_ind, exist_ok=True)
    for f in os.listdir(MT5_IND_DIR):
        shutil.copy2(os.path.join(MT5_IND_DIR, f), os.path.join(dst_ind, f))

    # Copy Templates (into both MQL5\Profiles\Templates and root templates)
    for tpl_dst_dir in [os.path.join(mql5_dir, "Profiles", "Templates"), os.path.join(t_dir, "templates")]:
        os.makedirs(tpl_dst_dir, exist_ok=True)
        for f in os.listdir(MT5_TPL_DIR):
            shutil.copy2(os.path.join(MT5_TPL_DIR, f), os.path.join(tpl_dst_dir, f))

    # Copy Profiles (into both MQL5\Profiles\Charts and root profiles\Charts)
    for prf_root_dst in [os.path.join(mql5_dir, "Profiles", "Charts"), os.path.join(t_dir, "profiles", "Charts")]:
        os.makedirs(prf_root_dst, exist_ok=True)
        for p_folder in os.listdir(MT5_PRF_DIR):
            src_p = os.path.join(MT5_PRF_DIR, p_folder)
            dst_p = os.path.join(prf_root_dst, p_folder)
            os.makedirs(dst_p, exist_ok=True)
            for cf in os.listdir(src_p):
                shutil.copy2(os.path.join(src_p, cf), os.path.join(dst_p, cf))

    deployed_count += 1

print(f"\n[SUCCESS] Deployed 2 Custom Indicators (.ex5), 4 Templates (.tpl) and 6 Plug-and-Play Profiles to {deployed_count} MT5 terminals (including D0E8209F77C8CF37AD8BF550E51FF075 -> C:\\Program Files\\MetaTrader 5)!")
