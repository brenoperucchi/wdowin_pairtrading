# -*- coding: utf-8 -*-
"""
BACKTEST DE LONGO PRAZO 2026 (OOS vs IS vs TOTAL) — ESTRATÉGIAS DO DASHBOARD (FLUXO NAS WALLS & JANELA A.S.G)
=============================================================================================================
Períodos avaliados (212 pregões completos de 2026 com GEX B3 + Fluxo Tick-a-Tick MT5):
  - OOS (Novo Backfill B3 + Ticks 2026): 02/01/2026 a 06/05/2026 (84 pregões)
  - IS  (Período Original):              07/05/2026 a 06/11/2026 (128 pregões)
  - TOTAL (Ano Completo 2026):           02/01/2026 a 06/11/2026 (212 pregões)

Escopo completo:
  1. Todas as 16 estratégias (15 MT5 + WIN_E2 Wall Gasta) avaliadas sob os 7 modos de filtro:
       - 0_BASE_MT5 (Sem filtro de fluxo/janela)
       - 1_JANELA_ASG (A favor da Janela de Fluxo A.S.G)
       - 2_JANELA_S_EXPLOSAO (Janela A.S.G + Horário S 9h-11h / 15h-16h40)
       - 3_FLUXO_INST (Delta Institucional 5m/15m a favor)
       - 4_FLUXO_ABSORCAO (Absorção/Defesa de Pavio ou Agressão na Wall)
       - 5_COMBO_ESTRITO (Janela A.S.G + Delta Inst. 5m/15m)
       - 6_COMBO_SMART (Janela S ou Janela A.S.G + Absorção Institucional)
  2. Carteiras do Dashboard (Localhost 1 e Localhost 2):
       - PORTFOLIO_WALLS_6 (4 WIN + 2 WDO Fluxo nas Walls: EST-14, EST-04, EST-07, WIN-E2, WDO-07, WDO-10)
       - PORTFOLIO_TOP_6   (Top 6 Campeãs: EST-04, EST-07, EST-14, WDO-02, WDO-07, WDO-10)
       - PORTFOLIO_ALL_11  (11 Estratégias Alinhadas do Dashboard: 7 WIN + 4 WDO)
       - PORTFOLIO_ALL_15  (15 Estratégias MT5 Completas: 9 WIN + 6 WDO)
       - PORTFOLIO_ALL_16  (15 Estratégias MT5 + WIN-E2 Wall Gasta)
  3. Operação Pura da Virada da Janela A.S.G (Stop & Reverse 09:15–17:00) no WIN e WDO (Baseline e Top Setup).
"""

import os
import sys
import glob
import json
import functools
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.discover_gex_nwe_setups as disc
import research.optimizers.optimize_existing_16_setups as o16
from research.optimizers.test_win_aligned_wdo_matrix import simulate_aligned_win_wdo_slot
import research.optimizers.sg_sim as sg_sim
import research.optimizers.wdo_mt5_sim as wsim
from research.discover_m15_deep_dive import run_experiment, load_tf_bars
from research.flow_window_asg.flow_filters import (
    load_flow_tables,
    make_sig_filter,
    FILTER_NAMES,
    FILTER_LABELS,
)

sg_sim.load_m5_m1_wdo_gex = functools.lru_cache(maxsize=1)(sg_sim.load_m5_m1_wdo_gex)

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "bt_dashboard_flow_2026")
os.makedirs(OUT_DIR, exist_ok=True)

FULL_START = "2026-01-02"
OOS_END = "2026-05-06"
IS_START = "2026-05-07"
FULL_END = "2026-11-06"

WIN_COST_PTS = 10.0  # R$ 2,00 / contrato WIN
WDO_COST_PTS = 0.5   # R$ 5,00 / contrato WDO

# Mapa Oficial de Filtros de Fluxo/Janela Campeões do Dashboard (definido no IS original)
CHAMPION_FLOW_FILTER_MAP = {
    "EST-01": "6_COMBO_SMART",
    "EST-03": "4_FLUXO_ABSORCAO",
    "EST-04": "4_FLUXO_ABSORCAO",
    "EST-05": "4_FLUXO_ABSORCAO",
    "EST-07": "4_FLUXO_ABSORCAO",
    "EST-13": "4_FLUXO_ABSORCAO",
    "EST-14": "4_FLUXO_ABSORCAO",
    "EST-15": "0_BASE_MT5",
    "EST-16": "2_JANELA_S_EXPLOSAO",
    "WIN-E2": "6_COMBO_SMART",
    "WDO-01": "3_FLUXO_INST",
    "WDO-02": "0_BASE_MT5",
    "WDO-05": "1_JANELA_ASG",
    "WDO-07": "0_BASE_MT5",
    "WDO-09": "1_JANELA_ASG",
    "WDO-10": "3_FLUXO_INST",
}

# Mesma carteira sem nenhum "0_BASE_MT5" (forçando o melhor filtro ativo 1..6 em cada uma)
STRICT_ACTIVE_FLOW_MAP = {
    "EST-01": "6_COMBO_SMART",
    "EST-03": "4_FLUXO_ABSORCAO",
    "EST-04": "4_FLUXO_ABSORCAO",
    "EST-05": "4_FLUXO_ABSORCAO",
    "EST-07": "4_FLUXO_ABSORCAO",
    "EST-13": "4_FLUXO_ABSORCAO",
    "EST-14": "4_FLUXO_ABSORCAO",
    "EST-15": "4_FLUXO_ABSORCAO",
    "EST-16": "2_JANELA_S_EXPLOSAO",
    "WIN-E2": "6_COMBO_SMART",
    "WDO-01": "3_FLUXO_INST",
    "WDO-02": "4_FLUXO_ABSORCAO",
    "WDO-05": "1_JANELA_ASG",
    "WDO-07": "3_FLUXO_INST",
    "WDO-09": "1_JANELA_ASG",
    "WDO-10": "3_FLUXO_INST",
}

