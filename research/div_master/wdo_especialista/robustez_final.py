"""Auditoria completa de robustez, platô, estresse, placebo e correlação para os melhores setups WDO."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import modulo as M
from research.div_master.especialistas import bt

raw_m5 = {d: v for d, v in load_asset("WDO", "M5").items() if d <= bt.END}
DS = bt.market("WDO")
X = bt.X["WDO"]
lo_w, hi_w = bt.WINDOW["WDO"]

days_cache = {}
for d in sorted(raw_m5):
    D = DS.get(d)
    if D is None:
        continue
    bars, walls, _ = raw_m5[d]
    fb = M.compute_flow(bars, "WDO")
    w_all = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    w_wall = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall")
    days_cache[d] = (fb, w_all, w_wall, D)


def sim_exact(D, band, e, ep, d, sl, tp_fix, use_band, front, tp_lo, tp_hi, be_trig, be_lock, tmax,
              tick, cost, stop_slip, entry_slip, adv_m1=False):
    """Espelho exato de bt.sim com parâmetros de estresse (entry_slip, stop_slip, cost, adv_m1)."""
    ep_eff = ep + d * entry_slip
    stop = ep_eff - d * sl
    mfe = 0.0
    px = D["px"]
    op = D["op"]
    off = D["off"]
    nn = D["nn"]
    fb_arr = D["fb"]
    o5 = D["o5"]
    h5 = D["h5"]
    l5 = D["l5"]
    c5 = D["c5"]
    tm5 = D["tm5"]
    n5 = len(o5)

    for k in range(e, n5):
        if k > e:
            if tm5[k] >= 1045 or k - e > tmax:
                return ((o5[k] - ep_eff) * d - cost) * X["brl"], int(tm5[k])
            if be_trig > 0.0 and mfe >= be_trig:
                cand = ep_eff + d * be_lock
                if (o5[k] - cand) * d > 0.0 and (cand - stop) * d > 0.0:
                    stop = cand
        if use_band:
            raw = band[k] - d * front
            lo = ep_eff + d * tp_lo
            hi = ep_eff + d * tp_hi
            tgt = min(max(raw, lo), hi) if d == 1 else max(min(raw, lo), hi)
            tgt = np.round(tgt / tick) * tick
        else:
            tgt = tp_fix

        nt = int(nn[k]) if fb_arr[k] == 0 else 4
        for j in range(nt):
            if fb_arr[k] == 0:
                p = float(px[off[k] + j])
                is_o = bool(op[off[k] + j])
            else:
                if j == 0:
                    p, is_o = float(o5[k]), True
                elif j == 1:
                    p, is_o = (float(l5[k]) if d == 1 else float(h5[k])), False
                elif j == 2:
                    p, is_o = (float(h5[k]) if d == 1 else float(l5[k])), False
                else:
                    p, is_o = float(c5[k]), False

            if (p - stop) * d <= 0.0:
                fill = p if is_o else stop - d * stop_slip
                return ((fill - ep_eff) * d - cost) * X["brl"], int(tm5[k])
            if (p - tgt) * d >= 0.0:
                if adv_m1 and not is_o:
                    # Pior caminho dentro do mesmo minuto (bloco de 4 ticks)
                    if fb_arr[k] == 0:
                        blk_end = min(nt, (j // 4 + 1) * 4)
                        for q in range(j, blk_end):
                            pq = float(px[off[k] + q])
                            if (pq - stop) * d <= 0.0:
                                return ((stop - d * stop_slip - ep_eff) * d - cost) * X["brl"], int(tm5[k])
                    else:
                        if (d == 1 and l5[k] <= stop) or (d == -1 and h5[k] >= stop):
                            return ((stop - d * stop_slip - ep_eff) * d - cost) * X["brl"], int(tm5[k])
                fill = p if is_o else tgt
                return ((fill - ep_eff) * d - cost) * X["brl"], int(tm5[k])
            if (p - ep_eff) * d > mfe:
                mfe = (p - ep_eff) * d
    return ((c5[n5 - 1] - ep_eff) * d - cost) * X["brl"], int(tm5[n5 - 1])


def make_P(**kw):
    P = dict(M.PARAMS["WDO"])
    P.update(kw)
    return P


def run_strategy(eng, P_cfg, lv_mode="wall", elig="common", ctx_fn=None, anc_fn=None, nodiv=False):
    rows = []
    for d in sorted(days_cache):
        fb, w_all, w_wall, D = days_cache[d]
        levels = w_wall if lv_mode == "wall" else w_all
        atr = M.atr_series(fb, P_cfg["tick"])
        if nodiv:
            cands = []
            piv_zz = M.zigzag(fb, atr, M.COMMON["r_atr"], P_cfg["zz_floor"])
            seen = set()
            evs = [(p["conf"], p["idx"], p["side"]) for p in piv_zz]
            for j in range(2, len(fb) - 1):
                for dr in (1, -1):
                    if M.is_piv(fb, j, dr, 2, 1):
                        evs.append((j + 1, j, dr))
            for conf, j, dr in sorted(evs):
                if (dr, j) in seen or conf + 1 >= len(fb):
                    continue
                seen.add((dr, j))
                a = M.anchors(fb, j, dr, levels, P_cfg)
                if not M.eligible(a, elig, fb, j, dr, levels, P_cfg):
                    continue
                cands.append(M._cand("placebo", dr, j, max(0, j - 5), conf, fb, 0.0, 0.0, 1.0, a))
        elif eng == "v3.1":
            cands = M.engine_v31(fb, levels, P_cfg, elig, atr=atr)
        elif eng == "v3.2":
            cands = M.engine_v32(fb, levels, P_cfg, elig, atr=atr, opt=M.V32_PROD)
        elif eng == "v2.2":
            cands = M.engine_v22(fb, levels, P_cfg, elig, atr=atr, opt=M.V22_ABERTURA)

        trigs, _ = M.triggers(fb, cands, P_cfg)
        opc_by = {(t["dir"], t["j"]): t for t in trigs if not t["dup"]}

        for c in cands:
            dr, j, conf = c["dir"], c["j"], c["conf"]
            tr = opc_by.get((dr, j))
            if tr is None or tr["idx"] + 1 >= len(fb):
                continue
            idx_in = tr["idx"] + 1
            tm = bt.hm(fb[idx_in]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            ep = float(D["o5"][e])
            half = max(float(D["u50"][e] - D["c50"][e]), X["tick"])
            ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half if e >= 1 else np.nan
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half
            ext30 = -dr * float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / max(0.5 * (D["u30"][e] - D["l30"][e]), X["tick"]) if e >= 1 else np.nan
            px2 = float(c["px2"])
            d_wall = min((abs(px2 - w) for w in w_wall), default=999.0)
            pass_s = dr * sum(float(fb[x].get("inst_pass_delta", 0)) for x in range(j, conf + 1))
            rec = dict(
                date=d, e=e, ep=ep, dir=dr, j=j, tm=tm, hora=tm // 100,
                has_w=(c["c1"] is not None or c["c2"] is not None),
                has_c1=(c["c1"] is not None), has_d=(c["day"] is not None),
                d_wall=d_wall, ext50=ext50, slope50=slope50, ext30=ext30,
                pass_=pass_s, wd=float(c["wd"]) / max(float(c["thr"]), 1e-9),
                esp=tr["esp"], sub=tr["sub"],
            )
            if anc_fn and not anc_fn(rec):
                continue
            if ctx_fn and not ctx_fn(rec):
                continue
            rows.append(rec)
    return rows


def eval_rows(rows, sl, tp, tmax, use_n30=False, be=(0.0, 0.0), mgmt="UM",
              cost=0.5, stop_slip=0.5, entry_slip=0.0, adv_m1=False, inv=False, check_bt=False):
    if not rows:
        return dict(ops=0, rdd=0.0), pd.DataFrame()
    df_t = pd.DataFrame(rows).sort_values(["date", "tm", "j"]).reset_index(drop=True)
    pnls, xts, bt_pnls = [], [], []
    for r in df_t.itertuples():
        D = DS[r.date]
        dr = -r.dir if inv else r.dir
        band = D["u30"] if dr == 1 else D["l30"]
        tp_px = r.ep + dr * entry_slip + dr * tp
        p, xt = sim_exact(D, band, r.e, r.ep, dr, sl, tp_px, use_n30, X["front"], 2.0, 30.0,
                          be[0], be[1], tmax, X["tick"], cost, stop_slip, entry_slip, adv_m1)
        pnls.append(p)
        xts.append(xt)
        if check_bt:
            pb, xtb = bt.sim(*bt._args(D), band, r.e, r.ep, dr, sl, r.ep + dr * tp, use_n30, X["front"], 2.0, 30.0,
                              be[0], be[1], tmax, X["tick"])
            bt_pnls.append((pb - cost) * X["brl"])
    if check_bt:
        diff = np.max(np.abs(np.array(pnls) - np.array(bt_pnls)))
        if diff > 1e-6:
            print(f"  [WARN] max diff sim_exact vs bt.sim = {diff}")
    df_t["pnl"] = pnls
    df_t["xt"] = xts
    if mgmt == "UM":
        df_t = bt.mgmt(df_t, "pnl", "xt", "UM")
    return bt.stats(df_t, "pnl", "xt"), df_t


def full_audit(name, eng, P_cfg, lv_mode, elig, anc_fn, ctx_fn, sl, tp, tmax, use_n30=False, be=(0.0, 0.0)):
    print(f"\n{'='*80}\nAUDITORIA: {name}\n{'='*80}")
    rows = run_strategy(eng, P_cfg, lv_mode, elig, ctx_fn, anc_fn)
    st_base, df_t = eval_rows(rows, sl, tp, tmax, use_n30, be, "UM", check_bt=True)
    print("Base (UM, bt.sim parity):", st_base)
    print("LIVRE (sem UM):        ", eval_rows(rows, sl, tp, tmax, use_n30, be, "LIVRE")[0])
    print("Custo 2x (1.0/0.5):    ", eval_rows(rows, sl, tp, tmax, use_n30, be, "UM", cost=1.0)[0])
    print("Stop 2t (0.5/1.0):     ", eval_rows(rows, sl, tp, tmax, use_n30, be, "UM", stop_slip=1.0)[0])
    print("Pesado (1.0/1.0/+0.5e):", eval_rows(rows, sl, tp, tmax, use_n30, be, "UM", cost=1.0, stop_slip=1.0, entry_slip=0.5)[0])
    print("Pior M1 + Base:        ", eval_rows(rows, sl, tp, tmax, use_n30, be, "UM", adv_m1=True)[0])
    print("Pior M1 + Custo 2x:    ", eval_rows(rows, sl, tp, tmax, use_n30, be, "UM", cost=1.0, adv_m1=True)[0])
    print("Invertida (-dir):      ", eval_rows(rows, sl, tp, tmax, use_n30, be, "UM", inv=True)[0])
    rows_pl = run_strategy(eng, P_cfg, lv_mode, elig, ctx_fn, anc_fn, nodiv=True)
    print("Placebo SEM diverg.:   ", eval_rows(rows_pl, sl, tp, tmax, use_n30, be, "UM")[0])

    # Mensal
    mon = df_t.groupby(df_t["date"].str[:7])["pnl"].agg(["count", "sum", lambda x: round(100 * (x > 0).mean(), 1)])
    mon.columns = ["ops", "net", "wr%"]
    print("\nMensal:\n" + mon.to_string())
    return df_t


if __name__ == "__main__":
    df_c1 = full_audit(
        "C1: v3.1 (Wall only, zone=3.5, pierce=6.0) | OPC | ANY_WALL | ext50>0.3 | SL12 TP6.5 tm24",
        "v3.1", make_P(zone=3.5, pierce_max=6.0), "wall", "common",
        lambda r: r["has_w"], lambda r: r["ext50"] > 0.3, 12.0, 6.5, 24
    )
    print("\n[Plateau C1: (zone/pierce) x (lv_mode) x (elig)]")
    for lv in ("wall", "all"):
        for zp in ((2.0, 3.5), (2.5, 4.0), (3.0, 5.0), (3.5, 6.0), (4.5, 7.5)):
            r_p = run_strategy("v3.1", make_P(zone=zp[0], pierce_max=zp[1]), lv, "common",
                               lambda r: r["ext50"] > 0.3, lambda r: r["d_wall"] <= zp[0] if lv == "all" else r["has_w"])
            st, _ = eval_rows(r_p, 12.0, 6.5, 24)
            print(f"  lv={lv:4s} z={zp[0]:.1f}/p={zp[1]:.1f} -> ops={st['ops']:3d} rdd={st['rdd']:5.2f} net={st['net']:5d} dd={st['dd']:4d} h1={st['h1']} h2={st['h2']} oos={st['oos']} {st['meses']}")

    print("\n[Plateau C1: SL x TP x ext50_thr (v3.1 wall_only zone=3.5)]")
    for e5 in (0.0, 0.1, 0.2, 0.3, 0.4):
        r_e = run_strategy("v3.1", make_P(zone=3.5, pierce_max=6.0), "wall", "common",
                           lambda r, t=e5: r["ext50"] > t, lambda r: r["has_w"])
        line = []
        for sl in (8.5, 10.0, 12.0, 14.0):
            for tp in (5.5, 6.5, 8.0, 10.0):
                st, _ = eval_rows(r_e, sl, tp, 24)
                line.append(f"{sl:.0f}/{tp:.1f}:{st['rdd']:4.2f}")
        print(f"  e50>{e5:.1f} (n={len(r_e):3d}) | " + " ".join(line))

    df_c2 = full_audit(
        "C2: v3.1 (Wall only, zone=2.5, pierce=4.0) | OPC | ANY_WALL | ext30>0.0 | SL12 TP6.5 tm24",
        "v3.1", make_P(zone=2.5, pierce_max=4.0), "wall", "common",
        lambda r: r["has_w"], lambda r: r["ext30"] > 0.0, 12.0, 6.5, 24
    )

    df_c3 = full_audit(
        "C3: v3.1 (Wall+Mid, elig=all) | OPC | d_wall<=3.5 | pass>0 | SL12 TP6.5 tm24",
        "v3.1", make_P(zone=3.5, pierce_max=6.0), "all", "all",
        lambda r: r["d_wall"] <= 3.5, lambda r: r["pass_"] > 0.0, 12.0, 6.5, 24
    )

    df_c4 = full_audit(
        "C4: v3.2 (Wall only, zone=2.5, pierce=4.0) | OPC | EXT_OR_FURO | ext50>0.3 | SL12 TP12 tm12",
        "v3.2", make_P(zone=2.5, pierce_max=4.0), "wall", "all",
        lambda r: (r["has_d"] or r["has_c1"]), lambda r: r["ext50"] > 0.3, 12.0, 12.0, 12
    )
    print("\n[Plateau C4: (zone/pierce) x (lv_mode) x (SL/TP/tm)]")
    for lv in ("wall", "all"):
        for zp in ((2.0, 3.5), (2.5, 4.0), (3.0, 5.0), (3.5, 6.0)):
            r_p = run_strategy("v3.2", make_P(zone=zp[0], pierce_max=zp[1]), lv, "all",
                               lambda r: r["ext50"] > 0.3, lambda r: (r["has_d"] or r["has_c1"]))
            st, _ = eval_rows(r_p, 12.0, 12.0, 12)
            print(f"  lv={lv:4s} z={zp[0]:.1f}/p={zp[1]:.1f} -> ops={st['ops']:3d} rdd={st['rdd']:5.2f} net={st['net']:5d} dd={st['dd']:4d} h1={st['h1']} h2={st['h2']} oos={st['oos']} {st['meses']}")

    print("\n[Plateau C4: SL x TP x tm x ext50 (v3.2 wall_only zone=2.5)]")
    r_c4_base = run_strategy("v3.2", make_P(zone=2.5, pierce_max=4.0), "wall", "all",
                             lambda r: r["ext50"] > 0.3, lambda r: (r["has_d"] or r["has_c1"]))
    for sl in (8.5, 10.0, 12.0, 14.0):
        line = []
        for tp in (8.0, 10.0, 12.0, 15.0):
            for tm in (12, 24):
                st, _ = eval_rows(r_c4_base, sl, tp, tm)
                line.append(f"tp{tp:.0f}t{tm}:{st['rdd']:4.2f}")
        print(f"  SL={sl:4.1f} | " + " ".join(line))
