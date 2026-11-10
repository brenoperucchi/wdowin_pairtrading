"""
GERADOR OFICIAL DE PERFIL MT5 - PORTFÓLIO 22 ROBÔS ATIVOS + MONITOR
===================================================================
13 Robôs WIN (EST-01 a EST-08, EST-12 a EST-16)
   - EST-03 e EST-05 operam no timeframe M15 (period_size=15)
   - Demais robôs WIN operam no timeframe M5 (period_size=5)
09 Robôs WDO (WDO-01, WDO-02, WDO-05, WDO-06, WDO-07, WDO-09, WDO-10, WDO-11, WDO-15)
   - Todos operam no timeframe M5 (period_size=5)
01 Gráfico Central de Monitoramento (Jumba_Portfolio_Live_Monitor)
===================================================================
"""

import os
import shutil

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
MT5_PROJ_DIR = os.path.join(PROJECT_ROOT, "mt5")
MT5_EXP_DIR = os.path.join(MT5_PROJ_DIR, "Experts")
MT5_EXP_SUB = os.path.join(MT5_EXP_DIR, "Jumba_GEX_NWE")
MT5_PRF_DIR = os.path.join(MT5_PROJ_DIR, "Profiles", "Charts")

os.makedirs(MT5_EXP_SUB, exist_ok=True)
os.makedirs(MT5_PRF_DIR, exist_ok=True)

# 1. Garante que os monitores estejam presentes em ambos diretórios
mon_ex5_root = os.path.join(MT5_EXP_DIR, "Jumba_Portfolio_Live_Monitor.ex5")
mon_mq5_root = os.path.join(MT5_EXP_DIR, "Jumba_Portfolio_Live_Monitor.mq5")
if os.path.exists(mon_ex5_root):
    shutil.copy2(mon_ex5_root, os.path.join(MT5_EXP_SUB, "Jumba_Portfolio_Live_Monitor.ex5"))
if os.path.exists(mon_mq5_root):
    shutil.copy2(mon_mq5_root, os.path.join(MT5_EXP_SUB, "Jumba_Portfolio_Live_Monitor.mq5"))

# 2. Definições dos 13 robôs WIN
# (slot_id, ea_name, base_magic, desc, period_size)
WIN_13_SPECS = [
    (1,  "Jumba_EST01_Scalper_Hibrido_NY",      88001, "EST-01 | WIN_PA_PINBAR_WALL (M5 | Magic 88001)",        5),
    (2,  "Jumba_EST02_Scalper_Hibrido_DiaTodo", 88002, "EST-02 | WIN_PA_OUTSIDE_MID (M5 | Magic 88002)",       5),
    (3,  "Jumba_EST03_Scalper_Cambial_WDO",     88003, "EST-03 | WIN_M15_FAKEOUT_TRAP (M15 | Magic 88003)",    15),
    (4,  "Jumba_EST04_Pullback_Reteste_Wall",   88004, "EST-04 | WIN_PA_INSIDE_BREAK (M5 | Magic 88004)",       5),
    (5,  "Jumba_EST05_Pullback_Cluster_NWE",    88005, "EST-05 | WIN_M15_MIDWALL_PULLBACK (M15 | Magic 88005)", 15),
    (6,  "Jumba_EST06_Pullback_Limit_Slope",    88006, "EST-06 | WIN_OF_ABSORPTION (M5 | Magic 88006)",        5),
    (7,  "Jumba_EST07_Breakout_Momentum_NY",    88007, "EST-07 | WIN_OF_CLIMAX_WALL (M5 | Magic 88007)",        5),
    (8,  "Jumba_EST08_Breakout_Rapido_Core",    88008, "EST-08 | WIN_OF_SPRING_UPTHRUST (M5 | Magic 88008)",    5),
    (12, "Jumba_EST12_Piramidacao_Lucro_11L",   88012, "EST-12 | WIN_REG_TREND_WALL (M5 | Magic 88012)",        5),
    (13, "Jumba_EST13_SmartGrid_RSI_BE",        88013, "EST-13 | WIN_SG_SCALPER_3C (M5 | Magic 88013)",         5),
    (14, "Jumba_EST14_Grid_Institucional_123L", 88014, "EST-14 | WIN_SG_MOMENTUM_3C (M5 | Magic 88014)",        5),
    (15, "Jumba_EST15_Posicional_EOD_Breakout", 88015, "EST-15 | WIN_SG_Z30_REV_WALL (M5 | Magic 88015)",       5),
    (16, "Jumba_EST16_Posicional_EOD_Fade",     88016, "EST-16 | WIN_SG_SPRING_Z30_WALL (M5 | Magic 88016)",    5),
]

