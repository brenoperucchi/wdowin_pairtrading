# -*- coding: utf-8 -*-
"""
Magic Walls — Compilador de EAs/Indicadores MT5 e Gerador de Perfis (MagicWalls_8 e MagicWalls_10).
Compila todos os EAs MagicWalls_*.mq5 + Indicadores MagicWalls_*.mq5 (0 erros),
migra os CSVs de Common\\Files para magicwalls_* (sem perder historico ao vivo),
gera APENAS os perfis MagicWalls_8 e MagicWalls_10 e sincroniza nos terminais MT5
(removendo perfis/arquivos antigos Jumba_* de forma segura sem tocar nos processos abertos).
"""
import os
import glob
import shutil
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MT5_DIR = os.path.join(ROOT_DIR, "mt5")
EXPERTS_DIR = os.path.join(MT5_DIR, "Experts")
SUB_EXPERTS_DIR = os.path.join(EXPERTS_DIR, "MagicWalls")
IND_SUB_DIR = os.path.join(MT5_DIR, "Indicators", "MagicWalls")
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


def migrate_common_files():
    """Copia jumba_* -> magicwalls_* em Common\\Files se ainda nao existir ou estiver mais antigo."""
    appdata = os.environ.get("APPDATA", "")
    common_dir = os.path.join(appdata, "MetaQuotes", "Terminal", "Common", "Files")
    if not os.path.isdir(common_dir):
        return
    copied = 0
    for fn in os.listdir(common_dir):
        if fn.startswith("jumba_"):
            src = os.path.join(common_dir, fn)
            dst = os.path.join(common_dir, fn.replace("jumba_", "magicwalls_", 1))
            if os.path.isfile(src):
                if (not os.path.exists(dst)) or (os.path.getmtime(src) > os.path.getmtime(dst)):
                    try:
                        shutil.copy2(src, dst)
                        copied += 1
                    except Exception:
                        pass
    print(f"[OK] Common\\Files migrado: {copied} arquivos copiados para magicwalls_*.")


def compile_file(metaeditor: str, dst_mq5: str) -> str:
    log_fp = dst_mq5 + ".log"
    if os.path.exists(log_fp):
        os.remove(log_fp)
    subprocess.run([metaeditor, f"/compile:{dst_mq5}", f"/log:{log_fp}"], check=False)
    ex5_fp = dst_mq5[:-4] + ".ex5"
    log_txt = ""
    if os.path.isfile(log_fp):
        log_txt = open(log_fp, "rb").read().decode("utf-16", errors="ignore")
    if (not os.path.isfile(ex5_fp)) or ("0 errors" not in log_txt and "0 error(s)" not in log_txt):
        raise RuntimeError(f"Falha ao compilar {os.path.basename(dst_mq5)}:\n{log_txt}")
    return ex5_fp


