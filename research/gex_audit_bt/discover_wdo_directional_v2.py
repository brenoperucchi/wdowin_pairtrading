"""
Round 2 — Estrategias Direcionais Macro-Estruturais para WDO (IS-Driven -> OOS Cego)
Totalmente isolado em research/gex_audit_bt/ (ZERO alteracoes em producao).

Uso: python -m research.gex_audit_bt.discover_wdo_directional_v2
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import setups_runner  # noqa: E402
from research.flow_window_asg.flow_filters import load_flow_tables, make_sig_filter  # noqa: E402
from research.gex_audit_bt.run_bt_compare import set_gex_paths  # noqa: E402
from research.gex_audit_bt.run_gex_relevance_study import (  # noqa: E402
    RES_DIR,
    WDO_LIVE_3,
    WDO_PLAIN,
    WDO_SIGNED,
    WIN_LIVE_7,
    WIN_PLAIN,
    WIN_SIGNED,
    ContextProvider,
    SimRunner,
    build_bar_lookup,
    daily_pnl_series,
    eval_metrics,
    load_signed_gex_map,
)
from research.optimizers.wdo_mt5_sim import find_nearest_level, round05  # noqa: E402
from research.setup_parity.bt_32_slots import END, SPLIT, START, stats  # noqa: E402

COST_WDO_PTS = 0.5  # R$ 5,00 / contrato


@dataclass
class MacroDirConfig:
    family: str
    variant: str
    insp: str
    is_hybrid: bool = False


def build_wdo_macro_arrays(df_wdo: pd.DataFrame, n50d, n30d) -> dict:
    df = df_wdo.copy()
    df["n50_s"] = n50d[4]
    df["n30_s"] = n30d[4]

    vol_eff = df["real_volume"].where(df["real_volume"] > 0, 1.0).astype(float)
    tp = (df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3.0
    df["pv"] = tp * vol_eff
    df["vol_eff"] = vol_eff
    df["vwap"] = df.groupby("session_date")["pv"].cumsum() / df.groupby("session_date")["vol_eff"].cumsum()

    daily = df.groupby("session_date").agg(
        o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last")
    )
    daily["pdh"] = daily["h"].shift(1)
    daily["pdl"] = daily["l"].shift(1)
    daily["pdc"] = daily["c"].shift(1)
    daily["ema10_d"] = daily["c"].shift(1).ewm(span=10, adjust=False).mean()
    df = df.merge(daily[["pdh", "pdl", "pdc", "ema10_d"]], on="session_date", how="left")

    return {
        "dates": df["session_date"].astype(str).to_numpy(),
        "ts_str": df["t"].dt.strftime("%Y-%m-%d %H:%M").to_numpy(),
        "tmins": df["t_min"].astype(int).to_numpy(),
        "opens": df["open"].astype(float).to_numpy(),
        "highs": df["high"].astype(float).to_numpy(),
        "lows": df["low"].astype(float).to_numpy(),
        "closes": df["close"].astype(float).to_numpy(),
        "vwap": df["vwap"].astype(float).to_numpy(),
        "pdh": df["pdh"].astype(float).to_numpy(),
        "pdl": df["pdl"].astype(float).to_numpy(),
        "pdc": df["pdc"].astype(float).to_numpy(),
        "ema10_d": df["ema10_d"].astype(float).to_numpy(),
        "win_ret3": df["win_ret3"].fillna(0.0).astype(float).to_numpy(),
        "win_z": df["win_z"].fillna(0.0).astype(float).to_numpy(),
        "n50_s": df["n50_s"].astype(float).to_numpy(),
        "n30_s": df["n30_s"].astype(float).to_numpy(),
    }


def sim_macro_dir(
    cfg: MacroDirConfig,
    arr: dict,
    signed_wdo: dict,
    regime_gate: str = "ALL",
    sig_filter=None,
) -> list[dict]:
    dates = arr["dates"]
    ts_str = arr["ts_str"]
    tmins = arr["tmins"]
    opens = arr["opens"]
    highs = arr["highs"]
    lows = arr["lows"]
    closes = arr["closes"]
    vwap = arr["vwap"]
    pdh = arr["pdh"]
    pdl = arr["pdl"]
    pdc = arr["pdc"]
    ema10_d = arr["ema10_d"]
    win_z = arr["win_z"]
    n50_s = arr["n50_s"]
    n30_s = arr["n30_s"]
    n = len(dates)

    trades = []
    cur_day = ""
    trades_today = 0

    d_pos = 0
    entry_px = 0.0
    entry_time = ""
    curr_sl = 0.0
    curr_tp = 0.0
    max_fav = 0.0
    be_active = False
    opened_intrabar = False
    p_be_trig = 0.0
    p_be_lock = 0.0
    p_tr_trig = 0.0
    p_tr_dist = 0.0

    pend_dir = 0
    pend_px = 0.0
    pend_valid = 0
    pend_params = None

    def _close(px_out: float, reason: str, idx_bar: int):
        nonlocal d_pos
        net_pts = (px_out - entry_px) * d_pos - COST_WDO_PTS
        d_s = dates[idx_bar]
        trades.append({
            "date": d_s,
            "month": d_s[:7],
            "time": entry_time,
            "exit_time": ts_str[idx_bar][11:16],
            "asset": "WDO",
            "strategy_id": f"{cfg.family}_{cfg.variant}",
            "direction": "COMPRA" if d_pos == 1 else "VENDA",
            "entry_price": round(entry_px, 1),
            "exit_price": round(px_out, 1),
            "contracts": 1,
            "pts": round(net_pts, 2),
            "brl_1c": round(net_pts * 10.0, 2),
            "reason": reason,
        })
        d_pos = 0

    def _open_pos(sig: int, px_in: float, idx_bar: int, intrabar: bool, sl_pts: float, tp_pts: float, be_t: float, be_l: float, tr_t: float, tr_d: float):
        nonlocal d_pos, entry_px, entry_time, curr_sl, curr_tp, max_fav, be_active, opened_intrabar
        nonlocal p_be_trig, p_be_lock, p_tr_trig, p_tr_dist, trades_today
        p05 = round05(px_in)
        d_pos = sig
        entry_px = p05
        entry_time = ts_str[idx_bar][11:16]
        curr_sl = round05(p05 - sl_pts) if sig == 1 else round05(p05 + sl_pts)
        if tp_pts > 0.0:
            curr_tp = round05(p05 + tp_pts) if sig == 1 else round05(p05 - tp_pts)
        else:
            curr_tp = 1e9 if sig == 1 else -1e9
        max_fav = 0.0
        be_active = False
        opened_intrabar = intrabar
        p_be_trig, p_be_lock, p_tr_trig, p_tr_dist = be_t, be_l, tr_t, tr_d
        trades_today += 1

    def _eval_signal(b1: int, today: str, sg: dict):
        o1, h1, l1, c1 = opens[b1], highs[b1], lows[b1], closes[b1]
        tm1 = int(tmins[b1])
        vw1 = vwap[b1]
        h_prev, l_prev, c_prev, em_d = pdh[b1], pdl[b1], pdc[b1], ema10_d[b1]
        if np.isnan(h_prev) or np.isnan(l_prev) or np.isnan(c_prev) or np.isnan(vw1):
            return None

        s50, s30 = n50_s[b1], n30_s[b1]
        wz1 = win_z[b1]
        gf = sg["gamma_flip"]
        all_px = sg["all_px"]

        if regime_gate == "ONLY_NEG_GAMMA" and c1 >= gf:
            return None
        if regime_gate == "ONLY_POS_GAMMA" and c1 < gf:
            return None

        fam, var = cfg.family, cfg.variant
        sig, kind, px_trig, valid_b = 0, "MKT", opens[b1 + 1], 1
        sl_pts, tp_pts, be_t, be_l, tr_t, tr_d, max_tr = 18.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1

        # ------------------------------------------------------------------
        # M1: Abertura NY / 1a PTAX 10:00 (PDC +- thr + VWAP)
        # ------------------------------------------------------------------
        if fam == "M1_PTAX_10H_MACRO":
            if tm1 != 600:
                return None
            thr = 10.0 if var in ("V4_10P_EOD_SL18", "V5_10P_TRAIL") else 15.0
            if c1 >= c_prev + thr and c1 > vw1:
                sig = 1
            elif c1 <= c_prev - thr and c1 < vw1:
                sig = -1
            if sig != 0:
                if var == "V2_15P_EOD_SL24":
                    sl_pts = 24.0
                elif var in ("V3_15P_TRAIL", "V5_10P_TRAIL"):
                    sl_pts, tp_pts, be_t, be_l, tr_t, tr_d = 18.0, 55.0, 15.0, 2.0, 22.0, 10.0
                elif var == "V6_15P_VWAP_LIM":
                    kind, px_trig, valid_b = "LIMIT", round05(0.5 * (c1 + vw1)), 6

        # ------------------------------------------------------------------
        # M2: Rompimento PDH / PDL (09:15-14:00)
        # ------------------------------------------------------------------
        elif fam == "M2_PDH_PDL_BO":
            if tm1 < 555 or tm1 > 840:
                return None
            if c1 > h_prev:
                sig = 1
            elif c1 < l_prev:
                sig = -1
            if sig != 0:
                if var == "V2_MKT_EOD_SL25":
                    sl_pts = 25.0
                elif var == "V3_MKT_TRAIL":
                    sl_pts, tp_pts, be_t, be_l, tr_t, tr_d = 18.0, 55.0, 14.0, 2.0, 22.0, 10.0
                elif var == "V4_MKT_VWAP_NWE":
                    if (sig == 1 and not (c1 > vw1 and s50 > 0.2)) or (sig == -1 and not (c1 < vw1 and s50 < -0.2)):
                        sig = 0
                elif var == "V5_RETEST_LIMIT":
                    kind = "LIMIT"
                    px_trig = round05(h_prev if sig == 1 else l_prev)
                    valid_b, sl_pts = 6, 16.0
                elif var == "V6_D1EMA10_ALIGN":
                    if np.isnan(em_d) or (sig == 1 and c_prev <= em_d) or (sig == -1 and c_prev >= em_d):
                        sig = 0
                    sl_pts = 20.0

        # ------------------------------------------------------------------
        # M3: Pullback / BO na Wall GEX a favor da Tendencia Macro
        # ------------------------------------------------------------------
        elif fam == "M3_MACRO_WALL_PB":
            if tm1 < 595 or tm1 > 895:
                return None
            up_macro = ((c1 >= c_prev + 12.0) and (c1 > vw1)) or ((c1 > h_prev) and (c1 > vw1))
            dn_macro = ((c1 <= c_prev - 12.0) and (c1 < vw1)) or ((c1 < l_prev) and (c1 < vw1))
            if not (up_macro or dn_macro):
                return None
            dl, ls = find_nearest_level(all_px, l1)
            dh, lr = find_nearest_level(all_px, h1)
            if var in ("V1_WALL_MKT_EOD", "V2_WALL_MKT_TRAIL", "V3_WALL_LIM_EOD"):
                if up_macro and dl <= 3.5 and c1 > ls and c1 > o1:
                    sig = 1
                    px_trig = round05(ls + 0.5) if var == "V3_WALL_LIM_EOD" else opens[b1 + 1]
                elif dn_macro and dh <= 3.5 and c1 < lr and c1 < o1:
                    sig = -1
                    px_trig = round05(lr - 0.5) if var == "V3_WALL_LIM_EOD" else opens[b1 + 1]
                if var == "V1_WALL_MKT_EOD":
                    sl_pts, max_tr = 16.0, 1
                elif var == "V2_WALL_MKT_TRAIL":
                    sl_pts, tp_pts, be_t, be_l, tr_t, tr_d, max_tr = 14.0, 40.0, 12.0, 2.0, 18.0, 8.0, 2
                else:
                    kind, valid_b, sl_pts, max_tr = "LIMIT", 3, 15.0, 1
            elif var == "V4_VWAP_PB_EOD":
                if up_macro and l1 <= vw1 + 2.0 and c1 > vw1 and c1 > o1:
                    sig, sl_pts = 1, 16.0
                elif dn_macro and h1 >= vw1 - 2.0 and c1 < vw1 and c1 < o1:
                    sig, sl_pts = -1, 16.0
            else:  # V5_WALL_BO_IN_MACRO / V6_WALL_BO_EOD_IN_MACRO
                body1 = c1 - o1
                for p in all_px:
                    if up_macro and o1 <= p + 0.5 and c1 > p + 1.0 and body1 >= 1.5:
                        sig = 1; break
                    if dn_macro and o1 >= p - 0.5 and c1 < p - 1.0 and (-body1) >= 1.5:
                        sig = -1; break
                if var == "V5_WALL_BO_IN_MACRO":
                    sl_pts, tp_pts, be_t, be_l, tr_t, tr_d = 16.0, 45.0, 12.0, 2.0, 20.0, 9.0
                else:
                    sl_pts = 18.0

        # ------------------------------------------------------------------
        # M4: Confluencia Macro (PTAX 10h / PDH-PDL / WIN / 2:1 R:R)
        # ------------------------------------------------------------------
        elif fam == "M4_COMBO_PTAX_PDHL":
            if var in ("V1_10H_OR_PDHL_EOD", "V2_10H_OR_PDHL_TRAIL"):
                is_10h_b = (tm1 == 600 and c1 >= c_prev + 15.0 and c1 > vw1)
                is_10h_s = (tm1 == 600 and c1 <= c_prev - 15.0 and c1 < vw1)
                is_pd_b = (570 <= tm1 <= 840 and c1 > h_prev and c1 > vw1)
                is_pd_s = (570 <= tm1 <= 840 and c1 < l_prev and c1 < vw1)
                if is_10h_b or is_pd_b:
                    sig = 1
                elif is_10h_s or is_pd_s:
                    sig = -1
                if var == "V2_10H_OR_PDHL_TRAIL":
                    sl_pts, tp_pts, be_t, be_l, tr_t, tr_d = 18.0, 55.0, 15.0, 2.0, 22.0, 10.0
            elif var == "V3_10H_AND_WIN_ALIGN":
                if tm1 == 600:
                    if c1 >= c_prev + 10.0 and c1 > vw1 and wz1 <= -0.3:
                        sig = 1
                    elif c1 <= c_prev - 10.0 and c1 < vw1 and wz1 >= 0.3:
                        sig = -1
            elif var == "V4_PDHL_AND_WIN_ALIGN":
                if 555 <= tm1 <= 840:
                    if c1 > h_prev and c1 > vw1 and wz1 <= -0.3:
                        sig = 1
                    elif c1 < l_prev and c1 < vw1 and wz1 >= 0.3:
                        sig = -1
            elif var == "V5_10H_15P_TP35_SL18":
                if tm1 == 600:
                    if c1 >= c_prev + 15.0 and c1 > vw1:
                        sig, sl_pts, tp_pts = 1, 18.0, 35.0
                    elif c1 <= c_prev - 15.0 and c1 < vw1:
                        sig, sl_pts, tp_pts = -1, 18.0, 35.0
            else:  # V6_PDHL_TP35_SL18
                if 555 <= tm1 <= 840:
                    if c1 > h_prev and c1 > vw1:
                        sig, sl_pts, tp_pts = 1, 18.0, 35.0
                    elif c1 < l_prev and c1 < vw1:
                        sig, sl_pts, tp_pts = -1, 18.0, 35.0

        if sig == 0 or trades_today >= max_tr:
            return None
        if sig_filter is not None and not sig_filter(today, tm1, sig):
            return None
        return (sig, kind, px_trig, valid_b, sl_pts, tp_pts, be_t, be_l, tr_t, tr_d)

    for idx in range(2, n - 1):
        today = dates[idx]
        b1 = idx - 1
        if today != cur_day:
            if d_pos != 0:
                _close(opens[idx], "GAP_EOD", idx)
            pend_dir = 0
            cur_day = today
            trades_today = 0

        if today < START or today > END or today not in signed_wdo or dates[b1] != today:
            continue

        sg = signed_wdo[today]
        o0, h0, l0, c0 = opens[idx], highs[idx], lows[idx], closes[idx]
        tm0 = int(tmins[idx])

        if tm0 >= 1035:
            if d_pos != 0:
                _close(o0, "EOD", idx)
            pend_dir = 0
            continue

        if d_pos != 0:
            if opened_intrabar:
                fav_c = (closes[b1] - entry_px) * d_pos
                if fav_c > max_fav:
                    max_fav = fav_c
                opened_intrabar = False
            else:
                fav = (highs[b1] - entry_px) if d_pos == 1 else (entry_px - lows[b1])
                if fav > max_fav:
                    max_fav = fav
            if p_be_trig > 0.0 and not be_active and max_fav >= p_be_trig:
                cand = round05(entry_px + d_pos * p_be_lock)
                if (d_pos == 1 and o0 > cand + 0.5) or (d_pos == -1 and o0 < cand - 0.5):
                    curr_sl = max(curr_sl, cand) if d_pos == 1 else min(curr_sl, cand)
                    be_active = True
            if p_tr_trig > 0.0 and max_fav >= p_tr_trig:
                cand_tr = round05(entry_px + max_fav - p_tr_dist) if d_pos == 1 else round05(entry_px - max_fav + p_tr_dist)
                if (d_pos == 1 and o0 > cand_tr + 0.5) or (d_pos == -1 and o0 < cand_tr - 0.5):
                    curr_sl = max(curr_sl, cand_tr) if d_pos == 1 else min(curr_sl, cand_tr)

        if d_pos == 0 and pend_dir != 0 and pend_valid <= 0:
            pend_dir = 0

        if d_pos == 0 and pend_dir == 0:
            res = _eval_signal(b1, today, sg)
            if res is not None:
                sig, kind, px_trig, valid_b, sl_p, tp_p, be_t, be_l, tr_t, tr_d = res
                if kind == "MKT":
                    _open_pos(sig, o0, idx, False, sl_p, tp_p, be_t, be_l, tr_t, tr_d)
                else:
                    if (sig == 1 and o0 >= px_trig) or (sig == -1 and o0 <= px_trig):
                        pend_dir, pend_px, pend_valid = sig, px_trig, valid_b
                        pend_params = (sl_p, tp_p, be_t, be_l, tr_t, tr_d)

        if d_pos == 0 and pend_dir != 0:
            if (pend_dir == 1 and l0 <= pend_px) or (pend_dir == -1 and h0 >= pend_px):
                sl_p, tp_p, be_t, be_l, tr_t, tr_d = pend_params
                _open_pos(pend_dir, pend_px, idx, True, sl_p, tp_p, be_t, be_l, tr_t, tr_d)
                pend_dir = 0
            else:
                pend_valid -= 1
                if pend_valid <= 0:
                    pend_dir = 0

        if d_pos != 0:
            is_bull = c0 >= o0
            if opened_intrabar and o0 != entry_px:
                if d_pos == 1:
                    eff_l = l0
                    eff_h = h0 if is_bull else max(entry_px, c0)
                else:
                    eff_h = h0
                    eff_l = l0 if not is_bull else min(entry_px, c0)
            else:
                eff_h, eff_l = h0, l0

            if d_pos == 1:
                if eff_l <= curr_sl:
                    _close(curr_sl, "BE_SL" if be_active else "SL", idx)
                elif eff_h >= curr_tp:
                    _close(curr_tp, "TP", idx)
            else:
                if eff_h >= curr_sl:
                    _close(curr_sl, "BE_SL" if be_active else "SL", idx)
                elif eff_l <= curr_tp:
                    _close(curr_tp, "TP", idx)

    return trades


def build_macro_configs() -> list[MacroDirConfig]:
    specs = [
        ("M1_PTAX_10H_MACRO", "V1_15P_EOD_SL18", "PTAX-10h", False),
        ("M1_PTAX_10H_MACRO", "V2_15P_EOD_SL24", "PTAX-10h", False),
        ("M1_PTAX_10H_MACRO", "V3_15P_TRAIL", "PTAX-10h", False),
        ("M1_PTAX_10H_MACRO", "V4_10P_EOD_SL18", "PTAX-10h", False),
        ("M1_PTAX_10H_MACRO", "V5_10P_TRAIL", "PTAX-10h", False),
        ("M1_PTAX_10H_MACRO", "V6_15P_VWAP_LIM", "PTAX-10h", False),
        ("M2_PDH_PDL_BO", "V1_MKT_EOD_SL18", "PDH/PDL", False),
        ("M2_PDH_PDL_BO", "V2_MKT_EOD_SL25", "PDH/PDL", False),
        ("M2_PDH_PDL_BO", "V3_MKT_TRAIL", "PDH/PDL", False),
        ("M2_PDH_PDL_BO", "V4_MKT_VWAP_NWE", "PDH/PDL", False),
        ("M2_PDH_PDL_BO", "V5_RETEST_LIMIT", "PDH/PDL", False),
        ("M2_PDH_PDL_BO", "V6_D1EMA10_ALIGN", "PDH/PDL", False),
        ("M3_MACRO_WALL_PB", "V1_WALL_MKT_EOD", "EST-04/06+Macro", True),
        ("M3_MACRO_WALL_PB", "V2_WALL_MKT_TRAIL", "EST-04/06+Macro", True),
        ("M3_MACRO_WALL_PB", "V3_WALL_LIM_EOD", "EST-04/06+Macro", True),
        ("M3_MACRO_WALL_PB", "V4_VWAP_PB_EOD", "VWAP-PB+Macro", True),
        ("M3_MACRO_WALL_PB", "V5_WALL_BO_IN_MACRO", "WallBO+Macro", True),
        ("M3_MACRO_WALL_PB", "V6_WALL_BO_EOD_IN_MACRO", "WallBO+Macro", True),
        ("M4_COMBO_PTAX_PDHL", "V1_10H_OR_PDHL_EOD", "MacroCombo", False),
        ("M4_COMBO_PTAX_PDHL", "V2_10H_OR_PDHL_TRAIL", "MacroCombo", False),
        ("M4_COMBO_PTAX_PDHL", "V3_10H_AND_WIN_ALIGN", "Macro+WIN", False),
        ("M4_COMBO_PTAX_PDHL", "V4_PDHL_AND_WIN_ALIGN", "Macro+WIN", False),
        ("M4_COMBO_PTAX_PDHL", "V5_10H_15P_TP35_SL18", "PTAX-2:1", False),
        ("M4_COMBO_PTAX_PDHL", "V6_PDHL_TP35_SL18", "PDH/PDL-2:1", False),
    ]
    return [MacroDirConfig(f, v, i, h) for f, v, i, h in specs]


def dir_side_breakdown(trs: list[dict]) -> dict:
    df = pd.DataFrame(trs)
    if df.empty:
        return {"buy_net": 0.0, "sell_net": 0.0, "is_buy_net": 0.0, "is_sell_net": 0.0, "oos_buy_net": 0.0, "oos_sell_net": 0.0}
    b = df[df["direction"] == "COMPRA"]
    s = df[df["direction"] == "VENDA"]
    return {
        "buy_net": round(float(b["brl_1c"].sum()), 0),
        "sell_net": round(float(s["brl_1c"].sum()), 0),
        "is_buy_net": round(float(b[b["date"] <= SPLIT]["brl_1c"].sum()), 0),
        "is_sell_net": round(float(s[s["date"] <= SPLIT]["brl_1c"].sum()), 0),
        "oos_buy_net": round(float(b[b["date"] > SPLIT]["brl_1c"].sum()), 0),
        "oos_sell_net": round(float(s[s["date"] > SPLIT]["brl_1c"].sum()), 0),
    }


def main():
    t0 = time.time()
    os.makedirs(RES_DIR, exist_ok=True)
    ft, _ = load_flow_tables("min")
    set_gex_paths(WIN_PLAIN, WDO_PLAIN)

    signed_win = load_signed_gex_map(WIN_SIGNED)
    signed_wdo_raw = load_signed_gex_map(WDO_SIGNED)
    signed_wdo = {}
    for d, g in signed_wdo_raw.items():
        all_px = np.array([x[0] for x in g["levels"]], dtype=float)
        signed_wdo[d] = {**g, "all_px": all_px}

    with setups_runner._window(START, END, None, None):
        mk = setups_runner._load_market()
        df_win, _, _, _, _, df_wdo, _, n50d, n30d, _ = mk
        assert "win_ret3" in df_wdo.columns and "win_z" in df_wdo.columns

        bm_win, dt_win = build_bar_lookup(df_win)
        bm_wdo, dt_wdo = build_bar_lookup(df_wdo)
        ctx_prov = ContextProvider({"WIN": signed_win, "WDO": signed_wdo_raw}, {"WIN": bm_win, "WDO": bm_wdo}, {"WIN": dt_win, "WDO": dt_wdo})
        runner = SimRunner(mk, ft, ctx_prov)

        wdo_live3_sch = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "ALL", 895)]
        wdo_noput_sch = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "NO_PUT_WALL", 895)]
        win_live7_sch = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", "ALL", 955)]
        win_sel_map = {4: "ONLY_POS_GAMMA", 7: "ONLY_NEG_GAMMA", 9: "ONLY_NEG_GAMMA", 10: "ONLY_NEG_GAMMA", 13: "ONLY_NEG_GAMMA", 14: "ONLY_NEG_GAMMA", 15: "ALL"}
        win_sel_sch = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", win_sel_map[k], 955)]

        wdo_live3_bt = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "ALL", None)]
        win_live7_bt = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", "ALL", None)]

        all_dates = sorted(df_wdo.loc[(df_wdo["session_date"] >= START) & (df_wdo["session_date"] <= END), "session_date"].unique())
        s_live3_sch = daily_pnl_series(wdo_live3_sch, all_dates)
        worst20_days = list(s_live3_sch.nsmallest(20).index)
        worst20_loss = float(s_live3_sch.loc[worst20_days].sum())

        arr = build_wdo_macro_arrays(df_wdo, n50d, n30d)
        configs = build_macro_configs()

        rows = []
        trs_by_key = {}
        for cfg in configs:
            for reg in ("ALL", "ONLY_NEG_GAMMA", "ONLY_POS_GAMMA"):
                trs = sim_macro_dir(cfg, arr, signed_wdo, regime_gate=reg, sig_filter=None)
                m = eval_metrics(trs)
                sb = dir_side_breakdown(trs)
                sd = daily_pnl_series(trs, all_dates)
                corr = float(sd.corr(s_live3_sch)) if sd.std() > 0 and s_live3_sch.std() > 0 else 0.0
                hedge20 = float(sd.loc[worst20_days].sum())
                w_comb = eval_metrics(wdo_live3_sch + trs)
                p_comb = eval_metrics(win_live7_sch + wdo_live3_sch + trs)
                key = f"{cfg.family}|{cfg.variant}|{reg}"
                trs_by_key[key] = trs
                rows.append({
                    "key": key,
                    "family": cfg.family,
                    "variant": cfg.variant,
                    "insp": cfg.insp,
                    "regime": reg,
                    "corr_wdo3": round(corr, 3),
                    "hedge_worst20": round(hedge20, 0),
                    **m,
                    **sb,
                    "wdo_comb_ret_dd": w_comb["ret_dd"],
                    "wdo_comb_oos_rdd": w_comb["oos_ret_dd"],
                    "p10_comb_ret_dd": p_comb["ret_dd"],
                    "p10_comb_oos_rdd": p_comb["oos_ret_dd"],
                })

        df_all = pd.DataFrame(rows)
        df_all.to_csv(os.path.join(RES_DIR, "wdo_dir_v2_all.csv"), index=False)

        # Stage 2: strict IS screen (is_ops >= 30, is_pf >= 1.25, is_ret_dd >= 1.5, is_net > 0)
        strict = df_all[(df_all["is_ops"] >= 30) & (df_all["is_pf"] >= 1.25) & (df_all["is_ret_dd"] >= 1.5) & (df_all["is_net"] > 0)].copy()
        two_sided = strict[(strict["is_buy_net"] > 0) & (strict["is_sell_net"] > 0)].copy()
        pick_pool = two_sided if not two_sided.empty else strict
        if pick_pool.empty:
            pick_pool = df_all[df_all["is_ops"] >= 20].copy()

        top_fam = pick_pool.sort_values("is_ret_dd", ascending=False).drop_duplicates("family").head(4)
        best_global = strict.sort_values("is_ret_dd", ascending=False).head(4) if not strict.empty else top_fam
        winners_df = pd.concat([top_fam, best_global]).drop_duplicates("key").head(6)

        s2_rows = []
        for _, row in winners_df.iterrows():
            cfg = next(c for c in configs if c.family == row["family"] and c.variant == row["variant"])
            reg = row["regime"]
            for flow_name in ("0_BASE_MT5", "1_JANELA_ASG", "3_FLUXO_INST"):
                sf = make_sig_filter(ft, "WDO", flow_name)
                trs = trs_by_key[row["key"]] if flow_name == "0_BASE_MT5" else sim_macro_dir(cfg, arr, signed_wdo, regime_gate=reg, sig_filter=sf)
                m = eval_metrics(trs)
                sb = dir_side_breakdown(trs)
                sd = daily_pnl_series(trs, all_dates)
                corr = float(sd.corr(s_live3_sch)) if sd.std() > 0 and s_live3_sch.std() > 0 else 0.0
                hedge20 = float(sd.loc[worst20_days].sum())
                w_sch = eval_metrics(wdo_live3_sch + trs)
                p_sch = eval_metrics(win_live7_sch + wdo_live3_sch + trs)
                w_np = eval_metrics(wdo_noput_sch + trs)
                p_np = eval_metrics(win_live7_sch + wdo_noput_sch + trs)
                p_sel = eval_metrics(win_sel_sch + wdo_noput_sch + trs)
                w_bt = eval_metrics(wdo_live3_bt + trs)
                p_bt = eval_metrics(win_live7_bt + wdo_live3_bt + trs)
                s2_rows.append({
                    "kind": "WINNER_FLOW",
                    "label": row["key"],
                    "flow": flow_name,
                    "corr_wdo3": round(corr, 3),
                    "hedge_worst20": round(hedge20, 0),
                    **m,
                    **sb,
                    "sch_wdo_rdd": w_sch["ret_dd"], "sch_wdo_oos_rdd": w_sch["oos_ret_dd"],
                    "sch_p10_rdd": p_sch["ret_dd"], "sch_p10_oos_rdd": p_sch["oos_ret_dd"],
                    "sch_noput_wdo_rdd": w_np["ret_dd"], "sch_noput_p10_rdd": p_np["ret_dd"],
                    "sch_allopt_p10_rdd": p_sel["ret_dd"],
                    "bt_wdo_rdd": w_bt["ret_dd"], "bt_p10_rdd": p_bt["ret_dd"],
                })

        # Portfolio comparisons (Baseline vs Top M1 vs Top M2 vs M1+M2)
        b_w = eval_metrics(wdo_live3_sch)
        b_p = eval_metrics(win_live7_sch + wdo_live3_sch)
        b_wnp = eval_metrics(wdo_noput_sch)
        b_pnp = eval_metrics(win_live7_sch + wdo_noput_sch)
        b_psel = eval_metrics(win_sel_sch + wdo_noput_sch)
        b_bt_w = eval_metrics(wdo_live3_bt)
        b_bt_p = eval_metrics(win_live7_bt + wdo_live3_bt)

        s2_rows.append({
            "kind": "PORTFOLIO",
            "label": "0. ATUAL (WDO 01+05+07 / WIN 7)",
            "flow": "0_BASE_MT5",
            "corr_wdo3": 1.0, "hedge_worst20": round(worst20_loss, 0),
            **b_w, "buy_net": 0.0, "sell_net": 0.0, "is_buy_net": 0.0, "is_sell_net": 0.0, "oos_buy_net": 0.0, "oos_sell_net": 0.0,
            "sch_wdo_rdd": b_w["ret_dd"], "sch_wdo_oos_rdd": b_w["oos_ret_dd"],
            "sch_p10_rdd": b_p["ret_dd"], "sch_p10_oos_rdd": b_p["oos_ret_dd"],
            "sch_noput_wdo_rdd": b_wnp["ret_dd"], "sch_noput_p10_rdd": b_pnp["ret_dd"],
            "sch_allopt_p10_rdd": b_psel["ret_dd"],
            "bt_wdo_rdd": b_bt_w["ret_dd"], "bt_p10_rdd": b_bt_p["ret_dd"],
        })

        # Pick Top M1 and Top M2 from top_fam if available
        m1_row = top_fam[top_fam["family"] == "M1_PTAX_10H_MACRO"]
        m2_row = top_fam[top_fam["family"] == "M2_PDH_PDL_BO"]
        combo_cands = []
        for _, r in winners_df.head(2).iterrows():
            combo_cands.append((f"ATUAL + {r['key']}", trs_by_key[r["key"]]))
        if not m1_row.empty and not m2_row.empty:
            k1, k2 = m1_row.iloc[0]["key"], m2_row.iloc[0]["key"]
            combo_cands.append((f"ATUAL + M1+M2 ({k1} + {k2})", trs_by_key[k1] + trs_by_key[k2]))

        for plbl, d_trs in combo_cands:
            w_s = eval_metrics(wdo_live3_sch + d_trs)
            p_s = eval_metrics(win_live7_sch + wdo_live3_sch + d_trs)
            w_n = eval_metrics(wdo_noput_sch + d_trs)
            p_n = eval_metrics(win_live7_sch + wdo_noput_sch + d_trs)
            p_sel = eval_metrics(win_sel_sch + wdo_noput_sch + d_trs)
            w_b = eval_metrics(wdo_live3_bt + d_trs)
            p_b = eval_metrics(win_live7_bt + wdo_live3_bt + d_trs)
            sd = daily_pnl_series(d_trs, all_dates)
            s2_rows.append({
                "kind": "PORTFOLIO",
                "label": plbl,
                "flow": "0_BASE_MT5",
                "corr_wdo3": round(float(sd.corr(s_live3_sch)), 3) if sd.std() > 0 else 0.0,
                "hedge_worst20": round(float(sd.loc[worst20_days].sum()), 0),
                **w_s, **dir_side_breakdown(d_trs),
                "sch_wdo_rdd": w_s["ret_dd"], "sch_wdo_oos_rdd": w_s["oos_ret_dd"],
                "sch_p10_rdd": p_s["ret_dd"], "sch_p10_oos_rdd": p_s["oos_ret_dd"],
                "sch_noput_wdo_rdd": w_n["ret_dd"], "sch_noput_p10_rdd": p_n["ret_dd"],
                "sch_allopt_p10_rdd": p_sel["ret_dd"],
                "bt_wdo_rdd": w_b["ret_dd"], "bt_p10_rdd": p_b["ret_dd"],
            })

        df_s2 = pd.DataFrame(s2_rows)
        df_s2.to_csv(os.path.join(RES_DIR, "wdo_dir_v2_portfolio.csv"), index=False)

        pd.set_option("display.max_columns", 35)
        pd.set_option("display.width", 280)
        print(f"\n[CONCLUIDO em {time.time() - t0:.1f}s] Strict IS winners: {len(strict)} / {len(df_all)} | Two-sided IS winners: {len(two_sided)}")
        print("\n=== TOP 16 CANDIDATOS POR IS RET/DD (0_BASE_MT5) ===")
        c1 = ["family", "variant", "regime", "ops", "wr", "pf", "net", "mdd", "ret_dd", "is_ops", "is_pf", "is_ret_dd", "is_buy_net", "is_sell_net", "oos_ops", "oos_pf", "oos_net", "oos_ret_dd", "corr_wdo3", "hedge_worst20", "wdo_comb_ret_dd", "p10_comb_ret_dd"]
        print(df_all.sort_values("is_ret_dd", ascending=False).head(16)[c1].to_string(index=False))

        print("\n=== STAGE 2: WINNERS x FLUXO & PORTFOLIO FIT ===")
        c2 = ["kind", "label", "flow", "ops", "pf", "net", "ret_dd", "is_ret_dd", "oos_ops", "oos_pf", "oos_net", "oos_ret_dd", "buy_net", "sell_net", "corr_wdo3", "hedge_worst20", "sch_wdo_rdd", "sch_p10_rdd", "sch_noput_wdo_rdd", "sch_noput_p10_rdd", "sch_allopt_p10_rdd", "bt_wdo_rdd", "bt_p10_rdd"]
        print(df_s2[c2].to_string(index=False))


if __name__ == "__main__":
    main()