# 3. Definições dos 9 robôs WDO
WDO_9_SPECS = [
    (1,  "Jumba_WDO01_Scalper_Hibrido_NY",      89000, "WDO-01 | WDO_PA_WALL_SCALPER_NY (M5 | Magic 89001)",   5),
    (2,  "Jumba_WDO02_Scalper_Hibrido_CORE",    89000, "WDO-02 | WDO_PA_OUTSIDE_MID (M5 | Magic 89002)",        5),
    (5,  "Jumba_WDO05_Cluster_NWE30_NWE50",     89000, "WDO-05 | WDO_PA_CLUSTER_NWE (M5 | Magic 89005)",        5),
    (6,  "Jumba_WDO06_Limit_Wall_Rejeicao",     89000, "WDO-06 | WDO_OF_ABSORPTION (M5 | Magic 89006)",         5),
    (7,  "Jumba_WDO07_Absorcao_Mkt_NY",         89000, "WDO-07 | WDO_OF_CLIMAX_WALL (M5 | Magic 89007)",        5),
    (9,  "Jumba_WDO09_Stop_Limit_Wall_NY",      89000, "WDO-09 | WDO_PB_WALL_PULLBACK (M5 | Magic 89009)",      5),
    (10, "Jumba_WDO10_Stop_Limit_Main_Walls",   89000, "WDO-10 | WDO_S2_MIDWALL_Z30 (M5 | Magic 89010)",        5),
    (11, "Jumba_WDO11_Grid_Absorcao_NWE",       89000, "WDO-11 | WDO_REG_PINNED_FADE (M5 | Magic 89011)",       5),
    (15, "Jumba_WDO15_Posicional_EOD_Matinal",  89000, "WDO-15 | WDO_PA_MAINWALL_Z30_REV (M5 | Magic 89015)",   5),
]


def make_robot_chr(chart_id, symbol, desc, digits, tick_size, expert_name, expert_inputs_str, period_size, w_left, w_top, w_right, w_bottom):
    return f"""<chart>
id={chart_id}
symbol={symbol}
description={desc}
period_type=0
period_size={period_size}
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
background_color=16777215
foreground_color=0
barup_color=25600
bardown_color=178
bullcandle_color=25600
bearcandle_color=178
chartline_color=8421504
volumes_color=25600
grid_color=14737632
bidline_color=8421504
askline_color=255
lastline_color=8421504
stops_color=255

<expert>
name=Jumba_GEX_NWE\\{expert_name}
flags=339
window_num=0
<inputs>
{expert_inputs_str}
</inputs>
</expert>

<window>
height=100
fixed_height=-1

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
description=JUMBA QUANT MONITOR LIVE vs BACKTEST (22 ROBOS)
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
window_right=1200
window_bottom=800
window_type=1
background_color=16777215
foreground_color=0
barup_color=25600
bardown_color=178
bullcandle_color=25600
bearcandle_color=178
chartline_color=8421504
volumes_color=25600
grid_color=14737632
bidline_color=8421504
askline_color=255
lastline_color=8421504
stops_color=255

<expert>
name=Jumba_GEX_NWE\\Jumba_Portfolio_Live_Monitor
flags=339
window_num=0
<inputs>
InpWinBaseMagic=88000
InpWdoBaseMagic=89000
InpBtDdReference=1
InpHistorySource=0
InpRefreshSeconds=2
InpHistoryStartDate=2025.01.01 00:00:00
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
height=100
fixed_height=-1

<indicator>
name=Main
path=
apply=1
show_data=0
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


def build_profile_dir(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    order_lines = []

    # Grid de 6 colunas por 4 linhas para os 23 gráficos
    cols = 6
    col_w, row_h = 320, 240

    # Charts 01..13: 13 robôs WIN
    for idx, (slot_id, ea_name, base_magic, desc, period_size) in enumerate(WIN_13_SPECS):
        c_num = idx + 1
        c_fname = f"chart{c_num:02d}.chr"
        order_lines.append(c_fname)
        col = idx % cols
        row = idx // cols
        wl, wt = col * col_w, row * row_h
        wr, wb = wl + col_w, wt + row_h
        inp_str = f"""InpExecMode=0
