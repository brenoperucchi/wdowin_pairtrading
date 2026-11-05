"""
Port fiel (MQL -> Python) dos SmartGrids EST-13..16 de `mt5/Include/Jumba_GEX_NWE_Core.mqh`,
simulado tick a tick sobre barras M1 do próprio MT5 (como o Strategy Tester 'OHLC 1 minuto'),
em modo HEDGING (ordens nativas c/ SL/TP no servidor).
"""
import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.discover_gex_nwe_setups as disc
from research.mt5_loader import load_m5_m1_wdo_gex

SPREAD = 5.0


def r5(x):
    return float(np.round(x / 5.0) * 5.0)


def wdo_z_series(wdo):
    """ComputeWdoMetrics(): z do último retorno vs 20 retornos (M5)."""
    c = wdo["close"].values
    z = np.zeros(len(c))
    for i in range(21, len(c)):
        rets = c[i - 19:i + 1] / c[i - 20:i] - 1.0
        sd = rets.std()
        z[i] = (rets[-1] - rets.mean()) / sd if sd > 1e-9 else 0.0
    return pd.Series(z, index=wdo["t"])


def structural_mid(entry, d, lv_all):
    """FindStructuralTargets() -> tp_mid (front_run 20)."""
    if d == 1:
        c = lv_all[lv_all >= entry + 135.0]
        raw = c[0] if len(c) else entry + 460.0
        return r5(raw - 20.0), raw
    c = lv_all[lv_all <= entry - 135.0]
    raw = c[-1] if len(c) else entry - 460.0
    return r5(raw + 20.0), raw


def next_wall_behind(entry, d, lv_all, mn=140.0, mx=280.0, fb=190.0):
    if d == 1:
        for v in lv_all[::-1]:
            dd = entry - v
            if mn <= dd <= mx:
                return r5(dd)
    else:
        for v in lv_all:
            dd = v - entry
            if mn <= dd <= mx:
                return r5(dd)
    return r5(fb)


def nearest(lv, p):
    i = int(np.argmin(np.abs(lv - p)))
    return abs(lv[i] - p), lv[i]


def ticks(o, h, l, c):
    """Sequência de ticks gerada pelo tester a partir de uma barra M1 (OHLC)."""
    return (o, h, l, c) if abs(h - o) <= abs(o - l) else (o, l, h, c)


def open_pos(s, k, lv_all, t, fill):
    d = s["pend"]
    p5 = s["pend_px"]
    s2 = next_wall_behind(p5, d, lv_all)
    s.update(
        dir=d, p1=p5, avg=p5, lots=1, leg=1,
        sl=r5(p5 - d * (s2 + 175.0)), tp=r5(p5 + d * s["pend_tp"]),
        mfe=0.0, be_active=False, intrabar=True, bars=0,
        be_trig=130.0, be_lock=20.0, be_mode=1, buf=20.0,
        max_hold=18, step2=s2, pend=0,
        fills=[(fill, 1)], t_in=t, t_leg2=None,
    )


def close_pos(s, k, px, t, why, trades, cost_pts: float = 0.0):
    d = s["dir"]
    brl = sum(((px - f) * d - cost_pts) * q for f, q in s["fills"]) * 0.20
    trades.append(dict(
        k=k, side=d, t_in=s["t_in"], t_out=t,
        px_in=s["fills"][0][0], px_out=px,
        lots=s["lots"], why=why, brl=brl, leg2=s["t_leg2"],
    ))
    s["dir"] = 0
    s["trades_today"] += 1


