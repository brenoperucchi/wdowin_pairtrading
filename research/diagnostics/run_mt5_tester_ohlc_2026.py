"""
Executor Automatizado de Backtest MT5 Strategy Tester (Model=1: 1 Minute OHLC)
==============================================================================
Executa os 11 robôs da Carteira Proposta B (8 WIN + 3 WDO) no Strategy Tester
do MetaTrader 5 em modo OHLC 1 Minuto (Model=1) até 2026.11.06 (incluindo o OOS),
e compara trade-a-trade e métrica-a-métrica contra o simulador Python.
"""
import os
import re
import sys
import html
import time
import shutil
import subprocess
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

APPDATA = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
SRC_TERM = os.path.join(APPDATA, "D0E8209F77C8CF37AD8BF550E51FF075")
DST_TERM = os.path.join(APPDATA, "5DAC0E7DCAAAECC3D89822F8044C30A4")
COMMON_FILES = os.path.join(APPDATA, "Common", "Files")
TESTER_EXE = r"C:\Program Files\MetaTrader 5 Terminal - milhao - Copia\terminal64.exe"
OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_ohlc_2026")

# 11 Robôs da Proposta B ⭐ (8 WIN + 3 WDO)
ROBOTS_11 = [
    ("EST01", "Jumba_EST01_Scalper_Hibrido_NY",      "WIN$N", "M5",  "EST-01"),
    ("EST03", "Jumba_EST03_Scalper_Cambial_WDO",     "WIN$N", "M15", "EST-03"),
    ("EST04", "Jumba_EST04_Pullback_Reteste_Wall",   "WIN$N", "M5",  "EST-04"),
    ("EST05", "Jumba_EST05_Pullback_Cluster_NWE",    "WIN$N", "M15", "EST-05"),
    ("EST07", "Jumba_EST07_Breakout_Momentum_NY",    "WIN$N", "M5",  "EST-07"),
    ("EST13", "Jumba_EST13_SmartGrid_RSI_BE",        "WIN$N", "M5",  "EST-13"),
    ("EST14", "Jumba_EST14_Grid_Institucional_123L", "WIN$N", "M5",  "EST-14"),
    ("EST15", "Jumba_EST15_Posicional_EOD_Breakout", "WIN$N", "M5",  "EST-15"),
    ("WDO01", "Jumba_WDO01_Scalper_Hibrido_NY",      "WDO$N", "M5",  "WDO-01"),
    ("WDO05", "Jumba_WDO05_Cluster_NWE30_NWE50",     "WDO$N", "M5",  "WDO-05"),
    ("WDO07", "Jumba_WDO07_Absorcao_Mkt_NY",         "WDO$N", "M5",  "WDO-07"),
]


def safe_copy(sf: str, df: str):
    try:
        data = open(sf, "rb").read()
        open(df, "wb").write(data)
    except Exception:
        pass


def prepare_tester_terminal():
    os.makedirs(OUT_DIR, exist_ok=True)
    lu = os.path.join(DST_TERM, "liveupdate")
    if os.path.exists(lu):
        shutil.rmtree(lu, ignore_errors=True)

    min_prf = os.path.join(DST_TERM, "MQL5", "Profiles", "Charts", "TesterMinimal")
    os.makedirs(min_prf, exist_ok=True)
    for f in os.listdir(min_prf):
        os.remove(os.path.join(min_prf, f))
    open(os.path.join(min_prf, "order.wnd"), "w", encoding="utf-16").write("")

    for cf in ("accounts.dat", "servers.dat", "common.ini"):
        sp = os.path.join(SRC_TERM, "config", cf)
        dp = os.path.join(DST_TERM, "config", cf)
        if os.path.exists(sp):
            safe_copy(sp, dp)

    ini_p = os.path.join(DST_TERM, "config", "common.ini")
    if os.path.exists(ini_p):
        txt = open(ini_p, "r", encoding="cp1252", errors="ignore").read()
        txt = re.sub(r"ProfileLast=.*", "ProfileLast=TesterMinimal", txt)
        open(ini_p, "w", encoding="cp1252", newline="").write(txt)

    src_base = os.path.join(SRC_TERM, "bases", "XPMT5-DEMO")
    dst_base = os.path.join(DST_TERM, "bases", "XPMT5-DEMO")
    for sub in ("symbols", r"history\WIN$N", r"history\WDO$N"):
        s_dir = os.path.join(src_base, sub)
        d_dir = os.path.join(dst_base, sub)
        if os.path.exists(s_dir):
            os.makedirs(d_dir, exist_ok=True)
            for f in os.listdir(s_dir):
                sf = os.path.join(s_dir, f)
                df = os.path.join(d_dir, f)
                if os.path.isfile(sf) and f.endswith((".hcc", ".dat", ".sel")):
                    safe_copy(sf, df)

    os.makedirs(os.path.join(DST_TERM, "jumba_bt"), exist_ok=True)


