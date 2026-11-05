import os
import shutil

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
MT5_PROJ_DIR = os.path.join(PROJECT_ROOT, "mt5")
MT5_EXP_DIR = os.path.join(MT5_PROJ_DIR, "Experts")
MT5_EXP_SUB = os.path.join(MT5_EXP_DIR, "Jumba_GEX_NWE")
MT5_PRF_DIR = os.path.join(MT5_PROJ_DIR, "Profiles", "Charts")

os.makedirs(MT5_EXP_SUB, exist_ok=True)
os.makedirs(MT5_PRF_DIR, exist_ok=True)

# 1. Ensure Jumba_Portfolio_Live_Monitor.ex5 is in MT5_EXP_SUB as well as MT5_EXP_DIR
mon_ex5_root = os.path.join(MT5_EXP_DIR, "Jumba_Portfolio_Live_Monitor.ex5")
mon_mq5_root = os.path.join(MT5_EXP_DIR, "Jumba_Portfolio_Live_Monitor.mq5")
if os.path.exists(mon_ex5_root):
    shutil.copy2(mon_ex5_root, os.path.join(MT5_EXP_SUB, "Jumba_Portfolio_Live_Monitor.ex5"))
if os.path.exists(mon_mq5_root):
    shutil.copy2(mon_mq5_root, os.path.join(MT5_EXP_SUB, "Jumba_Portfolio_Live_Monitor.mq5"))

# 2. Alias map (in case any old profile/template references legacy names)
ALIAS_EX5_MAP = {
    "Jumba_EST02_Fade_NWE_Extremo.ex5": "Jumba_EST02_Scalper_Hibrido_DiaTodo.ex5",
    "Jumba_EST04_Breakout_Gamma_Manha.ex5": "Jumba_EST04_Pullback_Reteste_Wall.ex5",
    "Jumba_EST06_PingPong_Range_Walls.ex5": "Jumba_EST06_Pullback_Limit_Slope.ex5",
    "Jumba_EST07_Trend_Pullback_NWE.ex5": "Jumba_EST07_Breakout_Momentum_NY.ex5",
    "Jumba_EST08_Abertura_NY_10h30.ex5": "Jumba_EST08_Breakout_Rapido_Core.ex5",
    "Jumba_EST12_Confluencia_Dolar.ex5": "Jumba_EST12_Piramidacao_Lucro_11L.ex5",
    "Jumba_EST13_Grid_2L_Padrao.ex5": "Jumba_EST13_SmartGrid_RSI_BE.ex5",
    "Jumba_EST14_Grid_3L_Padrao.ex5": "Jumba_EST14_Grid_Institucional_123L.ex5",
    "Jumba_WDO02_Fade_NWE_Extremo.ex5": "Jumba_WDO02_Scalper_Hibrido_CORE.ex5",
    "Jumba_WDO06_PingPong_Range_Walls.ex5": "Jumba_WDO06_Limit_Wall_Rejeicao.ex5",
    "Jumba_WDO07_Trend_Pullback_NWE.ex5": "Jumba_WDO07_Absorcao_Mkt_NY.ex5",
    "Jumba_WDO09_PowerHour_Tarde.ex5": "Jumba_WDO09_Stop_Limit_Wall_NY.ex5",
    "Jumba_WDO10_Opening_Drive_09h.ex5": "Jumba_WDO10_Stop_Limit_Main_Walls.ex5",
    "Jumba_WDO11_Grid_2L_Padrao.ex5": "Jumba_WDO11_Grid_Absorcao_NWE.ex5",
}

for alias_name, canonical_name in ALIAS_EX5_MAP.items():
    src_canonical = os.path.join(MT5_EXP_SUB, canonical_name)
    if not os.path.exists(src_canonical):
        src_canonical = os.path.join(MT5_EXP_DIR, canonical_name)
    if os.path.exists(src_canonical):
        shutil.copy2(src_canonical, os.path.join(MT5_EXP_SUB, alias_name))

