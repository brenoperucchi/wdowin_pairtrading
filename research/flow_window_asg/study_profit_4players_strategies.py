# -*- coding: utf-8 -*-
"""
Estudo Completo 2026 (212 Pregões) · 4 Players Profit nas Walls & Otimização 5176
=================================================================================
"""
import os
import sys
import glob
import json
import functools
import itertools
from datetime import datetime, timezone
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.optimizers import optimize_existing_16_setups as o16
from research.optimizers import sg_sim
from research.optimizers import wdo_mt5_sim as wsim
from research.optimizers.test_win_aligned_wdo_matrix import simulate_aligned_win_wdo_slot
from research.flow_window_asg.generate_portfolio_6_json import (
    START_DATE, END_DATE, SPLIT_DATE, COST_WIN_PTS, COST_WDO_PTS,
    format_win_o16_trades, format_sg_trades, format_wdo_trades,
    compute_summary_from_trades, simulate_win_e2_wall_gasta,
)

sg_sim.load_m5_m1_wdo_gex = functools.lru_cache(maxsize=1)(sg_sim.load_m5_m1_wdo_gex)

SESSIONS_DIR = os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1")


def build_extended_flow_features(m5_series, is_win: bool):
    """Extrai features A.S.G + 4 Players Profit por barra M5."""
    fast_p = 5.0 if is_win else 4.0
    slow_p = 18.0 if is_win else 22.0
    w_cvd, w_price = 0.85, 0.15
    smooth_a = 0.45 if is_win else 0.60
    flip_thr = 11.0
    alpha_fast = 2.0 / (fast_p + 1.0)
    alpha_slow = 2.0 / (slow_p + 1.0)
    alpha_band = 2.0 / (7.0 + 1.0)
    if not m5_series:
        return []

    fb = m5_series[0]
    first_c = float(fb.get("close", 0.0))
    first_h = float(fb.get("high", first_c))
    first_l = float(fb.get("low", first_c))
    first_cvd = round(float(fb.get("cvd_inst", 0.0)), 0)

    ema_p_high, ema_p_low = first_h, first_l
    ema_atr = max(first_h - first_l, 40.0 if is_win else 1.5)
    ema_cvd_f = ema_cvd_s = first_cvd
    ema_cvd_step = max(abs(float(fb.get("inst_delta_bar", 0.0))), 2500.0 if is_win else 500.0)
    ema_hist = 0.0
    active_win_dir = 0
    prev_cvd = first_cvd
    prev_hist = 0.0
    out = []

    for idx, b in enumerate(m5_series):
        dt = datetime.fromtimestamp(int(b.get("time", 0)), tz=timezone.utc)
        t_min = dt.hour * 60 + dt.minute
        o = float(b.get("open", b.get("close", 0.0)))
        h = float(b.get("high", o))
        l = float(b.get("low", o))
        c = float(b.get("close", o))

        inst_5m = float(b.get("inst_delta_bar", 0.0))
        inst_aggr_5m = float(b.get("inst_aggr_delta", inst_5m))
        inst_pass_5m = float(b.get("inst_pass_delta", 0.0))
        ret_5m = float(b.get("ret_delta_bar", 0.0))
        hft_5m = float(b.get("hft_delta_bar", 0.0))
        hft_churn = float(b.get("hft_churn_pct", 0.0))
        rlp_pct = float(b.get("rlp_pct", 0.0))
        avg_buy = float(b.get("avg_buy_lot", 1.0))
        avg_sell = float(b.get("avg_sell_lot", 1.0))
        lot_imb = float(b.get("lot_imb", avg_buy / max(avg_sell, 0.1)))
        delta_5m = float(b.get("delta_bar", 0.0))
        cvd = round(float(b.get("cvd_inst", 0.0)), 0)

        inst_15m = sum(float(m5_series[k].get("inst_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))
        inst_aggr_15m = sum(float(m5_series[k].get("inst_aggr_delta", m5_series[k].get("inst_delta_bar", 0.0))) for k in range(max(0, idx - 2), idx + 1))
        inst_pass_15m = sum(float(m5_series[k].get("inst_pass_delta", 0.0)) for k in range(max(0, idx - 2), idx + 1))
        ret_15m = sum(float(m5_series[k].get("ret_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))

        if idx == 0:
            prev_cvd = cvd - round(inst_5m, 0)

        rng_bar = max(round(h, 2) - round(l, 2), 15.0 if is_win else 0.5)
        ema_atr = alpha_band * rng_bar + (1.0 - alpha_band) * ema_atr
        ema_p_high = alpha_band * round(h, 2) + (1.0 - alpha_band) * ema_p_high
        ema_p_low = alpha_band * round(l, 2) + (1.0 - alpha_band) * ema_p_low
        p_upper = round(ema_p_high + 0.35 * ema_atr, 2)
        p_lower = round(ema_p_low - 0.35 * ema_atr, 2)
        p_mid = round(0.5 * (p_upper + p_lower), 2)

        ema_cvd_f = alpha_fast * cvd + (1.0 - alpha_fast) * ema_cvd_f
        ema_cvd_s = alpha_slow * cvd + (1.0 - alpha_slow) * ema_cvd_s
        ema_cvd_step = alpha_band * max(abs(cvd - prev_cvd), 500.0 if is_win else 100.0) + (1.0 - alpha_band) * ema_cvd_step
        raw_cvd_osc = (ema_cvd_f - ema_cvd_s) / max(1.0, ema_cvd_step * 1.4)
        raw_price_osc = (round(c, 2) - p_mid) / max(1.0, ema_atr * 0.9)
        raw_score = float(np.clip((w_cvd * raw_cvd_osc + w_price * raw_price_osc) * 55.0, -100.0, 100.0))
        ema_hist = smooth_a * raw_score + (1.0 - smooth_a) * ema_hist
        hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

        if active_win_dir == 0:
            active_win_dir = 1 if (hist_val >= 4.0 or (cvd >= prev_cvd and round(c, 2) >= round(o, 2))) else -1
        elif active_win_dir == 1 and hist_val <= -flip_thr:
            active_win_dir = -1
        elif active_win_dir == -1 and hist_val >= flip_thr:
            active_win_dir = 1

        out.append(dict(
            t_min=t_min, o=o, h=h, l=l, c=c,
            window_dir=active_win_dir, flow_hist=hist_val,
            hist_slope=hist_val - prev_hist,
            inst_5m=inst_5m, inst_15m=inst_15m, delta_5m=delta_5m,
            inst_aggr_5m=inst_aggr_5m, inst_aggr_15m=inst_aggr_15m,
            inst_pass_5m=inst_pass_5m, inst_pass_15m=inst_pass_15m,
            ret_5m=ret_5m, ret_15m=ret_15m,
            hft_5m=hft_5m, hft_churn=hft_churn,
            rlp_pct=rlp_pct, avg_buy=avg_buy, avg_sell=avg_sell, lot_imb=lot_imb,
        ))
        prev_cvd = cvd
        prev_hist = hist_val
    return out


def build_candidate_masks(f: dict, is_win: bool) -> dict:
    wdir, fhist, hslope = f["window_dir"], f["flow_hist"], f["hist_slope"]
    i5, i15, d5 = f["inst_5m"], f["inst_15m"], f["delta_5m"]
    ia5, ia15 = f["inst_aggr_5m"], f["inst_aggr_15m"]
    ip5, ip15 = f["inst_pass_5m"], f["inst_pass_15m"]
    r5, r15 = f["ret_5m"], f["ret_15m"]
    churn = f["hft_churn"]
    lot_imb = f["lot_imb"]
    o, h, l, c = f["o"], f["h"], f["l"], f["c"]
    rng = max(h - l, 5.0 if is_win else 0.5)
    lwick = min(o, c) - l
    uwick = h - max(o, c)

    b1 = wdir == 1
    s1 = wdir == -1
    b2 = (wdir == 1) or (fhist >= -14.0) or (hslope >= 0.0)
    s2 = (wdir == -1) or (fhist <= 14.0) or (hslope <= 0.0)
    b3 = (i5 >= 0.0) or (i15 >= 0.0)
    s3 = (i5 <= 0.0) or (i15 <= 0.0)
    abs_buy = (lwick >= 0.22 * rng) or (c >= o)
    abs_sell = (uwick >= 0.22 * rng) or (c <= o)
    crash_thr = -12000.0 if is_win else -800.0
    surge_thr = 12000.0 if is_win else 800.0
    b4 = ((i5 >= 0.0) or (d5 >= 0.0) or abs_buy) and (i5 >= crash_thr)
    s4 = ((i5 <= 0.0) or (d5 <= 0.0) or abs_sell) and (i5 <= surge_thr)

    # 7_PROFIT_DEFENSE (Absorção Passiva Inst + Armadilha Varejo + Bloqueio Sweep Violento Contra)
    sweep_crash = (ia5 < (-4200.0 if is_win else -480.0)) and (lot_imb < 0.88) and (ip5 <= 0.0)
    sweep_surge = (ia5 > (4200.0 if is_win else 480.0)) and (lot_imb > 1.14) and (ip5 >= 0.0)
    b7 = ((i5 >= 0.0) or (i15 >= 0.0) or (ip5 > 0.0) or (r5 < 0.0 and ia5 >= -2500.0) or abs_buy) and (not sweep_crash)
    s7 = ((i5 <= 0.0) or (i15 <= 0.0) or (ip5 < 0.0) or (r5 > 0.0 and ia5 <= 2500.0) or abs_sell) and (not sweep_surge)

    # 8_PROFIT_SWEEP (Sweep / Ignição Institucional + Ticket Médio Agressor a Favor)
    b8 = ((ia5 >= 0.0) or (ia15 >= 0.0) or (lot_imb >= 1.02) or (b2 and b4)) and (ia5 >= (-5500.0 if is_win else -450.0)) and (lot_imb >= 0.88)
    s8 = ((ia5 <= 0.0) or (ia15 <= 0.0) or (lot_imb <= 0.98) or (s2 and s4)) and (ia5 <= (5500.0 if is_win else 450.0)) and (lot_imb <= 1.14)

    # 9_PROFIT_INST_RET (Fluxo Institucional + Divergência Varejo + Ticket Médio sem Sweep Oposto)
    sweep_crash_w = (ia5 < (-9000.0 if is_win else -650.0)) and (lot_imb < 0.82)
    sweep_surge_w = (ia5 > (9000.0 if is_win else 650.0)) and (lot_imb > 1.22)
    b9 = ((i5 >= 0.0) or (i15 >= 0.0) or (ip5 > 0.0 and r5 < 0.0) or (lot_imb >= 1.04)) and (not sweep_crash_w)
    s9 = ((i5 <= 0.0) or (i15 <= 0.0) or (ip5 < 0.0 and r5 > 0.0) or (lot_imb <= 0.96)) and (not sweep_surge_w)

    # 10_PROFIT_SMART_WALL (Janela s/ Explosão + Profit Defense)
    b10 = b2 and b7
    s10 = s2 and s7

    # 11_PROFIT_WALL_SHIELD (Janela s/ Explosão + Profit Inst/Ret Divergence)
    b11 = b2 and b9
    s11 = s2 and s9

    return {
        "1_JANELA_ASG": (b1, s1),
        "2_JANELA_S_EXPLOSAO": (b2, s2),
        "3_FLUXO_INST": (b3, s3),
        "4_FLUXO_ABSORCAO": (b4, s4),
        "5_COMBO_ESTRITO": (b1 and b4, s1 and s4),
        "6_COMBO_SMART": (b2 and b4, s2 and s4),
        "7_PROFIT_DEFENSE": (b7, s7),
        "8_PROFIT_SWEEP": (b8, s8),
        "9_PROFIT_INST_RET": (b9, s9),
        "10_PROFIT_SMART_WALL": (b10, s10),
        "11_PROFIT_WALL_SHIELD": (b11, s11),
    }


def main():
    files = sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json")))
    filter_keys = [
        "0_BASE_MT5",
        "1_JANELA_ASG", "2_JANELA_S_EXPLOSAO", "3_FLUXO_INST",
        "4_FLUXO_ABSORCAO", "5_COMBO_ESTRITO", "6_COMBO_SMART",
        "7_PROFIT_DEFENSE", "8_PROFIT_SWEEP", "9_PROFIT_INST_RET", "10_PROFIT_SMART_WALL", "11_PROFIT_WALL_SHIELD",
    ]
    flow = {a: {fn: {} for fn in filter_keys[1:]} for a in ("WIN", "WDO")}
    wall_touches_stats = {"WIN": [], "WDO": []}

    for fp in files:
        date = os.path.basename(fp).replace(".json", "")
        if date < START_DATE or date > END_DATE:
            continue
        with open(fp, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for asset in ("WIN", "WDO"):
            ad = data.get(asset, {})
            series = ad.get("m5_cvd_series", [])
            feats = build_extended_flow_features(series, is_win=(asset == "WIN"))
            for f in feats:
                for fn, ok in build_candidate_masks(f, is_win=(asset == "WIN")).items():
                    flow[asset][fn][(date, f["t_min"])] = ok

            for w in ad.get("all_walls", []):
                if float(w.get("total_vol", 0.0)) > 0:
                    wall_touches_stats[asset].append({
                        "date": date,
                        "label": w.get("label", ""),
                        "deals": int(w.get("deals", 0)),
                        "total_vol": float(w.get("total_vol", 0.0)),
                        "inst_aggr": float(w.get("inst_aggr_delta", 0.0)),
                        "inst_pass": float(w.get("inst_pass_delta", 0.0)),
                        "ret_delta": float(w.get("ret_delta", 0.0)),
                        "hft_churn": float(w.get("hft_churn_pct", 0.0)),
                        "rlp_pct": float(w.get("rlp_share_pct", w.get("rlp_pct", 0.0))),
                        "sig": w.get("player_signature", "EM_DISPUTA"),
                        "hint": w.get("strategy_hint", ""),
                    })

    print("=" * 115)
    print("  PARTE 1: RADIOGRAFIA DAS WALLS EM 2026 (212 PREGÕES) POR ASSINATURA DE PLAYER")
    print("=" * 115)
    for asset in ("WIN", "WDO"):
        df_w = pd.DataFrame(wall_touches_stats[asset])
        if df_w.empty:
            continue
        print(f"\n  [{asset}] Total de Walls com Negócio em 2026: {len(df_w)} (Negócios nas Walls: {df_w['deals'].sum():,})")
        grp = df_w.groupby("sig").agg(
            walls=("deals", "count"),
            deals=("deals", "sum"),
            vol=("total_vol", "mean"),
            inst_aggr=("inst_aggr", "mean"),
            inst_pass=("inst_pass", "mean"),
            ret_delta=("ret_delta", "mean"),
            hft_churn=("hft_churn", "mean"),
            rlp_pct=("rlp_pct", "mean"),
            hint=("hint", "first"),
        ).reset_index().sort_values("walls", ascending=False)
        for _, r in grp.iterrows():
            print(
                f"    {r['sig']:<26} | Walls={int(r['walls']):>4d} | VolMéd={r['vol']:>8.0f}L "
                f"| InstAggr={r['inst_aggr']:>+8.0f} | InstPass={r['inst_pass']:>+7.0f} "
                f"| Varejo={r['ret_delta']:>+7.0f} | Churn={r['hft_churn']:>4.1f}% | RLP={r['rlp_pct']:>4.1f}% -> {r['hint']}"
            )

    # Pré-computa os trades de cada estratégia para os candidatos de filtro e encontra a combinação ótima de 5176
    df_win, gex_win = o16.load_win_and_wdo_aligned()
    closes_w = df_win["close"].values
    n50w = o16.compute_nwe_series(closes_w, lookback=50, bw=5.0, mult=2.0)
    n30w = o16.compute_nwe_series(closes_w, lookback=30, bw=3.0, mult=1.6)
    dp_w = pd.Series(closes_w).diff()
    rsi7w = (100.0 - (100.0 / (1.0 + (dp_w.clip(lower=0).rolling(7).mean() / (-dp_w.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    df_wdo, gex_wdo = wsim.load_wdo_mt5_raw()
    closes_d = df_wdo["close"].values
    n50d = wsim.compute_nwe_series(closes_d, lookback=50, bw=5.0, mult=2.0)
    n30d = wsim.compute_nwe_series(closes_d, lookback=30, bw=3.0, mult=1.6)
    rsi7d = wsim.compute_rsi7_series(closes_d)

    win_dates = sorted(set(str(d) for d in df_win["session_date"].unique() if START_DATE <= str(d) <= END_DATE and str(d) in gex_win))
    wdo_dates = sorted(set(str(d) for d in df_wdo["session_date"].unique() if START_DATE <= str(d) <= END_DATE and str(d) in gex_wdo))
    all_dates = sorted(set(win_dates) | set(wdo_dates))
    A = (df_win, gex_win, n50w[0], n50w[1], n50w[2], n50w[4], n30w[0], n30w[1], n30w[2], n30w[4], rsi7w)

    def make_sf(asset, fn):
        if fn == "0_BASE_MT5":
            return None
        tab = flow[asset][fn]
        def _f(d, tm, s):
            ok = tab.get((str(d), int(tm)))
            return True if ok is None else bool(ok[0] if s == 1 else ok[1])
        return _f

    cand_by_strat = {
        "EST_14": ["4_FLUXO_ABSORCAO", "7_PROFIT_DEFENSE", "9_PROFIT_INST_RET", "10_PROFIT_SMART_WALL", "11_PROFIT_WALL_SHIELD"],
        "EST_04": ["4_FLUXO_ABSORCAO", "7_PROFIT_DEFENSE", "8_PROFIT_SWEEP", "9_PROFIT_INST_RET"],
        "EST_07": ["4_FLUXO_ABSORCAO", "7_PROFIT_DEFENSE", "8_PROFIT_SWEEP", "9_PROFIT_INST_RET"],
        "WIN_E2": ["6_COMBO_SMART", "7_PROFIT_DEFENSE", "8_PROFIT_SWEEP", "9_PROFIT_INST_RET", "1_JANELA_ASG"],
        "WDO_07": ["3_FLUXO_INST", "2_JANELA_S_EXPLOSAO", "10_PROFIT_SMART_WALL", "11_PROFIT_WALL_SHIELD"],
        "WDO_01": ["3_FLUXO_INST", "2_JANELA_S_EXPLOSAO", "9_PROFIT_INST_RET", "10_PROFIT_SMART_WALL", "11_PROFIT_WALL_SHIELD"],
    }

    trades_cache = {s: {} for s in cand_by_strat}
    for fn in cand_by_strat["EST_14"]:
        df_sg14 = sg_sim.run(slots=(14,), start=START_DATE, cost_pts=COST_WIN_PTS, sig_filter=make_sf("WIN", fn))
        trades_cache["EST_14"][fn] = [t for t in format_sg_trades(df_sg14) if START_DATE <= t["date"] <= END_DATE]

    for fn in cand_by_strat["EST_04"]:
        tr_04_raw, _ = simulate_aligned_win_wdo_slot(
            4, *A, be_mode="BE_WALL_2STAGE_177K", wall_shield_buf=15.0, tp_mode="TP_MIDWALL",
            entry_override="ALIGNED", cost_pts=COST_WIN_PTS, sig_filter=make_sf("WIN", fn), start_date=START_DATE,
        )
        trades_cache["EST_04"][fn] = format_win_o16_trades([t for t in tr_04_raw if START_DATE <= str(t["date"]) <= END_DATE], df_win, "EST_04")

    for fn in cand_by_strat["EST_07"]:
        tr_07_raw, _ = o16.simulate_single_est_slot(
            7, *A, entry_override="CURRENT", be_mode="BE_WALL_SHIELD", wall_shield_buf=15.0,
            tp_mode="TP_MIDWALL", cost_pts=COST_WIN_PTS, sig_filter=make_sf("WIN", fn), start_date=START_DATE,
        )
        trades_cache["EST_07"][fn] = format_win_o16_trades([t for t in tr_07_raw if START_DATE <= str(t["date"]) <= END_DATE], df_win, "EST_07")

    for fn in cand_by_strat["WIN_E2"]:
        trades_cache["WIN_E2"][fn] = simulate_win_e2_wall_gasta(
            df_win, gex_win, n50w, n30w, {"WIN": {"6_COMBO_SMART": flow["WIN"][fn]}}, use_flow=True
        )

    for slot_id, sid in [(7, "WDO_07"), (1, "WDO_01")]:
        for fn in cand_by_strat[sid]:
            tr_wdo_raw = wsim.simulate_wdo_core_slot(
                slot_id, df_wdo, gex_wdo,
                n50d[0], n50d[1], n50d[2], n50d[4],
                n30d[0], n30d[1], n30d[2], n30d[4], rsi7d,
                start_date=START_DATE, end_date=END_DATE,
                cost_pts=COST_WDO_PTS, sig_filter=make_sf("WDO", fn),
            )
            trades_cache[sid][fn] = format_wdo_trades(tr_wdo_raw, sid)

    # Busca combinações de filtros que maximizem pos_months (11/11), Ret/DD e Net Profit
    sids = ["EST_14", "EST_04", "EST_07", "WIN_E2", "WDO_07", "WDO_01"]
    combos_res = []
    for prod in itertools.product(*(cand_by_strat[s] for s in sids)):
        fmap = dict(zip(sids, prod))
        merged = []
        for s in sids:
            merged.extend(trades_cache[s][fmap[s]])
        st = compute_summary_from_trades(merged, all_dates)
        combos_res.append((st["pos_months"], st["ret_dd"], st["tot_brl_1c"], fmap, st))

    combos_res.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    print("\n" + "=" * 115)
    print("  PARTE 3A: TOP 5 COMBINAÇÕES 11/11 M+ (TODOS OS MESES POSITIVOS)")
    print("=" * 115)
    for rank, (pm, rdd, net, fmap, st) in enumerate(combos_res[:5], 1):
        print(
            f"\n  #{rank} -> {st['ops']:>4d} tr | WR {st['wr_pct']:>4.1f}% | PF {st['pf']:>4.2f} (Bruto {st['pf_nocost']:>4.2f}) "
            f"| Net R$ {st['tot_brl_1c']:>7.0f} | DD R$ {st['max_dd_brl_1c']:>5.0f} | Ret/DD {st['ret_dd']:>5.2f}x | {st['pos_months']}/{st['total_months']} M+\n"
            f"       IS: R$ {st['is_net']:>6.0f} (PF {st['is_pf']:>4.2f}) | OOS: R$ {st['oos_net']:>6.0f} (PF {st['oos_pf']:>4.2f})\n"
            f"       Filtros: {fmap}\n"
            f"       Meses: {st['by_month_1c']}"
        )

    combos_res_rdd = sorted(combos_res, key=lambda x: (x[1], x[2]), reverse=True)
    print("\n" + "=" * 115)
    print("  PARTE 3B: TOP 5 COMBINAÇÕES POR MAIOR RET/DD & LUCRO LÍQUIDO")
    print("=" * 115)
    for rank, (pm, rdd, net, fmap, st) in enumerate(combos_res_rdd[:5], 1):
        print(
            f"\n  #{rank} -> {st['ops']:>4d} tr | WR {st['wr_pct']:>4.1f}% | PF {st['pf']:>4.2f} (Bruto {st['pf_nocost']:>4.2f}) "
            f"| Net R$ {st['tot_brl_1c']:>7.0f} | DD R$ {st['max_dd_brl_1c']:>5.0f} | Ret/DD {st['ret_dd']:>5.2f}x | {st['pos_months']}/{st['total_months']} M+\n"
            f"       IS: R$ {st['is_net']:>6.0f} (PF {st['is_pf']:>4.2f}) | OOS: R$ {st['oos_net']:>6.0f} (PF {st['oos_pf']:>4.2f})\n"
            f"       Filtros: {fmap}\n"
            f"       Meses: {st['by_month_1c']}"
        )


if __name__ == "__main__":
    main()
