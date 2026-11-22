"""
Valida no MT5 Strategy Tester REAL (Model=1: 1 Minute OHLC, 2026.01.02..2026.11.06)
todos os 10 robos da carteira `top_10` com o corte horario anti-furia B3
(WDO < 15:00 e WIN < 16:00), comparando Antes vs Depois + simulacao M1 de Stop Diario.
"""
import os
import re
import sys
import time
import json
import shutil
import subprocess
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.stop_diario.data_loader import (
    load_portfolio_trades,
    load_m1_bars,
    PORTFOLIO_PRESETS,
)
from research.stop_diario.engine import (
    build_intraday_days,
    simulate_combined_stops,
)


def summarize_daily_curve(pnls: list[float]) -> dict:
    arr = np.array(pnls, dtype=float)
    total = float(arr.sum()) if len(arr) else 0.0
    eq = np.cumsum(arr)
    peak = np.maximum.accumulate(np.insert(eq, 0, 0.0))[1:]
    dd = float(np.max(peak - eq)) if len(eq) else 0.0
    ret_dd = total / dd if dd > 0 else (99.0 if total > 0 else 0.0)
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    sharpe = (float(np.mean(arr)) / std) * np.sqrt(252.0) if std > 1e-9 else 0.0
    worst = float(np.min(arr)) if len(arr) else 0.0
    return {"total_pnl": total, "max_dd": dd, "ret_dd": ret_dd, "sharpe": sharpe, "worst_day": worst}

APPDATA = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
SRC_TERM = os.path.join(APPDATA, "D0E8209F77C8CF37AD8BF550E51FF075")
DST_TERM = os.path.join(APPDATA, "5DAC0E7DCAAAECC3D89822F8044C30A4")
TESTER_EXE = r"C:\Program Files\MetaTrader 5 Terminal - milhao - Copia\terminal64.exe"
OLD_DIR = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_ohlc_2026")
NEW_DIR = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_ohlc_2026_b3")

ROBOTS_TOP10 = [
    ("EST04", "Jumba_EST04_Pullback_Reteste_Wall",   "WIN$N", "M5", "EST-04", "WIN"),
    ("EST07", "Jumba_EST07_Breakout_Momentum_NY",    "WIN$N", "M5", "EST-07", "WIN"),
    ("EST09", "Jumba_EST09_Breakout_Stop_Wall",      "WIN$N", "M5", "EST-09", "WIN"),
    ("EST10", "Jumba_EST10_Breakout_Stop_Wick",      "WIN$N", "M5", "EST-10", "WIN"),
    ("EST13", "Jumba_EST13_SmartGrid_RSI_BE",        "WIN$N", "M5", "EST-13", "WIN"),
    ("EST14", "Jumba_EST14_Grid_Institucional_123L", "WIN$N", "M5", "EST-14", "WIN"),
    ("EST15", "Jumba_EST15_Posicional_EOD_Breakout", "WIN$N", "M5", "EST-15", "WIN"),
    ("WDO01", "Jumba_WDO01_Scalper_Hibrido_NY",      "WDO$N", "M5", "WDO-01", "WDO"),
    ("WDO05", "Jumba_WDO05_Cluster_NWE30_NWE50",     "WDO$N", "M5", "WDO-05", "WDO"),
    ("WDO07", "Jumba_WDO07_Absorcao_Mkt_NY",         "WDO$N", "M5", "WDO-07", "WDO"),
]


def safe_copy(sf: str, df: str):
    try:
        with open(sf, "rb") as f:
            data = f.read()
        with open(df, "wb") as f:
            f.write(data)
    except Exception:
        pass


def prepare_tester():
    os.makedirs(NEW_DIR, exist_ok=True)
    lu = os.path.join(DST_TERM, "liveupdate")
    if os.path.exists(lu):
        shutil.rmtree(lu, ignore_errors=True)

    min_prf = os.path.join(DST_TERM, "MQL5", "Profiles", "Charts", "TesterMinimal")
    os.makedirs(min_prf, exist_ok=True)
    for f in os.listdir(min_prf):
        os.remove(os.path.join(min_prf, f))
    with open(os.path.join(min_prf, "order.wnd"), "w", encoding="utf-16") as f:
        f.write("")

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