# 3. Exact 18 validated robots (>=100 trades + WF) + 19th chart (Live Monitor)
WIN_11_SPECS = [
    (1,  "Jumba_EST01_Scalper_Hibrido_NY",      88001, "EST-01 | WIN_PA_PINBAR_WALL (Magic 88001)"),
    (2,  "Jumba_EST02_Scalper_Hibrido_DiaTodo", 88002, "EST-02 | WIN_PA_OUTSIDE_MID (Magic 88002)"),
    (4,  "Jumba_EST04_Pullback_Reteste_Wall",   88004, "EST-04 | WIN_PA_INSIDE_BREAK (Magic 88004)"),
    (6,  "Jumba_EST06_Pullback_Limit_Slope",    88006, "EST-06 | WIN_OF_ABSORPTION (Magic 88006)"),
    (7,  "Jumba_EST07_Breakout_Momentum_NY",    88007, "EST-07 | WIN_OF_CLIMAX_WALL (Magic 88007)"),
    (8,  "Jumba_EST08_Breakout_Rapido_Core",    88008, "EST-08 | WIN_OF_SPRING_UPTHRUST (Magic 88008)"),
    (12, "Jumba_EST12_Piramidacao_Lucro_11L",   88012, "EST-12 | WIN_REG_TREND_WALL (Magic 88012)"),
    (13, "Jumba_EST13_SmartGrid_RSI_BE",        88013, "EST-13 | WIN_SG_SCALPER_3C (Magic 88013)"),
    (14, "Jumba_EST14_Grid_Institucional_123L", 88014, "EST-14 | WIN_SG_MOMENTUM_3C (Magic 88014)"),
    (15, "Jumba_EST15_Posicional_EOD_Breakout", 88015, "EST-15 | WIN_SG_Z30_REV_WALL (Magic 88015)"),
    (16, "Jumba_EST16_Posicional_EOD_Fade",     88016, "EST-16 | WIN_SG_SPRING_Z30_WALL (Magic 88016)"),
]

WDO_7_SPECS = [
    (2,  "Jumba_WDO02_Scalper_Hibrido_CORE",     89000, "WDO-02 | WDO_PA_OUTSIDE_MID (Magic 89002)"),
    (6,  "Jumba_WDO06_Limit_Wall_Rejeicao",      89000, "WDO-06 | WDO_OF_ABSORPTION (Magic 89006)"),
    (7,  "Jumba_WDO07_Absorcao_Mkt_NY",          89000, "WDO-07 | WDO_OF_CLIMAX_WALL (Magic 89007)"),
    (9,  "Jumba_WDO09_Stop_Limit_Wall_NY",       89000, "WDO-09 | WDO_PB_WALL_PULLBACK (Magic 89009)"),
    (10, "Jumba_WDO10_Stop_Limit_Main_Walls",    89000, "WDO-10 | WDO_S2_MIDWALL_Z30 (Magic 89010)"),
    (11, "Jumba_WDO11_Grid_Absorcao_NWE",        89000, "WDO-11 | WDO_REG_PINNED_FADE (Magic 89011)"),
    (15, "Jumba_WDO15_Posicional_EOD_Matinal",   89000, "WDO-15 | WDO_PA_MAINWALL_Z30_REV (Magic 89015)"),
]


def make_robot_chr(chart_id, symbol, desc, digits, tick_size, expert_name, expert_inputs_str, w_left, w_top, w_right, w_bottom):
    return f"""<chart>
id={chart_id}
symbol={symbol}
description={desc}
period_type=0
period_size=5
digits={digits}
tick_size={tick_size}
position_time=0
scale_fix=0
scale_fix11=0
scale_bar=0
scale_bar_val=1.000000
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
window_type=1
floating=0
floating_left=0
floating_top=0
floating_right=0
floating_bottom=0
floating_type=1
floating_toolbar=1
floating_tbstate=
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
path=Experts\\Jumba_GEX_NWE\\{expert_name}.ex5
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
InpHistoryDays=0
InpShowWallLabels=true
</inputs>
</indicator>
</window>
</chart>
"""


