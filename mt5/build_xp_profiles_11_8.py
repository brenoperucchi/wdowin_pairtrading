# -*- coding: utf-8 -*-
"""
Atualiza todos os EAs individuais WIN (EST-01..16) e WDO (WDO-01..16) com o input
`InpUseFlowFilter` (Filtro de Fluxo Institucional Nativo via CopyTicksRange),
recompila todos os .ex5 sem tocar nos terminais abertos, e cria/sincroniza os perfis:
  - Jumba_11_SEM_FILTRO (11 Robôs M5 s/ Filtro + Monitor Live)
  - Jumba_11_COM_FILTRO (11 Robôs M5 c/ Filtro Nativo + Monitor Live)
  - Jumba_8_COM_FILTRO  (8 Robôs Campeões c/ Filtro Nativo + Monitor Live)
  - Jumba_8_SEM_FILTRO  (8 Robôs Campeões s/ Filtro + Monitor Live)
em todos os terminais MT5 (incluindo XP).
"""
import os
import glob
import shutil
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MT5_DIR = os.path.join(ROOT_DIR, "mt5")
EXPERTS_DIR = os.path.join(MT5_DIR, "Experts")
SUB_EXPERTS_DIR = os.path.join(EXPERTS_DIR, "Jumba_GEX_NWE")
INCLUDE_DIR = os.path.join(MT5_DIR, "Include")
PROFILES_DIR = os.path.join(MT5_DIR, "Profiles", "Charts")

METAEDITOR = r"C:\Program Files\MetaTrader 5\metaeditor64.exe"
if not os.path.isfile(METAEDITOR):
    for cand in [
        r"C:\Program Files\MetaTrader 5 Terminal\metaeditor64.exe",
        r"C:\Program Files\MetaTrader 5btg\metaeditor64.exe",
    ]:
        if os.path.isfile(cand):
            METAEDITOR = cand
            break


