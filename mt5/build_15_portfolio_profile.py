"""
GERADOR OFICIAL DE PERFIL MT5 - JUMBA 11 OOS+ ELITE (11 ROBÔS + MONITOR · PROPOSTA B)
==============================================================================
08 Robôs WIN OOS+ (EST-01, EST-03, EST-04, EST-05, EST-07, EST-13, EST-14, EST-15)
   - EST-03 e EST-05 operam no timeframe M15 (period_size=15)
   - Demais robôs WIN operam no timeframe M5 (period_size=5)
03 Robôs WDO OOS+ (WDO-01, WDO-05, WDO-07)
   - Todos operam no timeframe M5 (period_size=5)
01 Gráfico Central de Monitoramento (Jumba_Portfolio_Live_Monitor)
Total: 12 janelas dispostas em grade de 4 colunas x 3 linhas.
==============================================================================
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

# 1. Garante que todos os .ex5 e .mq5 da raiz Experts estejam também em Experts/Jumba_GEX_NWE
for f in os.listdir(MT5_EXP_DIR):
    if f.endswith((".ex5", ".mq5")):
        shutil.copy2(os.path.join(MT5_EXP_DIR, f), os.path.join(MT5_EXP_SUB, f))

# 2. Definições dos 8 robôs WIN OOS+ aprovados (MT5 Proposta B ⭐)
# (slot_id, ea_name, magic, desc, period_size)
WIN_8_SPECS = [
    (1,  "Jumba_EST01_Scalper_Hibrido_NY",      88001, "EST-01 M5",  5),
    (3,  "Jumba_EST03_Scalper_Cambial_WDO",     88003, "EST-03 M15", 15),
    (4,  "Jumba_EST04_Pullback_Reteste_Wall",   88004, "EST-04 M5",  5),
    (5,  "Jumba_EST05_Pullback_Cluster_NWE",    88005, "EST-05 M15", 15),
    (7,  "Jumba_EST07_Breakout_Momentum_NY",    88007, "EST-07 M5",  5),
    (13, "Jumba_EST13_SmartGrid_RSI_BE",        88013, "EST-13 M5",  5),
    (14, "Jumba_EST14_Grid_Institucional_123L", 88014, "EST-14 M5",  5),
    (15, "Jumba_EST15_Posicional_EOD_Breakout", 88015, "EST-15 M5",  5),
]

# 3. Definições dos 3 robôs WDO OOS+ aprovados (MT5 Proposta B ⭐)
WDO_3_SPECS = [
    (1,  "Jumba_WDO01_Scalper_Hibrido_NY",      89000, "WDO-01 M5",  5),
    (5,  "Jumba_WDO05_Cluster_NWE30_NWE50",     89000, "WDO-05 M5",  5),
    (7,  "Jumba_WDO07_Absorcao_Mkt_NY",         89000, "WDO-07 M5",  5),
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
ohlc=0
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


def make_monitor_chr(chart_id, w_left, w_top, w_right, w_bottom):
    return f"""<chart>
id={chart_id}
symbol=WINZ26
description=JUMBA QUANT MONITOR LIVE vs BACKTEST (11 ROBOS OOS+ · PROPOSTA B)
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


def build_15_profile_dir(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    for f in os.listdir(target_dir):
        if f.endswith((".chr", ".wnd")):
            os.remove(os.path.join(target_dir, f))

    order_lines = []
    cols = 4
    col_w = 340
    row_h = 280
    chart_counter = 0

    # Charts 01..08: 8 WIN robots (MT5 Proposta B ⭐)
    for slot_id, ea_name, magic, desc, period_size in WIN_8_SPECS:
        chart_counter += 1
        c_fname = f"chart{chart_counter:02d}.chr"
        order_lines.append(c_fname)
        grid_pos = chart_counter - 1
        col = grid_pos % cols
        row = grid_pos // cols
        wl, wt = col * col_w, row * row_h
        wr, wb = wl + col_w, wt + row_h
        inp_str = f"""InpExecMode=1
InpLotMultiplier=1.0
InpMaxDailyLoss=1000.0
InpMagicNumber={magic}
InpDrawLevels=true
InpWdoSymbol=WDOZ26"""
        chr_txt = make_robot_chr(
            chart_id=146000000000000900 + chart_counter,
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

    # Charts 09..11: 3 WDO robots (MT5 Proposta B ⭐)
    for slot_id, ea_name, base_magic, desc, period_size in WDO_3_SPECS:
        chart_counter += 1
        c_fname = f"chart{chart_counter:02d}.chr"
        order_lines.append(c_fname)
        grid_pos = chart_counter - 1
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
            chart_id=146000000000000900 + chart_counter,
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

    # Chart 12: Live Monitor Geral (Jumba 11 OOS+ Proposta B)
    chart_counter += 1
    c_fname = f"chart{chart_counter:02d}.chr"
    order_lines.append(c_fname)
    grid_pos = chart_counter - 1
    col = grid_pos % cols
    row = grid_pos // cols
    wl, wt = col * col_w, row * row_h
    wr, wb = wl + col_w, wt + row_h
    with open(os.path.join(target_dir, c_fname), "w", encoding="utf-16") as f:
        f.write(make_monitor_chr(146000000000000912, wl, wt, wr, wb))

    with open(os.path.join(target_dir, "order.wnd"), "w", encoding="utf-16") as f:
        f.write("\r\n".join(order_lines) + "\r\n")


def main():
    profile_names = [
        "Jumba_11_OOS_ELITE",
        "Jumba_11_CARTEIRA_ALINHADA",
        "Jumba_15_CARTEIRA_V2",
        "Jumba_15_CARTEIRA_ALINHADA",
        "Jumba_18_WF_100TR_MONITOR",
        "Jumba_18_WF_MONITOR_V2",
    ]

    for prf in profile_names:
        p_path = os.path.join(MT5_PRF_DIR, prf)
        if os.path.exists(p_path):
            shutil.rmtree(p_path)
        build_15_profile_dir(p_path)

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
            for f in os.listdir(MT5_EXP_SUB):
                if f.endswith((".ex5", ".mq5")):
                    shutil.copy2(os.path.join(MT5_EXP_SUB, f), os.path.join(dst_exp_sub, f))
                    shutil.copy2(os.path.join(MT5_EXP_SUB, f), os.path.join(dst_exp_root, f))

            # 2. Copia Perfis
            for prf_dst_base in (os.path.join(mql5_dir, "Profiles", "Charts"), os.path.join(t_dir, "profiles", "Charts")):
                os.makedirs(prf_dst_base, exist_ok=True)
                for prf in profile_names:
                    src_p = os.path.join(MT5_PRF_DIR, prf)
                    dst_p = os.path.join(prf_dst_base, prf)
                    if os.path.exists(dst_p):
                        shutil.rmtree(dst_p)
                    os.makedirs(dst_p, exist_ok=True)
                    for cf in os.listdir(src_p):
                        shutil.copy2(os.path.join(src_p, cf), os.path.join(dst_p, cf))

            synced += 1

    print(f"[OK] Gerados perfis JUMBA 15 com EAs anexados (path=Experts\\Jumba_GEX_NWE\\*.ex5, expertmode=5) e sincronizados em {synced} terminais MT5.")


if __name__ == "__main__":
    main()