def make_monitor_chr(chart_id):
    return f"""<chart>
id={chart_id}
symbol=WINZ26
description=JUMBA QUANT MONITOR LIVE vs BACKTEST (18 ROBOS)
period_type=0
period_size=5
digits=0
tick_size=5.000000
position_time=0
scale_fix=0
scale_fix11=0
scale_bar=0
scale_bar_val=1.000000
scale=8
mode=1
fore=0
grid=0
volume=0
scroll=1
shift=1
shift_size=20.000000
fixed_pos=0.000000
ticker=1
ohlc=0
one_click=0
one_click_btn=1
bidline=0
askline=0
lastline=0
days=0
descriptions=0
tradelines=0
tradehistory=0
window_left=0
window_top=0
window_right=1280
window_bottom=720
window_type=3
floating=0
floating_left=0
floating_top=0
floating_right=0
floating_bottom=0
floating_type=1
floating_toolbar=1
floating_tbstate=
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
name=Jumba_Portfolio_Live_Monitor
path=Experts\\Jumba_GEX_NWE\\Jumba_Portfolio_Live_Monitor.ex5
expertmode=5
<inputs>
InpWinBaseMagic=88000
InpWdoBaseMagic=89000
InpBtDdReference=0
InpHistorySource=0
InpRefreshSeconds=2
InpHistoryStartDate=1735689600
InpResetReplacedSlots=true
InpIncludeFloatingDD=true
InpExportCsvReport=true
InpAlertOnBtBreach=true
InpPanelX=12
InpPanelY=24
InpFontSize=8
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
</window>
</chart>
"""