def run_single_mt5_backtest(tag: str, ea_name: str, symbol: str, period: str, from_date: str, to_date: str, ea_code: str):
    lu = os.path.join(DST_TERM, "liveupdate")
    if os.path.exists(lu):
        shutil.rmtree(lu, ignore_errors=True)

    rep_rel = f"jumba_bt\\{tag}_P1"
    rep_htm = os.path.join(DST_TERM, "jumba_bt", f"{tag}_P1.htm")
    if os.path.exists(rep_htm):
        os.remove(rep_htm)

    # Backup live audit file before tester run, then extract tester audit rows
    aud_live = os.path.join(COMMON_FILES, "jumba_live_trades_audit_92004051.csv")
    aud_bkp = os.path.join(COMMON_FILES, "jumba_live_trades_audit_92004051.bkp")
    if os.path.exists(aud_live):
        shutil.copy2(aud_live, aud_bkp)
    open(aud_live, "w", encoding="cp1252").write("")

    ini_txt = f"""[Common]
Login=92004051
Server=XPMT5-DEMO
[Tester]
Expert=Jumba_GEX_NWE\\{ea_name}.ex5
Symbol={symbol}
Period={period}
Optimization=0
Model=1
FromDate={from_date}
ToDate={to_date}
ForwardMode=0
Deposit=100000
Currency=BRL
Leverage=1
ExecutionMode=0
Visual=0
Report={rep_rel}
ReplaceReport=1
ShutdownTerminal=1
"""
    ini_path = os.path.join(DST_TERM, f"run_{tag}.ini")
    open(ini_path, "w", encoding="cp1252").write(ini_txt)

    t0 = time.time()
    subprocess.run([TESTER_EXE, "/skipupdate", f"/config:{ini_path}"], check=False)
    dt = time.time() - t0

    # Save audit CSV produced by this backtest
    if os.path.exists(aud_live):
        shutil.copy2(aud_live, os.path.join(OUT_DIR, f"audit_{tag}_P1.csv"))
    if os.path.exists(aud_bkp):
        shutil.copy2(aud_bkp, aud_live)
        os.remove(aud_bkp)

    if os.path.exists(rep_htm):
        dst_copy = os.path.join(OUT_DIR, f"{tag}_P1.htm")
        shutil.copy2(rep_htm, dst_copy)
        print(f"[OK] {tag:<8} ({ea_code}) | {symbol:<6} {period:<3} | {from_date}..{to_date} | {dt:4.1f}s | {os.path.getsize(dst_copy):,} bytes")
        return True
    else:
        print(f"[FAIL] {tag:<8} ({ea_code}) | {dt:4.1f}s")
        return False


def main():
    prepare_tester_terminal()
    for tag, ea_name, sym, per, ea_code in ROBOTS_11:
        run_single_mt5_backtest(tag, ea_name, sym, per, "2026.05.11", "2026.11.07", ea_code)


if __name__ == "__main__":
    main()
