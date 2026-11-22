# -*- coding: utf-8 -*-
"""
MOMENTO 2 — Estudo independente da estratégia de Pullback na VWAP Ancorada (AVWAP) na Máxima ou Mínima do Dia.

Princípio 100% causal (sem repainting / sem lookahead):
  - Em cada barra M5 t do pregão:
      * i_low[t]  = índice da mínima do dia considerando APENAS [0 .. t]
      * i_high[t] = índice da máxima do dia considerando APENAS [0 .. t]
      * AVWAP_low[t]  = sum_{m=i_low[t]..t} (px[m] * vol[m]) / sum_{m=i_low[t]..t} vol[m]
      * AVWAP_high[t] = sum_{m=i_high[t]..t} (px[m] * vol[m]) / sum_{m=i_high[t]..t} vol[m]
  - Gatilho avaliado no fechamento da barra t (t > i_anchor + min_age); entrada na abertura da barra e = t + 1.
  - Simulação tick-a-tick em M1 espelhando bt.sim / sim_exact para WIN e WDO (custos, slippage e execução idênticos).
  - Seleção de arquiteturas e saídas guiada estritamente no IS (<= 2026-07-31) com verificação cega no OOS (> 2026-07-31).
  - Inclui bateria de estresse, placebos (VWAP normal das 09h e Anti-Âncora) e impacto no portfólio 5176.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numba as nb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import win_cache, DS_WIN, XW
from research.div_master.wdo_especialista.robustez_final import days_cache as wdo_cache, DS as DS_WDO, X as X_WDO
from research.div_master.sim_portfolio_4_estrategias import build_strategies, eval_combo


# ───────────────────────── Simulador Numba Exato (WIN / WDO) ─────────────────────────

@nb.njit(cache=True)
def _sim_exact_nb(px, isop, off, nn, fb, o5, h5, l5, c5, tm5,
                  e, ep, d, sl, tp_fix, has_tp, be_trig, be_lock, tmax,
                  tick, cost, stop_slip, entry_slip, brl, adv_m1):
    """Espelho M1 tick-a-tick idêntico a sim_win_exact/sim_exact com estresse configurável."""
    ep_eff = ep + d * entry_slip
    stop = ep_eff - d * sl
    mfe = 0.0
    n5 = len(o5)
    tp = ep_eff + d * tp_fix if has_tp else ep_eff + d * 1e9

    for k in range(e, n5):
        if k > e:
            if tm5[k] >= 1045 or k - e > tmax:
                return ((o5[k] - ep_eff) * d - cost) * brl, int(tm5[k])
            if be_trig > 0.0 and mfe >= be_trig:
                cand = ep_eff + d * be_lock
                if (o5[k] - cand) * d > 0.0 and (cand - stop) * d > 0.0:
                    stop = cand

        nt = int(nn[k]) if fb[k] == 0 else 4
        for j in range(nt):
            if fb[k] == 0:
                p = px[off[k] + j]
                is_o = isop[off[k] + j]
            else:
                if j == 0:
                    p, is_o = o5[k], True
                elif j == 1:
                    p, is_o = (l5[k] if d == 1 else h5[k]), False
                elif j == 2:
                    p, is_o = (h5[k] if d == 1 else l5[k]), False
                else:
                    p, is_o = c5[k], False

            if k == e and j == 0:
                continue

            if (p - stop) * d <= 0.0:
                fill = p if is_o else (stop - d * stop_slip)
                return ((fill - ep_eff) * d - cost) * brl, int(tm5[k])

            if has_tp and (p - tp) * d >= 0.0:
                if adv_m1 and not is_o:
                    if fb[k] == 0:
                        blk_end = min(nt, (j // 4 + 1) * 4)
                        for q in range(j, blk_end):
                            if (px[off[k] + q] - stop) * d <= 0.0:
                                return (((stop - d * stop_slip) - ep_eff) * d - cost) * brl, int(tm5[k])
                    else:
                        if (d == 1 and l5[k] <= stop) or (d == -1 and h5[k] >= stop):
                            return (((stop - d * stop_slip) - ep_eff) * d - cost) * brl, int(tm5[k])
                fill = p if is_o else tp
                return ((fill - ep_eff) * d - cost) * brl, int(tm5[k])

            if (p - ep_eff) * d > mfe:
                mfe = (p - ep_eff) * d

    return ((c5[n5 - 1] - ep_eff) * d - cost) * brl, int(tm5[n5 - 1])


# ───────────────────────── Pré-computação AVWAP Causal ─────────────────────────

def _causal_atr14(h: np.ndarray, l: np.ndarray, c: np.ndarray, tick: float) -> np.ndarray:
    n = len(c)
    tr = np.empty(n, dtype=float)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.empty(n, dtype=float)
    s = 0.0
    for i in range(n):
        if i < 14:
            s += tr[i]
            atr[i] = max(s / (i + 1), tick)
        else:
            atr[i] = max((atr[i - 1] * 13.0 + tr[i]) / 14.0, tick)
    return atr


def _compute_avwap_day(h: np.ndarray, l: np.ndarray, c: np.ndarray, v: np.ndarray,
                       extreme_anchor: bool = False, reset_tie: bool = False):
    """
    Calcula bar-a-bar de forma 100% causal:
      - aw_lo, i_lo, d_lo, age_lo, imp_lo (impulso máximo em preço pré-barra t desde i_lo)
      - aw_hi, i_hi, d_hi, age_hi, imp_hi
      - aw_day (VWAP padrão ancorada na barra 0)
    """
    n = len(c)
    tp = (h + l + c) / 3.0

    aw_lo = np.empty(n, dtype=float)
    aw_hi = np.empty(n, dtype=float)
    aw_day = np.empty(n, dtype=float)
    i_lo = np.empty(n, dtype=np.int64)
    i_hi = np.empty(n, dtype=np.int64)
    d_lo = np.empty(n, dtype=float)
    d_hi = np.empty(n, dtype=float)
    imp_lo = np.zeros(n, dtype=float)  # max(h[i_lo..t-1]) - low_day
    imp_hi = np.zeros(n, dtype=float)  # high_day - min(l[i_hi..t-1])

    cur_lo = l[0]
    cur_hi = h[0]
    idx_lo = 0
    idx_hi = 0
    pv_lo, v_lo = 0.0, 0.0
    pv_hi, v_hi = 0.0, 0.0
    pv_day, v_day = 0.0, 0.0
    max_since_lo = h[0]
    min_since_hi = l[0]

    for t in range(n):
        vol = v[t] if v[t] > 0.0 else 1.0
        pv_day += tp[t] * vol
        v_day += vol
        aw_day[t] = pv_day / v_day

        # Low anchor update (causal, somente [0..t])
        is_new_lo = (l[t] <= cur_lo) if (t > 0 and reset_tie) else (t > 0 and l[t] < cur_lo)
        if t == 0 or is_new_lo:
            cur_lo = l[t]
            idx_lo = t
            pv_lo, v_lo = 0.0, 0.0
            max_since_lo = h[t]
            imp_lo[t] = 0.0
        else:
            imp_lo[t] = max(0.0, max_since_lo - cur_lo)
            if h[t] > max_since_lo:
                max_since_lo = h[t]

        px_lo = cur_lo if (extreme_anchor and t == idx_lo) else tp[t]
        pv_lo += px_lo * vol
        v_lo += vol
        aw_lo[t] = pv_lo / v_lo
        i_lo[t] = idx_lo
        d_lo[t] = cur_lo

        # High anchor update (causal, somente [0..t])
        is_new_hi = (h[t] >= cur_hi) if (t > 0 and reset_tie) else (t > 0 and h[t] > cur_hi)
        if t == 0 or is_new_hi:
            cur_hi = h[t]
            idx_hi = t
            pv_hi, v_hi = 0.0, 0.0
            min_since_hi = l[t]
            imp_hi[t] = 0.0
        else:
            imp_hi[t] = max(0.0, cur_hi - min_since_hi)
            if l[t] < min_since_hi:
                min_since_hi = l[t]

        px_hi = cur_hi if (extreme_anchor and t == idx_hi) else tp[t]
        pv_hi += px_hi * vol
        v_hi += vol
        aw_hi[t] = pv_hi / v_hi
        i_hi[t] = idx_hi
        d_hi[t] = cur_hi

    return dict(
        aw_lo=aw_lo, aw_hi=aw_hi, aw_day=aw_day,
        i_lo=i_lo, i_hi=i_hi, d_lo=d_lo, d_hi=d_hi,
        imp_lo=imp_lo, imp_hi=imp_hi,
    )


def prepare_asset(asset: str) -> dict:
    sym = "WIN_N" if asset == "WIN" else "WDO_N"
    DS = DS_WIN if asset == "WIN" else DS_WDO
    cache = win_cache if asset == "WIN" else wdo_cache
    X = XW if asset == "WIN" else X_WDO

    m5 = pd.read_csv(os.path.join(bt.RATES, f"mt5_{sym}_M5.csv"), parse_dates=["t"])
    m5["date"] = m5.t.dt.strftime("%Y-%m-%d")
    m5["tm"] = m5.t.dt.hour * 60 + m5.t.dt.minute
    m5 = m5[(m5.tm >= 540) & (m5.tm <= 1075) & (m5.date <= bt.END)].reset_index(drop=True)

    vol_map = {}
    for d, g in m5.groupby("date"):
        vol_map[d] = (
            g["tm"].values.astype(np.int64),
            g["close"].values.astype(float),
            g["real_volume"].values.astype(float),
            g["tick_volume"].values.astype(float),
        )

    out = {}
    for d in sorted(cache):
        fb, w_all, w_wall, D = cache[d]
        tm_csv, cl_csv, rvol, tvol = vol_map[d]
        assert len(tm_csv) == len(D["tm5"]) and np.array_equal(tm_csv, D["tm5"]), f"{asset} {d} tm mismatch"
        assert np.allclose(cl_csv, D["c5"]), f"{asset} {d} close mismatch"

        atr = _causal_atr14(D["h5"], D["l5"], D["c5"], X["tick"])
        wave_by_tm = {bt.hm(b["time"]): float(b.get("wave", 0.0)) for b in fb}
        wave = np.array([wave_by_tm.get(int(tm), 0.0) for tm in D["tm5"]], dtype=float)

        av_std = _compute_avwap_day(D["h5"], D["l5"], D["c5"], rvol, extreme_anchor=False, reset_tie=False)
        av_ext = _compute_avwap_day(D["h5"], D["l5"], D["c5"], rvol, extreme_anchor=True, reset_tie=False)
        av_tie = _compute_avwap_day(D["h5"], D["l5"], D["c5"], rvol, extreme_anchor=False, reset_tie=True)

        out[d] = dict(
            D=D, atr=atr, wave=wave, w_all=w_all, w_wall=w_wall,
            rvol=rvol, tvol=tvol,
            av_std=av_std, av_ext=av_ext, av_tie=av_tie,
        )
    return out


# ───────────────────────── Gerador Causal de Sinais AVWAP ─────────────────────────

def collect_avwap_signals(
    asset: str,
    prep: dict,
    anchor_mode: str = "HLC3",         # HLC3 | EXTREME | TIE_RESET | VWAP_DAY | ANTI_ANCHOR
    trig_mode: str = "T2_TOUCH_DIR",   # T1_HOLD | T2_TOUCH_DIR | T3_RECLAIM | T4_REV_NEXT
    min_age: int = 6,
    min_imp_atr: float = 1.5,
    tol_atr: float = 0.20,
    pierce_atr: float = 0.60,
    dominant_only: bool = False,
    max_pb_seq: int = 99,
    min_tm: int = 570,                 # entrada >= 09:30 (ou 09:05)
    max_tm: int = 1005,
    cooldown: int = 2,
) -> pd.DataFrame:
    """Extrai sinais causais de pullback em AVWAP no fechamento de t, entrada na abertura de e = t + 1."""
    X = XW if asset == "WIN" else X_WDO
    tick = X["tick"]
    lo_w, hi_w = bt.WINDOW[asset]
    wall_zone = 150.0 if asset == "WIN" else 3.5
    min_nw = 50.0 if asset == "WIN" else 2.0

    rows = []
    for d in sorted(prep):
        P = prep[d]
        D = P["D"]
        o5, h5, l5, c5, tm5 = D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"]
        atr = P["atr"]
        wave = P["wave"]
        w_all, w_wall = P["w_all"], P["w_wall"]
        n = len(c5)

        if anchor_mode == "EXTREME":
            av = P["av_ext"]
        elif anchor_mode == "TIE_RESET":
            av = P["av_tie"]
        else:
            av = P["av_std"]

        pb_count = {(1, -1): 0, (-1, -1): 0}
        last_anchor_seen = {1: -1, -1: -1}
        last_trig_bar = {1: -999, -1: -999}

        for t in range(3, n - 1):
            e = t + 1
            tm = int(tm5[e])
            if tm < lo_w or tm > hi_w or tm < min_tm or tm > max_tm:
                continue

            ep = float(o5[e])
            a = float(atr[t])
            tol = tol_atr * a
            pierce = pierce_atr * a

            for dr in (1, -1):
                if t - last_trig_bar[dr] < cooldown:
                    continue

                if anchor_mode == "VWAP_DAY":
                    aw = av["aw_day"]
                    anchor_idx = av["i_lo"][t] if dr == 1 else av["i_hi"][t]
                    imp_val = av["imp_lo"][t] if dr == 1 else av["imp_hi"][t]
                elif anchor_mode == "ANTI_ANCHOR":
                    # Placebo anti-âncora: comprar pullback na AVWAP da máxima / vender na AVWAP da mínima
                    aw = av["aw_hi"] if dr == 1 else av["aw_lo"]
                    anchor_idx = int(av["i_hi"][t] if dr == 1 else av["i_lo"][t])
                    imp_val = av["imp_hi"][t] if dr == 1 else av["imp_lo"][t]
                else:
                    aw = av["aw_lo"] if dr == 1 else av["aw_hi"]
                    anchor_idx = int(av["i_lo"][t] if dr == 1 else av["i_hi"][t])
                    imp_val = av["imp_lo"][t] if dr == 1 else av["imp_hi"][t]

                age = t - anchor_idx
                if age < min_age:
                    continue
                if anchor_mode != "ANTI_ANCHOR":
                    if (imp_val / a) < min_imp_atr:
                        continue
                else:
                    # Para anti-âncora exige apenas afastamento prévio do preço acima/abaixo da aw
                    sep = max(0.0, float(dr * (c5[t - 1] - aw[t - 1])))
                    if sep / a < 0.3:
                        continue

                if dominant_only and anchor_mode not in ("VWAP_DAY", "ANTI_ANCHOR"):
                    # Âncora sendo defendida deve ser mais antiga que o extremo oposto (ex.: fundo antes do topo na alta)
                    other_idx = int(av["i_hi"][t] if dr == 1 else av["i_lo"][t])
                    if anchor_idx >= other_idx:
                        continue

                # Reset contador de pullbacks se mudou a âncora
                if anchor_idx != last_anchor_seen[dr]:
                    last_anchor_seen[dr] = anchor_idx
                    pb_count[(dr, -1)] = 0

                # Avalia gatilho
                aw_t = float(aw[t])
                aw_prev = float(aw[t - 1])
                ext_against = float(l5[t]) if dr == 1 else float(h5[t])
                ext_prev_against = float(l5[t - 1]) if dr == 1 else float(h5[t - 1])
                body_dir = dr * float(c5[t] - o5[t])
                rng = max(float(h5[t] - l5[t]), tick)
                close_pos = (float(c5[t] - l5[t]) / rng) if dr == 1 else (float(h5[t] - c5[t]) / rng)

                # Distância de toque e fechamento relativo à AVWAP (em termos de dr: >0 está no lado certo)
                touch_pen = dr * (aw_t - ext_against)       # >0 significa furou contra; [-tol, +pierce] é zona válida
                close_side = dr * (float(c5[t]) - aw_t)     # >0 fechou no lado a favor da tendência
                prev_side = dr * (float(c5[t - 1]) - aw_prev)

                fired = False
                if trig_mode == "T1_HOLD":
                    fired = (prev_side > 0.0) and (-tol <= touch_pen <= pierce) and (close_side >= -0.15 * a)
                elif trig_mode == "T2_TOUCH_DIR":
                    fired = (prev_side > 0.0) and (-tol <= touch_pen <= pierce) and (close_side > 0.0) and (body_dir > 0.0)
                elif trig_mode == "T3_RECLAIM":
                    # Barra t ou t-1 furou a AVWAP contra e barra t fecha reconquistando a favor
                    furou_t = (touch_pen > 0.0) and (touch_pen <= pierce)
                    furou_p = (prev_side < 0.0) and (dr * (aw_prev - ext_prev_against) <= pierce)
                    fired = (furou_t or furou_p) and (close_side > 0.0) and (body_dir > 0.0) and (close_pos >= 0.5)
                elif trig_mode == "T4_REV_NEXT":
                    # Barra t-1 testou a AVWAP sem colapsar e barra t confirma retomada a favor
                    pen_prev = dr * (aw_prev - ext_prev_against)
                    fired = (-tol <= pen_prev <= pierce) and (dr * (float(c5[t - 1]) - aw_prev) >= -0.30 * a) \
                            and (close_side > 0.0) and (body_dir > 0.0) and (dr * (float(c5[t] - c5[t - 1])) > 0.0)

                if not fired:
                    continue

                pb_count[(dr, -1)] += 1
                seq_pb = pb_count[(dr, -1)]
                if seq_pb > max_pb_seq:
                    continue

                last_trig_bar[dr] = t

                # Contextos causais em t / e
                half50 = max(float(D["u50"][e] - D["c50"][e]), tick)
                ext50 = -dr * float(D["c5"][t] - D["c50"][e]) / half50
                slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
                aw_slope = dr * float(aw[t] - aw[max(0, t - 3)]) / a
                flow_t = dr * float(wave[t])
                flow_rev = dr * float(wave[t] - wave[t - 1])

                # Distância para Walls GEX e Máx/Mín causal do dia
                d_aw_wall = min((abs(aw_t - w) for w in w_wall), default=99999.0)
                d_px_wall = min((abs(ext_against - w) for w in w_wall), default=99999.0)
                near_wall = (min(d_aw_wall, d_px_wall) <= wall_zone)

                nw_all = bt.next_level(w_all, ep, dr, min_nw + X["front"])
                nw_all_d = dr * (nw_all - ep) - X["front"] if nw_all is not None else np.nan

                day_tgt_px = float(av["d_hi"][t] if dr == 1 else av["d_lo"][t]) - dr * X["front"]
                day_tgt_d = dr * (day_tgt_px - ep)

                # Pivô estrutural da perna de pullback (mínimo/máximo de [t-1 .. t])
                piv_pb = min(float(l5[t - 1]), float(l5[t])) if dr == 1 else max(float(h5[t - 1]), float(h5[t]))

                other_idx = int(av["i_hi"][t] if dr == 1 else av["i_lo"][t])
                is_dom = anchor_idx < other_idx

                rows.append(dict(
                    date=d, e=e, ep=ep, dir=dr, tm=tm, hh=tm // 60,
                    age=age, imp_atr=imp_val / a, seq_pb=seq_pb, is_dom=is_dom,
                    aw=aw_t, aw_slope=aw_slope, atr=a,
                    ext50=ext50, slope50=slope50,
                    flow_t=flow_t, flow_rev=flow_rev,
                    near_wall=near_wall, nw_all_d=nw_all_d,
                    day_tgt_d=day_tgt_d, piv_pb=piv_pb,
                    dist_day_ext_atr=max(0.0, dr * (float(av["d_hi"][t] if dr == 1 else av["d_lo"][t]) - ep)) / a,
                ))

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["date", "tm", "dir"]).reset_index(drop=True)


# ───────────────────────── Motor de Simulação e Métricas ─────────────────────────

def run_sim_df(
    df: pd.DataFrame,
    asset: str,
    sl_mode: str = "fix",      # fix | struct | aw_buf
    sl_val: float = 240.0,     # pts se fix, ou buffer pts se struct
    tp_mode: str = "fix",      # fix | rr | day_ext | nw_all | sniper | none
    tp_val: float = 240.0,     # pts se fix, multiplicador R se rr
    be_trig: float = 0.0,
    be_lock: float = 0.0,
    tmax: int = 24,
    mode: str = "padrao",      # padrao | stop2t | custo2x | entry1t | adv_m1 | pesado | invertida
    mgmt_mode: str = "UM",
    lots_mult: float = 1.0,
) -> tuple[dict, pd.DataFrame]:
    if len(df) == 0:
        return bt.stats(pd.DataFrame(columns=["date", "tm", "xt", "pnl"]), "pnl", "xt"), df

    DS = DS_WIN if asset == "WIN" else DS_WDO
    X = XW if asset == "WIN" else X_WDO
    tick = float(X["tick"])
    cost = float(X["cost"])
    stop_slip = tick
    entry_slip = 0.0
    adv_m1 = False
    sl_add = 0.0

    if mode == "stop2t":
        sl_add = 2.0 * tick
    elif mode == "custo2x":
        cost = cost * 2.0
    elif mode == "entry1t":
        entry_slip = tick
    elif mode == "adv_m1":
        adv_m1 = True
    elif mode == "pesado":
        sl_add = 2.0 * tick
        cost = cost * 2.0 + tick

    sl_min = 4.0 * tick
    sl_max = 360.0 if asset == "WIN" else 16.0
    tp_lo, tp_hi = (100.0, 600.0) if asset == "WIN" else (4.0, 24.0)
    nw_min, nw_lo, nw_hi = (50.0, 80.0, 440.0) if asset == "WIN" else (2.0, 3.5, 20.0)

    n = len(df)
    pnl = np.full(n, np.nan)
    xt = np.zeros(n, dtype=np.int64)

    for i, r in enumerate(df.itertuples()):
        D = DS[r.date]
        orig_dr = int(r.dir)
        dr = -orig_dr if mode == "invertida" else orig_dr
        ep = float(r.ep)

        # Stop (calculado usando a estrutura da sinalização original)
        if sl_mode == "fix":
            sl = sl_val
        elif sl_mode == "struct":
            sl = orig_dr * (ep - (float(r.piv_pb) - orig_dr * sl_val))
            sl = float(np.round(sl / tick) * tick)
            if sl < sl_min or sl > sl_max:
                continue
        elif sl_mode == "aw_buf":
            sl = orig_dr * (ep - (float(r.aw) - orig_dr * sl_val))
            sl = float(np.round(sl / tick) * tick)
            if sl < sl_min or sl > sl_max:
                continue
        else:
            sl = sl_val
        sl_eff = sl + sl_add

        # Sniper mode usa exit_A padrão do ativo (com estresse respeitado via _sim_exact_nb para comparação limpa)
        if tp_mode == "sniper":
            if asset == "WIN":
                res1, t1 = bt.exit_A("WIN", D, r.e, ep, dr, [])
                # Para sniper com estresse seria diferente, mas mantemos padrão bt.exit_A por contrato (dividido por 2)
                pnl[i] = (res1 / 2.0) * lots_mult
                xt[i] = t1
            else:
                res1, t1 = bt.exit_A("WDO", D, r.e, ep, dr, [])
                pnl[i] = res1 * lots_mult
                xt[i] = t1
            continue

        # Target
        has_tp = True
        tp_pts = 0.0
        if tp_mode == "fix":
            tp_pts = tp_val
        elif tp_mode == "rr":
            tp_pts = float(np.round((tp_val * sl) / tick) * tick)
        elif tp_mode == "day_ext":
            if np.isnan(r.day_tgt_d) or r.day_tgt_d < tp_lo:
                continue
            tp_pts = min(float(r.day_tgt_d), tp_hi)
            tp_pts = float(np.round(tp_pts / tick) * tick)
        elif tp_mode == "nw_all":
            if np.isnan(r.nw_all_d) or r.nw_all_d < nw_min:
                continue
            tp_pts = min(max(float(r.nw_all_d), nw_lo), nw_hi)
            tp_pts = float(np.round(tp_pts / tick) * tick)
        elif tp_mode == "none":
            has_tp = False
            tp_pts = 0.0

        p, x = _sim_exact_nb(
            D["px"], D["op"], D["off"], D["nn"], D["fb"],
            D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"],
            int(r.e), ep, dr, sl_eff, tp_pts, has_tp,
            float(be_trig), float(be_lock), int(tmax),
            tick, cost, stop_slip, entry_slip, float(X["brl"]), adv_m1
        )
        pnl[i] = p * lots_mult
        xt[i] = x

    out = df[["date", "tm", "dir", "hh"]].copy()
    out["asset"] = asset
    out["pnl"] = pnl
    out["xt"] = xt
    out = out.dropna(subset=["pnl"]).reset_index(drop=True)
    if len(out) == 0:
        return bt.stats(pd.DataFrame(columns=["date", "tm", "xt", "pnl"]), "pnl", "xt"), out
    tf = bt.mgmt(out, "pnl", "xt", mgmt_mode)
    st = bt.stats(tf, "pnl", "xt")
    d_sum = tf.groupby("date")["pnl"].sum()
    st["worst_day"] = round(float(d_sum.min())) if len(d_sum) else 0
    return st, tf


def fmt_row(lbl: str, st: dict) -> str:
    sub = f"{st.get('h1', 0):+5d}/{st.get('h2', 0):+5d}/{st.get('oos', 0):+5d}"
    return (
        f"| {lbl:<44} | {st['ops']:4d} | {st['wr']:4.1f}% | {st['pf']:4.2f} | "
        f"{st['net']:+7d} | {st['dd']:5d} | {st['rdd']:5.2f} | "
        f"{st['is_']:+6d}({st['rdd_is']:4.2f}) | {st['oos']:+6d}({st['rdd_oos']:4.2f}) | "
        f"{st['meses']:>5} | {sub:<19} | {st.get('worst_day', 0):+6d} |"
    )


def table_header() -> list[str]:
    return [
        "| Setup / Regra                                |  Ops |    WR |   PF |  Net R$ |    DD |  R/DD | IS (R/DD)     | OOS (R/DD)    | Meses | H1 / H2 / OOS       | PiorDia |",
        "|----------------------------------------------|------|-------|------|---------|-------|-------|---------------|---------------|-------|---------------------|---------|",
    ]


# ───────────────────────── Execução Principal (Momento 2) ─────────────────────────

def main():
    t0 = time.time()
    lines = []

    def log(*parts: str):
        if not parts:
            print("")
            lines.append("")
            return
        for s in parts:
            print(s)
            lines.append(s)

    prep = {
        "WIN": prepare_asset("WIN"),
        "WDO": prepare_asset("WDO"),
    }
    dates_w = sorted(prep["WIN"])
    dates_d = sorted(prep["WDO"])

    log("# Momento 2 — Estratégia de Pullback na VWAP Ancorada na Máxima / Mínima do Dia")
    log("")
    log(f"**Pregões avaliados:** WIN={len(dates_w)} (`{dates_w[0]}` a `{dates_w[-1]}`), WDO={len(dates_d)} (`{dates_d[0]}` a `{dates_d[-1]}`)")
    log("**Split de validação:** H1 `<= 2026-04-30` · H2 `<= 2026-07-31` · IS = H1+H2 (`<= 2026-07-31`) · OOS Cego `> 2026-07-31`")
    log("**Volume AVWAP:** `real_volume` das barras MT5 M5 (`mt5_WIN_N_M5.csv` / `mt5_WDO_N_M5.csv`), 100% causal bar-a-bar em `[i_anchor .. t]`.")
    log("**Execução:** M1 tick-a-tick causal (`_sim_exact_nb`, entrada na abertura de `e = t + 1`), custo padrão + 1 tick slippage no stop.")
    log("")

    # Warm-up numba
    _tmp = collect_avwap_signals("WIN", prep["WIN"], "HLC3", "T2_TOUCH_DIR", 6, 1.5, 0.2, 0.6)
    run_sim_df(_tmp.head(5), "WIN", "fix", 240.0, "fix", 240.0, 0.0, 0.0, 24)

    # ── SEÇÃO 2A: VARREDURA DE ARQUITETURAS DE SINAL (IS-GUIDED) ─────────────────────────
    log("## 2A. Varredura Sistemática de Sinais AVWAP (Saída Neutra Fixa)")
    log("")
    log("Saída neutra de comparação: **WIN** = `SL 240 / TP 240 / tmax 24` · **WDO** = `SL 10 / TP 10 / tmax 24`.")
    log("Classificação ordenada por **Ret/DD IS** (exigindo >= 35 ops no IS), exibindo o OOS cego ao lado.")
    log("")

    base_exit = {
        "WIN": dict(sl_mode="fix", sl_val=240.0, tp_mode="fix", tp_val=240.0, tmax=24),
        "WDO": dict(sl_mode="fix", sl_val=10.0, tp_mode="fix", tp_val=10.0, tmax=24),
    }

    configs_2a = []
    for anch in ("HLC3", "EXTREME", "TIE_RESET"):
        for trig in ("T1_HOLD", "T2_TOUCH_DIR", "T3_RECLAIM", "T4_REV_NEXT"):
            configs_2a.append((f"{anch[:3]}|{trig[3:]}|age6|imp1.5|all",
                               dict(anchor_mode=anch, trig_mode=trig, min_age=6, min_imp_atr=1.5,
                                    tol_atr=0.20, pierce_atr=0.60, dominant_only=False, max_pb_seq=99),
                               lambda df: np.ones(len(df), bool), "BASE"))

    # Grade de maturidade, impulso, dominância e filtros causais sobre HLC3 + T2/T3/T4
    for trig in ("T1_HOLD", "T2_TOUCH_DIR", "T3_RECLAIM", "T4_REV_NEXT"):
        for age, imp in ((3, 1.0), (6, 1.5), (9, 2.0), (12, 2.5)):
            configs_2a.append((f"HLC|{trig[3:]}|a{age}|i{imp}|pb1",
                               dict(anchor_mode="HLC3", trig_mode=trig, min_age=age, min_imp_atr=imp,
                                    tol_atr=0.20, pierce_atr=0.60, dominant_only=False, max_pb_seq=1),
                               lambda df: np.ones(len(df), bool), "MAT_PB1"))
            configs_2a.append((f"HLC|{trig[3:]}|a{age}|i{imp}|DOM",
                               dict(anchor_mode="HLC3", trig_mode=trig, min_age=age, min_imp_atr=imp,
                                    tol_atr=0.20, pierce_atr=0.60, dominant_only=True, max_pb_seq=99),
                               lambda df: np.ones(len(df), bool), "MAT_DOM"))
            configs_2a.append((f"EXT|{trig[3:]}|a{age}|i{imp}|DOM_pb1",
                               dict(anchor_mode="EXTREME", trig_mode=trig, min_age=age, min_imp_atr=imp,
                                    tol_atr=0.20, pierce_atr=0.60, dominant_only=True, max_pb_seq=1),
                               lambda df: np.ones(len(df), bool), "EXT_DOM1"))

    # Filtros de contexto aplicados sobre bases representativas (HLC3 age6 imp1.5 + DOM)
    ctx_filters = [
        ("RAW",          lambda d: np.ones(len(d), bool)),
        ("NO_11H",       lambda d: d["hh"] != 11),
        ("H_0930_1530",  lambda d: (d["tm"] >= 570) & (d["tm"] <= 930)),
        ("SLOPE_FAV",    lambda d: d["aw_slope"] > 0.0),
        ("FLOW_FAV",     lambda d: d["flow_t"] > 0.0),
        ("FLOW_REV",     lambda d: d["flow_rev"] > 0.0),
        ("NEAR_WALL",    lambda d: d["near_wall"]),
        ("NWE_ALINH",    lambda d: (d["ext50"] > -0.5) & (d["slope50"] > 0.0)),
        ("DOM_NO11",     lambda d: d["is_dom"] & (d["hh"] != 11)),
        ("DOM_SLOPE",    lambda d: d["is_dom"] & (d["aw_slope"] > 0.0)),
        ("DOM_FLOW",     lambda d: d["is_dom"] & (d["flow_t"] > 0.0)),
        ("DOM_WALL",     lambda d: d["is_dom"] & d["near_wall"]),
        ("COMPRA_ONLY",  lambda d: d["dir"] == 1),
        ("VENDA_ONLY",   lambda d: d["dir"] == -1),
    ]

    best_signals = {}
    sig_cache = {}

    for asset in ("WIN", "WDO"):
        results_a = []
        # 1) Varredura de configurações de sinal base
        for name, kw, fn_f, grp in configs_2a:
            key = tuple(sorted(kw.items()))
            if (asset, key) not in sig_cache:
                sig_cache[(asset, key)] = collect_avwap_signals(asset, prep[asset], **kw)
            df = sig_cache[(asset, key)]
            sub = df[fn_f(df)]
            st, _ = run_sim_df(sub, asset, **base_exit[asset])
            is_ops = int((sub.date <= bt.IS_END).sum())
            results_a.append((name, kw, fn_f, sub, st, is_ops))

        # 2) Varredura de filtros sobre HLC3 | T2_TOUCH_DIR | age6 imp1.5 & EXTREME | T4_REV_NEXT | age6 imp1.5
        for trig_lbl, trig_m, anch_m in (("T1_H", "T1_HOLD", "HLC3"), ("T2_D", "T2_TOUCH_DIR", "HLC3"),
                                         ("T3_R", "T3_RECLAIM", "HLC3"), ("T4_V", "T4_REV_NEXT", "HLC3"),
                                         ("E2_D", "T2_TOUCH_DIR", "EXTREME"), ("E3_R", "T3_RECLAIM", "EXTREME")):
            kw_b = dict(anchor_mode=anch_m, trig_mode=trig_m, min_age=6, min_imp_atr=1.5,
                        tol_atr=0.25, pierce_atr=0.60, dominant_only=False, max_pb_seq=2)
            key = tuple(sorted(kw_b.items()))
            if (asset, key) not in sig_cache:
                sig_cache[(asset, key)] = collect_avwap_signals(asset, prep[asset], **kw_b)
            dfb = sig_cache[(asset, key)]
            for flt_lbl, fn in ctx_filters:
                sub = dfb[fn(dfb)]
                st, _ = run_sim_df(sub, asset, **base_exit[asset])
                is_ops = int((sub.date <= bt.IS_END).sum())
                results_a.append((f"{trig_lbl}|a6|i1.5|pb2|{flt_lbl}", kw_b, fn, sub, st, is_ops))

        # Ordenar por R/DD IS (exigindo is_ops >= 35 para evitar ruído)
        valid_a = [r for r in results_a if r[5] >= 35]
        valid_a.sort(key=lambda r: (r[4]["rdd_is"], r[4]["is_"]), reverse=True)

        log(f"### 2A.{1 if asset=='WIN' else 2} — {asset}: Top 15 Regras AVWAP (ordenadas por Ret/DD IS, min 35 ops IS)")
        log("")
        log(*table_header())
        for name, _, _, _, st, _ in valid_a[:15]:
            log(fmt_row(name[:44], st))
        log("")
        # Mostrar também o resumo de sobrevivência no platô
        log(f"Total variantes testadas ({asset}, >=35 ops IS): **{len(valid_a)}** | Positivas no IS: **{sum(1 for r in valid_a if r[4]['is_'] > 0)}/{len(valid_a)}** | Positivas no OOS: **{sum(1 for r in valid_a if r[4]['oos'] > 0)}/{len(valid_a)}** | Positivas em ambos (IS e OOS): **{sum(1 for r in valid_a if r[4]['is_'] > 0 and r[4]['oos'] > 0)}/{len(valid_a)}**")
        log("")

        # Guardar os 4 candidatos mais distintos e sólidos no IS para fase 2B
        picked = []
        used_sigs = set()
        for name, kw, fn_f, sub_df, st, is_ops in valid_a:
            # Diversidade pelo prefixo trig+anch e filtro
            sig_tag = name.split("|")[0] + "|" + name.split("|")[1] + "|" + name.split("|")[-1]
            if len(picked) < 4 and sig_tag not in used_sigs:
                picked.append((name, kw, fn_f, sub_df))
                used_sigs.add(sig_tag)
        # Adicionar também sempre uma base pura (RAW) para comparação contra os filtros!
        kw_raw = dict(anchor_mode="HLC3", trig_mode="T2_TOUCH_DIR", min_age=6, min_imp_atr=1.5,
                      tol_atr=0.20, pierce_atr=0.60, dominant_only=False, max_pb_seq=2)
        df_raw = collect_avwap_signals(asset, prep[asset], **kw_raw)
        if not any(p[0] == "RAW_HLC3_T2_a6_i1.5_pb2" for p in picked):
            picked.append(("RAW_HLC3_T2_a6_i1.5_pb2", kw_raw, lambda d: np.ones(len(d), bool), df_raw))
        best_signals[asset] = picked

    # ── SEÇÃO 2B: EXPLORAÇÃO DE SAÍDAS E PLATÔ IS -> OOS ─────────────────────────
    log("## 2B. Geometria de Saídas e Teste de Platô (SL x TP, Estrutural, Máx/Mín Dia e ProxWall)")
    log("")

    exit_grids = {
        "WIN": {
            "sl": [160.0, 200.0, 240.0, 280.0, 320.0],
            "tp": [160.0, 200.0, 240.0, 280.0, 360.0, 440.0],
            "tmax": [12, 18, 24],
            "buf": 30.0,
        },
        "WDO": {
            "sl": [6.0, 8.0, 10.0, 12.0, 14.0],
            "tp": [6.0, 8.0, 10.0, 12.0, 14.0, 18.0],
            "tmax": [12, 18, 24],
            "buf": 1.0,
        },
    }

    finalists = {}
    for asset in ("WIN", "WDO"):
        g = exit_grids[asset]
        log(f"### 2B.{1 if asset=='WIN' else 2} — {asset}: Avaliação de Saídas nos Principais Sinais Selecionados no IS")
        log("")
        log(*table_header())

        cand_list = []
        for s_name, s_kw, s_fn, s_df in best_signals[asset]:
            is_cnt = int((s_df.date <= bt.IS_END).sum())
            if is_cnt < 25:
                continue

            grid_stats = []
            # 1) Platô fixo SL x TP (tmax=24 e 18)
            for tm_x in (18, 24):
                for sl_v in g["sl"]:
                    for tp_v in g["tp"]:
                        st, tf = run_sim_df(s_df, asset, "fix", sl_v, "fix", tp_v, 0.0, 0.0, tm_x)
                        grid_stats.append((f"SL{int(sl_v)}_TP{int(tp_v)}_t{tm_x}",
                                           dict(sl_mode="fix", sl_val=sl_v, tp_mode="fix", tp_val=tp_v, be_trig=0.0, be_lock=0.0, tmax=tm_x),
                                           st, tf))
            # 2) Saída Estrutural (piv_pb ± buf ou avwap ± buf) -> R multiples, day_ext, nw_all
            for sl_m in ("struct", "aw_buf"):
                for tp_m, tp_v, tag_tp in [
                    ("rr", 1.0, "1.0R"), ("rr", 1.5, "1.5R"), ("rr", 2.0, "2.0R"),
                    ("day_ext", 0.0, "DiaExt"), ("nw_all", 0.0, "ProxWall"),
                ]:
                    st, tf = run_sim_df(s_df, asset, sl_m, g["buf"], tp_m, tp_v, 0.0, 0.0, 24)
                    if st["ops"] >= 30:
                        grid_stats.append((f"{sl_m[:4]}_{tag_tp}_t24",
                                           dict(sl_mode=sl_m, sl_val=g["buf"], tp_mode=tp_m, tp_val=tp_v, be_trig=0.0, be_lock=0.0, tmax=24),
                                           st, tf))
            # 3) Saída para Máxima/Mínima do Dia e ProxWall com SL fixo central (+ Sniper comparativo)
            sl_c = g["sl"][2]
            for tp_m, tag_tp in [("day_ext", "DiaExt"), ("nw_all", "ProxWall"), ("sniper", "Sniper")]:
                st, tf = run_sim_df(s_df, asset, "fix", sl_c, tp_m, 0.0, 0.0, 0.0, 24)
                if st["ops"] >= 30:
                    grid_stats.append((f"SL{int(sl_c)}_{tag_tp}_t24",
                                       dict(sl_mode="fix", sl_val=sl_c, tp_mode=tp_m, tp_val=0.0, be_trig=0.0, be_lock=0.0, tmax=24),
                                       st, tf))

            fix_only = [x for x in grid_stats if x[0].startswith("SL") and "_TP" in x[0]]
            n_pos_is = sum(1 for x in fix_only if x[2]["is_"] > 0)
            n_pos_both = sum(1 for x in fix_only if x[2]["is_"] > 0 and x[2]["oos"] > 0)

            # Melhor pelo critério IS entre saídas auditáveis via _sim_exact_nb (excluindo sniper apenas da seleção automática)
            exact_only = [x for x in grid_stats if x[1]["tp_mode"] != "sniper"]
            exact_only.sort(key=lambda x: (x[2]["rdd_is"], x[2]["is_"]), reverse=True)
            best_ex_name, best_ex_kw, best_st, best_tf = exact_only[0]
            log(fmt_row(f"{s_name[:22]} | {best_ex_name}"[:44], best_st))

            # Também loga melhor DiaExt, ProxWall, struct_1.5R e Sniper para visibilidade
            for special in ("DiaExt", "ProxWall", "struct_1.5R", "Sniper"):
                sp = [x for x in grid_stats if special in x[0]]
                if sp:
                    sp.sort(key=lambda x: x[2]["rdd_is"], reverse=True)
                    log(fmt_row(f"{s_name[:22]} | {sp[0][0]}"[:44], sp[0][2]))

            log(f"|   -> Platô SLxTP ({s_name[:30]}): IS+>0 = {n_pos_is}/{len(fix_only)} ({100*n_pos_is/max(len(fix_only),1):.0f}%), IS&OOS>0 = {n_pos_both}/{len(fix_only)} ({100*n_pos_both/max(len(fix_only),1):.0f}%) | | | | | | | | | | |")

            cand_list.append((f"{s_name} | {best_ex_name}", s_df, best_ex_kw, best_st, best_tf, s_kw, s_fn))

        log("")
        cand_list.sort(key=lambda x: x[3]["rdd_is"], reverse=True)
        finalists[asset] = cand_list[0]

    # ── SEÇÃO 2C: AUDITORIA DE ROBUSTEZ, ESTABILIDADE E PLACEBOS ─────────────────────────
    log("## 2C. Auditoria de Robustez, Quebra Direcional e Placebos (Finalistas WIN e WDO)")
    log("")
    for asset in ("WIN", "WDO"):
        f_name, f_df, f_ex, _, f_tf, f_sig_kw, f_fn = finalists[asset]
        log(f"### 2C.{1 if asset=='WIN' else 2} — Finalista {asset}: `{f_name}`")
        log("")
        log(*table_header())

        for mode_lbl, m_key in [
            ("1. Padrão (bt.sim / slip 1t stop)",  "padrao"),
            ("2. Estresse Stop (+2 ticks SL)",     "stop2t"),
            ("3. Estresse Custo (2x B3)",          "custo2x"),
            ("4. Estresse Entrada (+1t open)",     "entry1t"),
            ("5. Estresse M1 Pior Caminho",        "adv_m1"),
            ("6. Estresse Pesado (SL+2t & C2x+1t)","pesado"),
            ("7. Invertida (entrar contra sinal)", "invertida"),
        ]:
            st_m, _ = run_sim_df(f_df, asset, **f_ex, mode=m_key)
            log(fmt_row(mode_lbl, st_m))

        # Quebra por direção: COMPRA (AVWAP_low) vs VENDA (AVWAP_high)
        st_c, _ = run_sim_df(f_df[f_df["dir"] == 1], asset, **f_ex)
        st_v, _ = run_sim_df(f_df[f_df["dir"] == -1], asset, **f_ex)
        log(fmt_row("Dir: APENAS COMPRA (AVWAP_low)", st_c))
        log(fmt_row("Dir: APENAS VENDA (AVWAP_high)", st_v))

        # Placebos causais com EXATAMENTE o mesmo gatilho e filtro de contexto
        kw_vwap_day = dict(f_sig_kw)
        kw_vwap_day["anchor_mode"] = "VWAP_DAY"
        kw_vwap_day["dominant_only"] = False
        df_vday_raw = collect_avwap_signals(asset, prep[asset], **kw_vwap_day)
        df_vday = df_vday_raw[f_fn(df_vday_raw)] if len(df_vday_raw) > 0 else df_vday_raw
        st_vday, _ = run_sim_df(df_vday, asset, **f_ex)
        log(fmt_row("Placebo: VWAP Normal Dia (mesmo filt.)", st_vday))
        if len(df_vday_raw) != len(df_vday):
            st_vday_r, _ = run_sim_df(df_vday_raw, asset, **f_ex)
            log(fmt_row("Placebo: VWAP Normal Dia (RAW)", st_vday_r))

        kw_anti = dict(f_sig_kw)
        kw_anti["anchor_mode"] = "ANTI_ANCHOR"
        kw_anti["dominant_only"] = False
        df_anti_raw = collect_avwap_signals(asset, prep[asset], **kw_anti)
        df_anti = df_anti_raw[f_fn(df_anti_raw)] if len(df_anti_raw) > 0 else df_anti_raw
        if len(df_anti) > 0:
            st_anti, _ = run_sim_df(df_anti, asset, **f_ex)
            log(fmt_row("Placebo: Anti-Âncora (Compra Hi/Venda Lo)", st_anti))
        if len(df_anti_raw) != len(df_anti):
            st_anti_r, _ = run_sim_df(df_anti_raw, asset, **f_ex)
            log(fmt_row("Placebo: Anti-Âncora (RAW)", st_anti_r))
        log("")

    # ── SEÇÃO 2D: IMPACTO NO PORTFÓLIO 5176 ─────────────────────────
    log("## 2D. Impacto no Portfólio 5176 (E22 2ct + C1a + SYM_WIN + V1a + SYM_WDO)")
    log("")
    strats = build_strategies()
    base_5176 = [
        ("E22_WIN", strats["E22_WIN"], 2.0),
        ("C1a_WIN", strats["C1a_WIN"], 1.0),
        ("SYM_WIN", strats["SYM_WIN"], 1.0),
        ("V1a_WDO", strats["V1a_WDO"], 1.0),
        ("SYM_WDO", strats["SYM_WDO"], 1.0),
    ]
    tf_av_w = finalists["WIN"][4][["date", "tm", "xt", "pnl", "asset"]].copy()
    tf_av_d = finalists["WDO"][4][["date", "tm", "xt", "pnl", "asset"]].copy()

    log("| Carteira / Combinação                                          |  Ops |    WR |   PF | Net (R$) |    DD |  R/DD | Meses | H1 / H2 / OOS       | PiorDia |")
    log("|----------------------------------------------------------------|------|-------|------|----------|-------|-------|-------|---------------------|---------|")
    for lbl, items, dedup in [
        ("BASE 5176 (5 robôs atuais)",                     base_5176, False),
        ("BASE 5176 + AVWAP_WIN (independente)",           base_5176 + [("AVWAP_W", tf_av_w, 1.0)], False),
        ("BASE 5176 + AVWAP_WDO (independente)",           base_5176 + [("AVWAP_D", tf_av_d, 1.0)], False),
        ("BASE 5176 + AVWAP_WIN + AVWAP_WDO (indep.)",     base_5176 + [("AVWAP_W", tf_av_w, 1.0), ("AVWAP_D", tf_av_d, 1.0)], False),
        ("BASE 5176 + AVWAP_WIN+WDO (trava UM ativo)",     base_5176 + [("AVWAP_W", tf_av_w, 1.0), ("AVWAP_D", tf_av_d, 1.0)], True),
    ]:
        st = eval_combo(items, dedup_asset=dedup)
        sub = f"{st['h1']:+6d}/{st['h2']:+6d}/{st['oos']:+6d}"
        log(f"| {lbl:<62} | {st['ops']:4d} | {st['wr']:4.1f}% | {st['pf']:4.2f} | "
            f"{st['net']:+8d} | {st['dd']:5d} | {st['rdd']:5.2f} | {st['meses']:>5} | {sub:<19} | {st['worst_day']:+7d} |")

    log("")
    log("### Correlação diária de PnL entre os Finalistas AVWAP e a Carteira 5176")
    log("")
    all_dates = sorted(win_cache.keys())
    daily_df = pd.DataFrame({
        "E22_2c": (strats["E22_WIN"].groupby("date")["pnl"].sum() * 2.0).reindex(all_dates, fill_value=0.0),
        "C1a_W":  strats["C1a_WIN"].groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0),
        "SYM_W":  strats["SYM_WIN"].groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0),
        "V1a_D":  strats["V1a_WDO"].groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0),
        "SYM_D":  strats["SYM_WDO"].groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0),
        "AVWAP_W": tf_av_w.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0),
        "AVWAP_D": tf_av_d.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0),
    })
    log("```")
    log(daily_df.corr().round(3).to_string())
    log("```")
    log("")
    log(f"*Gerado em {time.time() - t0:.1f}s.*")

    out_path = ROOT / "research" / "div_master" / "RESULTADOS_VWAP_ANCORADA.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRelatório salvo em: {out_path}")


if __name__ == "__main__":
    main()