def build_18_wf_profile_dir(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    # Remove any old .chr files first
    for f in os.listdir(target_dir):
        if f.endswith((".chr", ".wnd")):
            os.remove(os.path.join(target_dir, f))

    order_lines = []
    cols = 6
    col_w = 240
    row_h = 210

    # Charts 01..11: 11 WIN robots
    for idx, (slot_id, ea_name, magic, desc) in enumerate(WIN_11_SPECS):
        c_num = idx + 1
        c_fname = f"chart{c_num:02d}.chr"
        order_lines.append(c_fname)
        col = idx % cols
        row = idx // cols
        wl, wt = col * col_w, row * row_h
        wr, wb = wl + col_w, wt + row_h
        inp_str = f"""InpExecMode=1
InpLotMultiplier=1.0
InpMaxDailyLoss=1000.0
InpMagicNumber={magic}
InpDrawLevels=true
InpWdoSymbol=WDOZ26"""
        chr_txt = make_robot_chr(
            chart_id=145000000000000600 + c_num,
            symbol="WINZ26",
            desc=desc,
            digits=0,
            tick_size="5.000000",
            expert_name=ea_name,
            expert_inputs_str=inp_str,
            w_left=wl, w_top=wt, w_right=wr, w_bottom=wb,
        )
        with open(os.path.join(target_dir, c_fname), "w", encoding="utf-16") as f:
            f.write(chr_txt)

    # Charts 12..18: 7 WDO robots
    for w_idx, (slot_id, ea_name, base_magic, desc) in enumerate(WDO_7_SPECS):
        c_num = 12 + w_idx
        c_fname = f"chart{c_num:02d}.chr"
        order_lines.append(c_fname)
        grid_pos = 11 + w_idx
        col = grid_pos % cols
        row = grid_pos // cols
        wl, wt = col * col_w, row * row_h
        wr, wb = wl + col_w, wt + row_h
        inp_str = f"""InpBaseMagic={base_magic}
InpLotMultiplier=1.0
InpMaxDailyLossBRL=2000.0
InpExecMode=0
InpDrawGexLevels=true
InpShowHud=true"""
        chr_txt = make_robot_chr(
            chart_id=145000000000000600 + c_num,
            symbol="WDOZ26",
            desc=desc,
            digits=1,
            tick_size="0.500000",
            expert_name=ea_name,
            expert_inputs_str=inp_str,
            w_left=wl, w_top=wt, w_right=wr, w_bottom=wb,
        )
        with open(os.path.join(target_dir, c_fname), "w", encoding="utf-16") as f:
            f.write(chr_txt)

    # Chart 19: Live Monitor
    c19_fname = "chart19.chr"
    order_lines.append(c19_fname)
    with open(os.path.join(target_dir, c19_fname), "w", encoding="utf-16") as f:
        f.write(make_monitor_chr(145000000000000619))

    with open(os.path.join(target_dir, "order.wnd"), "w", encoding="utf-16") as f:
        f.write("\r\n".join(order_lines) + "\r\n")


# Build in project mt5/Profiles/Charts under both names:
# 1. Jumba_18_WF_100TR_MONITOR (original name)
# 2. Jumba_18_WF_MONITOR_V2 (fresh name so if MT5 has Jumba_18_WF_100TR_MONITOR open in memory, switching to V2 loads all 19 charts immediately)
for prf_name in ("Jumba_18_WF_100TR_MONITOR", "Jumba_18_WF_MONITOR_V2"):
    build_18_wf_profile_dir(os.path.join(MT5_PRF_DIR, prf_name))

# 4. Sync all Experts (.ex5 + aliases) and all Profiles to every MT5 terminal in %APPDATA%\MetaQuotes\Terminal
term_root = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
synced_terms = 0
if os.path.exists(term_root):
    for d in os.listdir(term_root):
        t_dir = os.path.join(term_root, d)
        mql5_dir = os.path.join(t_dir, "MQL5")
        if not os.path.isdir(mql5_dir):
            continue

        # Copy all .ex5 and .mq5 into MQL5\Experts\Jumba_GEX_NWE and MQL5\Experts
        dst_exp_sub = os.path.join(mql5_dir, "Experts", "Jumba_GEX_NWE")
        dst_exp_root = os.path.join(mql5_dir, "Experts")
        os.makedirs(dst_exp_sub, exist_ok=True)
        for f in os.listdir(MT5_EXP_SUB):
            if f.endswith((".ex5", ".mq5")):
                shutil.copy2(os.path.join(MT5_EXP_SUB, f), os.path.join(dst_exp_sub, f))
                shutil.copy2(os.path.join(MT5_EXP_SUB, f), os.path.join(dst_exp_root, f))
        if os.path.exists(mon_ex5_root):
            shutil.copy2(mon_ex5_root, os.path.join(dst_exp_root, "Jumba_Portfolio_Live_Monitor.ex5"))

        # Copy all profiles from project MT5_PRF_DIR into both MQL5\Profiles\Charts and profiles\Charts
        for prf_dst_base in (os.path.join(mql5_dir, "Profiles", "Charts"), os.path.join(t_dir, "profiles", "Charts")):
            os.makedirs(prf_dst_base, exist_ok=True)
            for p_folder in os.listdir(MT5_PRF_DIR):
                src_p = os.path.join(MT5_PRF_DIR, p_folder)
                if not os.path.isdir(src_p):
                    continue
                dst_p = os.path.join(prf_dst_base, p_folder)
                os.makedirs(dst_p, exist_ok=True)
                for cf in os.listdir(src_p):
                    shutil.copy2(os.path.join(src_p, cf), os.path.join(dst_p, cf))

        synced_terms += 1

print(f"[OK] Built and synced Jumba_18_WF_100TR_MONITOR & Jumba_18_WF_MONITOR_V2 + all .ex5 EAs across {synced_terms} MT5 terminals.")

