# -*- coding: utf-8 -*-
"""
Exploração de Stops e Alvos mais curtos no WDO para a SYM_TOP1:
  1. Stop Estrutural atrás do pivô px2: SL = clamp(dist_piv + buf, sl_min, sl_max)
  2. Filtro de distância máxima da entrada ao pivô (dist_piv <= max_d) permitindo SL 6..10 pts e TP 5..10 pts
  3. Alvo proporcional ao Stop ou à distância do pivô / ProxWall com teto menor.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.wdo_especialista.robustez_final import days_cache as wdo_cache, DS as DS_WDO, X as X_WDO
from research.div_master.win_especialista.audit_e22_win import win_cache, DS_WIN, XW, get_e22_signals, eval_e22
from research.div_master.test_sym_top1 import OPT_OPEN


def collect_sym_top1_rich(asset: str) -> pd.DataFrame:
    cache = win_cache if asset == "WIN" else wdo_cache
    X = XW if asset == "WIN" else X_WDO
    P = dict(M.PARAMS[asset])
    lo_w, hi_w = bt.WINDOW[asset]
    min_nw = 50.0 if asset == "WIN" else 2.0

    recs = []
    for d in sorted(cache):
        fb, w_all, w_wall, D = cache[d]
        atr = M.atr_series(fb, P["tick"])
        cands = M.engine_v32(fb, w_wall, P, "common", atr=atr, opt=OPT_OPEN)

        seq = {1: 0, -1: 0}
        for c in cands:
            conf = c["conf"]
            if conf + 1 >= len(fb):
                continue
            s = seq[c["dir"]]
            seq[c["dir"]] += 1
            if s > 1:
                continue
            idx_in = conf + 1
            tm = bt.hm(fb[idx_in]["time"])
            if not (lo_w <= tm <= hi_w) or (tm // 60) == 11 or tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            ep = float(D["o5"][e])
            dr = int(c["dir"])
            half50 = max(float(D["u50"][e] - D["c50"][e]), X["tick"])
            ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half50
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
            if not (ext50 > -0.5 and slope50 > -0.5):
                continue

            px2 = float(c["px2"])
            dist_piv = max(X["tick"], dr * (ep - px2))
            d_wall_piv = min((abs(px2 - w) for w in w_wall), default=99999.0)
            d_wall_ep = min((abs(ep - w) for w in w_wall), default=99999.0)
            nw_all = bt.next_level(w_all, ep, dr, min_nw + X["front"])
            nw_d = dr * (nw_all - ep) - X["front"] if nw_all is not None else np.nan

            recs.append(dict(
                date=d, e=e, ep=ep, dir=dr, j=c["j"], tm=tm, hh=tm // 60,
                px2=px2, dist_piv=dist_piv, atr_conf=float(atr[conf]),
                d_wall_piv=d_wall_piv, d_wall_ep=d_wall_ep,
                ext50=ext50, slope50=slope50, nw_d=nw_d,
            ))
    return pd.DataFrame(recs).sort_values(["date", "tm", "j"]).reset_index(drop=True)


def sim_custom_wdo(df: pd.DataFrame, sl_fn, tp_fn, be_trig=0.0, be_lock=0.0, tmax=24, mode="padrao"):
    X = dict(X_WDO)
    tick = X["tick"]
    cost = X["cost"]
    if mode == "custo2x":
        cost *= 2.0
    elif mode == "pesado":
        cost = cost * 2.0 + tick

    n = len(df)
    pnl = np.full(n, np.nan)
    xt = np.zeros(n, dtype=np.int64)
    sl_list = []
    tp_list = []

    for i, r in enumerate(df.itertuples()):
        D = DS_WDO[r.date]
        dr = -int(r.dir) if mode == "invertida" else int(r.dir)
        sl_val = sl_fn(r)
        tp_val = tp_fn(r, sl_val)
        if sl_val is None or tp_val is None or np.isnan(tp_val):
            continue
        sl_eff = sl_val + (2.0 * tick if mode in ("stop2t", "pesado") else 0.0)
        tp_px = r.ep + dr * tp_val
        p, x = bt.sim(*bt._args(D), D["u30"], r.e, r.ep, dr, sl_eff, tp_px, False,
                      0.0, 0.0, 0.0, be_trig, be_lock, int(tmax), tick)
        pnl[i] = (p - cost) * X["brl"]
        xt[i] = x
        sl_list.append(sl_val)
        tp_list.append(tp_val)

    out = df[["date", "tm"]].copy()
    out["pnl"] = pnl
    out["xt"] = xt
    out = out.dropna(subset=["pnl"]).reset_index(drop=True)
    if len(out) < 50:
        return None, out, 0.0, 0.0
    tf = bt.mgmt(out, "pnl", "xt", "UM")
    return bt.stats(tf, "pnl", "xt"), tf, float(np.mean(sl_list)), float(np.mean(tp_list))


def main():
    df_d = collect_sym_top1_rich("WDO")
    print(f"Total sinais SYM_TOP1 WDO: {len(df_d)}")

    # A. STOP ESTRUTURAL ATRÁS DO PIVÔ px2 (SL = clamp(dist_piv + buf, sl_min, sl_max))
    print("\n" + "=" * 115)
    print("A. STOP ESTRUTURAL NO WDO (SL = dist_piv + buf, limitado a [sl_min, sl_max]) SEM CORTAR TRADES")
    print("=" * 115)
    hits_a = []
    for buf in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
        for sl_min, sl_max in ((5.0, 10.0), (6.0, 10.0), (6.0, 11.0), (6.0, 12.0), (7.0, 11.0), (7.0, 12.0)):
            sl_fn = lambda r, b=buf, mn=sl_min, mx=sl_max: min(max(round((r.dist_piv + b) * 2) / 2, mn), mx)
            for tp_label, tp_fn in [
                ("TP=7.0",      lambda r, s: 7.0),
                ("TP=8.0",      lambda r, s: 8.0),
                ("TP=9.0",      lambda r, s: 9.0),
                ("TP=10.0",     lambda r, s: 10.0),
                ("TP=1.0*SL",   lambda r, s: s),
                ("TP=1.1*SL",   lambda r, s: round(s * 1.1 * 2) / 2),
                ("TP=ProxW<=10",lambda r, s: None if (np.isnan(r.nw_d) or r.nw_d < 2.0) else min(max(r.nw_d, 3.5), 10.0)),
                ("TP=ProxW<=12",lambda r, s: None if (np.isnan(r.nw_d) or r.nw_d < 2.0) else min(max(r.nw_d, 3.5), 12.0)),
            ]:
                for tmax in (12, 18, 24):
                    st, _, m_sl, m_tp = sim_custom_wdo(df_d, sl_fn, tp_fn, 0.0, 0.0, tmax)
                    if st and st["ops"] >= 100:
                        st_c2, _, _, _ = sim_custom_wdo(df_d, sl_fn, tp_fn, 0.0, 0.0, tmax, "custo2x")
                        hits_a.append((st["rdd"], f"SL=piv+{buf:.1f}[{sl_min:.0f}..{sl_max:.0f}] (méd {m_sl:.1f}) | {tp_label:<12} (méd {m_tp:.1f}) | t={tmax:2d}", st, st_c2))

    hits_a.sort(key=lambda x: x[0], reverse=True)
    for rdd, lbl, st, st_c2 in hits_a[:15]:
        print(f"  {lbl:<68} | {st['ops']:3d}op WR {st['wr']:4.1f}% PF {st['pf']:4.2f} Net {st['net']:+6.0f} DD {st['dd']:4.0f} "
              f"R/DD {st['rdd']:5.2f} ({st['meses']}) [H1 {st['h1']:+5.0f} H2 {st['h2']:+5.0f} OOS {st['oos']:+5.0f}] | C2x {st_c2['rdd']:4.2f}")

    # B. FILTRANDO SINAIS ONDE O PIVÔ NÃO ESTÁ ESTICADO (dist_piv <= max_d) COM SL E TP CURTOS FIXOS (6 a 10 pts)
    print("\n" + "=" * 115)
    print("B. FILTRO DE PROXIMIDADE DO PIVÔ (dist_piv <= max_d) + SL CURTO (6..10 pts) E TP CURTO (5..10 pts)")
    print("=" * 115)
    hits_b = []
    for max_d in (4.0, 5.0, 6.0, 7.0, 8.0):
        sub = df_d[df_d["dist_piv"] <= max_d].copy()
        for sl in (6.0, 7.0, 8.0, 9.0, 10.0, 12.0):
            sl_fn = lambda r, s=sl: s
            for tp_label, tp_fn in [
                ("TP=5.0",      lambda r, s: 5.0),
                ("TP=6.0",      lambda r, s: 6.0),
                ("TP=7.0",      lambda r, s: 7.0),
                ("TP=8.0",      lambda r, s: 8.0),
                ("TP=9.0",      lambda r, s: 9.0),
                ("TP=10.0",     lambda r, s: 10.0),
                ("TP=ProxW<=10",lambda r, s: None if (np.isnan(r.nw_d) or r.nw_d < 2.0) else min(max(r.nw_d, 3.5), 10.0)),
                ("TP=ProxW<=12",lambda r, s: None if (np.isnan(r.nw_d) or r.nw_d < 2.0) else min(max(r.nw_d, 3.5), 12.0)),
            ]:
                for tmax in (12, 18, 24):
                    st, _, m_sl, m_tp = sim_custom_wdo(sub, sl_fn, tp_fn, 0.0, 0.0, tmax)
                    if st and st["ops"] >= 100:
                        st_c2, _, _, _ = sim_custom_wdo(sub, sl_fn, tp_fn, 0.0, 0.0, tmax, "custo2x")
                        hits_b.append((st["rdd"], f"dist_piv<={max_d:3.1f} | SL={sl:4.1f} | {tp_label:<12} (méd {m_tp:.1f}) | t={tmax:2d}", st, st_c2))

    hits_b.sort(key=lambda x: x[0], reverse=True)
    for rdd, lbl, st, st_c2 in hits_b[:15]:
        print(f"  {lbl:<68} | {st['ops']:3d}op WR {st['wr']:4.1f}% PF {st['pf']:4.2f} Net {st['net']:+6.0f} DD {st['dd']:4.0f} "
              f"R/DD {st['rdd']:5.2f} ({st['meses']}) [H1 {st['h1']:+5.0f} H2 {st['h2']:+5.0f} OOS {st['oos']:+5.0f}] | C2x {st_c2['rdd']:4.2f}")


if __name__ == "__main__":
    main()