InpLotMultiplier=1.0
InpMaxDailyLoss=1000.0
InpMagicNumber={base_magic}
InpDrawLevels=true
InpWdoSymbol=WDO$N"""
        chr_txt = make_robot_chr(
            chart_id=145000000000000700 + c_num,
            symbol="WINZ26",
            desc=desc,
            digits=0,
            tick_size="5.000000",
            expert_name=ea_name,
            expert_inputs_str=inp_str,
            period_size=period_size,
            w_left=wl, w_top=wt, w_right=wr, w_bottom=wb,
        )
        with open(os.path.join(target_dir, c_fname), "w", encoding="utf-16") as f:
            f.write(chr_txt)

    # Charts 14..22: 9 robôs WDO
    for w_idx, (slot_id, ea_name, base_magic, desc, period_size) in enumerate(WDO_9_SPECS):
        c_num = 14 + w_idx
        c_fname = f"chart{c_num:02d}.chr"
        order_lines.append(c_fname)
        grid_pos = 13 + w_idx
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
            chart_id=145000000000000700 + c_num,
            symbol="WDOZ26",
            desc=desc,
            digits=1,
            tick_size="0.500000",
            expert_name=ea_name,
            expert_inputs_str=inp_str,
            period_size=period_size,
            w_left=wl, w_top=wt, w_right=wr, w_bottom=wb,
        )
        with open(os.path.join(target_dir, c_fname), "w", encoding="utf-16") as f:
            f.write(chr_txt)

    # Chart 23: Live Monitor Geral
    c23_fname = "chart23.chr"
    order_lines.append(c23_fname)
    with open(os.path.join(target_dir, c23_fname), "w", encoding="utf-16") as f:
        f.write(make_monitor_chr(145000000000000723))

    with open(os.path.join(target_dir, "order.wnd"), "w", encoding="utf-16") as f:
        f.write("\r\n".join(order_lines) + "\r\n")


def main():
    profile_names = [
        "Jumba_22_PORTFOLIO_MASTER",
        "Jumba_18_WF_100TR_MONITOR",
        "Jumba_18_WF_MONITOR_V2",
    ]

    for prf in profile_names:
        p_path = os.path.join(MT5_PRF_DIR, prf)
        build_profile_dir(p_path)

    # Sincroniza em todos os terminais MT5 instalados em %APPDATA%\MetaQuotes\Terminal
    term_root = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
    synced = 0
    if os.path.exists(term_root):
        for d in os.listdir(term_root):
            t_dir = os.path.join(term_root, d)
            mql5_dir = os.path.join(t_dir, "MQL5")
            if not os.path.isdir(mql5_dir):
                continue

            # 1. Copia EAs (.ex5 e .mq5) para Experts e Experts/Jumba_GEX_NWE
            dst_exp_sub = os.path.join(mql5_dir, "Experts", "Jumba_GEX_NWE")
            dst_exp_root = os.path.join(mql5_dir, "Experts")
            os.makedirs(dst_exp_sub, exist_ok=True)
            for f in os.listdir(MT5_EXP_DIR):
                if f.endswith((".ex5", ".mq5")):
                    shutil.copy2(os.path.join(MT5_EXP_DIR, f), os.path.join(dst_exp_sub, f))
                    shutil.copy2(os.path.join(MT5_EXP_DIR, f), os.path.join(dst_exp_root, f))

            # 2. Copia Perfis
            for prf_dst_base in (os.path.join(mql5_dir, "Profiles", "Charts"), os.path.join(t_dir, "profiles", "Charts")):
                os.makedirs(prf_dst_base, exist_ok=True)
                for prf in profile_names:
                    src_p = os.path.join(MT5_PRF_DIR, prf)
                    dst_p = os.path.join(prf_dst_base, prf)
                    os.makedirs(dst_p, exist_ok=True)
                    for cf in os.listdir(src_p):
                        shutil.copy2(os.path.join(src_p, cf), os.path.join(dst_p, cf))

            synced += 1

    print(f"[OK] Gerados perfis de 22 robôs + Monitor (23 gráficos) e sincronizados em {synced} terminais MT5.")


if __name__ == "__main__":
    main()

