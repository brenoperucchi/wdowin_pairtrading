"""
Entrada direta na divergência do Sniper 5176. Protocolo: research/sniper_direct/PLANO.md.
Uso: python -m research.sniper_direct.bt_direct
"""
from __future__ import annotations

import itertools
import json
import multiprocessing as mp
import os
import random
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.sniper2 import bt_sniper2 as V2  # noqa: E402

OUT = os.path.join(ROOT, "research", "sniper_direct", "results")
IS_END = "2026-07-31"
MIN_TRADES, N_PLACEBO, P_MAX = 150, 200, 0.10
WINDOW = {"WIN": (545, 1005), "WDO": (540, 1020)}  # 09:05–16:45 / 09:00–17:00


def three_motor(bars, i, d, asset):
    """bull_3motor / bear_3motor do Sniper (inject_unified_div_opt2), WDO com limiares na escala do detector."""
    ps, ws = (1.0, 1.0) if asset == "WIN" else (0.03, 0.12)
    b = bars[i]
    o_i, h_i, l_i, c_i = (float(b[k]) for k in ("open", "high", "low", "close"))
    w_i, wyk_i, urg_i = float(b["smart_swing_wave"]), float(b["wyckoff_abs_bar"]), float(b["lot_urgency_bar"])
    eff_i, imp3_i = float(b["effective_force_bar"]), float(b["swing_impulse_3b"])
    swing = False
    if i >= 3:
        l2, h2 = min(l_i, float(bars[i - 1]["low"])), max(h_i, float(bars[i - 1]["high"]))
        wl2, wh2 = min(w_i, float(bars[i - 1]["smart_swing_wave"])), max(w_i, float(bars[i - 1]["smart_swing_wave"]))
        for k in range(i - 2, max(0, i - 16), -1):
            kb = bars[k]
            l_k, h_k, w_k = float(kb["low"]), float(kb["high"]), float(kb["smart_swing_wave"])
            if d == 1:
                sv_i = float(b["sell_vol"]) + float(bars[i - 1]["sell_vol"])
                sv_k = float(kb["sell_vol"]) + float(bars[max(0, k - 1)]["sell_vol"])
                if (-380 * ps <= (l2 - l_k) <= 50 * ps) and (max(w_i, wl2) > w_k + 1200 * ws or sv_i < 0.85 * sv_k or wyk_i > 0):
                    swing = True
                    break
            else:
                bv_i = float(b["buy_vol"]) + float(bars[i - 1]["buy_vol"])
                bv_k = float(kb["buy_vol"]) + float(bars[max(0, k - 1)]["buy_vol"])
                if (-50 * ps <= (h2 - h_k) <= 380 * ps) and (min(w_i, wh2) < w_k - 1200 * ws or bv_i < 0.85 * bv_k or wyk_i < 0):
                    swing = True
                    break
    dp3 = c_i - float(bars[max(0, i - 3)]["close"])
    if d == 1:
        return bool((swing and (eff_i > 0 or wyk_i > 0 or imp3_i > 0 or urg_i > 0))
                    or ((dp3 <= 30 * ps or c_i <= o_i) and (wyk_i > 0 or eff_i > 0 or imp3_i > 0))
                    or (eff_i > 0 and imp3_i > 0 and wyk_i >= -800 * ws))
    return bool((swing and (eff_i < 0 or wyk_i < 0 or imp3_i < 0 or urg_i < 0))
                or ((dp3 >= -30 * ps or c_i >= o_i) and (wyk_i < 0 or eff_i < 0 or imp3_i < 0))
                or (eff_i < 0 and imp3_i < 0 and wyk_i <= 800 * ws))


