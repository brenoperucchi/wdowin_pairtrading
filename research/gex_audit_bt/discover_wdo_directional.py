"""
Descoberta e Validacao IS/OOS de Estrategias Direcionais para WDO (Inspiradas no WIN)
Totalmente isolado em research/gex_audit_bt/ (ZERO alteracoes em producao).

Uso: python -m research.gex_audit_bt.discover_wdo_directional
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
from research.optimizers.wdo_mt5_sim import (  # noqa: E402
    calc_wdo_target_pts,
    find_nearest_level,
    round05,
)
from research.setup_parity.bt_32_slots import END, SPLIT, START, stats  # noqa: E402

COST_WDO_PTS = 0.5  # R$ 5,00 / contrato


@dataclass
class DirConfig:
    arch: str
    variant: str
    win_insp: str
    is_positional: bool = False


def simulate_wdo_directional(
    cfg: DirConfig,
    mk_arrays: dict,
    signed_wdo: dict,
    regime_gate: str = "ALL",
    sig_filter=None,
) -> list[dict]:
    """Simulador fiel ao MT5 (b1 fechada -> entrada MKT/PEND_LIMIT/PEND_STOP na barra idx)."""
    dates = mk_arrays["dates"]
    ts_str = mk_arrays["ts_str"]
    tmins = mk_arrays["tmins"]
    opens = mk_arrays["opens"]
    highs = mk_arrays["highs"]
    lows = mk_arrays["lows"]
    closes = mk_arrays["closes"]
    win_ret3 = mk_arrays["win_ret3"]
    win_z = mk_arrays["win_z"]
    n50c, n50u, n50l, n50s = mk_arrays["n50"]
    n30c, n30u, n30l, n30s = mk_arrays["n30"]
    n = len(dates)

    trades = []
    cur_day = ""
    trades_today = 0
    last_entry_bar = -1
    wall_touches: dict[float, int] = {}

    # Posicao aberta
    d_pos = 0
    entry_px = 0.0
    entry_time = ""
    curr_sl = 0.0
    curr_tp = 0.0
    max_fav = 0.0
    be_active = False
    bars_held = 0
    opened_intrabar = False
    p_be_trig = 0.0
    p_be_lock = 0.0
    p_be_mode = 0
    p_def_wall = 0.0
    p_wall_buf = 1.0
    p_tr_trig = 0.0
    p_tr_dist = 0.0
    p_max_hold = 20

    # Ordem pendente
    pend_dir = 0
    pend_type = 0  # 1=LIMIT, 2=STOP
    pend_px = 0.0
    pend_valid = 0
    pend_params = None

    def _close(px_out: float, reason: str, idx_bar: int):
        nonlocal d_pos
        raw_pts = (px_out - entry_px) * d_pos
        net_pts = raw_pts - COST_WDO_PTS
        brl = round(net_pts * 10.0, 2)
        d_s = dates[idx_bar]
        trades.append({
            "date": d_s,
            "month": d_s[:7],
            "time": entry_time,
            "exit_time": ts_str[idx_bar][11:16],
            "asset": "WDO",
            "strategy_id": f"{cfg.arch}_{cfg.variant}",
            "direction": "COMPRA" if d_pos == 1 else "VENDA",
            "entry_price": round(entry_px, 1),
            "exit_price": round(px_out, 1),
            "contracts": 1,
            "pts": round(net_pts, 2),
            "brl_1c": brl,
            "reason": reason,
        })
        d_pos = 0

    def _open_pos(
        sig: int, px_in: float, idx_bar: int, intrabar: bool,
        tp_pts: float, sl_pts: float, be_trig: float, be_lock: float,
        tr_trig: float, tr_dist: float, max_hold: int,
        def_wall: float = 0.0, be_mode: int = 1, wall_buf: float = 1.0,
    ):
        nonlocal d_pos, entry_px, entry_time, curr_sl, curr_tp, max_fav, be_active
        nonlocal bars_held, opened_intrabar, p_be_trig, p_be_lock, p_be_mode
        nonlocal p_def_wall, p_wall_buf, p_tr_trig, p_tr_dist, p_max_hold
        nonlocal trades_today, last_entry_bar
        p05 = round05(px_in)
        d_pos = sig
        entry_px = p05
        entry_time = ts_str[idx_bar][11:16]
        curr_sl = round05(p05 - sl_pts) if sig == 1 else round05(p05 + sl_pts)
        curr_tp = round05(p05 + tp_pts) if sig == 1 else round05(p05 - tp_pts)
        max_fav = 0.0
        be_active = False
        bars_held = 0
        opened_intrabar = intrabar
        p_be_trig, p_be_lock, p_be_mode = be_trig, be_lock, be_mode
        p_def_wall, p_wall_buf = def_wall, wall_buf
        p_tr_trig, p_tr_dist, p_max_hold = tr_trig, tr_dist, max_hold
        trades_today += 1
        last_entry_bar = idx_bar

    def _regime_ok(b1_c: float, gf: float, lvl_meta: tuple | None) -> bool:
        if regime_gate == "ALL":
            return True
        if regime_gate == "ONLY_NEG_GAMMA":
            return b1_c < gf
        if regime_gate == "ONLY_POS_GAMMA":
            return b1_c >= gf
        if regime_gate == "FAR_FROM_FLIP_10":
            return abs(b1_c - gf) >= 10.0
        if lvl_meta is None:
            return False
        _, typ, wd, gex_v, _, _ = lvl_meta
        if regime_gate == "PUT_WALL_ONLY":
            return typ == "Wall" and gex_v < 0.0
        if regime_gate == "NO_CALL_WALL":
            return not (typ == "Wall" and gex_v > 0.0)
        if regime_gate == "WALL_W2_W3":
            return typ == "Wall" and wd >= 2
        return True

    def _eval_signal(b1: int, today: str, sg: dict) -> tuple:
        o1, h1, l1, c1 = opens[b1], highs[b1], lows[b1], closes[b1]
        tm1 = int(tmins[b1])
        rng1 = max(0.5, h1 - l1)
        body1 = c1 - o1
        mid_b1 = round05(0.5 * (h1 + l1))

        bw50 = max(1.0, n50u[b1] - n50l[b1])
        pos50 = (c1 - n50l[b1]) / bw50
        s50 = float(n50s[b1])
        bw30 = max(1.0, n30u[b1] - n30l[b1])
        pos30 = (c1 - n30l[b1]) / bw30
        s30 = float(n30s[b1])

        uw1 = h1 - max(o1, c1)
        lw1 = min(o1, c1) - l1
        wr3 = float(win_ret3[b1])
        wz1 = float(win_z[b1])
        gf = sg["gamma_flip"]
        lvls = sg["levels"]  # sorted [(price, type, width, gex, share, rank)]
        all_px = sg["all_px"]
        wall_px = sg["wall_px"]
        meta_by_px = sg["meta_by_px"]

        arch = cfg.arch
        var = cfg.variant

        # Limite horário padrão do operacional live
        max_tm = 810 if cfg.is_positional else 895
        if tm1 < 545 or tm1 > max_tm:
            return None

        # Atualiza contagem de toques para D6 sem look-ahead
        for p in all_px:
            if (l1 - 2.0) <= p <= (h1 + 2.0):
                wall_touches[p] = wall_touches.get(p, 0) + 1

        sig = 0
        kind = ""
        px_trig = 0.0
        def_w = 0.0
        valid_b = 1
        lvl_hit = None
        # defaults exit: (tp_type, orig_tp, sl, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr)
        tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
            1, 24.0, 10.0, 6.5, 1.5, 12.0, 5.0, 18, 3
        )

        # ------------------------------------------------------------------
        # D1: Pullback / Reteste Limit de Wall Rompida (inspirado EST-04 WIN)
        # ------------------------------------------------------------------
        if arch == "D1_PB_WALL_RETEST":
            pool = wall_px if var == "V2_MAIN_WALL_ONLY" else all_px
            s_thr = 0.40 if var != "V2_MAIN_WALL_ONLY" else 0.30
            tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                2, 24.0, 9.5, 6.5, 1.5, 12.0, 5.0, 18, 3
            )
            for p in pool:
                if o1 <= p + 0.5 and c1 > p + 0.5 and (c1 - p) <= 5.5 and body1 >= 1.5 and s50 >= s_thr and pos50 < 0.85:
                    if var != "V3_WITH_WIN_ALIGN" or (wr3 <= -3.0 or wz1 <= 0.0):
                        sig, kind, px_trig, def_w, valid_b, lvl_hit = 1, "LIMIT", float(p), float(p), 2, float(p)
                        break
                if o1 >= p - 0.5 and c1 < p - 0.5 and (p - c1) <= 5.5 and (-body1) >= 1.5 and s50 <= -s_thr and pos50 > 0.15:
                    if var != "V3_WITH_WIN_ALIGN" or (wr3 >= 3.0 or wz1 >= 0.0):
                        sig, kind, px_trig, def_w, valid_b, lvl_hit = -1, "LIMIT", float(p), float(p), 2, float(p)
                        break

        # ------------------------------------------------------------------
        # D2: Rompimento Momentum a Mercado (inspirado EST-07 WIN)
        # ------------------------------------------------------------------
        elif arch == "D2_BO_MOMENTUM_MKT":
            if last_entry_bar == b1:
                return None
            min_tm = 600 if var == "V1_NY_10_15" else 545
            if tm1 < min_tm:
                return None
            pool = wall_px if var == "V3_MAIN_WALL_BIG_TR" else all_px
            b_min = 2.5 if var == "V2_FULL_09_15" else 2.0
            s50_min = 0.45 if var == "V2_FULL_09_15" else 0.30
            s30_min = 0.45 if var == "V2_FULL_09_15" else 0.30
            if var == "V3_MAIN_WALL_BIG_TR":
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    0, 32.0, 11.5, 7.5, 1.5, 14.0, 6.0, 22, 3
                )
            else:
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    2, 24.0, 10.5, 7.0, 1.5, 12.0, 5.0, 18, 3
                )
            for p in pool:
                if o1 <= p + 0.5 and c1 > p + 1.0 and (c1 - p) <= 6.0 and body1 >= b_min and uw1 <= 0.30 * rng1 and s50 >= s50_min and s30 >= s30_min and pos50 < 0.82:
                    sig, kind, px_trig, def_w, lvl_hit = 1, "MKT", opens[b1 + 1], float(p), float(p)
                    break
                if o1 >= p - 0.5 and c1 < p - 1.0 and (p - c1) <= 6.0 and (-body1) >= b_min and lw1 <= 0.30 * rng1 and s50 <= -s50_min and s30 <= -s30_min and pos50 > 0.18:
                    sig, kind, px_trig, def_w, lvl_hit = -1, "MKT", opens[b1 + 1], float(p), float(p)
                    break

        # ------------------------------------------------------------------
        # D3: Pre-Breakout STOP Order (inspirado EST-09 WIN)
        # ------------------------------------------------------------------
        elif arch == "D3_PRE_BO_STOP":
            min_tm = 600 if var == "V1_ALL_LVLS_NY" else 545
            if tm1 < min_tm:
                return None
            if var == "V2_ALL_LVLS_CORE":
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    0, 28.0, 11.0, 7.5, 1.5, 14.0, 6.0, 20, 2
                )
            else:
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    2, 24.0, 10.0, 6.5, 1.5, 12.0, 5.0, 18, 2
                )
            if s30 >= 0.45 and s50 >= 0.25 and body1 >= 1.0 and pos30 < 0.80:
                if var != "V3_WITH_WIN_ALIGN" or (wr3 <= -3.0 or wz1 <= 0.0):
                    for p in all_px:
                        if p >= c1 - 0.5 and (p - c1) <= 4.0:
                            sig, kind, px_trig, def_w, valid_b, lvl_hit = 1, "STOP", max(p + 0.5, h1 + 0.5), float(p), 2, float(p)
                            break
            if sig == 0 and s30 <= -0.45 and s50 <= -0.25 and (-body1) >= 1.0 and pos30 > 0.20:
                if var != "V3_WITH_WIN_ALIGN" or (wr3 >= 3.0 or wz1 >= 0.0):
                    for p in all_px[::-1]:
                        if p <= c1 + 0.5 and (c1 - p) <= 4.0:
                            sig, kind, px_trig, def_w, valid_b, lvl_hit = -1, "STOP", min(p - 0.5, l1 - 0.5), float(p), 2, float(p)
                            break

        # ------------------------------------------------------------------
        # D4: MainWall Breakout STOP (inspirado EST-10 WIN)
        # ------------------------------------------------------------------
        elif arch == "D4_MAINWALL_STOP_1D":
            if var == "V1_1TR_DAY":
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    0, 28.0, 11.0, 7.5, 1.5, 14.0, 6.0, 20, 1
                )
            else:
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    2, 22.0, 9.5, 6.5, 1.5, 11.0, 4.5, 18, 2
                )
            if s30 >= 0.45 and s50 >= 0.25 and body1 >= 1.0 and pos30 < 0.82:
                for p in wall_px:
                    if p >= c1 - 0.5 and (p - c1) <= 4.5:
                        sig, kind, px_trig, def_w, valid_b, lvl_hit = 1, "STOP", max(p + 0.5, h1 + 0.5), float(p), 2, float(p)
                        break
            if sig == 0 and s30 <= -0.45 and s50 <= -0.25 and (-body1) >= 1.0 and pos30 > 0.18:
                for p in wall_px[::-1]:
                    if p <= c1 + 0.5 and (c1 - p) <= 4.5:
                        sig, kind, px_trig, def_w, valid_b, lvl_hit = -1, "STOP", min(p - 0.5, l1 - 0.5), float(p), 2, float(p)
                        break
            if sig == 0 and var == "V3_STOP_OR_PB":
                dw_l, ws_m = find_nearest_level(wall_px, l1)
                dw_h, wr_m = find_nearest_level(wall_px, h1)
                if s50 >= 0.60 and dw_l <= 4.0 and c1 > ws_m and pos50 <= 0.68:
                    sig, kind, px_trig, def_w, valid_b, lvl_hit = 1, "LIMIT", ws_m, ws_m, 2, ws_m
                elif s50 <= -0.60 and dw_h <= 4.0 and c1 < wr_m and pos50 >= 0.32:
                    sig, kind, px_trig, def_w, valid_b, lvl_hit = -1, "LIMIT", wr_m, wr_m, 2, wr_m

        # ------------------------------------------------------------------
        # D5: Posicional EOD Trend Rider (inspirado EST-15 e EST-16 WIN)
        # ------------------------------------------------------------------
        elif arch == "D5_POSICIONAL_EOD":
            tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                0, 55.0, 14.0, 9.0, 2.0, 16.0, 7.5, 100, 1
            )
            if var in ("V1_MKT_BO", "V3_MKT_WIN_ALIGN"):
                for p in all_px:
                    if o1 <= p + 0.5 and c1 > p + 1.0 and (c1 - p) <= 6.5 and body1 >= 2.0 and s50 >= 0.45 and s30 >= 0.45 and pos50 < 0.82:
                        if var != "V3_MKT_WIN_ALIGN" or (wr3 <= -5.0 or wz1 <= -0.3):
                            sig, kind, px_trig, def_w, lvl_hit = 1, "MKT", opens[b1 + 1], float(p), float(p)
                            break
                    if o1 >= p - 0.5 and c1 < p - 1.0 and (p - c1) <= 6.5 and (-body1) >= 2.0 and s50 <= -0.45 and s30 <= -0.45 and pos50 > 0.18:
                        if var != "V3_MKT_WIN_ALIGN" or (wr3 >= 5.0 or wz1 >= 0.3):
                            sig, kind, px_trig, def_w, lvl_hit = -1, "MKT", opens[b1 + 1], float(p), float(p)
                            break
            else:  # V2_STOP_BO (EST-16)
                if s30 >= 0.50 and s50 >= 0.35 and body1 >= 1.5 and pos30 < 0.78:
                    for p in all_px:
                        if p >= c1 - 0.5 and (p - c1) <= 4.5:
                            sig, kind, px_trig, def_w, valid_b, lvl_hit = 1, "STOP", max(p + 0.5, h1 + 0.5), float(p), 2, float(p)
                            break
                if sig == 0 and s30 <= -0.50 and s50 <= -0.35 and (-body1) >= 1.5 and pos30 > 0.22:
                    for p in all_px[::-1]:
                        if p <= c1 + 0.5 and (c1 - p) <= 4.5:
                            sig, kind, px_trig, def_w, valid_b, lvl_hit = -1, "STOP", min(p - 0.5, l1 - 0.5), float(p), 2, float(p)
                            break

        # ------------------------------------------------------------------
        # D6: Rompimento de Wall Gasta (inspirado WIN_E2)
        # ------------------------------------------------------------------
        elif arch == "D6_WALL_GASTA_BO":
            min_touches = 2 if var == "V3_2TOUCH_MKT" else 3
            s_min = 0.40 if var == "V3_2TOUCH_MKT" else 0.15
            tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                2, 24.0, 10.5, 6.5, 1.5, 12.0, 5.0, 18, 2
            )
            dc, lc = find_nearest_level(all_px, c1)
            if dc <= 5.0 and wall_touches.get(lc, 0) >= min_touches:
                if c1 > lc and c1 > o1 and (body1 / rng1) >= 0.35 and s50 >= s_min and s30 > 0.0 and 0.30 <= pos50 <= 0.85:
                    sig, def_w, lvl_hit = 1, lc, lc
                elif c1 < lc and c1 < o1 and ((-body1) / rng1) >= 0.35 and s50 <= -s_min and s30 < 0.0 and 0.15 <= pos50 <= 0.70:
                    sig, def_w, lvl_hit = -1, lc, lc
                if sig != 0:
                    if var == "V1_3TOUCH_LIMIT_MID":
                        kind, px_trig, valid_b = "LIMIT", mid_b1, 2
                    else:
                        kind, px_trig = "MKT", opens[b1 + 1]

        # ------------------------------------------------------------------
        # D7: Pullback a Favor da Tendencia na Wall
        # ------------------------------------------------------------------
        elif arch == "D7_TREND_PB_WALL":
            pool = wall_px if var == "V3_MAIN_WALL_PB" else all_px
            if var == "V3_MAIN_WALL_PB":
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    0, 26.0, 11.0, 7.0, 1.5, 13.0, 5.5, 20, 3
                )
            else:
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    2, 20.0, 10.0, 6.5, 1.5, 11.0, 4.5, 18, 3
                )
            dl, ls = find_nearest_level(pool, l1)
            dh, lr = find_nearest_level(pool, h1)
            if s50 >= 0.60 and s30 >= 0.30 and dl <= 3.5 and c1 > ls and c1 > o1 and 0.30 <= pos50 <= 0.72:
                sig, def_w, lvl_hit = 1, ls, ls
                if var == "V2_LIMIT_WALL":
                    kind, px_trig, valid_b = "LIMIT", round05(ls + 0.5), 2
                else:
                    kind, px_trig = "MKT", opens[b1 + 1]
            elif s50 <= -0.60 and s30 <= -0.30 and dh <= 3.5 and c1 < lr and c1 < o1 and 0.28 <= pos50 <= 0.70:
                sig, def_w, lvl_hit = -1, lr, lr
                if var == "V2_LIMIT_WALL":
                    kind, px_trig, valid_b = "LIMIT", round05(lr - 0.5), 2
                else:
                    kind, px_trig = "MKT", opens[b1 + 1]

        # ------------------------------------------------------------------
        # D8: Rompimento Estrutural GEX (GammaFlip / PutWall-W3 / NegGamma)
        # ------------------------------------------------------------------
        elif arch == "D8_GEX_REGIME_BO":
            if var == "V1_FLIP_CROSS":
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    0, 32.0, 12.0, 7.5, 1.5, 14.0, 6.0, 24, 2
                )
                if o1 <= gf + 1.0 and c1 > gf + 1.5 and (c1 - gf) <= 8.0 and body1 >= 2.0 and s50 >= 0.25:
                    sig, kind, px_trig, def_w = 1, "MKT", opens[b1 + 1], gf
                elif o1 >= gf - 1.0 and c1 < gf - 1.5 and (gf - c1) <= 8.0 and (-body1) >= 2.0 and s50 <= -0.25:
                    sig, kind, px_trig, def_w = -1, "MKT", opens[b1 + 1], gf
            elif var == "V2_PUTWALL_OR_W3_BO":
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    0, 28.0, 10.5, 7.0, 1.5, 13.0, 5.5, 20, 2
                )
                for p, typ, wd, gex_v, _, _ in lvls:
                    if typ != "Wall" or not (gex_v < 0.0 or wd >= 2):
                        continue
                    if o1 <= p + 0.5 and c1 > p + 1.0 and (c1 - p) <= 6.0 and body1 >= 1.5 and s50 >= 0.25 and s30 >= 0.25 and pos50 < 0.85:
                        sig, kind, px_trig, def_w, lvl_hit = 1, "MKT", opens[b1 + 1], float(p), float(p)
                        break
                    if o1 >= p - 0.5 and c1 < p - 1.0 and (p - c1) <= 6.0 and (-body1) >= 1.5 and s50 <= -0.25 and s30 <= -0.25 and pos50 > 0.15:
                        sig, kind, px_trig, def_w, lvl_hit = -1, "MKT", opens[b1 + 1], float(p), float(p)
                        break
            else:  # V3_NEG_GAMMA_TREND_RIDE
                tp_type, orig_tp, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, max_tr = (
                    0, 35.0, 11.5, 7.5, 1.5, 15.0, 6.5, 24, 2
                )
                if c1 < gf:
                    for p in all_px:
                        if o1 <= p + 0.5 and c1 > p + 1.0 and (c1 - p) <= 6.0 and body1 >= 2.0 and s50 >= 0.30 and s30 >= 0.30 and pos50 < 0.85:
                            sig, kind, px_trig, def_w, lvl_hit = 1, "MKT", opens[b1 + 1], float(p), float(p)
                            break
                        if o1 >= p - 0.5 and c1 < p - 1.0 and (p - c1) <= 6.0 and (-body1) >= 2.0 and s50 <= -0.30 and s30 <= -0.30 and pos50 > 0.15:
                            sig, kind, px_trig, def_w, lvl_hit = -1, "MKT", opens[b1 + 1], float(p), float(p)
                            break

        if sig == 0 or trades_today >= max_tr:
            return None

        lvl_meta = meta_by_px.get(lvl_hit) if lvl_hit is not None else None
        if not _regime_ok(c1, gf, lvl_meta):
            return None
        if sig_filter is not None and not sig_filter(today, tm1, sig):
            return None

        tp_final = calc_wdo_target_pts(round05(px_trig), sig, tp_type, orig_tp, wall_px, all_px, 0.5)
        return (sig, kind, round05(px_trig), valid_b, tp_final, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_w)

    for idx in range(2, n - 1):
        today = dates[idx]
        b1 = idx - 1
        if today != cur_day:
            if d_pos != 0:
                _close(opens[idx], "GAP_EOD", idx)
            pend_dir = 0
            cur_day = today
            trades_today = 0
            wall_touches = {}

        if today < START or today > END or today not in signed_wdo or dates[b1] != today:
            continue

        sg = signed_wdo[today]
        o0, h0, l0, c0 = opens[idx], highs[idx], lows[idx], closes[idx]
        tm0 = int(tmins[idx])

        # EOD
        if tm0 >= 1035:
            if d_pos != 0:
                _close(o0, "EOD", idx)
            pend_dir = 0
            continue

        # 1. Atualiza BE / Trailing / Time-stop na abertura da barra `idx` (apos b1 fechar)
        if d_pos != 0:
            if opened_intrabar:
                fav_c = (closes[b1] - entry_px) * d_pos
                if fav_c > max_fav:
                    max_fav = fav_c
                opened_intrabar = False
            else:
                bars_held += 1
                fav = (highs[b1] - entry_px) if d_pos == 1 else (entry_px - lows[b1])
                if fav > max_fav:
                    max_fav = fav
            if p_be_trig > 0.0 and not be_active and max_fav >= p_be_trig:
                if p_be_mode == 1 and p_def_wall > 0.0:
                    cand = max(curr_sl, min(round05(p_def_wall - p_wall_buf), round05(entry_px + p_be_lock))) if d_pos == 1 else min(curr_sl, max(round05(p_def_wall + p_wall_buf), round05(entry_px - p_be_lock)))
                else:
                    cand = round05(entry_px + d_pos * p_be_lock)
                if (d_pos == 1 and o0 > cand + 0.5) or (d_pos == -1 and o0 < cand - 0.5):
                    curr_sl = max(curr_sl, cand) if d_pos == 1 else min(curr_sl, cand)
                    be_active = True
            if p_tr_trig > 0.0 and max_fav >= p_tr_trig:
                cand_tr = round05(entry_px + max_fav - p_tr_dist) if d_pos == 1 else round05(entry_px - max_fav + p_tr_dist)
                if (d_pos == 1 and o0 > cand_tr + 0.5) or (d_pos == -1 and o0 < cand_tr - 0.5):
                    curr_sl = max(curr_sl, cand_tr) if d_pos == 1 else min(curr_sl, cand_tr)
            if bars_held >= p_max_hold:
                _close(o0, "TIME_STOP", idx)

        # 2. Avalia sinal em b1 se FLAT e sem pendente (ou substitui pendente expirado)
        if d_pos == 0 and pend_dir != 0 and pend_valid <= 0:
            pend_dir = 0

        if d_pos == 0 and pend_dir == 0:
            res = _eval_signal(b1, today, sg)
            if res is not None:
                sig, kind, px_trig, valid_b, tp_f, sl_f, be_t, be_l, tr_t, tr_d, mh, dw = res
                if kind == "MKT":
                    _open_pos(sig, o0, idx, False, tp_f, sl_f, be_t, be_l, tr_t, tr_d, mh, dw)
                else:
                    pt = 1 if kind == "LIMIT" else 2
                    # Verifica preenchimento plausivel sem gap contra regra do MT5
                    if pt == 1 and ((sig == 1 and o0 >= px_trig) or (sig == -1 and o0 <= px_trig)):
                        pend_dir, pend_type, pend_px, pend_valid = sig, pt, px_trig, valid_b
                        pend_params = (tp_f, sl_f, be_t, be_l, tr_t, tr_d, mh, dw)
                    elif pt == 2 and ((sig == 1 and o0 <= px_trig) or (sig == -1 and o0 >= px_trig)):
                        pend_dir, pend_type, pend_px, pend_valid = sig, pt, px_trig, valid_b
                        pend_params = (tp_f, sl_f, be_t, be_l, tr_t, tr_d, mh, dw)

        # 3. Checa trigger de ordem pendente na barra `idx`
        if d_pos == 0 and pend_dir != 0:
            trig = False
            if pend_type == 1:
                if (pend_dir == 1 and l0 <= pend_px) or (pend_dir == -1 and h0 >= pend_px):
                    trig = True
            else:
                if (pend_dir == 1 and o0 <= pend_px and h0 >= pend_px) or (pend_dir == -1 and o0 >= pend_px and l0 <= pend_px):
                    trig = True
            if trig:
                tp_f, sl_f, be_t, be_l, tr_t, tr_d, mh, dw = pend_params
                _open_pos(pend_dir, pend_px, idx, True, tp_f, sl_f, be_t, be_l, tr_t, tr_d, mh, dw)
                pend_dir = 0
            else:
                pend_valid -= 1
                if pend_valid <= 0:
                    pend_dir = 0

        # 4. Checa SL / TP intrabar na barra `idx` (SL conservador primeiro)
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


def build_configs() -> list[DirConfig]:
    specs = [
        ("D1_PB_WALL_RETEST", "V1_ALL_TP_WALL", "EST-04", False),
        ("D1_PB_WALL_RETEST", "V2_MAIN_WALL_ONLY", "EST-04", False),
        ("D1_PB_WALL_RETEST", "V3_WITH_WIN_ALIGN", "EST-04", False),
        ("D2_BO_MOMENTUM_MKT", "V1_NY_10_15", "EST-07", False),
        ("D2_BO_MOMENTUM_MKT", "V2_FULL_09_15", "EST-07", False),
        ("D2_BO_MOMENTUM_MKT", "V3_MAIN_WALL_BIG_TR", "EST-07", False),
        ("D3_PRE_BO_STOP", "V1_ALL_LVLS_NY", "EST-09", False),
        ("D3_PRE_BO_STOP", "V2_ALL_LVLS_CORE", "EST-09", False),
        ("D3_PRE_BO_STOP", "V3_WITH_WIN_ALIGN", "EST-09", False),
        ("D4_MAINWALL_STOP_1D", "V1_1TR_DAY", "EST-10", False),
        ("D4_MAINWALL_STOP_1D", "V2_2TR_DAY_TIGHT", "EST-10", False),
        ("D4_MAINWALL_STOP_1D", "V3_STOP_OR_PB", "EST-10", False),
        ("D5_POSICIONAL_EOD", "V1_MKT_BO", "EST-15", True),
        ("D5_POSICIONAL_EOD", "V2_STOP_BO", "EST-16", True),
        ("D5_POSICIONAL_EOD", "V3_MKT_WIN_ALIGN", "EST-15", True),
        ("D6_WALL_GASTA_BO", "V1_3TOUCH_LIMIT_MID", "WIN-E2", False),
        ("D6_WALL_GASTA_BO", "V2_3TOUCH_MKT", "WIN-E2", False),
        ("D6_WALL_GASTA_BO", "V3_2TOUCH_MKT", "WIN-E2", False),
        ("D7_TREND_PB_WALL", "V1_MKT_PB", "EST-04/06", False),
        ("D7_TREND_PB_WALL", "V2_LIMIT_WALL", "EST-04/06", False),
        ("D7_TREND_PB_WALL", "V3_MAIN_WALL_PB", "EST-04/06", False),
        ("D8_GEX_REGIME_BO", "V1_FLIP_CROSS", "GEX-BO", False),
        ("D8_GEX_REGIME_BO", "V2_PUTWALL_OR_W3_BO", "GEX-BO", False),
        ("D8_GEX_REGIME_BO", "V3_NEG_GAMMA_TREND_RIDE", "GEX-BO", False),
    ]
    return [DirConfig(a, v, w, p) for a, v, w, p in specs]


def main():
    t0 = time.time()
    os.makedirs(RES_DIR, exist_ok=True)
    ft, _ = load_flow_tables("min")
    set_gex_paths(WIN_PLAIN, WDO_PLAIN)

    signed_win = load_signed_gex_map(WIN_SIGNED)
    signed_wdo_raw = load_signed_gex_map(WDO_SIGNED)
    signed_wdo = {}
    for d, g in signed_wdo_raw.items():
        lvls = g["levels"]
        all_px = np.array([x[0] for x in lvls], dtype=float)
        wall_px = np.array([x[0] for x in lvls if x[1] == "Wall"], dtype=float)
        meta_by_px = {x[0]: x for x in lvls}
        signed_wdo[d] = {**g, "all_px": all_px, "wall_px": wall_px, "meta_by_px": meta_by_px}

    with setups_runner._window(START, END, None, None):
        mk = setups_runner._load_market()
        df_win, _, _, _, _, df_wdo, _, _, _, df_rsi7d = None, None, None, None, None, None, None, None, None, None
        df_win, _, _, _, _, df_wdo, _, n50d, n30d, _ = mk
        assert "win_ret3" in df_wdo.columns and "win_z" in df_wdo.columns, "df_wdo sem win_ret3/win_z!"

        bm_win, dt_win = build_bar_lookup(df_win)
        bm_wdo, dt_wdo = build_bar_lookup(df_wdo)
        ctx_prov = ContextProvider({"WIN": signed_win, "WDO": signed_wdo_raw}, {"WIN": bm_win, "WDO": bm_wdo}, {"WIN": dt_win, "WDO": dt_wdo})
        runner = SimRunner(mk, ft, ctx_prov)

        # Baselines (Live Schedule: WDO<=15h / WIN<=16h e BT Padrao)
        wdo_live3_sch = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "ALL", 895)]
        win_live7_sch = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", "ALL", 955)]
        wdo_noput_sch = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "NO_PUT_WALL", 895)]
        wdo_live3_bt = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "ALL", None)]
        win_live7_bt = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", "ALL", None)]

        all_dates = sorted(df_wdo.loc[(df_wdo["session_date"] >= START) & (df_wdo["session_date"] <= END), "session_date"].unique())
        s_live3_sch = daily_pnl_series(wdo_live3_sch, all_dates)
        worst20_days = list(s_live3_sch.nsmallest(20).index)
        worst20_loss = float(s_live3_sch.loc[worst20_days].sum())

        mk_arrays = {
            "dates": df_wdo["session_date"].astype(str).to_numpy(),
            "ts_str": df_wdo["t"].dt.strftime("%Y-%m-%d %H:%M").to_numpy(),
            "tmins": df_wdo["t_min"].astype(int).to_numpy(),
            "opens": df_wdo["open"].astype(float).to_numpy(),
            "highs": df_wdo["high"].astype(float).to_numpy(),
            "lows": df_wdo["low"].astype(float).to_numpy(),
            "closes": df_wdo["close"].astype(float).to_numpy(),
            "win_ret3": df_wdo["win_ret3"].fillna(0.0).astype(float).to_numpy(),
            "win_z": df_wdo["win_z"].fillna(0.0).astype(float).to_numpy(),
            "n50": (n50d[0], n50d[1], n50d[2], n50d[4]),
            "n30": (n30d[0], n30d[1], n30d[2], n30d[4]),
        }

        configs = build_configs()
        regimes = ("ALL", "ONLY_NEG_GAMMA", "ONLY_POS_GAMMA")
        cand_rows = []
        cand_trades = {}

        for cfg in configs:
            for reg in regimes:
                trs = simulate_wdo_directional(cfg, mk_arrays, signed_wdo, regime_gate=reg, sig_filter=None)
                m = eval_metrics(trs)
                sd = daily_pnl_series(trs, all_dates)
                corr = float(sd.corr(s_live3_sch)) if sd.std() > 0 and s_live3_sch.std() > 0 else 0.0
                hedge20 = float(sd.loc[worst20_days].sum())
                w_comb = eval_metrics(wdo_live3_sch + trs)
                p_comb = eval_metrics(win_live7_sch + wdo_live3_sch + trs)
                key = f"{cfg.arch}|{cfg.variant}|{reg}"
                cand_trades[key] = trs
                cand_rows.append({
                    "key": key,
                    "arch": cfg.arch,
                    "variant": cfg.variant,
                    "win_insp": cfg.win_insp,
                    "is_positional": cfg.is_positional,
                    "regime": reg,
                    "corr_wdo3": round(corr, 3),
                    "hedge_worst20": round(hedge20, 0),
                    **m,
                    "wdo_comb_ret_dd": w_comb["ret_dd"],
                    "wdo_comb_oos_rdd": w_comb["oos_ret_dd"],
                    "p10_comb_ret_dd": p_comb["ret_dd"],
                    "p10_comb_oos_rdd": p_comb["oos_ret_dd"],
                })

        df_all = pd.DataFrame(cand_rows)
        df_all.to_csv(os.path.join(RES_DIR, "wdo_dir_all_candidates.csv"), index=False)

        # Stage 2: Strict IS selection (por arquetipo, melhor config/regime no IS)
        min_is_ops = np.where(df_all["is_positional"], 25, 35)
        passed = df_all[(df_all["is_ops"] >= min_is_ops) & (df_all["is_pf"] >= 1.20) & (df_all["is_ret_dd"] >= 1.5) & (df_all["is_net"] > 0)].copy()
        if passed.empty:
            passed = df_all[df_all["is_ops"] >= 20].copy()
        top_by_arch = passed.sort_values("is_ret_dd", ascending=False).drop_duplicates("arch").head(8)

        # Se algum arquetipo ficou de fora dos 8, tambem mostramos o top geral no print
        stage2_rows = []
        top_keys = list(top_by_arch["key"])

        for _, row in top_by_arch.iterrows():
            cfg = next(c for c in configs if c.arch == row["arch"] and c.variant == row["variant"])
            reg = row["regime"]
            for flow_name in ("0_BASE_MT5", "3_FLUXO_INST", "1_JANELA_ASG", "14_NR_BREAKOUT_SQUEEZE"):
                sf = make_sig_filter(ft, "WDO", flow_name)
                trs = cand_trades[row["key"]] if flow_name == "0_BASE_MT5" else simulate_wdo_directional(cfg, mk_arrays, signed_wdo, regime_gate=reg, sig_filter=sf)
                m = eval_metrics(trs)
                sd = daily_pnl_series(trs, all_dates)
                corr = float(sd.corr(s_live3_sch)) if sd.std() > 0 and s_live3_sch.std() > 0 else 0.0
                hedge20 = float(sd.loc[worst20_days].sum())
                w_sch = eval_metrics(wdo_live3_sch + trs)
                p_sch = eval_metrics(win_live7_sch + wdo_live3_sch + trs)
                w_np = eval_metrics(wdo_noput_sch + trs)
                p_np = eval_metrics(win_live7_sch + wdo_noput_sch + trs)
                w_bt = eval_metrics(wdo_live3_bt + trs)
                p_bt = eval_metrics(win_live7_bt + wdo_live3_bt + trs)
                stage2_rows.append({
                    "kind": "SINGLE_FLOW",
                    "label": f"{row['arch']} ({row['variant']} | {reg})",
                    "flow": flow_name,
                    "corr_wdo3": round(corr, 3),
                    "hedge_worst20": round(hedge20, 0),
                    **m,
                    "sch_wdo_rdd": w_sch["ret_dd"], "sch_wdo_oos_rdd": w_sch["oos_ret_dd"],
                    "sch_p10_rdd": p_sch["ret_dd"], "sch_p10_oos_rdd": p_sch["oos_ret_dd"],
                    "sch_noput_wdo_rdd": w_np["ret_dd"], "sch_noput_p10_rdd": p_np["ret_dd"],
                    "bt_wdo_rdd": w_bt["ret_dd"], "bt_p10_rdd": p_bt["ret_dd"],
                })

        # Combinacoes de portfolio com os Top 1 / Top 2 direcionais (em 0_BASE_MT5 Puro OHLC)
        top_trs = [cand_trades[k] for k in top_keys]
        base_sch_w = eval_metrics(wdo_live3_sch)
        base_sch_p = eval_metrics(win_live7_sch + wdo_live3_sch)
        base_bt_w = eval_metrics(wdo_live3_bt)
        base_bt_p = eval_metrics(win_live7_bt + wdo_live3_bt)
        stage2_rows.append({
            "kind": "PORTFOLIO",
            "label": "0. ATUAL (WDO 01+05+07 / WIN 7)",
            "flow": "0_BASE_MT5",
            "corr_wdo3": 1.0,
            "hedge_worst20": round(worst20_loss, 0),
            **base_sch_w,
            "sch_wdo_rdd": base_sch_w["ret_dd"], "sch_wdo_oos_rdd": base_sch_w["oos_ret_dd"],
            "sch_p10_rdd": base_sch_p["ret_dd"], "sch_p10_oos_rdd": base_sch_p["oos_ret_dd"],
            "sch_noput_wdo_rdd": eval_metrics(wdo_noput_sch)["ret_dd"],
            "sch_noput_p10_rdd": eval_metrics(win_live7_sch + wdo_noput_sch)["ret_dd"],
            "bt_wdo_rdd": base_bt_w["ret_dd"], "bt_p10_rdd": base_bt_p["ret_dd"],
        })
        if len(top_trs) >= 2:
            comb2 = top_trs[0] + top_trs[1]
            for plbl, d_trs in [
                (f"ATUAL + TOP1_DIR ({top_keys[0]})", top_trs[0]),
                (f"ATUAL + TOP2_DIR ({top_keys[0]} + {top_keys[1]})", comb2),
            ]:
                w_s = eval_metrics(wdo_live3_sch + d_trs)
                p_s = eval_metrics(win_live7_sch + wdo_live3_sch + d_trs)
                w_n = eval_metrics(wdo_noput_sch + d_trs)
                p_n = eval_metrics(win_live7_sch + wdo_noput_sch + d_trs)
                w_b = eval_metrics(wdo_live3_bt + d_trs)
                p_b = eval_metrics(win_live7_bt + wdo_live3_bt + d_trs)
                stage2_rows.append({
                    "kind": "PORTFOLIO",
                    "label": plbl,
                    "flow": "0_BASE_MT5",
                    "corr_wdo3": round(float(daily_pnl_series(d_trs, all_dates).corr(s_live3_sch)), 3),
                    "hedge_worst20": round(float(daily_pnl_series(d_trs, all_dates).loc[worst20_days].sum()), 0),
                    **w_s,
                    "sch_wdo_rdd": w_s["ret_dd"], "sch_wdo_oos_rdd": w_s["oos_ret_dd"],
                    "sch_p10_rdd": p_s["ret_dd"], "sch_p10_oos_rdd": p_s["oos_ret_dd"],
                    "sch_noput_wdo_rdd": w_n["ret_dd"], "sch_noput_p10_rdd": p_n["ret_dd"],
                    "bt_wdo_rdd": w_b["ret_dd"], "bt_p10_rdd": p_b["ret_dd"],
                })

        df_s2 = pd.DataFrame(stage2_rows)
        df_s2.to_csv(os.path.join(RES_DIR, "wdo_dir_top_is_oos_portfolio.csv"), index=False)

        pd.set_option("display.max_columns", 30)
        pd.set_option("display.width", 260)
        print(f"\n[CONCLUIDO em {time.time() - t0:.1f}s] Worst-20 days sum WDO_LIVE_3 = R$ {worst20_loss:.0f}")
        print(f"Passaram no filtro IS estrito: {len(passed)} de {len(df_all)} configuracoes")
        print("\n=== TOP 12 POR IS RET/DD (PURO OHLC 0_BASE_MT5) ===")
        cols = ["arch", "variant", "regime", "ops", "wr", "pf", "net", "mdd", "ret_dd", "is_ops", "is_pf", "is_ret_dd", "oos_ops", "oos_pf", "oos_net", "oos_ret_dd", "corr_wdo3", "hedge_worst20", "wdo_comb_ret_dd", "p10_comb_ret_dd"]
        print(df_all.sort_values("is_ret_dd", ascending=False).head(15)[cols].to_string(index=False))

        print("\n=== STAGE 2: TOP POR ARQUETIPO x FLUXO & PORTFOLIO FIT ===")
        c2 = ["kind", "label", "flow", "ops", "pf", "net", "ret_dd", "is_ret_dd", "oos_ops", "oos_pf", "oos_ret_dd", "corr_wdo3", "hedge_worst20", "sch_wdo_rdd", "sch_p10_rdd", "sch_noput_wdo_rdd", "sch_noput_p10_rdd", "bt_wdo_rdd", "bt_p10_rdd"]
        print(df_s2[c2].to_string(index=False))


if __name__ == "__main__":
    main()