STRAT_META = [
    ("EST-01", "WIN", "M5",  "EST-01 · WIN Rejeição/Pinbar Wall"),
    ("EST-03", "WIN", "M15", "EST-03 · WIN Fakeout Trap Wall M15"),
    ("EST-04", "WIN", "M5",  "EST-04 · 🔄 WIN-B1 Pullback Virou Sup/Res"),
    ("EST-05", "WIN", "M15", "EST-05 · WIN MidWall Pullback M15"),
    ("EST-07", "WIN", "M5",  "EST-07 · 💥 WIN-C1 Ignição/Romperam Wall"),
    ("EST-13", "WIN", "M5",  "EST-13 · WIN SmartGrid CrossWDO 1+2L"),
    ("EST-14", "WIN", "M5",  "EST-14 · 🛡️ WIN-A1 SmartGrid Vai Defender"),
    ("EST-15", "WIN", "M5",  "EST-15 · WIN SmartGrid Z30 Reversal Wall"),
    ("EST-16", "WIN", "M5",  "EST-16 · WIN SmartGrid Spring MidWall"),
    ("WIN-E2", "WIN", "M5",  "WIN-E2 · ⚪ WALL GASTA Rompimento 3º+ Toque"),
    ("WDO-01", "WDO", "M5",  "WDO-01 · WDO Scalper Híbrido NY"),
    ("WDO-02", "WDO", "M5",  "WDO-02 · ⚡ WDO Scalper Híbrido Core"),
    ("WDO-05", "WDO", "M5",  "WDO-05 · WDO Cluster NWE30+50"),
    ("WDO-07", "WDO", "M5",  "WDO-07 · 🪤 WDO-B1 Absorção/Violinada NY"),
    ("WDO-09", "WDO", "M5",  "WDO-09 · WDO Cluster Limit Wall"),
    ("WDO-10", "WDO", "M5",  "WDO-10 · 🛡️ WDO-A2 Lunch Reversão NWE"),
]

WALLS_FLOW_6_STRATS = ["EST-14", "EST-04", "EST-07", "WIN-E2", "WDO-07", "WDO-10"]
TOP_6_STRATS = ["EST-04", "EST-07", "EST-14", "WDO-02", "WDO-07", "WDO-10"]
ALL_11_STRATS = ["EST-01", "EST-04", "EST-07", "EST-13", "EST-14", "EST-15", "EST-16", "WDO-02", "WDO-07", "WDO-09", "WDO-10"]
ALL_15_STRATS = [s[0] for s in STRAT_META if s[0] != "WIN-E2"]
ALL_16_STRATS = [s[0] for s in STRAT_META]


