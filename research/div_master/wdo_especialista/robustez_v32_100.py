"""Auditoria completa de robustez, platô, estresse e placebo para os candidatos v3.2 (>= 100 trades) no WDO."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import modulo as M
from research.div_master.especialistas import bt
from research.div_master.wdo_especialista.robustez_final import sim_exact, make_P, days_cache, DS, X, lo_w, hi_w

raw_m5 = {d: v for d, v in load_asset("WDO", "M5").items() if d <= bt.END}


def run_v32(P_cfg, lv_mode="wall", elig="common", opt=None, mode="CONF",
            anc_fn=None, time_fn=None, ctx_fn=None, nodiv=False):
    opt_eff = dict(M.V32)
    if opt is not None:
        opt_eff.update(opt)
    rows = []
    for d in sorted(days_cache):
        fb, w_all, w_wall, D = days_cache[d]
        levels = w_wall if lv_mode == "wall" else w_all
        atr = M.atr_series(fb, P_cfg["tick"])

        if nodiv:
            # Placebo: mesmos pivôs do v3.2 (ZigZag 1.2 + opcional abertura zz08 + lr), sem filtro de divergência
            t_open = M.hm(M.COMMON["open_conf_end"])
            evs = [(p["conf"], p["idx"], p["side"]) for p in M.zigzag(fb, atr, M.COMMON["r_atr"], P_cfg["zz_floor"])]
            if opt_eff.get("open_module"):
                for p in M.zigzag(fb, atr, M.COMMON["r_atr_open"], P_cfg["zz_floor"]):
                    if M.hm(fb[p["conf"]]["time"]) <= t_open:
                        evs.append((p["conf"], p["idx"], p["side"]))
                for j in range(1, len(fb) - 1):
                    conf = j + 1
                    for dr in (1, -1):
                        if M.hm(fb[conf]["time"]) <= t_open and M.is_piv(fb, j, dr, 2, 1) and dr * (fb[conf]["close"] - fb[conf]["open"]) > 0:
                            evs.append((conf, j, dr))
            seen = set()
            cands = []
            for conf, j, dr in sorted(evs):
                if (dr, j) in seen or conf + 1 >= len(fb):
                    continue
                seen.add((dr, j))
                a = M.anchors(fb, j, dr, levels, P_cfg)
                if not M.eligible(a, elig, fb, j, dr, levels, P_cfg):
                    continue
                cands.append(M._cand("placebo_v32", dr, j, max(0, j - 5), conf, fb, 0.0, 0.0, 1.0, a))
        else:
            cands = M.engine_v32(fb, levels, P_cfg, elig, atr=atr, opt=opt_eff)

        opc_by = {}
        if mode == "OPC":
            trigs, _ = M.triggers(fb, cands, P_cfg)
            opc_by = {(t["dir"], t["j"]): t for t in trigs if not t["dup"]}

        for c in cands:
            dr, j, conf = c["dir"], c["j"], c["conf"]
            if mode == "OPC":
                tr = opc_by.get((dr, j))
                if tr is None or tr["idx"] + 1 >= len(fb):
                    continue
                idx_in = tr["idx"] + 1
            else:
                if conf + 1 >= len(fb):
                    continue
                idx_in = conf + 1

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
            nw = bt.next_level(w_all, ep, dr, 2.0 + X["front"])
            nw_d = dr * (nw - ep) - X["front"] if nw is not None else np.nan

            rec = dict(
                date=d, e=e, ep=ep, dir=dr, j=j, tm=tm, hh=tm // 60,
                has_w=(c["c1"] is not None or c["c2"] is not None),
                has_c1=(c["c1"] is not None), has_d=(c["day"] is not None),
                d_wall=d_wall, ext50=ext50, slope50=slope50, ext30=ext30,
                pass_=pass_s, nw_d=nw_d, src=c.get("src", ""),
            )
            if anc_fn and not anc_fn(rec):
                continue
            if time_fn and not time_fn(rec):
                continue
            if ctx_fn and not ctx_fn(rec):
                continue
            rows.append(rec)
    return rows


def eval_v32(rows, sl, tp_kind, tp_val, tmax, mgmt="UM", cost=0.5, stop_slip=0.5, entry_slip=0.0, adv_m1=False, inv=False, check_bt=False):
    if not rows:
        return dict(ops=0, rdd=0.0), pd.DataFrame()
    df_t = pd.DataFrame(rows).sort_values(["date", "tm", "j"]).reset_index(drop=True)
    pnls, xts, bt_pnls = [], [], []
    valid = []
    for i, r in enumerate(df_t.itertuples()):
        D = DS[r.date]
        dr = -r.dir if inv else r.dir
        if tp_kind == "nw":
            if inv:
                # Se invertida, recalcula próxima wall na direção invertida
                _, w_all, _, _ = days_cache[r.date]
                nw = bt.next_level(w_all, r.ep + dr * entry_slip, dr, 2.0 + X["front"])
                nwd = dr * (nw - (r.ep + dr * entry_slip)) - X["front"] if nw is not None else np.nan
            else:
                nwd = r.nw_d
            if np.isnan(nwd) or nwd < 2.5:
                continue
            tp_pts = min(max(nwd, 4.0), 22.0)
        else:
            tp_pts = tp_val

        valid.append(i)
        tp_px = r.ep + dr * entry_slip + dr * tp_pts
        p, xt = sim_exact(D, D["u30"], r.e, r.ep, dr, sl, tp_px, False, 0.0, 0.0, 0.0,
                          0.0, 0.0, tmax, X["tick"], cost, stop_slip, entry_slip, adv_m1)
        pnls.append(p)
        xts.append(xt)
        if check_bt:
            pb, _ = bt.sim(*bt._args(D), D["u30"], r.e, r.ep, dr, sl, r.ep + dr * tp_pts, False, 0.0, 0.0, 0.0,
                           0.0, 0.0, tmax, X["tick"])
            bt_pnls.append((pb - cost) * X["brl"])

    if not valid:
        return dict(ops=0, rdd=0.0), pd.DataFrame()
    if check_bt:
        diff = np.max(np.abs(np.array(pnls) - np.array(bt_pnls)))
        if diff > 1e-6:
            print(f"  [WARN] diff vs bt.sim = {diff}")
    df_v = df_t.iloc[valid].copy().reset_index(drop=True)
    df_v["pnl"] = pnls
    df_v["xt"] = xts
    if mgmt == "UM":
        df_v = bt.mgmt(df_v, "pnl", "xt", "UM")
    return bt.stats(df_v, "pnl", "xt"), df_v


def audit(title, P_cfg, lv_mode, elig, opt, mode, anc_fn, time_fn, ctx_fn, sl, tp_kind, tp_val, tmax):
    print(f"\n{'='*86}\n{title}\n{'='*86}")
    rows = run_v32(P_cfg, lv_mode, elig, opt, mode, anc_fn, time_fn, ctx_fn)
    st, df_v = eval_v32(rows, sl, tp_kind, tp_val, tmax, "UM", check_bt=True)
    print("Base (UM, bt.sim parity):", st)
    print("LIVRE (sem UM):        ", eval_v32(rows, sl, tp_kind, tp_val, tmax, "LIVRE")[0])
    print("Custo 2x (1.0/0.5):    ", eval_v32(rows, sl, tp_kind, tp_val, tmax, "UM", cost=1.0)[0])
    print("Stop 2t (0.5/1.0):     ", eval_v32(rows, sl, tp_kind, tp_val, tmax, "UM", stop_slip=1.0)[0])
    print("Pesado (1.0/1.0/+0.5e):", eval_v32(rows, sl, tp_kind, tp_val, tmax, "UM", cost=1.0, stop_slip=1.0, entry_slip=0.5)[0])
    print("Pior M1 + Base:        ", eval_v32(rows, sl, tp_kind, tp_val, tmax, "UM", adv_m1=True)[0])
    print("Invertida (-dir):      ", eval_v32(rows, sl, tp_kind, tp_val, tmax, "UM", inv=True)[0])
    rows_pl = run_v32(P_cfg, lv_mode, elig, opt, mode, anc_fn, time_fn, ctx_fn, nodiv=True)
    print("Placebo SEM diverg.:   ", eval_v32(rows_pl, sl, tp_kind, tp_val, tmax, "UM")[0])
    mon = df_v.groupby(df_v["date"].str[:7])["pnl"].agg(["count", "sum", lambda x: round(100 * (x > 0).mean(), 1)])
    mon.columns = ["ops", "net", "wr%"]
    print("\nMensal:\n" + mon.to_string())
    return df_v


OPT_OPEN = {**M.V32, "abertura": M.V22_ABERTURA}

if __name__ == "__main__":
    # 1. V1a: V32 abertura + CONF + Wall pura z=3.5 + no11 + ext30>0 + NW sl14 tm24
    audit(
        "V1a: v3.2 (open=True, Wall only z=3.5/p=6.0) | CONF | WALL | hh!=11 | ext30>0 | TP=ProxWall SL14 tm24",
        make_P(zone=3.5, pierce_max=6.0), "wall", "common", OPT_OPEN, "CONF",
        lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0,
        14.0, "nw", 0.0, 24
    )

    print("\n[Plateau V1a: ext30_thr x (SL/TP_mode) & open_module]")
    for om_name, om in [("open=True", OPT_OPEN), ("open=False(PROD)", M.V32_PROD)]:
        for lv in ("wall", "all"):
            r_t = run_v32(make_P(zone=3.5, pierce_max=6.0), lv, "common", om, "CONF",
                          lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
            st_nw, _ = eval_v32(r_t, 14.0, "nw", 0.0, 24)
            st_f12, _ = eval_v32(r_t, 14.0, "fix", 12.0, 24)
            print(f"  {om_name:16s} lv={lv:4s} e30>0 -> NW: ops={st_nw['ops']} rdd={st_nw['rdd']} {st_nw['meses']} [{st_nw['h1']}/{st_nw['h2']}/{st_nw['oos']}] | TP12: ops={st_f12['ops']} rdd={st_f12['rdd']}")

    for e3 in (-0.2, 0.0, 0.1, 0.2, 0.3):
        r_e = run_v32(make_P(zone=3.5, pierce_max=6.0), "wall", "common", OPT_OPEN, "CONF",
                      lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r, t=e3: r["ext30"] > t)
        outs = []
        for sl in (10.0, 12.0, 14.0):
            for tk, tv in [("nw", 0.0), ("fix", 10.0), ("fix", 12.0), ("fix", 15.0)]:
                st, _ = eval_v32(r_e, sl, tk, tv, 24)
                lbl = "NW" if tk == "nw" else f"{tv:.0f}"
                outs.append(f"{sl:.0f}/{lbl}:{st['rdd']:4.2f}({st['ops']})")
        print(f"  e30>{e3:+.1f} | " + " ".join(outs))

    for zp in ((2.0, 3.5), (2.5, 4.0), (3.0, 5.0), (3.5, 6.0), (5.0, 8.0)):
        r_z = run_v32(make_P(zone=zp[0], pierce_max=zp[1]), "wall", "common", OPT_OPEN, "CONF",
                      lambda r, z=zp[0]: r["d_wall"] <= z, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
        st_nw, _ = eval_v32(r_z, 14.0, "nw", 0.0, 24)
        st_12, _ = eval_v32(r_z, 14.0, "nw", 0.0, 12)
        print(f"  zone={zp[0]:.1f}/p={zp[1]:.1f} -> tm24: {st_nw['ops']} ops rdd={st_nw['rdd']} {st_nw['meses']} [{st_nw['h1']}/{st_nw['h2']}/{st_nw['oos']}] | tm12: rdd={st_12['rdd']}")

    # 2. V2: V32_PROD wideW z=5.0/p=8.0 | CONF | ANY_WALL | 09a12 | ext30>0.2 & 0.0
    audit(
        "V2: v3.2 (PROD open=False, Wall only z=5.0/p=8.0) | CONF | ANY_WALL | 09h-12h | ext30>0.2 | SL14 TP12 tm8",
        make_P(zone=5.0, pierce_max=8.0), "wall", "common", M.V32_PROD, "CONF",
        lambda r: r["has_w"], lambda r: r["tm"] <= 720, lambda r: r["ext30"] > 0.2,
        14.0, "fix", 12.0, 8
    )
    print("\n[Plateau V2: ext30 x zone x SL/TP/tm]")
    for e3 in (0.0, 0.1, 0.2, 0.3):
        r_v2 = run_v32(make_P(zone=5.0, pierce_max=8.0), "wall", "common", M.V32_PROD, "CONF",
                       lambda r: r["has_w"], lambda r: r["tm"] <= 720, lambda r, t=e3: r["ext30"] > t)
        s1 = eval_v32(r_v2, 12.0, "fix", 8.0, 8)[0]
        s2 = eval_v32(r_v2, 14.0, "fix", 12.0, 8)[0]
        s3 = eval_v32(r_v2, 12.0, "fix", 12.0, 12)[0]
        print(f"  e30>{e3:.1f} -> 12/8t8: ops={s1['ops']} rdd={s1['rdd']} | 14/12t8: ops={s2['ops']} rdd={s2['rdd']} | 12/12t12: ops={s3['ops']} rdd={s3['rdd']}")

    # 3. V3: v3.2 f1=flow_k1 vs flow | CONF | COMMON | 09h-12h | pass>0 | SL14 TP12 tm12
    audit(
        "V3: v3.2 (open=False, f1=flow_k1, Wall only z=3.5) | CONF | COMMON | 09h-12h | pass>0 | SL14 TP12 tm12",
        make_P(zone=3.5, pierce_max=6.0), "wall", "common", {**M.V32_PROD, "f1": "flow_k1"}, "CONF",
        lambda r: (r["has_w"] or r["has_d"]), lambda r: r["tm"] <= 720, lambda r: r["pass_"] > 0.0,
        14.0, "fix", 12.0, 12
    )
    print("\n[Comparação V3 com f1='flow' padrão vs 'flow_k1' e SL/TP/hora]")
    for f1m in ("flow", "flow_k1"):
        for om_b in (False, True):
            r_v3 = run_v32(make_P(zone=3.5, pierce_max=6.0), "wall", "common",
                           {**M.V32_PROD, "f1": f1m, "open_module": om_b}, "CONF",
                           lambda r: (r["has_w"] or r["has_d"]), lambda r: r["tm"] <= 720, lambda r: r["pass_"] > 0.0)
            st, _ = eval_v32(r_v3, 14.0, "fix", 12.0, 12)
            print(f"  f1={f1m:7s} open={str(om_b):5s} -> {st}")

    # 4. V4: V32_PROD tight alllv | OPC | EXT_OR_FURO | 09h-15h | pass>0 | SL12 TP12 tm24
    audit(
        "V4: v3.2 (PROD, Wall+Mid z=2.5/p=4.0) | OPC | EXT_OR_FURO | 09h-15h | pass>0 | SL12 TP12 tm24",
        make_P(zone=2.5, pierce_max=4.0), "all", "common", M.V32_PROD, "OPC",
        lambda r: (r["has_d"] or r["has_c1"]), lambda r: r["tm"] <= 900, lambda r: r["pass_"] > 0.0,
        12.0, "fix", 12.0, 24
    )