def update_and_compile_all():
    os.makedirs(SUB_EXPERTS_DIR, exist_ok=True)
    os.makedirs(IND_SUB_DIR, exist_ok=True)

    mq5_experts = sorted(glob.glob(os.path.join(SUB_EXPERTS_DIR, "MagicWalls_*.mq5")))
    mq5_inds = sorted(glob.glob(os.path.join(IND_SUB_DIR, "MagicWalls_*.mq5")))

    # Espelha fontes tambem em mt5/Experts/
    for fp in mq5_experts:
        shutil.copy2(fp, os.path.join(EXPERTS_DIR, os.path.basename(fp)))

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
        for mqh in glob.glob(os.path.join(INCLUDE_DIR, "MagicWalls_*.mqh")):
            shutil.copy2(mqh, os.path.join(inc_d, os.path.basename(mqh)))

    os.makedirs(os.path.join(primary_mql5, "Experts", "MagicWalls"), exist_ok=True)
    os.makedirs(os.path.join(primary_mql5, "Indicators", "MagicWalls"), exist_ok=True)

    # 1. Compila todos os EAs MagicWalls_*.mq5
    compiled_eas = 0
    for fp in mq5_experts:
        base = os.path.basename(fp)
        dst_mq5 = os.path.join(primary_mql5, "Experts", "MagicWalls", base)
        shutil.copy2(fp, dst_mq5)
        ex5_fp = compile_file(METAEDITOR, dst_mq5)
        shutil.copy2(ex5_fp, os.path.join(EXPERTS_DIR, os.path.basename(ex5_fp)))
        shutil.copy2(ex5_fp, os.path.join(SUB_EXPERTS_DIR, os.path.basename(ex5_fp)))
        compiled_eas += 1

    # 2. Compila todos os Indicadores MagicWalls_*.mq5
    compiled_inds = 0
    for fp in mq5_inds:
        base = os.path.basename(fp)
        dst_mq5 = os.path.join(primary_mql5, "Indicators", "MagicWalls", base)
        shutil.copy2(fp, dst_mq5)
        ex5_fp = compile_file(METAEDITOR, dst_mq5)
        shutil.copy2(ex5_fp, os.path.join(IND_SUB_DIR, os.path.basename(ex5_fp)))
        compiled_inds += 1

    print(f"[OK] {compiled_eas} EAs + {compiled_inds} Indicadores Magic Walls compilados (0 erros).")
    return term_dirs