def patch_mq5_file(filepath: str) -> bool:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()

    if "InpUseFlowFilter" in code:
        return False

    base = os.path.basename(filepath)
    if base.startswith("Jumba_EST"):
        # Insert input bool InpUseFlowFilter after InpWdoSymbol
        target_in = 'input string              InpWdoSymbol     = "WDO$N"; // Símbolo do Dólar (se usado)'
        replacement_in = (
            target_in
            + "\ninput bool                InpUseFlowFilter = false;   // Filtro de Fluxo Institucional Nativo (CopyTicks)"
        )
        if target_in not in code:
            # Fallback: insert before CJumbaGexNweEngine g_engine;
            code = code.replace(
                "CJumbaGexNweEngine g_engine;",
                "input bool                InpUseFlowFilter = false;   // Filtro de Fluxo Institucional Nativo (CopyTicks)\n\nCJumbaGexNweEngine g_engine;",
            )
        else:
            code = code.replace(target_in, replacement_in)

        # Call g_engine.SetUseFlowFilter(InpUseFlowFilter); in OnInit()
        code = code.replace(
            "   return(INIT_SUCCEEDED);",
            "   g_engine.SetUseFlowFilter(InpUseFlowFilter);\n   return(INIT_SUCCEEDED);",
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return True

    elif base.startswith("Jumba_WDO") and "Portfolio_Master" not in base:
        target_in = "input bool                     InpShowHud          = true;                         // Mostrar Painel HUD"
        replacement_in = (
            target_in
            + "\ninput bool                     InpUseFlowFilter    = false;                        // Filtro de Fluxo Institucional Nativo (CopyTicks)"
        )
        if target_in not in code:
            code = code.replace(
                "CJumbaWdoGexNweEngine ExtEngine;",
                "input bool                     InpUseFlowFilter    = false;                        // Filtro de Fluxo Institucional Nativo (CopyTicks)\n\nCJumbaWdoGexNweEngine ExtEngine;",
            )
        else:
            code = code.replace(target_in, replacement_in)

        code = code.replace(
            "   return(INIT_SUCCEEDED);",
            "   ExtEngine.SetUseFlowFilter(InpUseFlowFilter);\n   return(INIT_SUCCEEDED);",
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return True

    return False


def update_and_compile_all():
    # 1. Patch all Jumba_EST*.mq5 and Jumba_WDO*.mq5 in Experts/ and Experts/Jumba_GEX_NWE/
    mq5_files = sorted(
        glob.glob(os.path.join(EXPERTS_DIR, "Jumba_EST*.mq5"))
        + glob.glob(os.path.join(EXPERTS_DIR, "Jumba_WDO*.mq5"))
    )
    for fp in mq5_files:
        patched = patch_mq5_file(fp)
        # Copy identical source to SUB_EXPERTS_DIR if it exists there
        sub_fp = os.path.join(SUB_EXPERTS_DIR, os.path.basename(fp))
        shutil.copy2(fp, sub_fp)

    # 2. Sync Include/*.mqh and Experts/*.mq5 to primary terminal MQL5 folder for compilation
    appdata = os.environ.get("APPDATA", "")
    term_dirs = [
        d for d in glob.glob(os.path.join(appdata, "MetaQuotes", "Terminal", "*"))
        if os.path.isdir(os.path.join(d, "MQL5"))
    ]
    if not term_dirs:
        raise RuntimeError("Nenhum diretório MQL5 encontrado em %APPDATA%\\MetaQuotes\\Terminal")

    primary_mql5 = os.path.join(term_dirs[0], "MQL5")
    for td in term_dirs:
        if "D0E8209F77C8CF37AD8BF550E51FF075" in td:
            primary_mql5 = os.path.join(td, "MQL5")
        inc_d = os.path.join(td, "MQL5", "Include")
        os.makedirs(inc_d, exist_ok=True)
        for mqh in glob.glob(os.path.join(INCLUDE_DIR, "*.mqh")):
            shutil.copy2(mqh, os.path.join(inc_d, os.path.basename(mqh)))

    os.makedirs(os.path.join(primary_mql5, "Experts", "Jumba_GEX_NWE"), exist_ok=True)
    compiled_count = 0
    for fp in mq5_files:
        base = os.path.basename(fp)
        dst_mq5 = os.path.join(primary_mql5, "Experts", base)
        shutil.copy2(fp, dst_mq5)
        log_fp = dst_mq5 + ".log"
        if os.path.exists(log_fp):
            os.remove(log_fp)
        subprocess.run([METAEDITOR, f"/compile:{dst_mq5}", f"/log:{log_fp}"], check=False)
        ex5_fp = dst_mq5[:-4] + ".ex5"
        if not os.path.isfile(ex5_fp):
            log_txt = ""
            if os.path.isfile(log_fp):
                log_txt = open(log_fp, "rb").read().decode("utf-16", errors="ignore")
            raise RuntimeError(f"Falha ao compilar {base}:\n{log_txt}")
        # Copy compiled .ex5 back to repo Experts/ and Experts/Jumba_GEX_NWE/
        shutil.copy2(ex5_fp, os.path.join(EXPERTS_DIR, os.path.basename(ex5_fp)))
        shutil.copy2(ex5_fp, os.path.join(SUB_EXPERTS_DIR, os.path.basename(ex5_fp)))
        compiled_count += 1

    print(f"[OK] {compiled_count} EAs recompilados com InpUseFlowFilter nativo (0 erros).")
    return term_dirs


ROBOT_SPECS = {
    "EST_01": ("WIN", 88001, 5, "EST-01 M5", "Jumba_EST01_Scalper_Hibrido_NY"),
    "EST_04": ("WIN", 88004, 5, "EST-04 M5", "Jumba_EST04_Pullback_Reteste_Wall"),
    "EST_07": ("WIN", 88007, 5, "EST-07 M5", "Jumba_EST07_Breakout_Momentum_NY"),
    "EST_13": ("WIN", 88013, 5, "EST-13 M5", "Jumba_EST13_SmartGrid_RSI_BE"),
    "EST_14": ("WIN", 88014, 5, "EST-14 M5", "Jumba_EST14_Grid_Institucional_123L"),
    "EST_15": ("WIN", 88015, 5, "EST-15 M5", "Jumba_EST15_Posicional_EOD_Breakout"),
    "EST_16": ("WIN", 88016, 5, "EST-16 M5", "Jumba_EST16_Posicional_EOD_Reversion"),
    "WDO_01": ("WDO", 89001, 5, "WDO-01 M5", "Jumba_WDO01_Scalper_Hibrido_NY"),
    "WDO_05": ("WDO", 89005, 5, "WDO-05 M5", "Jumba_WDO05_Cluster_NWE30_NWE50"),
    "WDO_07": ("WDO", 89007, 5, "WDO-07 M5", "Jumba_WDO07_Absorcao_Mkt_NY"),
    "WDO_09": ("WDO", 89009, 5, "WDO-09 M5", "Jumba_WDO09_Breakout_Stop_Limit_NY"),
}


def make_chart_chr(
    chart_id: int,
    symbol: str,
    title: str,
    period_size: int,
    ea_name: str,
    ea_inputs: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
    include_indicators: bool = True,
) -> str:
    is_wdo = symbol.startswith("WDO")
    digits = 1 if is_wdo else 0
    tick_size = "0.500000" if is_wdo else "5.000000"

    ind_block = ""
    if include_indicators:
        ind_block = """
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
</indicator>"""

    content = f"""<chart>
id={chart_id}
symbol={symbol}
description={title}
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
window_left={left}
window_top={top}
window_right={right}
window_bottom={bottom}
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
name={ea_name}
path=Experts\\Jumba_GEX_NWE\\{ea_name}.ex5
expertmode=5
<inputs>
{ea_inputs}
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
</indicator>{ind_block}
</window>
</chart>
"""
    return content.replace("\r\n", "\n").replace("\n", "\r\n")


def build_profile(profile_name: str, robot_ids: list, use_flow_filter: bool, win_sym: str = "WINZ26", wdo_sym: str = "WDOZ26"):
    out_dir = os.path.join(PROFILES_DIR, profile_name)
    os.makedirs(out_dir, exist_ok=True)
    for old_f in glob.glob(os.path.join(out_dir, "*")):
        if os.path.isfile(old_f):
            os.remove(old_f)

    total_charts = len(robot_ids) + 1  # +1 Monitor chart
    cols = 3 if total_charts <= 9 else 4
    rows = (total_charts + cols - 1) // cols
    cell_w = 1360 // cols
    cell_h = 840 // rows

    flow_str = "true" if use_flow_filter else "false"
    flow_tag = "COM FILTRO FLUXO" if use_flow_filter else "SEM FILTRO"

    order_lines = []
    for idx, rid in enumerate(robot_ids, start=1):
        asset, magic, tf_min, base_desc, ea_name = ROBOT_SPECS[rid]
        sym = win_sym if asset == "WIN" else wdo_sym
        r_idx = (idx - 1) // cols
        c_idx = (idx - 1) % cols
        left = c_idx * cell_w
        top = r_idx * cell_h
        right = left + cell_w
        bottom = top + cell_h

        chart_id = 148000000000000000 + idx
        desc = f"{base_desc} [{flow_tag}]"

        if asset == "WIN":
            ea_inputs = f"""InpExecMode=1
InpLotMultiplier=1.0
InpMaxDailyLoss=1000.0
InpMagicNumber={magic}
InpDrawLevels=true
InpWdoSymbol={wdo_sym}
InpUseFlowFilter={flow_str}"""
        else:
            ea_inputs = f"""InpBaseMagic=89000
InpLotMultiplier=1.0
InpMaxDailyLossBRL=2000.0
InpExecMode=0
InpDrawGexLevels=true
InpShowHud=true
InpUseFlowFilter={flow_str}"""

        chr_text = make_chart_chr(
            chart_id=chart_id,
            symbol=sym,
            title=desc,
            period_size=tf_min,
            ea_name=ea_name,
            ea_inputs=ea_inputs,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            include_indicators=True,
        )
        chr_fn = f"chart{idx:02d}.chr"
        with open(os.path.join(out_dir, chr_fn), "wb") as f:
            f.write(b"\xff\xfe" + chr_text.encode("utf-16-le"))
        order_lines.append(chr_fn)

    # Last chart: Jumba_Portfolio_Live_Monitor
    m_idx = len(robot_ids) + 1
    r_idx = (m_idx - 1) // cols
    c_idx = (m_idx - 1) % cols
    left = c_idx * cell_w
    top = r_idx * cell_h
    right = left + cell_w
    bottom = top + cell_h
    mon_id = 148000000000000000 + m_idx
    mon_title = f"JUMBA MONITOR LIVE ({len(robot_ids)} ROBOS {flow_tag})"
    mon_inputs = """InpWinBaseMagic=88000
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
InpFontSize=8"""

    mon_text = make_chart_chr(
        chart_id=mon_id,
        symbol=win_sym,
        title=mon_title,
        period_size=5,
        ea_name="Jumba_Portfolio_Live_Monitor",
        ea_inputs=mon_inputs,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        include_indicators=False,
    )
    mon_fn = f"chart{m_idx:02d}.chr"
    with open(os.path.join(out_dir, mon_fn), "wb") as f:
        f.write(b"\xff\xfe" + mon_text.encode("utf-16-le"))
    order_lines.append(mon_fn)

    order_txt = "\r\n".join(order_lines) + "\r\n"
    with open(os.path.join(out_dir, "order.wnd"), "wb") as f:
        f.write(b"\xff\xfe" + order_txt.encode("utf-16-le"))

    print(f"[OK] Perfil '{profile_name}' gerado com {m_idx} gráficos ({len(robot_ids)} robôs + Monitor | InpUseFlowFilter={flow_str}).")
    return out_dir


def sync_everything_to_terminals(term_dirs: list, profile_names: list):
    for tdir in term_dirs:
        mql5_dir = os.path.join(tdir, "MQL5")
        if not os.path.isdir(mql5_dir):
            continue

        # 1. Sync Include/*.mqh
        inc_dst = os.path.join(mql5_dir, "Include")
        os.makedirs(inc_dst, exist_ok=True)
        for mqh in glob.glob(os.path.join(INCLUDE_DIR, "*.mqh")):
            shutil.copy2(mqh, os.path.join(inc_dst, os.path.basename(mqh)))

        # 2. Sync Experts/*.ex5 and Experts/Jumba_GEX_NWE/*.ex5
        exp_dst = os.path.join(mql5_dir, "Experts")
        sub_dst = os.path.join(exp_dst, "Jumba_GEX_NWE")
        os.makedirs(sub_dst, exist_ok=True)
        for f in glob.glob(os.path.join(EXPERTS_DIR, "Jumba_*.*")):
            if f.endswith((".mq5", ".ex5")):
                shutil.copy2(f, os.path.join(exp_dst, os.path.basename(f)))
                shutil.copy2(f, os.path.join(sub_dst, os.path.basename(f)))

        # 3. Sync Profiles to both MQL5/Profiles/Charts and profiles/Charts
        for prof_sub in [
            os.path.join(mql5_dir, "Profiles", "Charts"),
            os.path.join(tdir, "profiles", "Charts"),
        ]:
            os.makedirs(prof_sub, exist_ok=True)
            for pname in profile_names:
                src_p = os.path.join(PROFILES_DIR, pname)
                dst_p = os.path.join(prof_sub, pname)
                if os.path.exists(dst_p):
                    shutil.rmtree(dst_p)
                shutil.copytree(src_p, dst_p)

        orig_file = os.path.join(tdir, "origin.txt")
        orig_txt = ""
        if os.path.isfile(orig_file):
            orig_txt = open(orig_file, "rb").read().decode("utf-16", errors="ignore").strip()
        print(f"  -> Sincronizado em {os.path.basename(tdir)} ({orig_txt})")


if __name__ == "__main__":
    term_dirs = update_and_compile_all()

    SIDS_8 = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"]
    SIDS_11 = ["EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "EST_16", "WDO_01", "WDO_05", "WDO_07", "WDO_09"]

    profiles_to_build = [
        ("Jumba_11_SEM_FILTRO", SIDS_11, False),
        ("Jumba_8_COM_FILTRO",  SIDS_8,  True),
        ("Jumba_8_SEM_FILTRO",  SIDS_8,  False),
        ("Jumba_11_COM_FILTRO", SIDS_11, True),
    ]

    built_names = []
    for pname, rids, use_flow in profiles_to_build:
        build_profile(pname, rids, use_flow)
        built_names.append(pname)

    sync_everything_to_terminals(term_dirs, built_names)
    print("\n[SUCESSO TOTAL] Todos os perfis e robôs compilados foram instalados nos MT5!")