def run_single(tag: str, ea_name: str, symbol: str, period: str, ea_code: str, from_date: str = "2026.01.02", to_date: str = "2026.11.06"):
    lu = os.path.join(DST_TERM, "liveupdate")
    if os.path.exists(lu):
        shutil.rmtree(lu, ignore_errors=True)

    rep_rel = f"jumba_bt\\{tag}_B3"
    rep_htm = os.path.join(DST_TERM, "jumba_bt", f"{tag}_B3.htm")
    if os.path.exists(rep_htm):
        os.remove(rep_htm)

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
    ini_path = os.path.join(DST_TERM, f"run_{tag}_b3.ini")
    with open(ini_path, "w", encoding="cp1252") as f:
        f.write(ini_txt)

    t0 = time.time()
    subprocess.run([TESTER_EXE, "/skipupdate", f"/config:{ini_path}"], check=False)
    dt = time.time() - t0

    if os.path.exists(rep_htm):
        dst_copy = os.path.join(NEW_DIR, f"{tag}_P1.htm")
        shutil.copy2(rep_htm, dst_copy)
        print(f"[OK] {tag:<6} ({ea_code:<6}) | {symbol:<5} | {dt:4.1f}s | {os.path.getsize(dst_copy):,} bytes", flush=True)
        return True
    print(f"[FAIL] {tag:<6} ({ea_code:<6}) | {dt:4.1f}s", flush=True)
    return False