def prepare(asset):
    import research.flow_window_asg.inject_unified_div_opt2 as S
    from research.div_gate import bt_gate_grid as B
    from research.div_gate import select_oos as SO
    SO._init_full()
    df_win, gex_win, _, n30w, _, df_wdo, gex_wdo, _, n30d, _ = B._MK
    df, gex, n30 = (df_win, gex_win, n30w) if asset == "WIN" else (df_wdo, gex_wdo, n30d)
    mt5 = V2.day_bars(df, n30)
    p4 = json.load(open(os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json"), encoding="utf-8"))
    dates = set(d["date"] for d in p4["days"]) & set(mt5)
    lo, hi = WINDOW[asset]
    sig_rows, bar_rows = [], []
    for d, bars, walls in S.load_cached_or_build_session_bars(sorted(dates), asset == "WIN"):
        if d not in dates:
            continue
        b5 = mt5[d]
        pos = {int(t): j for j, t in enumerate(b5["tm"])}
        sigs = {(s["sig_idx"], s["dir"]): s for s in S.detect_visual_swing_divergences(bars, walls, asset == "WIN")}
        for i in range(len(bars) - 1):
            tm = V2.hm(bars[i + 1]["time"])
            if not (lo <= tm <= hi) or tm not in pos:
                continue
            for dirn in (1, -1):
                row = dict(date=d, time=bars[i + 1]["time"], tm=tm, direction=dirn, e=pos[tm],
                           entry_price=float(b5["o"][pos[tm]]), m3=three_motor(bars, i, dirn, asset))
                s = sigs.get((i, dirn))
                if s is not None:
                    sig_rows.append(dict(row, near_wall=bool(s["near_wall"]), sig_time=bars[i]["time"]))
                if d <= IS_END:
                    bar_rows.append(row)
    P = pd.DataFrame(sig_rows).sort_values(["date", "tm"]).reset_index(drop=True)
    Q = pd.DataFrame(bar_rows).sort_values(["date", "tm"]).reset_index(drop=True)
    for T in (P, Q):
        T["month"] = T["date"].str[:7]
        T["di"] = pd.factorize(T["date"], sort=True)[0]
    X = V2.exits(asset)[1:]  # sem NATIVA

    def levels(d):
        g = gex.get(d, {})
        return sorted(list(np.asarray(g.get("walls", []), float)) + list(np.asarray(g.get("mid_walls", []), float)))

    pnl = np.zeros((len(P), len(X)))
    xt = np.zeros((len(P), len(X)), dtype=int)
    for r in P.itertuples():
        lv = levels(r.date)
        for xi, x in enumerate(X):
            pnl[r.Index, xi], xt[r.Index, xi] = V2.sim_exit(asset, mt5[r.date], r.e, r.entry_price, r.direction, x, lv)
    return P, Q, X, pnl, xt, mt5, levels


def masks(P):
    F = {}
    for m3, wall in itertools.product((False, True), (False, True)):
        F[(m3, wall)] = ((P["m3"].values | (not m3)) & (P["near_wall"].values | (not wall)))
    return F


def run_is(asset):
    t0 = datetime.now()
    P, Q, X, pnl, xt, mt5, levels = prepare(asset)
    is_mask = (P["date"] <= IS_END).values
    F = masks(P)
    print(f"{asset}: {len(P)} divergências ({int(is_mask.sum())} IS) · preparo {datetime.now() - t0}", flush=True)
    rows = []
    for (m3, wall), m in F.items():
        sel = np.where(m & is_mask)[0]
        for xi, x in enumerate(X):
            ct = 2 if x["tp"] == "mix2L" else 1
            for skip, cap, mode in itertools.product((False, True), (False, True), ("LIVRE", "UM_POR_VEZ")):
                acc = V2.apply_mgmt(sel, P, pnl[:, xi], xt[:, xi], asset, skip, cap, mode, ct)
                s = V2.stats(acc, P, pnl[:, xi], xt[:, xi])
                rows.append(dict(asset=asset, m3=m3, wall=wall, saida=x["name"], xi=xi, sl=x["sl"], tp=x["tp"], be=x["be"],
                                 skip=skip, cap=cap, mode=mode, **s, score=V2.score(s)))
    G = pd.DataFrame(rows)
    key = ["m3", "wall", "sl", "tp", "be", "skip", "cap", "mode"]
    idx = {tuple(r[c] for c in key): r["score"] for _, r in G.iterrows()}
    sls = list(V2.SPEC[asset]["sl"])
    plat = []
    for _, r in G.iterrows():
        vals = [r["score"]]
        for chg in ({"sl": sls[1 - sls.index(r["sl"])]}, {"be": not r["be"]}, {"wall": not r["wall"]}):
            nb = dict(r)
            nb.update(chg)
            k = tuple(nb[c] for c in key)
            if k in idx:
                vals.append(idx[k])
        plat.append(float(np.median(vals)))
    G["plateau"] = plat
    G.to_csv(os.path.join(OUT, f"grid_is_{asset}.csv"), index=False)
    top = G.sort_values(["plateau", "ops"], ascending=False).iloc[0].to_dict()
    top_m3 = G[G.m3].sort_values(["plateau", "ops"], ascending=False).iloc[0].to_dict()

    # placebo: barras quaisquer do IS (com o mesmo filtro 3 motores), mesmo nº por (mês, direção)
    xi = int(top["xi"])
    x = X[xi]
    ct = 2 if x["tp"] == "mix2L" else 1
    sel = np.where(F[(top["m3"], top["wall"])] & is_mask)[0]
    want = defaultdict(int)
    for i in sel:
        want[(P["month"].values[i], int(P["direction"].values[i]))] += 1
    Qp = Q[Q["m3"]] if top["m3"] else Q
    Qp = Qp.reset_index(drop=True)
    qpnl = np.zeros(len(Qp))
    qxt = np.zeros(len(Qp), dtype=int)
    for r in Qp.itertuples():
        qpnl[r.Index], qxt[r.Index] = V2.sim_exit(asset, mt5[r.date], r.e, r.entry_price, r.direction, x, levels(r.date))
    pool = defaultdict(list)
    for i in range(len(Qp)):
        pool[(Qp["month"].values[i], int(Qp["direction"].values[i]))].append(i)
    rng = random.Random(7)
    pl = []
    for _ in range(N_PLACEBO):
        pick = []
        for kk, n in want.items():
            pick += rng.sample(pool[kk], min(n, len(pool[kk])))
        pick = np.array(sorted(pick, key=lambda j: (Qp["di"].values[j], Qp["tm"].values[j])), dtype=int)
        acc = V2.apply_mgmt(pick, Qp, qpnl, qxt, asset, top["skip"], top["cap"], top["mode"], ct)
        pl.append(V2.stats(acc, Qp, qpnl, qxt)["ret_dd"])
    p = (1 + sum(v >= top["ret_dd"] for v in pl)) / (1 + len(pl))
    top.update(placebo_p=p, placebo_med=float(np.median(pl)), ok_is=bool(top["plateau"] > 0 and p < P_MAX))
    print(f"{asset}: escolha m3={top['m3']} wall={top['wall']} {top['saida']} skip={top['skip']} cap={top['cap']} {top['mode']} "
          f"platô {top['plateau']:.2f} ponto {top['ret_dd']:.2f} ({top['ops']} tr, PF {top['pf']}) · placebo med {np.median(pl):.2f} "
          f"p={p:.3f} · {datetime.now() - t0}", flush=True)
    print(f"{asset}: melhor com 3 motores ligado m3={top_m3['m3']} wall={top_m3['wall']} {top_m3['saida']} skip={top_m3['skip']} "
          f"cap={top_m3['cap']} {top_m3['mode']} platô {top_m3['plateau']:.2f} ({top_m3['ops']} tr)", flush=True)
    return asset, dict(escolha=top, melhor_3m=top_m3)


def run_oos(args):
    asset, picks = args
    P, Q, X, pnl, xt, mt5, levels = prepare(asset)
    F = masks(P)
    out, trades = {}, []
    for label, top in picks.items():
        xi = int(top["xi"])
        ct = 2 if X[xi]["tp"] == "mix2L" else 1
        res = {}
        for part, msk in (("is", (P["date"] <= IS_END).values), ("oos", (P["date"] > IS_END).values)):
            sel = np.where(F[(top["m3"], top["wall"])] & msk)[0]
            acc = V2.apply_mgmt(sel, P, pnl[:, xi], xt[:, xi], asset, top["skip"], top["cap"], top["mode"], ct)
            res[part] = V2.stats(acc, P, pnl[:, xi], xt[:, xi])
            trades += [dict(asset=asset, escolha=label, part=part, date=P["date"].values[i], time=P["time"].values[i],
                            sig_time=P["sig_time"].values[i], direction=int(P["direction"].values[i]),
                            brl=float(pnl[i, xi]), exit_tm=int(xt[i, xi])) for i in acc]
        o = res["oos"]
        n_pos = int(o["pos_m"].split("/")[0])
        res["aprovado_oos"] = bool(o["pf"] >= 1.3 and o["net"] > 0 and n_pos >= 3 and (label != "escolha" or top.get("ok_is")))
        out[label] = res
    return asset, out, trades


def main():
    os.makedirs(OUT, exist_ok=True)
    lock = os.path.join(OUT, "oos_log.json")
    if os.path.exists(lock):
        raise SystemExit("OOS já executado.")
    with mp.Pool(2) as pool:
        picks = dict(pool.map(run_is, ["WIN", "WDO"]))
    json.dump({"executed_at": datetime.now().isoformat(timespec="seconds"), "picks": picks},
              open(lock, "w", encoding="utf-8"), indent=1, default=str)
    with mp.Pool(2) as pool:
        res = pool.map(run_oos, [(a, picks[a]) for a in ("WIN", "WDO")])
    allres, trades = {}, []
    for a, o, t in res:
        allres[a] = o
        trades += t
    pd.DataFrame(trades).to_csv(os.path.join(OUT, "oos_trades.csv"), index=False)
    log = json.load(open(lock, encoding="utf-8"))
    log["result"] = allres
    json.dump(log, open(lock, "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(allres, indent=1, default=str))


if __name__ == "__main__":
    main()