def build_win_e2_wall_table(gex_win: dict) -> dict:
    """Pré-computa toques acumulados nas Walls/MidWalls por sessão para WIN-E2 (Wall Gasta 3º+ toque)."""
    sessions_dir = os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1")
    wall_tab = {}
    for fp in sorted(glob.glob(os.path.join(sessions_dir, "*.json"))):
        date = os.path.basename(fp).replace(".json", "")
        if date not in gex_win:
            continue
        lvls = gex_win[date].get("all_levels")
        if lvls is None or len(lvls) == 0:
            w_arr = gex_win[date]["walls"]
            mw_arr = gex_win[date]["mid_walls"]
            lvls = np.sort(np.concatenate([w_arr, mw_arr])) if len(mw_arr) > 0 else w_arr
            gex_win[date]["all_levels"] = lvls
        if len(lvls) == 0:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        series = data.get("WIN", {}).get("m5_cvd_series", [])
        if not series:
            continue
        w_state = {float(w): {"touches": 0} for w in lvls}
        for idx, b in enumerate(series):
            dt = datetime.fromtimestamp(int(b.get("time", 0)), tz=timezone.utc)
            t_min = dt.hour * 60 + dt.minute
            o = float(b.get("open", b.get("close", 0.0)))
            h = float(b.get("high", o))
            l = float(b.get("low", o))
            c = float(b.get("close", o))
            i5 = float(b.get("inst_delta_bar", 0.0))
            i15 = sum(float(series[k].get("inst_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))
            rng = max(h - l, 5.0)
            body_r = abs(c - o) / rng
            exbr_b = exbr_s = False
            for wp, st in w_state.items():
                if l - 70.0 <= wp <= h + 70.0:
                    st["touches"] += 1
                    if c > wp and c > o and (body_r >= 0.35 or i5 >= 0 or i15 >= 0) and st["touches"] >= 3:
                        exbr_b = True
                    if c < wp and c < o and (body_r >= 0.35 or i5 <= 0 or i15 <= 0) and st["touches"] >= 3:
                        exbr_s = True
            wall_tab[(date, t_min)] = (exbr_b, exbr_s)
    return wall_tab


def simulate_win_e2_with_filter(df_win, gex_win, n50w, n30w, wall_tab, sig_filter=None):
    dates = df_win["session_date"].values
    tmins = df_win["t_min"].values
    opens = df_win["open"].values
    highs = df_win["high"].values
    lows = df_win["low"].values
    closes = df_win["close"].values
    c50, u50, l50, _, s50 = n50w
    c30, u30, l30, _, s30 = n30w
    rnd = o16.round5

    trades = []
    n = len(df_win)
    i = 3
    day_cnt = {}

    while i < n - 1:
        b1 = i - 1
        d_str = str(dates[i])
        if d_str < FULL_START or d_str > FULL_END or d_str not in gex_win or str(dates[b1]) != d_str:
            i += 1
            continue
        if day_cnt.get(d_str, 0) >= 3:
            i += 1
            continue
        tm = int(tmins[b1])
        if not (545 <= tm <= 990):
            i += 1
            continue
        ex_pair = wall_tab.get((d_str, tm))
        if ex_pair is None:
            i += 1
            continue
        g = gex_win[d_str]
        lvls = g["all_levels"]
        walls = g["walls"]
        if len(lvls) == 0:
            i += 1
            continue

        o1, h1, l1, c1 = opens[b1], highs[b1], lows[b1], closes[b1]
        bw50 = max(u50[b1] - l50[b1], 10.0)
        pos50 = (c1 - l50[b1]) / bw50
        dc, lc = wsim.find_nearest_level(lvls, c1)

        sig = 0
        def_w = 0.0
        if ex_pair[0] and dc <= 85.0 and c1 > lc and c1 > o1 and s50[b1] > 0.0 and s30[b1] > 0.0 and 0.35 <= pos50 <= 0.80:
            sig, def_w = 1, lc
        elif ex_pair[1] and dc <= 85.0 and c1 < lc and c1 < o1 and s50[b1] < 0.0 and s30[b1] < 0.0 and 0.20 <= pos50 <= 0.65:
            sig, def_w = -1, lc

        if sig == 0 or (sig_filter is not None and not sig_filter(d_str, tm, sig)):
            i += 1
            continue

        lim_px = rnd(0.5 * (h1 + l1))
        if (sig == 1 and opens[i] < lim_px) or (sig == -1 and opens[i] > lim_px):
            i += 1
            continue

        filled, fbar, ep = False, i, lim_px
        for v in range(2):
            eb = i + v
            if eb >= n or str(dates[eb]) != d_str or int(tmins[eb]) >= 1005:
                break
            if (sig == 1 and lows[eb] <= lim_px) or (sig == -1 and highs[eb] >= lim_px):
                filled, fbar, ep = True, eb, lim_px
                break

        if not filled:
            i += 1
            continue

        tp_mid, _, _, _ = o16.find_structural_targets(ep, sig, walls, lvls, 20.0)
        tp_px = min(tp_mid, rnd(ep + 260.0)) if sig == 1 else max(tp_mid, rnd(ep - 260.0))
        sl_init_px = rnd(ep - sig * 230.0)
        sl_px = sl_init_px
        be_on = False
        mfe = 0.0
        k = fbar
        bars_held = 0
        xp = closes[fbar]

        while k < n:
            if str(dates[k]) != d_str or int(tmins[k]) >= 1030:
                xp = opens[k] if str(dates[k]) == d_str else closes[k - 1]
                break
            if (sig == 1 and lows[k] <= sl_px) or (sig == -1 and highs[k] >= sl_px):
                xp = sl_px
                break
            if (sig == 1 and highs[k] >= tp_px) or (sig == -1 and lows[k] <= tp_px):
                xp = tp_px
                break
            bars_held += 1
            fav = (highs[k] - ep) if sig == 1 else (ep - lows[k])
            if fav > mfe:
                mfe = fav
            if k + 1 < n and str(dates[k + 1]) == d_str:
                no = opens[k + 1]
                if not be_on and mfe >= 130.0:
                    w_cand = rnd(def_w - sig * 20.0)
                    max_lock = rnd(ep + sig * 15.0)
                    cand = min(w_cand, max_lock) if sig == 1 else max(w_cand, max_lock)
                    min_improve = rnd(ep - sig * 85.0)
                    cand = max(cand, min_improve) if sig == 1 else min(cand, min_improve)
                    if (sig == 1 and cand > sl_px and no > cand) or (sig == -1 and cand < sl_px and no < cand):
                        sl_px = cand
                        be_on = True
                if bars_held >= 18:
                    xp = no
                    k += 1
                    break
            k += 1

        pts_raw = (xp - ep) * sig
        pts_net = pts_raw - WIN_COST_PTS
        trades.append({
            "date": d_str,
            "lots": 1.0,
            "pnl": round(float(pts_net * 0.20), 2),
            "pnl_nocost": round(float(pts_raw * 0.20), 2),
        })
        day_cnt[d_str] = day_cnt.get(d_str, 0) + 1
        i = max(i + 1, k + 1)

    return trades


def max_loss_streak(pnls: np.ndarray) -> int:
    max_s = 0
    cur_s = 0
    for p in pnls:
        if p < 0:
            cur_s += 1
            if cur_s > max_s:
                max_s = cur_s
        elif p > 0:
            cur_s = 0
    return int(max_s)


def compute_detailed_metrics(df_tr: pd.DataFrame, all_trading_days: list) -> dict:
    if df_tr.empty:
        return {
            "trades": 0, "lots": 0, "wr": 0.0, "pf": 0.0, "pf_nocost": 0.0,
            "net": 0.0, "net_nocost": 0.0, "dd_day": 0.0, "dd_trade": 0.0,
            "ret_dd": 0.0, "payoff": 0.0, "avg_trade": 0.0, "sharpe": 0.0,
            "pos_days_pct": 0.0, "active_days": 0, "worst_day": 0.0, "best_day": 0.0,
            "max_streak": 0
        }

    df_sorted = df_tr.sort_values(["date", "seq"]).reset_index(drop=True)
    pnls = df_sorted["pnl"].values.astype(float)
    pnls_nc = df_sorted["pnl_nocost"].values.astype(float)
    lots = int(df_sorted["lots"].sum())
    n = len(pnls)

    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    wr = 100.0 * len(wins) / n if n > 0 else 0.0
    gw = float(wins.sum()) if len(wins) > 0 else 0.0
    gl = float(-losses.sum()) if len(losses) > 0 else 0.0
    pf = gw / gl if gl > 1e-6 else (99.9 if gw > 0 else 0.0)

    gw_nc = float(pnls_nc[pnls_nc > 0].sum())
    gl_nc = float(-pnls_nc[pnls_nc < 0].sum())
    pf_nc = gw_nc / gl_nc if gl_nc > 1e-6 else (99.9 if gw_nc > 0 else 0.0)

    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(-losses.mean()) if len(losses) > 0 else 0.0
    payoff = avg_win / avg_loss if avg_loss > 1e-6 else 0.0

    net = float(pnls.sum())
    net_nc = float(pnls_nc.sum())
    avg_tr = net / n if n > 0 else 0.0

    cum_tr = np.cumsum(pnls)
    pk_tr = np.maximum.accumulate(np.insert(cum_tr, 0, 0.0))[1:]
    dd_trade = float(np.max(pk_tr - cum_tr)) if len(cum_tr) > 0 else 0.0

    daily_active = df_sorted.groupby("date")["pnl"].sum()
    daily_full = daily_active.reindex(all_trading_days, fill_value=0.0)
    cum_day = daily_full.cumsum().values
    pk_day = np.maximum.accumulate(np.insert(cum_day, 0, 0.0))[1:]
    dd_day = float(np.max(pk_day - cum_day)) if len(cum_day) > 0 else 0.0

    ret_dd = net / dd_day if dd_day > 1e-6 else (99.9 if net > 0 else 0.0)

    std_d = float(daily_full.std(ddof=1)) if len(daily_full) > 1 else 0.0
    sharpe = (float(daily_full.mean()) / std_d * np.sqrt(252.0)) if std_d > 1e-9 else 0.0

    active_days = int(len(daily_active))
    pos_days = int((daily_active > 0).sum())
    pos_days_pct = 100.0 * pos_days / active_days if active_days > 0 else 0.0

    worst_day = float(daily_full.min()) if len(daily_full) > 0 else 0.0
    best_day = float(daily_full.max()) if len(daily_full) > 0 else 0.0
    streak = max_loss_streak(pnls)

    return {
        "trades": n,
        "lots": lots,
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "pf_nocost": round(pf_nc, 2),
        "net": round(net, 2),
        "net_nocost": round(net_nc, 2),
        "dd_day": round(dd_day, 2),
        "dd_trade": round(dd_trade, 2),
        "ret_dd": round(ret_dd, 2),
        "payoff": round(payoff, 2),
        "avg_trade": round(avg_tr, 2),
        "sharpe": round(sharpe, 2),
        "pos_days_pct": round(pos_days_pct, 1),
        "active_days": active_days,
        "worst_day": round(worst_day, 2),
        "best_day": round(best_day, 2),
        "max_streak": streak,
    }


def run_all_16_across_filters(flow_tables: dict) -> pd.DataFrame:
    rows = []
    seq = 0

    print("1/5 Carregando WIN M5 + WDO M5 + WIN M15 e tabela de toques WIN-E2...")
    df_win_m5, gex_win = o16.load_win_and_wdo_aligned()
    c_m5 = df_win_m5["close"].values
    n50 = disc.compute_nwe_series(c_m5, lookback=50, bw=5.0, mult=2.0)
    n30 = disc.compute_nwe_series(c_m5, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(c_m5).diff()
    rsi7 = (
        100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))
    ).fillna(50.0).values
    A_win_m5 = (df_win_m5, gex_win, n50[0], n50[1], n50[2], n50[4], n30[0], n30[1], n30[2], n30[4], rsi7)

    wall_tab_e2 = build_win_e2_wall_table(gex_win)

    df_win_m15 = load_tf_bars("WIN", "M15", start_date="2025-12-15", end_date=FULL_END)
    c_m15 = df_win_m15["close"].values
    c15, u15, l15, _, s15 = disc.compute_nwe_series(c_m15, lookback=30, bw=4.0, mult=1.8)
    nwe_win_m15 = {"center": c15, "upper": u15, "lower": l15, "slope": s15}

    wdf, wgex = wsim.load_wdo_mt5_raw()
    wc = wdf["close"].values
    w50 = wsim.compute_nwe_series(wc, lookback=50, bw=5.0, mult=2.0)
    w30 = wsim.compute_nwe_series(wc, lookback=30, bw=3.0, mult=1.6)
    wrsi = wsim.compute_rsi7_series(wc)

    win_m5_cfg = {
        1: ("3p", "CURRENT", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
        4: ("wdo", "ALIGNED", "BE_WALL_2STAGE_177K", 15.0, "TP_MIDWALL"),
        7: ("3p", "CURRENT", "BE_WALL_SHIELD", 15.0, "TP_MIDWALL"),
    }

    for fn in FILTER_NAMES:
        print(f"  -> Simulando filtro {fn} nas 16 estratégias (2026 completo)...", flush=True)
        f_win = make_sig_filter(flow_tables, "WIN", fn)
        f_wdo = make_sig_filter(flow_tables, "WDO", fn)

        # 1) EST-01, EST-04, EST-07
        for k, (eng, ent, be, buf, tp) in win_m5_cfg.items():
            if eng == "3p":
                tr, _ = o16.simulate_single_est_slot(
                    k, *A_win_m5, entry_override=ent, be_mode=be, wall_shield_buf=buf,
                    tp_mode=tp, cost_pts=WIN_COST_PTS, sig_filter=f_win, start_date=FULL_START
                )
            else:
                tr, _ = simulate_aligned_win_wdo_slot(
                    k, *A_win_m5, be_mode=be, wall_shield_buf=buf, tp_mode=tp,
                    entry_override=ent, cost_pts=WIN_COST_PTS, sig_filter=f_win, start_date=FULL_START
                )
            for t in tr:
                d = str(t["date"])
                if FULL_START <= d <= FULL_END:
                    seq += 1
                    lots = float(t.get("contracts", 1))
                    pnl = float(t["pnl_brl"])
                    rows.append({
                        "seq": seq, "filter": fn, "strat": f"EST-{k:02d}", "asset": "WIN",
                        "date": d, "lots": lots, "pnl": pnl, "pnl_nocost": pnl + 2.0 * lots
                    })

        # 2) EST-03 & EST-05 (M15)
        tr_03 = run_experiment(
            df_win_m15, gex_win, "WIN", "M15", "M15_FAKEOUT_TRAP", "MARKET", nwe_win_m15,
            wall_buf=30.0, min_tp_dist=220.0, front_run=20.0, be_ratio=0.50, be_lock_pts=25.0,
            sig_filter=f_win
        )
        for t in tr_03:
            d = str(t["date"])
            if FULL_START <= d <= FULL_END:
                seq += 1
                pnl = float(t["brl"])
                rows.append({
                    "seq": seq, "filter": fn, "strat": "EST-03", "asset": "WIN",
                    "date": d, "lots": 1.0, "pnl": pnl, "pnl_nocost": pnl + 2.0
                })

        tr_05 = run_experiment(
            df_win_m15, gex_win, "WIN", "M15", "M15_MIDWALL_PULLBACK", "MARKET", nwe_win_m15,
            wall_buf=35.0, min_tp_dist=250.0, front_run=20.0, be_ratio=0.50, be_lock_pts=25.0,
            use_nwe_slope=True, nwe_slope_thresh=4.0, min_nwe_bw=300.0,
            sig_filter=f_win
        )
        for t in tr_05:
            d = str(t["date"])
            if FULL_START <= d <= FULL_END:
                seq += 1
                pnl = float(t["brl"])
                rows.append({
                    "seq": seq, "filter": fn, "strat": "EST-05", "asset": "WIN",
                    "date": d, "lots": 1.0, "pnl": pnl, "pnl_nocost": pnl + 2.0
                })

        # 3) EST-13..16 (SmartGrids M5+M1)
        sg_df = sg_sim.run(slots=(13, 14, 15, 16), start=FULL_START, cost_pts=WIN_COST_PTS, sig_filter=f_win)
        for _, t in sg_df.iterrows():
            d = pd.Timestamp(t["t_in"]).strftime("%Y-%m-%d")
            if FULL_START <= d <= FULL_END:
                seq += 1
                lots = float(t["lots"])
                pnl = float(t["brl"])
                rows.append({
                    "seq": seq, "filter": fn, "strat": f"EST-{int(t['k']):02d}", "asset": "WIN",
                    "date": d, "lots": lots, "pnl": pnl,
                    "pnl_nocost": float(t.get("brl_nocost", pnl + 2.0 * lots))
                })

        # 4) WIN-E2 (Wall Gasta 3º+ Toque)
        tr_e2 = simulate_win_e2_with_filter(df_win_m5, gex_win, n50, n30, wall_tab_e2, sig_filter=f_win)
        for t in tr_e2:
            seq += 1
            rows.append({
                "seq": seq, "filter": fn, "strat": "WIN-E2", "asset": "WIN",
                "date": t["date"], "lots": 1.0, "pnl": t["pnl"], "pnl_nocost": t["pnl_nocost"]
            })

        # 5) WDO-01, WDO-02, WDO-05, WDO-07, WDO-09, WDO-10
        for sid in (1, 2, 5, 7, 9, 10):
            tr_w = wsim.simulate_wdo_core_slot(
                sid, wdf, wgex, w50[0], w50[1], w50[2], w50[4], w30[0], w30[1], w30[2], w30[4],
                wrsi, start_date=FULL_START, end_date=FULL_END, cost_pts=WDO_COST_PTS, sig_filter=f_wdo
            )
            for t in tr_w:
                d = str(t["date"])
                if FULL_START <= d <= FULL_END:
                    seq += 1
                    lots = float(t.get("contracts", 1))
                    rows.append({
                        "seq": seq, "filter": fn, "strat": f"WDO-{sid:02d}", "asset": "WDO",
                        "date": d, "lots": lots, "pnl": float(t["pnl_brl"]),
                        "pnl_nocost": float(t["pnl_brl_nocost"])
                    })

    return pd.DataFrame(rows)


def simulate_asg_pure_window_turn(all_days: list) -> pd.DataFrame:
    """Simula operar puramente a virada da Janela A.S.G (Stop & Reverse 09:15–17:00) em todas as sessões de 2026."""
    sessions_dir = os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1")
    rows = []
    seq = 0
    configs = [
        ("ASG_WIN_BASE (F4/S11/Flip6.5)", "WIN", 4.0, 11.0, 0.68, 0.45, 6.5),
        ("ASG_WIN_SLOW (F10/S22/Flip18)", "WIN", 10.0, 22.0, 0.50, 0.30, 18.0),
        ("ASG_WDO_BASE (F4/S11/Flip6.5)", "WDO", 4.0, 11.0, 0.68, 0.45, 6.5),
        ("ASG_WDO_SLOW (F10/S22/Flip22)", "WDO", 10.0, 22.0, 0.68, 0.30, 22.0),
    ]

    sess_cache = {"WIN": {}, "WDO": {}}
    for d_str in all_days:
        fp = os.path.join(sessions_dir, f"{d_str}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for sym in ("WIN", "WDO"):
            bars = [b for b in data.get(sym, {}).get("m5_cvd_series", []) if not b.get("is_prev_day", False)]
            if bars:
                sess_cache[sym][d_str] = bars

    for label, sym, fast_p, slow_p, w_cvd, smooth_alpha, flip_thr in configs:
        is_win = (sym == "WIN")
        alpha_fast = 2.0 / (fast_p + 1.0)
        alpha_slow = 2.0 / (slow_p + 1.0)
        alpha_band = 2.0 / (7.0 + 1.0)
        w_price = 1.0 - w_cvd
        mult_brl = 0.20 if is_win else 10.0
        cost_pts = WIN_COST_PTS if is_win else WDO_COST_PTS

        for d_str in all_days:
            bars = sess_cache[sym].get(d_str)
            if not bars:
                continue
            first_b = bars[0]
            first_h = float(first_b.get("high", first_b.get("close", 0.0)))
            first_l = float(first_b.get("low", first_h))
            first_cvd = round(float(first_b.get("cvd_inst", 0.0)), 0)
            first_inst = float(first_b.get("inst_delta_bar", 0.0))

            ema_p_high = first_h
            ema_p_low = first_l
            ema_atr = max(first_h - first_l, 40.0 if is_win else 1.5)
            ema_cvd_f = first_cvd
            ema_cvd_s = first_cvd
            ema_cvd_step = max(abs(first_inst), 2500.0 if is_win else 500.0)
            ema_hist = 0.0
            active_win_dir = 0
            prev_cvd = first_cvd - first_inst

            pos_dir = 0
            entry_px = 0.0
            n = len(bars)

            for i, b in enumerate(bars):
                dt = datetime.fromtimestamp(int(b.get("time", 0)), tz=timezone.utc)
                tm = dt.hour * 60 + dt.minute
                o = float(b.get("open", b.get("close", 0.0)))
                h = float(b.get("high", o))
                l = float(b.get("low", o))
                c = float(b.get("close", o))
                cvd = round(float(b.get("cvd_inst", 0.0)), 0)

                rng_bar = max(h - l, 15.0 if is_win else 0.5)
                ema_atr = alpha_band * rng_bar + (1.0 - alpha_band) * ema_atr
                ema_p_high = alpha_band * h + (1.0 - alpha_band) * ema_p_high
                ema_p_low = alpha_band * l + (1.0 - alpha_band) * ema_p_low
                p_mid_trava = 0.5 * ((ema_p_high + 0.35 * ema_atr) + (ema_p_low - 0.35 * ema_atr))

                ema_cvd_f = alpha_fast * cvd + (1.0 - alpha_fast) * ema_cvd_f
                ema_cvd_s = alpha_slow * cvd + (1.0 - alpha_slow) * ema_cvd_s
                ema_cvd_step = alpha_band * max(abs(cvd - prev_cvd), 500.0 if is_win else 100.0) + (1.0 - alpha_band) * ema_cvd_step

                raw_cvd_osc = (ema_cvd_f - ema_cvd_s) / max(1.0, ema_cvd_step * 1.4)
                raw_price_osc = (c - p_mid_trava) / max(1.0, ema_atr * 0.9)
                raw_score = np.clip((w_cvd * raw_cvd_osc + w_price * raw_price_osc) * 55.0, -100.0, 100.0)
                ema_hist = smooth_alpha * raw_score + (1.0 - smooth_alpha) * ema_hist
                hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

                prev_win_dir = active_win_dir
                if active_win_dir == 0:
                    active_win_dir = 1 if (hist_val >= 4.0 or (cvd >= prev_cvd and c >= o)) else -1
                else:
                    if active_win_dir == 1 and hist_val <= -flip_thr:
                        active_win_dir = -1
                    elif active_win_dir == -1 and hist_val >= flip_thr:
                        active_win_dir = 1
                prev_cvd = cvd

                if tm < 555:
                    continue
                if tm >= 1020 or i == n - 1:
                    if pos_dir != 0:
                        pts_raw = pos_dir * (c - entry_px)
                        pts_net = pts_raw - cost_pts
                        seq += 1
                        rows.append({
                            "seq": seq, "strat": label, "asset": sym, "date": d_str,
                            "lots": 1.0, "pnl": round(pts_net * mult_brl, 2),
                            "pnl_nocost": round(pts_raw * mult_brl, 2)
                        })
                        pos_dir = 0
                    continue

                if pos_dir == 0:
                    if prev_win_dir != active_win_dir or tm == 555:
                        pos_dir = active_win_dir
                        entry_px = c
                elif pos_dir != active_win_dir:
                    pts_raw = pos_dir * (c - entry_px)
                    pts_net = pts_raw - cost_pts
                    seq += 1
                    rows.append({
                        "seq": seq, "strat": label, "asset": sym, "date": d_str,
                        "lots": 1.0, "pnl": round(pts_net * mult_brl, 2),
                        "pnl_nocost": round(pts_raw * mult_brl, 2)
                    })
                    pos_dir = active_win_dir
                    entry_px = c

    return pd.DataFrame(rows)


def main():
    flow_tables, sess_dates = load_flow_tables()
    all_days = sorted([d for d in sess_dates if FULL_START <= d <= FULL_END])
    oos_days = [d for d in all_days if d <= OOS_END]
    is_days = [d for d in all_days if d >= IS_START]

    print("=" * 115)
    print(f"  BACKTEST DASHBOARD FLUXO NAS WALLS & JANELA A.S.G — 2026 COMPLETO ({len(all_days)} PREGÕES)")
    print(f"  - OOS (Novo Backfill B3 + Ticks): {oos_days[0]} a {oos_days[-1]} ({len(oos_days)} pregões)")
    print(f"  - IS  (Período Original):         {is_days[0]} a {is_days[-1]} ({len(is_days)} pregões)")
    print(f"  - TOTAL (Ano 2026):               {all_days[0]} a {all_days[-1]} ({len(all_days)} pregões)")
    print("=" * 115)

    df_all = run_all_16_across_filters(flow_tables)
    df_all.to_csv(os.path.join(OUT_DIR, "trades_16_strategies_all_filters_2026.csv"), index=False)

    # Salva métricas de cada Estratégia x Filtro para OOS, IS e TOTAL
    ind_rows = []
    for sid, asset, tf, desc in STRAT_META:
        for fn in FILTER_NAMES:
            sub = df_all[(df_all["strat"] == sid) & (df_all["filter"] == fn)]
            for p_name, p_days in [
                ("OOS_JAN_MAI", oos_days),
                ("IS_MAI_NOV", is_days),
                ("TOTAL_2026", all_days),
            ]:
                sub_p = sub[sub["date"].isin(p_days)]
                m = compute_detailed_metrics(sub_p, p_days)
                ind_rows.append({
                    "period": p_name,
                    "strat": sid,
                    "asset": asset,
                    "tf": tf,
                    "description": desc,
                    "filter": fn,
                    "is_champion_filter": (fn == CHAMPION_FLOW_FILTER_MAP[sid]),
                    **m,
                })

    df_ind = pd.DataFrame(ind_rows)
    df_ind.to_csv(os.path.join(OUT_DIR, "individual_16_x_7filters_is_oos_2026.csv"), index=False)

    # Helper para montar um dataframe de carteira combinando (strat, filter_map)
    def build_portfolio_df(strat_list, f_map):
        parts = []
        for s in strat_list:
            fn = f_map[s] if isinstance(f_map, dict) else f_map
            parts.append(df_all[(df_all["strat"] == s) & (df_all["filter"] == fn)])
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    portfolios_spec = [
        ("PORTFOLIO_WALLS_6_BASE", "Localhost 2 · 6 Walls (4 WIN + 2 WDO) SEM Filtro", WALLS_FLOW_6_STRATS, "0_BASE_MT5"),
        ("PORTFOLIO_WALLS_6_FLOW", "Localhost 2 · 6 Walls (4 WIN + 2 WDO) C/ FLUXO CAMPEÃO", WALLS_FLOW_6_STRATS, CHAMPION_FLOW_FILTER_MAP),
        ("PORTFOLIO_WALLS_6_STRICT", "Localhost 2 · 6 Walls (4 WIN + 2 WDO) C/ FLUXO ATIVO 100%", WALLS_FLOW_6_STRATS, STRICT_ACTIVE_FLOW_MAP),
        ("PORTFOLIO_TOP_6_BASE", "Top 6 Campeãs (3 WIN + 3 WDO) SEM Filtro", TOP_6_STRATS, "0_BASE_MT5"),
        ("PORTFOLIO_TOP_6_FLOW", "Top 6 Campeãs (3 WIN + 3 WDO) C/ FLUXO CAMPEÃO", TOP_6_STRATS, CHAMPION_FLOW_FILTER_MAP),
        ("PORTFOLIO_TOP_6_STRICT", "Top 6 Campeãs (3 WIN + 3 WDO) C/ FLUXO ATIVO 100%", TOP_6_STRATS, STRICT_ACTIVE_FLOW_MAP),
        ("PORTFOLIO_ALL_11_BASE", "Carteira Dashboard 11 Estratégias (7 WIN + 4 WDO) SEM Filtro", ALL_11_STRATS, "0_BASE_MT5"),
        ("PORTFOLIO_ALL_11_FLOW", "Carteira Dashboard 11 Estratégias (7 WIN + 4 WDO) C/ FLUXO CAMPEÃO", ALL_11_STRATS, CHAMPION_FLOW_FILTER_MAP),
        ("PORTFOLIO_ALL_11_STRICT", "Carteira Dashboard 11 Estratégias (7 WIN + 4 WDO) C/ FLUXO ATIVO 100%", ALL_11_STRATS, STRICT_ACTIVE_FLOW_MAP),
        ("PORTFOLIO_ALL_15_BASE", "Carteira MT5 15 Robôs (9 WIN + 6 WDO) SEM Filtro", ALL_15_STRATS, "0_BASE_MT5"),
        ("PORTFOLIO_ALL_15_FLOW", "Carteira MT5 15 Robôs (9 WIN + 6 WDO) C/ FLUXO CAMPEÃO", ALL_15_STRATS, CHAMPION_FLOW_FILTER_MAP),
        ("PORTFOLIO_ALL_15_STRICT", "Carteira MT5 15 Robôs (9 WIN + 6 WDO) C/ FLUXO ATIVO 100%", ALL_15_STRATS, STRICT_ACTIVE_FLOW_MAP),
        ("PORTFOLIO_ALL_16_BASE", "Todas 16 (15 MT5 + WIN-E2 Wall Gasta) SEM Filtro", ALL_16_STRATS, "0_BASE_MT5"),
        ("PORTFOLIO_ALL_16_FLOW", "Todas 16 (15 MT5 + WIN-E2 Wall Gasta) C/ FLUXO CAMPEÃO", ALL_16_STRATS, CHAMPION_FLOW_FILTER_MAP),
    ]
    # Também adiciona cada um dos 6 filtros aplicado uniformemente às 11 e às 15 estratégias
    for fn in FILTER_NAMES[1:]:
        portfolios_spec.append((f"PORT_11_UNIFORM_{fn}", f"11 Estratégias c/ Filtro Único {fn}", ALL_11_STRATS, fn))
        portfolios_spec.append((f"PORT_15_UNIFORM_{fn}", f"15 Estratégias c/ Filtro Único {fn}", ALL_15_STRATS, fn))

    port_rows = []
    port_dfs = {}
    for pid, pdesc, slist, fmap in portfolios_spec:
        pdf = build_portfolio_df(slist, fmap)
        port_dfs[pid] = pdf
        for p_name, p_days in [
            ("OOS_JAN_MAI", oos_days),
            ("IS_MAI_NOV", is_days),
            ("TOTAL_2026", all_days),
        ]:
            sub_p = pdf[pdf["date"].isin(p_days)]
            m = compute_detailed_metrics(sub_p, p_days)
            port_rows.append({
                "period": p_name,
                "portfolio_id": pid,
                "description": pdesc,
                **m,
            })

    df_port = pd.DataFrame(port_rows)
    df_port.to_csv(os.path.join(OUT_DIR, "portfolios_dashboard_flow_is_oos_2026.csv"), index=False)

    # Simula Virada Pura da Janela A.S.G (Stop & Reverse 09:15–17:00)
    df_asg = simulate_asg_pure_window_turn(all_days)
    asg_rows = []
    for s_label in df_asg["strat"].unique():
        sub = df_asg[df_asg["strat"] == s_label]
        for p_name, p_days in [
            ("OOS_JAN_MAI", oos_days),
            ("IS_MAI_NOV", is_days),
            ("TOTAL_2026", all_days),
        ]:
            sub_p = sub[sub["date"].isin(p_days)]
            m = compute_detailed_metrics(sub_p, p_days)
            asg_rows.append({
                "period": p_name,
                "strat": s_label,
                **m,
            })
    df_asg_sum = pd.DataFrame(asg_rows)
    df_asg_sum.to_csv(os.path.join(OUT_DIR, "asg_pure_window_turn_is_oos_2026.csv"), index=False)

    # Evolução Mensal das principais carteiras (Jan a Nov 2026)
    months = sorted(list({d[:7] for d in all_days}))
    monthly_rows = []
    for pid in [
        "PORTFOLIO_WALLS_6_BASE", "PORTFOLIO_WALLS_6_FLOW", "PORTFOLIO_WALLS_6_STRICT",
        "PORTFOLIO_TOP_6_BASE", "PORTFOLIO_TOP_6_FLOW",
        "PORTFOLIO_ALL_11_BASE", "PORTFOLIO_ALL_11_FLOW", "PORTFOLIO_ALL_11_STRICT",
        "PORTFOLIO_ALL_15_BASE", "PORTFOLIO_ALL_15_FLOW", "PORTFOLIO_ALL_15_STRICT",
        "PORTFOLIO_ALL_16_FLOW",
    ]:
        pdf = port_dfs[pid].copy()
        pdf["month"] = pdf["date"].str.slice(0, 7)
        row = {"portfolio_id": pid}
        for m in months:
            row[m] = round(float(pdf[pdf["month"] == m]["pnl"].sum()), 0)
        row["OOS_SUM"] = round(float(pdf[pdf["date"] <= OOS_END]["pnl"].sum()), 0)
        row["IS_SUM"] = round(float(pdf[pdf["date"] >= IS_START]["pnl"].sum()), 0)
        row["TOTAL_2026"] = round(float(pdf["pnl"].sum()), 0)
        monthly_rows.append(row)

    df_monthly = pd.DataFrame(monthly_rows)
    df_monthly.to_csv(os.path.join(OUT_DIR, "monthly_portfolios_2026.csv"), index=False)

    # Print executive summary to stdout
    for p_name, p_title in [
        ("OOS_JAN_MAI", "OUT-OF-SAMPLE (02/01/2026 a 06/05/2026 — 84 pregões)"),
        ("IS_MAI_NOV", "IN-SAMPLE (07/05/2026 a 06/11/2026 — 128 pregões)"),
        ("TOTAL_2026", "PERÍODO TOTAL 2026 (02/01/2026 a 06/11/2026 — 212 pregões)"),
    ]:
        print("\n" + "=" * 120)
        print(f"  CARTEIRAS DO DASHBOARD — {p_title}")
        print("=" * 120)
        sub_p = df_port[df_port["period"] == p_name]
        print(f"{'Carteira':<28} | {'Tr':>5} | {'WR%':>5} | {'PF':>5} | {'PF Br':>5} | {'Net (R$)':>10} | {'DD Dia':>8} | {'Ret/DD':>6} | {'Sharpe':>6} | {'Pior Dia':>9}")
        print("-" * 120)
        for _, r in sub_p.iterrows():
            print(
                f"{r['portfolio_id']:<28} | {int(r['trades']):>5d} | {r['wr']:>4.1f}% | {r['pf']:>5.2f} | "
                f"{r['pf_nocost']:>5.2f} | {r['net']:>+10.0f} | {r['dd_day']:>8.0f} | {r['ret_dd']:>5.2f}x | "
                f"{r['sharpe']:>6.2f} | {r['worst_day']:>+9.0f}"
            )

    print("\n" + "=" * 120)
    print("  EVOLUÇÃO MENSAL 2026 DAS CARTEIRAS (LÍQUIDO R$)")
    print("=" * 120)
    print(df_monthly.to_string(index=False))

    print("\n" + "=" * 120)
    print("  COMPARAÇÃO POR ESTRATÉGIA: SEM FILTRO (0_BASE_MT5) vs C/ FILUXO CAMPEÃO — OOS, IS e TOTAL 2026")
    print("=" * 120)
    for sid, asset, tf, desc in STRAT_META:
        fn_champ = CHAMPION_FLOW_FILTER_MAP[sid]
        fn_strict = STRICT_ACTIVE_FLOW_MAP[sid]
        b_oos = df_ind[(df_ind["strat"] == sid) & (df_ind["filter"] == "0_BASE_MT5") & (df_ind["period"] == "OOS_JAN_MAI")].iloc[0]
        f_oos = df_ind[(df_ind["strat"] == sid) & (df_ind["filter"] == fn_strict) & (df_ind["period"] == "OOS_JAN_MAI")].iloc[0]
        b_tot = df_ind[(df_ind["strat"] == sid) & (df_ind["filter"] == "0_BASE_MT5") & (df_ind["period"] == "TOTAL_2026")].iloc[0]
        f_tot = df_ind[(df_ind["strat"] == sid) & (df_ind["filter"] == fn_strict) & (df_ind["period"] == "TOTAL_2026")].iloc[0]
        print(
            f"{sid:<7} ({fn_strict:<19}) | "
            f"OOS Sem: {int(b_oos['trades']):>3d}tr PF {b_oos['pf']:>4.2f} R${b_oos['net']:>+7.0f} DD {b_oos['dd_day']:>5.0f} ({b_oos['ret_dd']:>4.2f}x) -> "
            f"OOS C/Fluxo: {int(f_oos['trades']):>3d}tr PF {f_oos['pf']:>4.2f} R${f_oos['net']:>+7.0f} DD {f_oos['dd_day']:>5.0f} ({f_oos['ret_dd']:>4.2f}x) | "
            f"2026 Sem: PF {b_tot['pf']:>4.2f} R${b_tot['net']:>+7.0f} ({b_tot['ret_dd']:>4.2f}x) -> "
            f"2026 C/Fluxo: PF {f_tot['pf']:>4.2f} R${f_tot['net']:>+7.0f} ({f_tot['ret_dd']:>4.2f}x)"
        )

    print("\n" + "=" * 120)
    print("  VIRADA PURA DA JANELA A.S.G (STOP & REVERSE 09:15-17:00)")
    print("=" * 120)
    print(df_asg_sum[["period", "strat", "trades", "wr", "pf", "pf_nocost", "net", "dd_day", "ret_dd", "sharpe"]].to_string(index=False))


if __name__ == "__main__":
    main()