def summarize_robot(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "net": 0.0, "dd_trade": 0.0, "dd_day": 0.0, "ret_dd": 0.0, "pf": 0.0, "wr": 0.0, "oos_net": 0.0, "max_h": -1, "max_streak": 0}
    pnl = np.array([t["pnl"] for t in trades], dtype=float)
    net = float(pnl.sum())
    gp = float(pnl[pnl > 0].sum())
    gl = float(-pnl[pnl < 0].sum())
    pf = gp / gl if gl > 0 else 99.0
    wr = 100.0 * float((pnl > 0).mean())
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.insert(eq, 0, 0.0))[1:]
    dd_tr = float(np.max(peak - eq))

    streak = 0
    max_streak = 0
    for v in pnl:
        if v < 0:
            streak += 1
            if streak > max_streak:
                max_streak = streak
        elif v > 0:
            streak = 0

    by_day = {}
    for t in trades:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + float(t["pnl"])
    d_vals = [by_day[d] for d in sorted(by_day)]
    d_eq = np.cumsum(d_vals)
    d_pk = np.maximum.accumulate(np.insert(d_eq, 0, 0.0))[1:]
    dd_day = float(np.max(d_pk - d_eq)) if len(d_eq) else 0.0
    ret_dd = net / dd_day if dd_day > 0 else 99.0
    oos = sum(float(t["pnl"]) for t in trades if t["date"] >= "2026-08-01")
    max_h = max(int(t["min_in"]) // 60 for t in trades)
    return {
        "n": len(trades),
        "net": round(net, 2),
        "dd_trade": round(dd_tr, 2),
        "dd_day": round(dd_day, 2),
        "ret_dd": round(ret_dd, 2),
        "pf": round(pf, 2),
        "wr": round(wr, 1),
        "oos_net": round(oos, 2),
        "max_entry_hour": max_h,
        "max_streak": max_streak,
    }


def eval_portfolio(trades: list[dict], win_m1: dict, wdo_m1: dict, all_dates: list[str], label: str) -> dict:
    days = build_intraday_days(trades, win_m1, wdo_m1, all_dates=all_dates)
    out = {
        "label": label,
        "trades": len(trades),
        "win_net": round(sum(t["pnl"] for t in trades if t["asset"] == "WIN"), 2),
        "wdo_net": round(sum(t["pnl"] for t in trades if t["asset"] == "WDO"), 2),
    }
    for name, sg, sw, sd in [
        ("no_stop", 0.0, 0.0, 0.0),
        ("G950_W400_D0", 950.0, 400.0, 0.0),
        ("G850_W400_D550", 850.0, 400.0, 550.0),
    ]:
        sim = simulate_combined_stops(days, stop_global=sg, stop_win=sw, stop_wdo=sd, slippage_per_lot=0.0)
        curve = sim["curve"]
        is_pnls = [r["day_pnl"] for r in curve if r["date"] < "2026-08-01"]
        oos_pnls = [r["day_pnl"] for r in curve if r["date"] >= "2026-08-01"]
        h1_pnls = [r["day_pnl"] for r in curve if r["date"] < "2026-06-01"]
        is_m = summarize_daily_curve(is_pnls)
        oos_m = summarize_daily_curve(oos_pnls)
        h1_m = summarize_daily_curve(h1_pnls)
        out[name] = {
            "total_pnl": sim["ret"],
            "max_dd": sim["max_dd"],
            "ret_dd": sim["ret_dd"],
            "sharpe": sim["sharpe"],
            "worst_day": sim["worst_day"],
            "days_stopped_any": sim["stopped"],
            "is_ret_dd": is_m["ret_dd"],
            "oos_ret_dd": oos_m["ret_dd"],
            "oos_net": oos_m["total_pnl"],
            "h1_ret_dd": h1_m["ret_dd"],
        }
    return out


def main():
    skip_run = "--analyze-only" in sys.argv
    if not skip_run:
        prepare_tester()
        for tag, ea_name, sym, per, ea_code, _ in ROBOTS_TOP10:
            ok = run_single(tag, ea_name, sym, per, ea_code)
            if not ok:
                raise RuntimeError(f"Backtest falhou para {tag}")

    codes = PORTFOLIO_PRESETS["top_10"]["robots"]
    trades_old = load_portfolio_trades(codes, htm_dir=OLD_DIR)
    trades_new = load_portfolio_trades(codes, htm_dir=NEW_DIR)
    trades_b1 = [t for t in trades_old if t["asset"] == "WIN"] + [t for t in trades_new if t["asset"] == "WDO"]

    print("\n=== COMPARATIVO POR ROBO (MT5 STRATEGY TESTER REAL OHLC 1m: ANTES vs B3 WDO<15h / WIN<16h) ===")
    print(f"{'Robo':<7} | {'Tr Old':>6} -> {'Tr New':>6} | {'Net Old':>9} -> {'Net New':>9} | {'DDday Old':>9} -> {'DDday New':>9} | {'R/DD Old':>8} -> {'R/DD New':>8} | {'MaxH':>4}")
    robot_cmp = {}
    for _, _, _, _, ea_code, _ in ROBOTS_TOP10:
        s_old = summarize_robot([t for t in trades_old if t["strat"] == ea_code])
        s_new = summarize_robot([t for t in trades_new if t["strat"] == ea_code])
        robot_cmp[ea_code] = {"old": s_old, "new": s_new}
        print(
            f"{ea_code:<7} | {s_old['n']:>6} -> {s_new['n']:>6} | "
            f"{s_old['net']:>9.0f} -> {s_new['net']:>9.0f} | "
            f"{s_old['dd_day']:>9.0f} -> {s_new['dd_day']:>9.0f} | "
            f"{s_old['ret_dd']:>7.2f}x -> {s_new['ret_dd']:>7.2f}x | {s_new['max_entry_hour']:>4d}"
        )

    win_m1, wdo_m1 = load_m1_bars()
    all_dates = sorted({t["date"] for t in trades_old} | {t["date"] for t in trades_new})
    p_old = eval_portfolio(trades_old, win_m1, wdo_m1, all_dates, "TOP10_ANTES")
    p_b1 = eval_portfolio(trades_b1, win_m1, wdo_m1, all_dates, "TOP10_B1_WDO15h_MT5_REAL")
    p_new = eval_portfolio(trades_new, win_m1, wdo_m1, all_dates, "TOP10_B3_WDO15h_WIN16h_MT5_REAL")

    print("\n=== PORTFOLIO TOP_10 REAL MT5 TESTER (ANTES vs B1 vs B3) ===")
    for p in (p_old, p_b1, p_new):
        print(f"\n[{p['label']}] Trades={p['trades']} | WIN=R$ {p['win_net']:,.0f} | WDO=R$ {p['wdo_net']:,.0f}")
        for k, lbl in [("no_stop", "Sem Stop      "), ("G950_W400_D0", "G950/W400/D0  "), ("G850_W400_D550", "G850/W400/D550")]:
            m = p[k]
            print(
                f"  {lbl}: Net=R$ {m['total_pnl']:,.0f} | DD=R$ {m['max_dd']:,.0f} | "
                f"Ret/DD={m['ret_dd']:.2f}x | Sharpe={m['sharpe']:.2f} | "
                f"IS={m['is_ret_dd']:.2f}x | OOS={m['oos_ret_dd']:.2f}x (R$ {m['oos_net']:,.0f}) | "
                f"H1={m['h1_ret_dd']:.2f}x | StopDias={m['days_stopped_any']} | PiorDia=R$ {m['worst_day']:,.0f}"
            )

    out_json = os.path.join(NEW_DIR, "validation_b3_summary.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"robots": robot_cmp, "portfolio_old": p_old, "portfolio_b1": p_b1, "portfolio_new": p_new}, f, indent=2, default=str)
    print(f"\n[SAVED] {out_json}")


if __name__ == "__main__":
    main()
