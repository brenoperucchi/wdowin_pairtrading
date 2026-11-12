"""
Sinais do detector v3 (`core.div_wall_signal.detect_divergences_v3`, definição aprovada pelo usuário em 11/11/2026)
no dataset congelado `div_wall_v1` (barras do Profit + Walls do dia), no mesmo formato de `research.div3m.investigar.load`
para reaproveitar o simulador M1 de `research.div3m.bt_div3m`.
Entrada base: abertura da barra MT5 seguinte à barra do sinal (barra em que a divergência passa a valer).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.div_wall_signal import DivParamsV2, compute_flow, detect_divergences_v3  # noqa: E402
from research.div3m.investigar import BUF, H1_END, IS_END, TICK  # noqa: E402,F401
from research.div_wall.data import load_asset  # noqa: E402
from research.sniper2 import bt_sniper2 as V2  # noqa: E402
from research.sniper_direct.bt_direct import WINDOW  # noqa: E402


# Modo do sinal: "div" (divergência v3) · "abs_div" (absorção rápida na Wall até ABS_N barras depois de uma
# divergência v3 no mesmo sentido) · "abs" (absorção rápida sozinha, controle). Raio da Wall da absorção: ABS_R.
MODE = "div"
ABS_N = 6
ABS_R = {"WIN": 100.0, "WDO": 4.0}


def _pseudo(i, d, ext, lvl, s=None):
    from types import SimpleNamespace
    return SimpleNamespace(idx=i, direction=d, pivot_px=ext, wall_type="perto", wall_px=lvl,
                           f1_idx=s.f1_idx if s else i, pivot_idx=s.pivot_idx if s else i,
                           wave_f1=s.wave_f1 if s else 0.0, wave_f2=s.wave_f2 if s else 0.0,
                           f1_px=s.f1_px if s else ext)


ROM_FLOW = "wave"      # rompimento: "wave" (onda no maior valor do dia no sentido) · "force" (força da barra) · "none"


def breakouts(fb, walls, flow="wave"):
    """Rompimento da Wall/MidWall: fechamento atravessa o nível (barra anterior fechou do outro lado) e o fluxo da barra,
    no sentido do rompimento, é o maior do dia até ali. Um sinal por nível e sentido no dia. Stop de referência:
    mínima (venda: máxima) da barra do rompimento."""
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in ("Wall", "MidWall"))
    out, used = [], set()
    best = {1: -1e18, -1: -1e18}
    for i in range(1, len(fb)):
        c0, c1 = float(fb[i - 1]["close"]), float(fb[i]["close"])
        val = float(fb[i]["wave" if flow != "force" else "force"])
        for d in (1, -1):
            v = d * val
            top = v > best[d]
            crossed = [lv for lv in levels if (c0 <= lv < c1 if d == 1 else c1 < lv <= c0)]
            if crossed and (flow == "none" or top):
                lv = crossed[-1] if d == 1 else crossed[0]
                if (lv, d) not in used:
                    used.add((lv, d))
                    ext = float(fb[i]["low"] if d == 1 else fb[i]["high"])
                    out.append(_pseudo(i, d, ext, lv))
            best[d] = max(best[d], v)
    out.sort(key=lambda s: s.idx)
    return out


def signals_day(asset, bars, walls, nwe):
    fb = compute_flow(bars, asset)
    divs = detect_divergences_v3(fb, walls, nwe, DivParamsV2.default(asset, nwe_filter="none"))
    if MODE == "div":
        return fb, divs
    if MODE == "rom":
        return fb, breakouts(fb, walls, ROM_FLOW)
    if MODE == "v4":
        from core.div_wall_signal import detect_divergences_v4
        zw = 1.0 if asset == "WIN" else 0.04
        return fb, detect_divergences_v4(fb, walls, nwe, DivParamsV2.default(asset, nwe_filter="none", pivot_left=1),
                                         rompimento=False, zone=200.0 * zw, furou=True)
    from research.div_entry.bt_entry import absorption
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in ("Wall", "MidWall"))
    ab = absorption(fb, levels, ABS_R[asset])
    if MODE == "abs":
        return fb, [_pseudo(i, d, ext, lvl) for (i, d, ext, lvl) in ab]
    out = []
    for (i, d, ext, lvl) in ab:
        src = [s for s in divs if s.direction == d and s.idx <= i <= s.idx + ABS_N]
        if src:
            out.append(_pseudo(i, d, ext, lvl, src[-1]))
    return fb, out


def load(asset, end=IS_END):
    from research.discover_gex_nwe_setups import compute_nwe_series
    from research.div_gate import bt_gate_grid as B
    from research.div_gate import select_oos as SO
    SO._init_full()
    df_win, _, _, n30w, _, df_wdo, _, _, n30d, _ = B._MK
    df, n30 = (df_win, n30w) if asset == "WIN" else (df_wdo, n30d)
    df = df.reset_index(drop=True)
    closes = df["close"].values.astype(float)
    nwe = {L: compute_nwe_series(closes, L, 8.0, 3.0)[:3] for L in (30, 50, 80, 100)}
    hi, lo, cl = df["high"].values, df["low"].values, closes
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.r_[cl[0], cl[:-1]]), np.abs(lo - np.r_[cl[0], cl[:-1]])))
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().values
    gidx = {(str(d), int(t)): i for i, (d, t) in enumerate(zip(df["session_date"], df["t_min"]))}
    mt5 = V2.day_bars(df, n30)
    p4 = json.load(open(os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json"), encoding="utf-8"))
    data = load_asset(asset, "M5")
    dates = sorted(d for d in set(x["date"] for x in p4["days"]) & set(mt5) & set(data) if d <= end)
    lo_w, hi_w = WINDOW[asset]
    rows = []
    for d in dates:
        bars, walls, dnwe = data[d]
        levels = sorted(float(w["price"]) for w in walls if w.get("type") in ("Wall", "MidWall"))
        fb, sigs = signals_day(asset, bars, walls, dnwe)
        b5 = mt5[d]
        pos = {int(t): j for j, t in enumerate(b5["tm"])}
        day_open = float(b5["o"][0])
        cnt = {1: 0, -1: 0}
        for s in sigs:
            i, dirn = s.idx, s.direction
            if i + 1 >= len(fb):
                continue
            tm = V2.hm(fb[i + 1]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in pos:
                continue
            e = pos[tm]
            gi = gidx.get((d, int(b5["tm"][e - 1]))) if e >= 1 else None
            if gi is None:
                continue
            b = fb[i]
            o_, h_, l_, c_ = (float(b[k]) for k in ("open", "high", "low", "close"))
            rng = max(h_ - l_, TICK[asset])
            ep = float(b5["o"][e])
            piv = float(s.pivot_px)
            a = float(atr[gi])
            r = dict(date=d, time=fb[i + 1]["time"], tm=tm, direction=dirn, e=e, ep=ep, piv=piv, atr=a, m3=True,
                     near_wall=s.wall_type == "perto", wall_kind=s.wall_type, seq=cnt[dirn], hora=f"{tm // 60:02d}h",
                     f1_time=fb[s.f1_idx]["time"], f2_time=fb[s.pivot_idx]["time"], wave_f1=s.wave_f1, wave_f2=s.wave_f2,
                     f1_px=s.f1_px, wall_px=s.wall_px)
            cnt[dirn] += 1
            for L, (c, u, l) in nwe.items():
                half = max(u[gi] - c[gi], TICK[asset])
                r[f"ext{L}"] = -dirn * (cl[gi] - c[gi]) / half
                r[f"extp{L}"] = -dirn * (piv - c[gi]) / half
                r[f"slope{L}"] = dirn * (c[gi] - c[max(0, gi - 6)]) / max(a, TICK[asset])
                r[f"c{L}"], r[f"opp{L}"] = float(c[gi]), float(u[gi] if dirn == 1 else l[gi])
            r["wall_dist"] = min((abs(piv - v) for v in levels), default=np.nan)
            nxt = [v for v in levels if (v - ep) * dirn >= TICK[asset] * 4]
            r["wall_next"] = (min(nxt) if dirn == 1 else max(nxt)) if nxt else np.nan
            r["clv"] = ((c_ - l_) if dirn == 1 else (h_ - c_)) / rng
            r["wick"] = ((min(o_, c_) - l_) if dirn == 1 else (h_ - max(o_, c_))) / rng
            r["body_fav"] = float(dirn * (c_ - o_) > 0)
            r["range_atr"] = rng / max(a, TICK[asset])
            r["dia_mov"] = dirn * (c_ - day_open) / max(a, TICK[asset])
            r["dist_piv"] = dirn * (ep - piv) / max(a, TICK[asset])
            r["inst"] = dirn * float(b.get("inst_aggr_delta", 0.0))
            r["ipas"] = dirn * float(b.get("inst_pass_delta", 0.0))
            r["ret"] = dirn * float(b.get("ret_delta_bar", 0.0))
            r["wave"] = dirn * float(b.get("wave", 0.0))
            r["wyk"] = dirn * float(b.get("wyckoff_abs", 0.0))
            r["eff"] = dirn * float(b.get("force", 0.0))
            r["sig_hi"], r["sig_lo"], r["sig_c"] = h_, l_, c_
            n = len(b5["o"])
            for k in (3, 6, 12, 24):
                j = min(e + k - 1, n - 1)
                r[f"r{k}"] = dirn * (float(b5["c"][j]) - ep)
            j = min(e + 12, n)
            r["mfe12"] = max(0.0, max(dirn * (float(x) - ep) for x in (b5["h"][e:j] if dirn == 1 else b5["lo"][e:j])))
            r["mae12"] = max(0.0, max(-dirn * (float(x) - ep) for x in (b5["lo"][e:j] if dirn == 1 else b5["h"][e:j])))
            rows.append(r)
    P = pd.DataFrame(rows).sort_values(["date", "tm"]).reset_index(drop=True)
    P["half"] = np.where(P["date"] <= H1_END, "H1", "H2")
    return P, mt5, df, nwe, gidx
