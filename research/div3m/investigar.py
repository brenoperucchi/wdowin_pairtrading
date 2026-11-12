"""
Investigação (só jan–jul) do setup "divergência 3 motores": o que acontece depois de cada divergência do Sniper e
quais condições, entradas e saídas separam as boas das ruins. Divide jan–jul em H1 (jan–abr) e H2 (mai–jul);
os cortes dos buckets são tirados do H1 e aplicados no H2. Ago–nov NÃO é lido aqui.
Uso: python -m research.div3m.investigar
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.sniper2 import bt_sniper2 as V2  # noqa: E402
from research.sniper_direct.bt_direct import WINDOW, three_motor  # noqa: E402

OUT = os.path.join(ROOT, "research", "div3m", "results")
IS_END, H1_END = "2026-07-31", "2026-04-30"
COST = {"WIN": 10.0, "WDO": 0.5}
BUF = {"WIN": 30.0, "WDO": 1.0}
TICK = {"WIN": 5.0, "WDO": 0.5}


def load(asset, end=IS_END):
    import research.flow_window_asg.inject_unified_div_opt2 as S
    from research.discover_gex_nwe_setups import compute_nwe_series
    from research.div_gate import bt_gate_grid as B
    from research.div_gate import select_oos as SO
    SO._init_full()
    df_win, gex_win, _, n30w, _, df_wdo, gex_wdo, _, n30d, _ = B._MK
    df, gex, n30 = (df_win, gex_win, n30w) if asset == "WIN" else (df_wdo, gex_wdo, n30d)
    df = df.reset_index(drop=True)
    closes = df["close"].values.astype(float)
    nwe = {L: compute_nwe_series(closes, L, 8.0, 3.0)[:3] for L in (30, 50, 80, 100)}
    hi, lo, cl = df["high"].values, df["low"].values, closes
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.r_[cl[0], cl[:-1]]), np.abs(lo - np.r_[cl[0], cl[:-1]])))
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().values
    gidx = {(str(d), int(t)): i for i, (d, t) in enumerate(zip(df["session_date"], df["t_min"]))}
    mt5 = V2.day_bars(df, n30)
    p4 = json.load(open(os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json"), encoding="utf-8"))
    dates = sorted(d for d in set(x["date"] for x in p4["days"]) & set(mt5) if d <= end)
    lo_w, hi_w = WINDOW[asset]
    rows = []
    for d, bars, walls in S.load_cached_or_build_session_bars(dates, asset == "WIN"):
        if d not in dates:
            continue
        g = gex.get(d, {})
        levels = sorted(list(np.asarray(g.get("walls", []), float)) + list(np.asarray(g.get("mid_walls", []), float)))
        b5 = mt5[d]
        pos = {int(t): j for j, t in enumerate(b5["tm"])}
        day_open = float(b5["o"][0])
        cnt = {1: 0, -1: 0}
        for s in S.detect_visual_swing_divergences(bars, walls, asset == "WIN"):
            i, dirn = s["sig_idx"], s["dir"]
            if i + 1 >= len(bars):
                continue
            tm = V2.hm(bars[i + 1]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in pos:
                continue
            e = pos[tm]
            gi = gidx.get((d, int(b5["tm"][e - 1]))) if e >= 1 else None
            if gi is None:
                continue
            b = bars[i]
            o_, h_, l_, c_ = (float(b[k]) for k in ("open", "high", "low", "close"))
            rng = max(h_ - l_, TICK[asset])
            ep = float(b5["o"][e])
            piv = float(s["pivot_px"])
            a = float(atr[gi])
            r = dict(date=d, time=bars[i + 1]["time"], tm=tm, direction=dirn, e=e, ep=ep, piv=piv, atr=a,
                     m3=three_motor(bars, i, dirn, asset), near_wall=bool(s["near_wall"]), seq=cnt[dirn],
                     hora=f"{tm // 60:02d}h")
            cnt[dirn] += 1
            for L, (c, u, l) in nwe.items():
                half = max(u[gi] - c[gi], TICK[asset])
                r[f"ext{L}"] = -dirn * (cl[gi] - c[gi]) / half          # >1: além da banda contra o trade
                r[f"extp{L}"] = -dirn * (piv - c[gi]) / half            # idem com o pivô F2
                r[f"slope{L}"] = dirn * (c[gi] - c[max(0, gi - 6)]) / max(a, TICK[asset])
                r[f"c{L}"], r[f"opp{L}"] = float(c[gi]), float(u[gi] if dirn == 1 else l[gi])
            r["wall_dist"] = min((abs(piv - v) for v in levels), default=np.nan)
            nxt = [v for v in levels if (v - ep) * dirn >= TICK[asset] * 4]
            r["wall_next"] = (min(nxt) if dirn == 1 else max(nxt)) if nxt else np.nan
            r["clv"] = ((c_ - l_) if dirn == 1 else (h_ - c_)) / rng
            r["wick"] = ((min(o_, c_) - l_) if dirn == 1 else (h_ - max(o_, c_))) / rng
            r["body_fav"] = float(dirn * (c_ - o_) > 0)
            r["range_atr"] = rng / max(a, TICK[asset])
            r["dia_mov"] = dirn * (c_ - day_open) / max(a, TICK[asset])   # <0: trade contra o movimento do dia
            r["dist_piv"] = dirn * (ep - piv) / max(a, TICK[asset])        # quanto já andou desde o pivô
            r["inst"] = dirn * float(b.get("inst_aggr_delta", 0.0))
            r["ipas"] = dirn * float(b.get("inst_pass_delta", 0.0))
            r["ret"] = dirn * float(b.get("ret_delta_bar", 0.0))
            r["wave"] = dirn * float(b.get("smart_swing_wave", 0.0))
            r["wyk"] = dirn * float(b.get("wyckoff_abs_bar", 0.0))
            r["eff"] = dirn * float(b.get("effective_force_bar", 0.0))
            r["sig_hi"], r["sig_lo"], r["sig_c"] = h_, l_, c_
            # resultado bruto (pts, sem custo) a partir da abertura de e
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


def bucket_table(P, col, q=4, cats=None):
    H1 = P[P.half == "H1"]
    if cats is None:
        edges = np.unique(np.nanquantile(H1[col].dropna(), np.linspace(0, 1, q + 1)))
        if len(edges) < 3:
            return None
        edges[0], edges[-1] = -np.inf, np.inf
        lab = pd.cut(P[col], edges, duplicates="drop").astype(str)
    else:
        lab = P[col].astype(str)
    T = P.assign(b=lab).groupby(["b", "half"]).agg(n=("r12", "size"), r12=("r12", "mean"), hit=("r12", lambda x: 100 * (x > 0).mean()),
                                                     mfe=("mfe12", "mean"), mae=("mae12", "mean")).unstack("half")
    T.columns = [f"{a}_{b}" for a, b in T.columns]
    return T.round(2)


def sim_trades(P, mt5, asset, stop_kind, tp_kind, be):
    """Saída com regras MT5 (V2.sim_lot). stop: ('fixo', pts) | ('piv', buffer) ; alvo: ('fixo', pts) | ('R', mult) |
    ('nwe_c', L) | ('nwe_opp', L) | ('wall', None). Retorna pnl R$ líquido por trade (1 contrato)."""
    sp = V2.SPEC[asset]
    out = np.zeros(len(P))
    for r in P.itertuples():
        d = r.direction
        sl = stop_kind[1] if stop_kind[0] == "fixo" else max(d * (r.ep - r.piv) + stop_kind[1], TICK[asset] * 2)
        k, v = tp_kind
        if k == "fixo":
            tp = r.ep + d * v
        elif k == "R":
            tp = r.ep + d * v * sl
        elif k == "nwe_c":
            tp = getattr(r, f"c{v}")
        elif k == "nwe_opp":
            tp = getattr(r, f"opp{v}")
        else:
            tp = r.wall_next if not np.isnan(r.wall_next) else r.ep + d * sp["fixed"][1]
        if (tp - r.ep) * d < TICK[asset] * 2:  # alvo já passou: usa 1R
            tp = r.ep + d * sl
        pts, _ = V2.sim_lot(mt5[r.date], r.e, r.ep, d, sl, "fixed", tp, be, sp, [])
        out[r.Index] = (pts - sp["cost"]) * sp["brl"]
    return out


def summ(p, mask=None):
    p = p if mask is None else p[mask]
    if len(p) == 0:
        return dict(n=0)
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    return dict(n=len(p), pf=round(g / l, 2) if l else 99, net=round(float(p.sum())), dd=round(dd),
                rdd=round(float(p.sum()) / dd, 2) if dd else 99, wr=round(100 * (p > 0).mean(), 1))


def main():
    os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    for asset in ("WIN", "WDO"):
        P, mt5, _, _, _ = load(asset)
        P.to_csv(os.path.join(OUT, f"sinais_is_{asset}.csv"), index=False)
        c = COST[asset]
        print(f"\n================ {asset}: {len(P)} divergências em jan–jul (H1 {int((P.half == 'H1').sum())} · H2 {int((P.half == 'H2').sum())}) · custo {c} pts")
        print("Retorno bruto médio depois da entrada (pts):",
              {k: round(P[k].mean(), 1) for k in ("r3", "r6", "r12", "r24", "mfe12", "mae12")})
        print("  por metade:", P.groupby("half")[["r6", "r12", "r24", "mfe12", "mae12"]].mean().round(1).to_dict("index"))
        feats = ["ext30", "ext50", "ext80", "ext100", "extp50", "slope50", "slope100", "wall_dist", "clv", "wick", "range_atr",
                 "dia_mov", "dist_piv", "inst", "ipas", "ret", "wave", "wyk", "eff"]
        for col in feats:
            T = bucket_table(P, col)
            if T is not None:
                print(f"\n-- {col}\n{T.to_string()}")
        for col in ("near_wall", "body_fav", "hora", "seq", "m3"):
            P2 = P.assign(seq=P.seq.clip(upper=3))
            print(f"\n-- {col}\n{bucket_table(P2, col, cats=True).to_string()}")
        # saídas alternativas sobre TODAS as divergências (entrada na abertura seguinte)
        sp = V2.SPEC[asset]
        print(f"\n-- Saídas (todas as divergências, 1 contrato, líquido) H1 | H2")
        stops = [("fixo", sp["sl"][0]), ("fixo", sp["sl"][1]), ("piv", BUF[asset]), ("piv", 2 * BUF[asset])]
        tps = [("fixo", sp["fixed"][0]), ("fixo", sp["fixed"][1]), ("R", 1.5), ("R", 2.0), ("nwe_c", 50), ("nwe_c", 100),
               ("nwe_opp", 50), ("wall", None)]
        res = []
        for st in stops:
            for tp in tps:
                for be in (False, True):
                    p = sim_trades(P, mt5, asset, st, tp, be)
                    h1, h2 = summ(p, (P.half == "H1").values), summ(p, (P.half == "H2").values)
                    res.append(dict(stop=f"{st[0]}{st[1]:g}", alvo=f"{tp[0]}{'' if tp[1] is None else f'{tp[1]:g}'}", be=be,
                                    h1_pf=h1["pf"], h1_net=h1["net"], h2_pf=h2["pf"], h2_net=h2["net"]))
        R = pd.DataFrame(res).sort_values("h1_pf", ascending=False)
        R.to_csv(os.path.join(OUT, f"saidas_is_{asset}.csv"), index=False)
        print(R.head(12).to_string(index=False))
        print("stop pelo pivô (distância média em pts):", round(float((P.direction * (P.ep - P.piv)).mean() + BUF[asset]), 1))


if __name__ == "__main__":
    main()