def run(slots=(13, 14, 15, 16), start="2026-05-11", cost_pts: float = 0.0):
    m5, m1, wdo, gex = load_m5_m1_wdo_gex()
    C = m5["close"].values
    n50 = disc.compute_nwe_series(C, lookback=50, bw=5.0, mult=2.0)
    n30 = disc.compute_nwe_series(C, lookback=30, bw=3.0, mult=1.6)
    wz = wdo_z_series(wdo).reindex(m5["t"]).ffill().fillna(0.0).values
    m5["date"] = m5["t"].dt.strftime("%Y-%m-%d")
    m5["tmin"] = m5["t"].dt.hour * 60 + m5["t"].dt.minute
    m1["bar5"] = m1["t"].dt.floor("5min")
    m1g = {k: g[["open", "high", "low", "close"]].values for k, g in m1.groupby("bar5")}
    trades = []
    S = {k: dict(dir=0, pend=0, trades_today=0, day="") for k in slots}
    for i in range(1, len(m5)):
        t_new = m5["t"][i]
        day = m5["date"][i]
        b1 = i - 1
        if day < start or day not in gex:
            continue
        g = gex[day]
        lv_all = np.sort(np.r_[g["walls"], g["mid_walls"]])
        gf = g["gamma_flip"] or 0.0
        new_open = m5["open"][i]
        new_tmin = int(m5["tmin"][i])
        # ---------- OnNewM5Bar (no 1º tick da barra i) ----------
        for k in slots:
            s = S[k]
            if s["day"] != day:
                s.update(trades_today=0, day=day)
            if s["pend"] != 0:
                s["pend_left"] -= 1
                if s["pend_left"] <= 0 or m5["date"][b1] != day or new_tmin > 1000:
                    s["pend"] = 0
            if s["dir"] != 0:
                d = s["dir"]
                bh, bl, bc = m5["high"][b1], m5["low"][b1], m5["close"][b1]
                if s["intrabar"]:
                    fav = (bc - s["avg"]) * d
                    s["mfe"] = max(s["mfe"], fav)
                    s["intrabar"] = False
                else:
                    s["bars"] += 1
                    fav = (bh - s["avg"]) if d == 1 else (s["avg"] - bl)
                    s["mfe"] = max(s["mfe"], fav)
                if s["be_trig"] > 0 and not s["be_active"] and s["mfe"] >= s["be_trig"]:
                    if s["be_mode"] == 0 or s["def_wall"] <= 0:
                        cand = r5(s["avg"] + d * s["be_lock"])
                    elif d == 1:
                        cand = max(s["sl"], min(r5(s["def_wall"] - s["buf"]), s["avg"] + 10.0))
                        cand = max(cand, r5(s["avg"] - 90.0))
                    else:
                        cand = min(s["sl"], max(r5(s["def_wall"] + s["buf"]), s["avg"] - 10.0))
                        cand = min(cand, r5(s["avg"] + 90.0))
                    if (d == 1 and new_open > cand + 5.0) or (d == -1 and new_open < cand - 5.0):
                        s["sl"] = max(s["sl"], cand) if d == 1 else min(s["sl"], cand)
                        s["be_active"] = True
                if not s.get("_intrabar_bar") and s["bars"] >= s["max_hold"]:
                    close_pos(s, k, new_open, t_new, "TIME", trades, cost_pts=cost_pts)
                    continue
        b1_tmin = int(m5["tmin"][b1])
        if m5["date"][b1] == day and new_tmin < 1035:
            o1, h1, l1, c1 = m5["open"][b1], m5["high"][b1], m5["low"][b1], m5["close"][b1]
            bw50 = max(1.0, n50[1][b1] - n50[2][b1])
            bw30 = max(1.0, n30[1][b1] - n30[2][b1])
            pos50 = (c1 - n50[2][b1]) / bw50
            pos30 = (c1 - n30[2][b1]) / bw30
            rng1 = max(1.0, h1 - l1)
            mid_b1 = r5(0.5 * (h1 + l1))
            d_l, lvl_s = nearest(lv_all, l1)
            d_h, lvl_r = nearest(lv_all, h1)
            hb30 = max(10.0, 0.5 * bw30)
            z30c = (c1 - n30[0][b1]) / hb30
            z30l = (l1 - n30[0][b1]) / hb30
            z30h = (h1 - n30[0][b1]) / hb30
            lw = min(o1, c1) - l1
            uw = h1 - max(o1, c1)
            rev_b = (c1 >= l1 + 0.45 * rng1) and (lw >= 0.22 * rng1 or c1 > o1)
            rev_s = (c1 <= h1 - 0.45 * rng1) and (uw >= 0.22 * rng1 or c1 < o1)
            gf_b = gf <= 0 or c1 < gf + 400.0
            gf_s = gf <= 0 or c1 > gf - 400.0
            wz1 = wz[b1]
            for k in slots:
                s = S[k]
                if s["dir"] != 0 or s["pend"] != 0:
                    continue
                sig = 0
                wall = 0.0
                if k == 13 and s["trades_today"] < 5 and 545 <= b1_tmin <= 975:
                    if d_l <= 80 and pos50 <= 0.45 and wz1 <= 0.35 and c1 > lvl_s and c1 > o1:
                        sig, wall = 1, lvl_s
                    elif d_h <= 80 and pos50 >= 0.55 and wz1 >= -0.35 and c1 < lvl_r and c1 < o1:
                        sig, wall = -1, lvl_r
                elif k == 14 and s["trades_today"] < 3 and 545 <= b1_tmin <= 1005:
                    if d_l <= 75 and lw >= 25 and pos50 <= 0.48 and c1 >= o1 and c1 > lvl_s - 15:
                        sig, wall = 1, lvl_s
                    elif d_h <= 75 and uw >= 25 and pos50 >= 0.52 and c1 <= o1 and c1 < lvl_r + 15:
                        sig, wall = -1, lvl_r
                elif k == 15 and s["trades_today"] < 3 and 555 <= b1_tmin <= 975:
                    if d_l <= 110 and (z30c <= -0.60 or z30l <= -0.80) and rev_b and c1 > lvl_s - 20 and gf_b:
                        sig, wall = 1, lvl_s
                    elif d_h <= 110 and (z30c >= 0.60 or z30h >= 0.80) and rev_s and c1 < lvl_r + 20 and gf_s:
                        sig, wall = -1, lvl_r
                elif k == 16 and s["trades_today"] < 3 and 555 <= b1_tmin <= 975:
                    if l1 <= lvl_s + 20 and c1 >= lvl_s and d_l <= 105 and (z30l <= -0.45 or pos30 <= 0.30) and c1 > o1 and gf_b:
                        sig, wall = 1, lvl_s
                    elif h1 >= lvl_r - 20 and c1 <= lvl_r and d_h <= 105 and (z30h >= 0.45 or pos30 >= 0.70) and c1 < o1 and gf_s:
                        sig, wall = -1, lvl_r
                if sig == 0:
                    continue
                s2 = next_wall_behind(mid_b1, sig, lv_all)
                tp_mid, raw_mid = structural_mid(mid_b1, sig, lv_all)
                tp_pts = min(220.0, max(140.0, abs(tp_mid - mid_b1)))
                p5 = r5(mid_b1)
                if (sig == 1 and new_open < p5) or (sig == -1 and new_open > p5):
                    continue  # filtro de abertura
                s.update(
                    pend=sig, pend_px=p5, pend_ord=(p5 + 5.0 if sig == 1 else p5),
                    pend_left=2, pend_tp=tp_pts, pend_sl=s2 + 175.0,
                    def_wall=wall, raw_mid=raw_mid, pend_bar=t_new,
                )
                # executa já na abertura se o preço já está no nível (ask<=ord p/ compra, bid>=ord p/ venda)
                ask, bid = new_open + SPREAD, new_open
                if (sig == 1 and ask <= s["pend_ord"]) or (sig == -1 and bid >= s["pend_ord"]):
                    open_pos(s, k, lv_all, t_new, fill=(ask if sig == 1 else bid))
        # ---------- ticks M1 da barra i ----------
        for (o, h, l, c) in m1g.get(t_new, np.array([[new_open] * 4])):
            for px in ticks(o, h, l, c):
                for k in slots:
                    s = S[k]
                    if s["dir"] == 0 and s["pend"] != 0:
                        if (s["pend"] == 1 and px + SPREAD <= s["pend_ord"]) or (s["pend"] == -1 and px >= s["pend_ord"]):
                            open_pos(s, k, lv_all, t_new, fill=s["pend_ord"])
                    if s["dir"] != 0:
                        d = s["dir"]
                        # SL/TP no servidor (compra fecha no bid; venda fecha no ask)
                        cl = px if d == 1 else px + SPREAD
                        if (d == 1 and cl <= s["sl"]) or (d == -1 and cl >= s["sl"]):
                            close_pos(s, k, s["sl"], t_new, "SL", trades, cost_pts=cost_pts)
                            continue
                        if (d == 1 and cl >= s["tp"]) or (d == -1 and cl <= s["tp"]):
                            close_pos(s, k, s["tp"], t_new, "TP", trades, cost_pts=cost_pts)
                            continue
                        # perna 2 na NextWall (last_px ~ bid)
                        if s["leg"] == 1 and not s["be_active"]:
                            p2 = r5(s["p1"] - d * s["step2"])
                            if (d == 1 and px <= p2) or (d == -1 and px >= p2):
                                s["fills"].append((px + SPREAD if d == 1 else px, 2))
                                s["lots"] = 3
                                s["leg"] = 2
                                s["avg"] = r5((s["p1"] * 1 + p2 * 2) / 3.0)
                                s["be_active"] = False
                                s["mfe"] = 0.0
                                s["be_trig"], s["be_lock"], s["be_mode"] = 90.0, 15.0, 0
                                s["tp"] = r5(s["avg"] + d * 170.0)
                                s["sl"] = r5(p2 - d * 175.0)
                                s["t_leg2"] = t_new
                if t_new.hour * 60 + t_new.minute >= 1035:
                    for k in slots:
                        if S[k]["dir"] != 0:
                            close_pos(S[k], k, px, t_new, "EOD", trades, cost_pts=cost_pts)
                        S[k]["pend"] = 0
    return pd.DataFrame(trades)


if __name__ == "__main__":
    out_dir = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_reference")
    os.makedirs(out_dir, exist_ok=True)
    t = run()
    t.to_csv(os.path.join(out_dir, "sg_trades.csv"), index=False)
    for k, g in t.groupby("k"):
        p = g["brl"]
        print(f"EST-{k}", len(g), "PF", round(p[p > 0].sum() / -p[p < 0].sum(), 2), "R$", round(p.sum()), "perna2", g["leg2"].notna().sum())

