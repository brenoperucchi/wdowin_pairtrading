"""Auditoria completa de robustez, placebo, platô e portfólio dos candidatos WIN v3.2 (>=100 trades)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import win_cache, DS_WIN, XW, sim_win_exact, get_e22_signals, eval_e22
from research.div_master.wdo_especialista.robustez_final import make_P as make_P_wdo
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo, OPT_OPEN

lo_w, hi_w = bt.WINDOW["WIN"]
OPT_WIN_OPEN = {**M.V32, "abertura": M.V22_ABERTURA}


def make_PW(zone=150.0, pierce_max=220.0):
    P = dict(M.PARAMS["WIN"])
    P["zone"] = zone
    P["pierce_max"] = pierce_max
    return P


def run_win_v32(P_cfg, lv_mode, opt, mode, anc_fn, time_fn, ctx_fn, nodiv=False):
    rows = []
    t_open = M.hm(M.COMMON["open_conf_end"])
    for d in sorted(win_cache):
        fb, w_all, w_wall, D = win_cache[d]
        levels = w_all if lv_mode == "all" else w_wall
        atr = M.atr_series(fb, P_cfg["tick"])
        if nodiv:
            evs = [(p["conf"], p["idx"], p["side"]) for p in M.zigzag(fb, atr, M.COMMON["r_atr"], P_cfg["zz_floor"])]
            if opt.get("open_module"):
                for p in M.zigzag(fb, atr, M.COMMON["r_atr_open"], P_cfg["zz_floor"]):
                    if M.hm(fb[p["conf"]]["time"]) <= t_open:
                        evs.append((p["conf"], p["idx"], p["side"]))
                for j in range(1, len(fb) - 1):
                    conf = j + 1
                    for dr in (1, -1):
                        if M.hm(fb[conf]["time"]) <= t_open and M.is_piv(fb, j, dr, 2, 1) and dr * (fb[conf]["close"] - fb[conf]["open"]) > 0:
                            evs.append((conf, j, dr))
            seen, cands = set(), []
            for conf, j, dr in sorted(evs):
                if (dr, j) in seen or conf + 1 >= len(fb):
                    continue
                seen.add((dr, j))
                a = M.anchors(fb, j, dr, levels, P_cfg)
                if not M.eligible(a, "common", fb, j, dr, levels, P_cfg):
                    continue
                cands.append(M._cand("placebo_v32", dr, j, max(0, j - 5), conf, fb, 0.0, 0.0, 1.0, a))
        else:
            cands = M.engine_v32(fb, levels, P_cfg, "common", atr=atr, opt=opt)

        raw = []
        if mode == "OPC":
            trigs, _ = M.triggers(fb, cands, P_cfg)
            by = {(c["dir"], c["j"]): c for c in cands}
            seq = {1: 0, -1: 0}
            for tr in trigs:
                if tr.get("dup"):
                    continue
                s = seq[tr["dir"]]
                seq[tr["dir"]] += 1
                t = tr["idx"]
                if t + 1 >= len(fb):
                    continue
                raw.append((by[(tr["dir"], tr["j"])], t, t + 1, s, bool(tr.get("super")), tr.get("esp", "")))
        else:
            for c in cands:
                if c["conf"] + 1 >= len(fb):
                    continue
                raw.append((c, c["conf"], c["conf"] + 1, 0, False, "CONF"))

        for c, idx_sig, idx_in, seq_n, is_super, esp in raw:
            tm = bt.hm(fb[idx_in]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            ep = float(D["o5"][e])
            dr = int(c["dir"])
            half50 = max(float(D["u50"][e] - D["c50"][e]), XW["tick"])
            ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half50
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
            d_wall = min((abs(float(c["px2"]) - w) for w in w_wall), default=99999.0)
            pass_s = dr * sum(float(fb[x].get("inst_pass_delta", 0.0)) for x in range(c["j"], idx_sig + 1))
            candle_fav = dr * (float(fb[idx_sig]["close"]) - float(fb[idx_sig]["open"])) > 0
            rec = dict(
                date=d, e=e, ep=ep, dir=dr, j=c["j"], tm=tm, hh=tm // 60, seq=seq_n, is_super=is_super,
                esp=esp, has_w=(c["c1"] is not None or c["c2"] is not None), has_d=(c["day"] is not None),
                d_wall=d_wall, ext50=ext50, slope50=slope50, pass_=pass_s, candle_fav=candle_fav,
            )
            if (not anc_fn or anc_fn(rec)) and (not time_fn or time_fn(rec)) and (not ctx_fn or ctx_fn(rec)):
                rows.append(rec)
    return rows


def eval_win(rows, sl, tp, tmax, be_t=0.0, be_l=0.0, mgmt="UM", cost=10.0, stop_slip=5.0, entry_slip=0.0, adv_m1=False, inv=False, mult=1.0):
    if not rows:
        return dict(ops=0, rdd=0.0), pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["date", "tm", "j"]).reset_index(drop=True)
    pnls, xts = [], []
    for r in df.itertuples():
        D = DS_WIN[r.date]
        dr = -r.dir if inv else r.dir
        p, xt = sim_win_exact(D, r.e, r.ep, dr, sl, tp, be_t, be_l, tmax, XW["tick"], cost, stop_slip, entry_slip, adv_m1)
        pnls.append(p * mult)
        xts.append(xt)
    df["pnl"] = pnls
    df["xt"] = xts
    if mgmt == "UM":
        df = bt.mgmt(df, "pnl", "xt", "UM")
    return bt.stats(df, "pnl", "xt"), df


def audit_cand(title, P_cfg, lv_mode, opt, mode, anc_fn, time_fn, ctx_fn, sl, tp, tmax, df_e22):
    print(f"\n{'='*88}\n{title}\n{'='*88}")
    rows = run_win_v32(P_cfg, lv_mode, opt, mode, anc_fn, time_fn, ctx_fn)
    st, df_v = eval_win(rows, sl, tp, tmax)
    print("Base (10/5):         ", st)
    print("LIVRE (sem UM):      ", eval_win(rows, sl, tp, tmax, mgmt="LIVRE")[0])
    print("Pior caminho M1:     ", eval_win(rows, sl, tp, tmax, adv_m1=True)[0])
    print("Stop 2 ticks (10/10):", eval_win(rows, sl, tp, tmax, stop_slip=10.0)[0])
    print("Custo 2x (20/5):     ", eval_win(rows, sl, tp, tmax, cost=20.0)[0])
    print("Pesado (20/10/+5e):  ", eval_win(rows, sl, tp, tmax, cost=20.0, stop_slip=10.0, entry_slip=5.0)[0])
    print("Invertida (-dir):    ", eval_win(rows, sl, tp, tmax, inv=True)[0])
    rows_nd = run_win_v32(P_cfg, lv_mode, opt, mode, anc_fn, time_fn, ctx_fn, nodiv=True)
    print("Placebo SEM diverg.: ", eval_win(rows_nd, sl, tp, tmax)[0])

    # Portfolio combinado com E22 atual (2ct E22 + 1ct candidato)
    port = bt.portfolio(df_e22, df_v, "pnl", "pnl", "xt", "xt")
    all_d = pd.Index(sorted(win_cache.keys()))
    s1 = df_e22.groupby("date")["pnl"].sum().reindex(all_d, fill_value=0.0)
    s2 = df_v.groupby("date")["pnl"].sum().reindex(all_d, fill_value=0.0)
    print(f"Corr diária vs E22: {s1.corr(s2):.3f} | Portfólio E22(2ct)+Cand(1ct): {port}")


if __name__ == "__main__":
    _, df_e22 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=2.0)

    # I1: estilo V1a (CONF + open=True + Wall-only + 09h-12h + candle_fav)
    audit_cand(
        "I1: V32 (open=True, Wall-only z=150) | CONF | COMMON | 09h-12h | candle_fav | SL250 TP200 t18",
        make_PW(150, 220), "wall", OPT_WIN_OPEN, "CONF",
        lambda r: (r["has_w"] or r["has_d"]), lambda r: r["tm"] <= 720, lambda r: r["candle_fav"],
        250.0, 200.0, 18, df_e22,
    )

    # I2: V32_PROD (open=False) | OPC | WALL_ESP | 09h-12h | ext50>-0.5&sl>-0.5 | SL200 TP300 t24
    audit_cand(
        "I2: V32_PROD (open=False, Wall+Mid z=150) | OPC | WALL_ESP | 09h-12h | ext50>-0.5&sl>-0.5 | SL200 TP300 t24",
        make_PW(150, 220), "all", M.V32_PROD, "OPC",
        lambda r: r["esp"] == "WALL", lambda r: r["tm"] <= 720, lambda r: r["ext50"] > -0.5 and r["slope50"] > -0.5,
        200.0, 300.0, 24, df_e22,
    )

    # I3: V32_PROD | OPC | ALL | 09h-11h | ext50>0 | SL250 TP250 t24
    audit_cand(
        "I3: V32_PROD (open=False, Wall+Mid z=150) | OPC | ALL | 09h-11h | ext50>0 | SL250 TP250 t24",
        make_PW(150, 220), "all", M.V32_PROD, "OPC",
        None, lambda r: r["tm"] < 660, lambda r: r["ext50"] > 0.0,
        250.0, 250.0, 24, df_e22,
    )

    # I4: V32_OPEN | OPC | NO_SUP_SEQ2 | 10h-16h | ext50>0 | SL250 TP350 t24
    audit_cand(
        "I4: V32 (open=True, Wall+Mid z=150) | OPC | NO_SUP_SEQ2 | 10h-16h | ext50>0 | SL250 TP350 t24",
        make_PW(150, 220), "all", OPT_WIN_OPEN, "OPC",
        lambda r: (not r["is_super"]) and r["seq"] <= 1, lambda r: 600 <= r["tm"] < 960, lambda r: r["ext50"] > 0.0,
        250.0, 350.0, 24, df_e22,
    )

    # I5: V32_OPEN | CONF | DWALL150 | 09h-12h | pass>0 | SL200 TP300 t24
    audit_cand(
        "I5: V32 (open=True, Wall+Mid z=150) | CONF | DWALL150 | 09h-12h | pass>0 | SL200 TP300 t24",
        make_PW(150, 220), "all", OPT_WIN_OPEN, "CONF",
        lambda r: r["d_wall"] <= 150.0, lambda r: r["tm"] <= 720, lambda r: r["pass_"] > 0.0,
        200.0, 300.0, 24, df_e22,
    )

    # Platô de vizinhos dos finalistas I1 e I2
    print("\n=== PLATÔ I1 (CONF Wall-only open=True | 09h-12h | candle_fav | t=18) ===")
    r_i1 = run_win_v32(make_PW(150, 220), "wall", OPT_WIN_OPEN, "CONF",
                       lambda r: (r["has_w"] or r["has_d"]), lambda r: r["tm"] <= 720, lambda r: r["candle_fav"])
    for sl in (200.0, 220.0, 250.0, 280.0, 300.0):
        print(f"  SL={sl:.0f}: " + " | ".join(
            f"TP{tp:.0f}:{eval_win(r_i1, sl, tp, 18)[0]['rdd']:.2f}({eval_win(r_i1, sl, tp, 18)[0]['meses']})"
            for tp in (150.0, 180.0, 200.0, 220.0, 250.0)
        ))
    print("  I1 sem candle_fav / all / zone=100 / zone=200:")
    for lbl, zp, lv, ctx in [
        ("z100/p150 wall candle", (100, 150), "wall", lambda r: r["candle_fav"]),
        ("z150/p220 wall candle", (150, 220), "wall", lambda r: r["candle_fav"]),
        ("z200/p300 wall candle", (200, 300), "wall", lambda r: r["candle_fav"]),
        ("z150/p220 wall sem candle", (150, 220), "wall", None),
        ("z150/p220 all candle", (150, 220), "all", lambda r: r["candle_fav"]),
    ]:
        rr = run_win_v32(make_PW(*zp), lv, OPT_WIN_OPEN, "CONF", lambda r: (r["has_w"] or r["has_d"]), lambda r: r["tm"] <= 720, ctx)
        print(f"    {lbl:25s}: {eval_win(rr, 250.0, 200.0, 18)[0]}")

    print("\n=== PLATÔ I2 (OPC WALL_ESP V32_PROD | 09h-12h | ext50>-0.5&sl>-0.5 | t=24) ===")
    r_i2 = run_win_v32(make_PW(150, 220), "all", M.V32_PROD, "OPC",
                       lambda r: r["esp"] == "WALL", lambda r: r["tm"] <= 720, lambda r: r["ext50"] > -0.5 and r["slope50"] > -0.5)
    for sl in (180.0, 200.0, 220.0, 250.0):
        print(f"  SL={sl:.0f}: " + " | ".join(
            f"TP{tp:.0f}:{eval_win(r_i2, sl, tp, 24)[0]['rdd']:.2f}({eval_win(r_i2, sl, tp, 24)[0]['meses']})"
            for tp in (200.0, 250.0, 300.0, 350.0)
        ))