ROBOT_SPECS = {
    "EST_01": ("WIN", 88001, 5, "EST-01 M5", "MagicWalls_EST01_Scalper_Hibrido_NY"),
    "EST_04": ("WIN", 88004, 5, "EST-04 M5", "MagicWalls_EST04_Pullback_Reteste_Wall"),
    "EST_07": ("WIN", 88007, 5, "EST-07 M5", "MagicWalls_EST07_Breakout_Momentum_NY"),
    "EST_09": ("WIN", 88009, 5, "EST-09 M5 [MaxTr=2/d]", "MagicWalls_EST09_Breakout_Stop_Wall"),
    "EST_10": ("WIN", 88010, 5, "EST-10 M5 [MaxTr=1/d]", "MagicWalls_EST10_Breakout_Stop_Wick"),
    "EST_13": ("WIN", 88013, 5, "EST-13 M5", "MagicWalls_EST13_SmartGrid_RSI_BE"),
    "EST_14": ("WIN", 88014, 5, "EST-14 M5", "MagicWalls_EST14_Grid_Institucional_123L"),
    "EST_15": ("WIN", 88015, 5, "EST-15 M5", "MagicWalls_EST15_Posicional_EOD_Breakout"),
    "EST_16": ("WIN", 88016, 5, "EST-16 M5", "MagicWalls_EST16_Posicional_EOD_Fade"),
    "WDO_01": ("WDO", 89001, 5, "WDO-01 M5", "MagicWalls_WDO01_Scalper_Hibrido_NY"),
    "WDO_05": ("WDO", 89005, 5, "WDO-05 M5", "MagicWalls_WDO05_Cluster_NWE30_NWE50"),
    "WDO_07": ("WDO", 89007, 5, "WDO-07 M5", "MagicWalls_WDO07_Absorcao_Mkt_NY"),
    "WDO_09": ("WDO", 89009, 5, "WDO-09 M5", "MagicWalls_WDO09_Stop_Limit_Wall_NY"),
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
path=Indicators\\MagicWalls\\MagicWalls_NWE_Envelope.ex5
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
path=Indicators\\MagicWalls\\MagicWalls_GEX_Ind.ex5
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
path=Experts\\MagicWalls\\{ea_name}.ex5
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


def build_profile(
    profile_name: str,
    robot_ids: list,
    use_flow_filter: bool,
    win_sym: str = "WINZ26",
    wdo_sym: str = "WDOZ26",
    stop_global: float = 950.0,
    stop_win: float = 400.0,
    stop_wdo: float = 0.0,
    win_max_entry: str = "16:00",
    wdo_max_entry: str = "15:00",
):
    out_dir = os.path.join(PROFILES_DIR, profile_name)
    os.makedirs(out_dir, exist_ok=True)
    for old_f in glob.glob(os.path.join(out_dir, "*")):
        if os.path.isfile(old_f):
            os.remove(old_f)

    total_charts = len(robot_ids) + 1
    cols = 3 if total_charts <= 9 else 4
    rows = (total_charts + cols - 1) // cols
    cell_w = 1360 // cols
    cell_h = 840 // rows

    flow_str = "true" if use_flow_filter else "false"
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
        desc = f"{base_desc} [MAGIC WALLS]"

        if asset == "WIN":
            ea_inputs = f"""InpExecMode=1
InpLotMultiplier=1.0
InpMaxDailyLoss=1000.0
InpMagicNumber={magic}
InpDrawLevels=true
InpWdoSymbol={wdo_sym}
InpUseFlowFilter={flow_str}
InpMaxEntryTime={win_max_entry}"""
        else:
            ea_inputs = f"""InpBaseMagic=89000
InpLotMultiplier=1.0
InpMaxDailyLossBRL=2000.0
InpExecMode=0
InpDrawGexLevels=true
InpShowHud=true
InpUseFlowFilter={flow_str}
InpMaxEntryTime={wdo_max_entry}"""

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

    # Ultimo grafico: MagicWalls_Portfolio_Live_Monitor
    m_idx = len(robot_ids) + 1
    r_idx = (m_idx - 1) // cols
    c_idx = (m_idx - 1) % cols
    left = c_idx * cell_w
    top = r_idx * cell_h
    right = left + cell_w
    bottom = top + cell_h
    mon_id = 148000000000000000 + m_idx
    mon_title = f"MAGIC WALLS MONITOR LIVE ({len(robot_ids)} ROBOS)"
    mon_inputs = f"""InpWinBaseMagic=88000
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
InpEnableDailyStop=true
InpMaxDailyLossGlobal={stop_global:.1f}
InpMaxDailyLossWin={stop_win:.1f}
InpMaxDailyLossWdo={stop_wdo:.1f}
InpStopWarningPct=70.0
InpClosePositionsOnStop=true
InpCancelPendingOnStop=true
InpIncludeAllMwMagics=true
InpUseAuctionFilter=true
InpBlockFrom1=08:55
InpBlockTo1=09:02
InpBlockFrom2=17:55
InpBlockTo2=18:35
InpSendPushOnStop=false
InpClearStopOnRemove=false"""

    mon_text = make_chart_chr(
        chart_id=mon_id,
        symbol=win_sym,
        title=mon_title,
        period_size=5,
        ea_name="MagicWalls_Portfolio_Live_Monitor",
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

    print(f"[OK] Perfil '{profile_name}' gerado com {m_idx} gráficos ({len(robot_ids)} robôs + Monitor | Stop={stop_global:.0f}/{stop_win:.0f}/{stop_wdo:.0f}).")
    return out_dir


def safe_remove_path(p: str):
    try:
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.isfile(p):
            os.remove(p)
    except Exception:
        pass


def sync_everything_to_terminals(term_dirs: list, profile_names: list):
    keep_set = set(profile_names)
    for tdir in term_dirs:
        mql5_dir = os.path.join(tdir, "MQL5")
        if not os.path.isdir(mql5_dir):
            continue

        # 1. Include/*.mqh (instala MagicWalls_*.mqh e remove Jumba_*.mqh antigos)
        inc_dst = os.path.join(mql5_dir, "Include")
        os.makedirs(inc_dst, exist_ok=True)
        for old_inc in glob.glob(os.path.join(inc_dst, "Jumba_*.mqh")):
            safe_remove_path(old_inc)
        for mqh in glob.glob(os.path.join(INCLUDE_DIR, "MagicWalls_*.mqh")):
            shutil.copy2(mqh, os.path.join(inc_dst, os.path.basename(mqh)))

        # 2. Experts (instala Experts/MagicWalls/ + Experts/ e limpa Jumba_* antigos)
        exp_dst = os.path.join(mql5_dir, "Experts")
        sub_dst = os.path.join(exp_dst, "MagicWalls")
        os.makedirs(sub_dst, exist_ok=True)
        for f in glob.glob(os.path.join(SUB_EXPERTS_DIR, "MagicWalls_*.*")):
            if f.endswith((".mq5", ".ex5")):
                shutil.copy2(f, os.path.join(exp_dst, os.path.basename(f)))
                shutil.copy2(f, os.path.join(sub_dst, os.path.basename(f)))
        safe_remove_path(os.path.join(exp_dst, "Jumba_GEX_NWE"))
        for old_e in glob.glob(os.path.join(exp_dst, "Jumba_*.*")):
            safe_remove_path(old_e)

        # 3. Indicators (instala Indicators/MagicWalls/ e limpa Indicators/Jumba_GEX_NWE/)
        ind_dst = os.path.join(mql5_dir, "Indicators", "MagicWalls")
        os.makedirs(ind_dst, exist_ok=True)
        for f in glob.glob(os.path.join(IND_SUB_DIR, "MagicWalls_*.*")):
            if f.endswith((".mq5", ".ex5")):
                shutil.copy2(f, os.path.join(ind_dst, os.path.basename(f)))
        safe_remove_path(os.path.join(mql5_dir, "Indicators", "Jumba_GEX_NWE"))

        # 4. Profiles (instala apenas MagicWalls_8 e MagicWalls_10; remove Jumba_* e MagicWalls_* antigos)
        for prof_sub in [
            os.path.join(mql5_dir, "Profiles", "Charts"),
            os.path.join(tdir, "profiles", "Charts"),
        ]:
            os.makedirs(prof_sub, exist_ok=True)
            for existing in os.listdir(prof_sub):
                full_p = os.path.join(prof_sub, existing)
                if os.path.isdir(full_p) and (existing.startswith("Jumba_") or (existing.startswith("MagicWalls_") and existing not in keep_set)):
                    safe_remove_path(full_p)
            for pname in profile_names:
                src_p = os.path.join(PROFILES_DIR, pname)
                dst_p = os.path.join(prof_sub, pname)
                if os.path.exists(dst_p):
                    safe_remove_path(dst_p)
                shutil.copytree(src_p, dst_p)

        orig_file = os.path.join(tdir, "origin.txt")
        orig_txt = ""
        if os.path.isfile(orig_file):
            orig_txt = open(orig_file, "rb").read().decode("utf-16", errors="ignore").strip()
        print(f"  -> Sincronizado em {os.path.basename(tdir)} ({orig_txt})")


if __name__ == "__main__":
    migrate_common_files()
    term_dirs = update_and_compile_all()

    SIDS_8 = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"]
    SIDS_10 = ["EST_04", "EST_07", "EST_09", "EST_10", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"]

    profiles_to_build = [
        ("MagicWalls_8",  SIDS_8,  False, 850.0, 400.0, 550.0),
        ("MagicWalls_10", SIDS_10, False, 950.0, 400.0, 0.0),
    ]

    built_names = []
    for pname, rids, use_flow, sg, sw, sd in profiles_to_build:
        build_profile(pname, rids, use_flow, stop_global=sg, stop_win=sw, stop_wdo=sd)
        built_names.append(pname)

    # Limpar perfis antigos do repositorio mt5/Profiles/Charts
    keep_set = set(built_names)
    for existing in os.listdir(PROFILES_DIR):
        full_p = os.path.join(PROFILES_DIR, existing)
        if os.path.isdir(full_p) and (existing.startswith("Jumba_") or (existing.startswith("MagicWalls_") and existing not in keep_set)):
            safe_remove_path(full_p)

    sync_everything_to_terminals(term_dirs, built_names)
    print("\n[SUCESSO TOTAL] Suite 100% Magic Walls compilada e instalada nos terminais MT5!")
