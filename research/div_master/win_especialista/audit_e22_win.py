"""Auditoria completa M1 (bt.sim) do ESP_DIV_V22_WIN em produção + portfólio com V1a (WDO v3.2)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import bt, modulo as M
from research.div_master.wdo_especialista.robustez_final import make_P as make_P_wdo
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo, OPT_OPEN

DS_WIN = bt.market("WIN")
raw_win = {d: v for d, v in load_asset("WIN", "M5").items() if d <= bt.END and d in DS_WIN}
XW = bt.X["WIN"]
PW = M.PARAMS["WIN"]

win_cache = {}
for d in sorted(raw_win):
    bars, walls, _ = raw_win[d]
    fb = M.compute_flow(bars, "WIN")
    w_all = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    w_wall = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall")
    win_cache[d] = (fb, w_all, w_wall, DS_WIN[d])


def sim_win_exact(D, e, ep, d, sl, tp_fix, be_trig, be_lock, tmax, tick, cost, stop_slip, entry_slip, adv_m1=False):
    """Espelho M1 tick-a-tick de bt.sim para WIN com parâmetros configuráveis de estresse."""
    ep_eff = ep + d * entry_slip
    stop = ep_eff - d * sl
    mfe = 0.0
    px, op, off, nn, fb_arr = D["px"], D["op"], D["off"], D["nn"], D["fb"]
    o5, h5, l5, c5, tm5 = D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"]
    n5 = len(o5)
    for k in range(e, n5):
        if k > e:
            if tm5[k] >= 1045 or k - e > tmax:
                return ((o5[k] - ep_eff) * d - cost) * XW["brl"], int(tm5[k])
            if be_trig > 0.0 and mfe >= be_trig:
                cand = ep_eff + d * be_lock
                if (o5[k] - cand) * d > 0.0 and (cand - stop) * d > 0.0:
                    stop = cand
        tp = ep_eff + d * tp_fix if tp_fix > 0 else ep_eff + d * 999999.0
        nt = int(nn[k]) if fb_arr[k] == 0 else 4
        for j in range(nt):
            if fb_arr[k] == 0:
                p, is_op = float(px[off[k] + j]), bool(op[off[k] + j])
            else:
                if j == 0:
                    p, is_op = float(o5[k]), True
                elif j == 1:
                    p, is_op = float(l5[k] if d == 1 else h5[k]), False
                elif j == 2:
                    p, is_op = float(h5[k] if d == 1 else l5[k]), False
                else:
                    p, is_op = float(c5[k]), False
            if k == e and j == 0:
                continue
            if adv_m1 and not is_op and (p - stop) * d <= 0.0:
                return ((stop - d * stop_slip) - ep_eff) * d * XW["brl"] - cost * XW["brl"], int(tm5[k])
            if (p - stop) * d <= 0.0:
                fill = p if is_op else (stop - d * stop_slip)
                return ((fill - ep_eff) * d - cost) * XW["brl"], int(tm5[k])
            if tp_fix > 0 and (p - tp) * d >= 0.0:
                fill = p if is_op else tp
                return ((fill - ep_eff) * d - cost) * XW["brl"], int(tm5[k])
            if (p - ep_eff) * d > mfe:
                mfe = (p - ep_eff) * d
    return ((c5[n5 - 1] - ep_eff) * d - cost) * XW["brl"], int(tm5[n5 - 1])


def get_e22_signals(lv_mode="all", opt=None, nodiv=False, use_filters=True):
    opt_eff = dict(M.V32_PROD if opt is None else opt)
    rows = []
    for d in sorted(win_cache):
        fb, w_all, w_wall, D = win_cache[d]
        levels = w_all if lv_mode == "all" else w_wall
        atr = M.atr_series(fb, PW["tick"])
        if nodiv:
            evs = [(p["conf"], p["idx"], p["side"]) for p in M.zigzag(fb, atr, M.COMMON["r_atr"], PW["zz_floor"])]
            seen, cands = set(), []
            for conf, j, dr in sorted(evs):
                if (dr, j) in seen or conf + 1 >= len(fb):
                    continue
                seen.add((dr, j))
                a = M.anchors(fb, j, dr, levels, PW)
                if not M.eligible(a, "common", fb, j, dr, levels, PW):
                    continue
                cands.append(M._cand("placebo_v32", dr, j, max(0, j - 5), conf, fb, 0.0, 0.0, 1.0, a))
        else:
            cands = M.engine_v32(fb, levels, PW, "common", atr=atr, opt=opt_eff)
        trig, _ = M.triggers(fb, cands, PW)
        seq = {1: 0, -1: 0}
        for x in trig:
            if x.get("dup"):
                continue
            s = seq[x["dir"]]
            seq[x["dir"]] += 1
            t = x["idx"]
            if t + 1 >= len(fb):
                continue
            tm = bt.hm(fb[t + 1]["time"])
            if tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            if use_filters and (x.get("super") or s > 1 or not (600 <= tm < 960)):
                continue
            half = max(float(D["u50"][e] - D["c50"][e]), XW["tick"])
            ext50 = -x["dir"] * float(D["c5"][e - 1] - D["c50"][e]) / half
            slope50 = x["dir"] * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half
            if use_filters and not (ext50 > -0.5 and slope50 > -0.5):
                continue
            rows.append(dict(date=d, e=e, ep=float(D["o5"][e]), dir=int(x["dir"]), tm=tm))
    return rows


def eval_e22(rows, sl=200.0, tp=0.0, be_trig=180.0, be_lock=20.0, tmax=12, mgmt="UM",
             cost=10.0, stop_slip=5.0, entry_slip=0.0, inv=False, mult=1.0):
    if not rows:
        return dict(ops=0, rdd=0.0), pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["date", "tm"]).reset_index(drop=True)
    pnls, xts = [], []
    for r in df.itertuples():
        D = DS_WIN[r.date]
        dr = -r.dir if inv else r.dir
        p, xt = sim_win_exact(D, r.e, r.ep, dr, sl, tp, be_trig, be_lock, tmax, XW["tick"], cost, stop_slip, entry_slip)
        pnls.append(p * mult)
        xts.append(xt)
    df["pnl"] = pnls
    df["xt"] = xts
    if mgmt == "UM":
        df = bt.mgmt(df, "pnl", "xt", "UM")
    return bt.stats(df, "pnl", "xt"), df


if __name__ == "__main__":
    r_prod = get_e22_signals("all", M.V32_PROD)
    print("=== 1. Auditoria ESP_DIV_V22_WIN atual (1 contrato, M1 bt.sim) ===")
    st_base, df_win = eval_e22(r_prod)
    for lbl, kw in [
        ("Base (10/5)", dict()),
        ("LIVRE", dict(mgmt="LIVRE")),
        ("Stop 2 ticks (10/10)", dict(stop_slip=10.0)),
        ("Custo 2x (20/5)", dict(cost=20.0)),
        ("Pesado (20/10/+5e)", dict(cost=20.0, stop_slip=10.0, entry_slip=5.0)),
        ("Invertida (-dir)", dict(inv=True)),
    ]:
        print(f"  {lbl:22s}:", eval_e22(r_prod, **kw)[0])
    r_nd = get_e22_signals("all", M.V32_PROD, nodiv=True)
    print("  Placebo SEM div      :", eval_e22(r_nd)[0])

    print("\n=== 2. Platô ESP_DIV_V22_WIN (SL x tmax) ===")
    for sl in (160.0, 180.0, 200.0, 220.0, 250.0):
        line = []
        for tmax in (8, 12, 16, 20):
            s, _ = eval_e22(r_prod, sl=sl, tmax=tmax)
            line.append(f"t{tmax}:{s['rdd']:.2f}({s['meses']})")
        print(f"  SL={sl:.0f}: " + " | ".join(line))

    print("\n=== 3. Portfólio ESP_DIV_V22_WIN (2 ct) + V1a WDO (1 ct) ===")
    _, df_win2 = eval_e22(r_prod, mult=2.0)
    P_wdo = make_P_wdo(zone=3.5, pierce_max=6.0)
    r_wdo = run_v32_wdo(P_wdo, "wall", "common", OPT_OPEN, "CONF",
                        lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
    st_wdo, df_wdo = eval_wdo(r_wdo, 14.0, "nw", 0.0, 24, "UM")
    print("  WIN E22 (2ct):     ", bt.stats(df_win2, "pnl", "xt"))
    print("  WDO V1a NW (1ct):  ", st_wdo)
    port = bt.portfolio(df_win2, df_wdo, "pnl", "pnl", "xt", "xt")
    print("  CARTEIRA CONJUNTA: ", port)
    idx = pd.Index(sorted(win_cache.keys()))
    s1 = df_win2.groupby("date")["pnl"].sum().reindex(idx, fill_value=0.0)
    s2 = df_wdo.groupby("date")["pnl"].sum().reindex(idx, fill_value=0.0)
    both = (s1 != 0) & (s2 != 0)
    print(f"  Correlação diária: todas={s1.corr(s2):.3f} | ambos operaram ({int(both.sum())}d)={s1[both].corr(s2[both]):.3f}")
