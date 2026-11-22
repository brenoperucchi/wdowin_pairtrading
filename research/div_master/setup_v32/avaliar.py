# -*- coding: utf-8 -*-
"""Grade do add-on v3.2 (pesquisa, causal). Uso: python research/div_master/setup_v32/avaliar.py"""
import json, os, sys, time, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from motor_addon import *  # noqa

OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)


def build_days(asset, shift=0.0):
    data = {d: v for d, v in load_asset(asset, "M5").items() if d <= END}
    DS = bt.market(asset)
    P = M.PARAMS[asset]
    days = {}
    for d in sorted(data):
        if d not in DS:
            continue
        bars, walls, _ = data[d]
        fb = M.compute_flow([dict(b) for b in bars], asset)
        if len(fb) < 5:
            continue
        lv = sorted(float(w["price"]) + shift for w in walls if w.get("type") in M.LEVEL_TYPES)
        wl = [dict(type=w["type"], price=float(w["price"]) + shift) for w in walls if w.get("type") in M.LEVEL_TYPES]
        atr = M.atr_series(fb, P["tick"])
        cands = M.engine_v32(fb, lv, P, "common", atr=atr, opt=M.V32_PROD)
        trig, _ = M.triggers(fb, cands, P)
        days[d] = dict(fb=fb, lv=lv, walls=wl, cands=cands, trig=trig, atr=atr, D=DS[d], ex=exec_bars(DS[d]))
    return days, DS


def e22_trades(days):
    rows, per = [], {}
    for d, x in days.items():
        trs = E.run(x["fb"], x["walls"], x["ex"])
        per[d] = []
        for t in trs:
            r = dict(date=d, tm=hm(t["time"]), xt=hm(t["exit_time"]), d=t["dir_num"],
                     be_tm=hm(t["be_time"]) if t.get("be_time") else None, brl=float(t["brl_1c"]))
            per[d].append(r)
            rows.append(r)
    return pd.DataFrame(rows), per


def placebo_cands(fb, lv, P, atr, real):
    """P1: pivôs ZigZag 1,2xATR elegíveis (Wall/extremo) que NÃO são F2 de divergência v3.2."""
    used = {(c["dir"], c["j"]) for c in real}
    out = []
    for p in M.zigzag(fb, atr, M.COMMON["r_atr"], P["zz_floor"]):
        j, d, conf = p["idx"], p["side"], p["conf"]
        if (d, j) in used or j < 2:
            continue
        a = M.anchors(fb, j, d, lv, P)
        if not M.eligible(a, "common"):
            continue
        out.append(dict(engine="P1", dir=d, j=j, k=max(0, j - 2), conf=conf, px1=M._px(fb[j], d),
                        px2=M._px(fb[j], d), w1=0.0, w2=0.0, wd=0.0, thr=0.0, c1=a["c1"], c2=a["c2"],
                        day=a["day"], time_j=fb[j]["time"], time_conf=fb[conf]["time"], micro=False))
    return out


def gen_signals(asset, days, e22per, tese, gat, source="real"):
    """Lista de sinais (data, tm entrada, d, piv, tese) antes da gestão de coexistência."""
    P = M.PARAMS[asset]
    tick = TICK[asset]
    sig = []
    for d, x in days.items():
        fb, lv, D = x["fb"], x["lv"], x["D"]
        pos = D["pos"]
        if source == "p1":
            cands = placebo_cands(fb, lv, P, x["atr"], x["cands"])
            trig, _ = M.triggers(fb, cands, P)
        else:
            cands, trig = x["cands"], x["trig"]
        by = {(c["dir"], c["j"]): c for c in cands}
        # funil E22 causal (só WIN, só sinais reais) — seq por direção e motivo
        e22_ent = {(r["tm"], r["d"]) for r in e22per.get(d, [])}
        seq_hist = {1: [], -1: []}  # idx dos gatilhos E22 por direção
        seq = {1: 0, -1: 0}
        trig_info = []
        for t_ in x["trig"]:
            s = seq[t_["dir"]]
            seq[t_["dir"]] += 1
            seq_hist[t_["dir"]].append(t_["idx"])
            trig_info.append((t_, s))

        def seq_at(dirn, t_idx):
            return sum(1 for i in seq_hist[dirn] if i <= t_idx)

        def push(c, t, label):
            if t is None or t + 1 >= len(fb):
                return
            tm = hm(fb[t + 1]["time"])
            if tm not in pos or not (T_START <= tm < T_END):
                return
            sig.append(dict(date=d, tm=tm, d=int(c["dir"]), piv=float(c["px2"]), t=t, j=c["j"],
                            super=bool((c["c1"] is not None or c["c2"] is not None) and c["day"] is not None),
                            tese=label))

        if tese == "T1":
            if gat == "G1":
                if source == "p1":
                    for t_ in trig:
                        c = by[(t_["dir"], t_["j"])]
                        if c["day"] is None:
                            continue
                        sq = seq_at(t_["dir"], t_["idx"])
                        if not (t_["super"] or sq >= 2):
                            continue
                        e = pos.get(hm(fb[t_["idx"] + 1]["time"])) if t_["idx"] + 1 < len(fb) else None
                        ctx = nwe_ctx(D, e, t_["dir"], tick) if e is not None else None
                        if ctx is None or not (ctx["ext"] > EXT_NWE_G1 and ctx["slope"] > SLOPE_NWE_G1):
                            continue
                        push(c, t_["idx"], "T1")
                else:
                    for t_, s in trig_info:
                        c = by[(t_["dir"], t_["j"])]
                        if c["day"] is None:
                            continue
                        if not (t_["super"] or s > 1):
                            continue
                        e = pos.get(hm(fb[t_["idx"] + 1]["time"])) if t_["idx"] + 1 < len(fb) else None
                        ctx = nwe_ctx(D, e, t_["dir"], tick) if e is not None else None
                        if ctx is None or not (ctx["ext"] > EXT_NWE_G1 and ctx["slope"] > SLOPE_NWE_G1):
                            continue
                        push(c, t_["idx"], "T1")
            else:  # G2
                for c in cands:
                    if c["day"] is None:
                        continue
                    t = first_hit(fb, c, P, "G2")
                    if t is None:
                        continue
                    sup = (c["c1"] is not None or c["c2"] is not None)
                    if not (sup or seq_at(c["dir"], t) >= 2):
                        continue
                    if (hm(fb[t + 1]["time"]) if t + 1 < len(fb) else -1, c["dir"]) in e22_ent:
                        continue
                    push(c, t, "T1")
        elif tese == "T2":
            for c in cands:
                t = first_hit(fb, c, P, gat, D=D, pos=pos, tick=tick, levels=lv)
                if t is None:
                    continue
                if (hm(fb[t + 1]["time"]) if t + 1 < len(fb) else -1, c["dir"]) in e22_ent:
                    continue
                push(c, t, "T2")
        elif tese in ("T3A", "T3B"):
            for t_ in trig if gat == "G1" else []:
                c = by[(t_["dir"], t_["j"])]
                wall = c["c1"] is not None or c["c2"] is not None
                if tese == "T3A" and not wall:
                    continue
                e = pos.get(hm(fb[t_["idx"] + 1]["time"])) if t_["idx"] + 1 < len(fb) else None
                ctx = nwe_ctx(D, e, t_["dir"], tick) if e is not None else None
                if ctx is None or not (ctx["ext"] > EXT_NWE_G1 and ctx["slope"] > SLOPE_NWE_G1):
                    continue
                push(c, t_["idx"], tese)
            if gat == "G2":
                for c in cands:
                    wall = c["c1"] is not None or c["c2"] is not None
                    if tese == "T3A" and not wall:
                        continue
                    t = first_hit(fb, c, P, "G2")
                    push(c, t, tese)
    S = pd.DataFrame(sig)
    if len(S):
        S = S.sort_values(["date", "tm"]).drop_duplicates(["date", "tm", "d"])
    return S


def execute(asset, days, S, e22per, tp_mode, invert=False, cost_mult=1.0, slip_ticks=1, max_day=2, one_per_dir=False):
    rows = []
    if S is None or len(S) == 0:
        return pd.DataFrame(columns=["date", "tm", "xt", "brl", "pts", "d", "why"])
    for d, g in S.groupby("date"):
        x = days[d]
        D, lv = x["D"], x["lv"]
        busy = -1
        n_day = 0
        dirs = set()
        e22d = e22per.get(d, []) if asset == "WIN" else []
        for r in g.itertuples():
            if r.tm <= busy or n_day >= max_day:
                continue
            if one_per_dir and r.d in dirs:
                continue
            if not allowed_vs_e22(r.tm, r.d, e22d):
                continue
            e = D["pos"][r.tm]
            ep = float(D["o5"][e])
            res = plan_exit(asset, D, e, ep, r.d, r.piv, lv, tp_mode, cost_mult, slip_ticks)
            if res is None:
                continue
            if invert:
                dd = -r.d
                sl, tp_dist = res["sl"], abs(res["tp"] - ep)
                pts, xt, why = addon_sim(D, e, ep, dd, sl, ep + dd * tp_dist, TMAX, TICK[asset],
                                         COST[asset] * cost_mult, slip_ticks)
                res = dict(pts=pts, brl=pts * BRL[asset], xt=xt, why=why)
            rows.append(dict(date=d, tm=r.tm, xt=res["xt"], brl=res["brl"], pts=res["pts"], d=r.d, why=res["why"]))
            busy = res["xt"]
            n_day += 1
            dirs.add(r.d)
    return pd.DataFrame(rows)


def gate(st, p1, p3, inv, stress, corr, comb, e22_is):
    reasons = []
    if st["n_is"] < 40:
        reasons.append(f"N_IS {st['n_is']}<40")
    if st["pf_is"] < 1.35:
        reasons.append(f"PF_IS {st['pf_is']}<1,35")
    if st["rdd_is"] < 4.0:
        reasons.append(f"Ret/DD_IS {st['rdd_is']}<4")
    if not (st["h1"] > 0 and st["h2"] > 0):
        reasons.append("jan–abr ou mai–jul ≤ 0")
    if st["mon_is_pos"] < 5:
        reasons.append(f"meses+ IS {st['mon_is_pos']}/7")
    if p1 is not None and not (st["pf_is"] > p1["pf_is"] and st["rdd_is"] > p1["rdd_is"]):
        reasons.append("não supera P1")
    if p3 is not None and not (st["pf_is"] > p3["pf_is"] and st["rdd_is"] > p3["rdd_is"]):
        reasons.append("não supera P3")
    if inv is not None and inv["net_is"] >= 0:
        reasons.append("P2 (invertida) ≥ 0")
    if stress is not None and stress["pf_is"] <= 1.10:
        reasons.append(f"estresse PF_IS {stress['pf_is']}≤1,10")
    if corr is not None and corr == corr and corr > 0.35:
        reasons.append(f"corr {corr:.2f}>0,35")
    if comb is not None and e22_is is not None:
        dd_ok = comb["dd_is"] <= 1.15 * e22_is["dd_is"]
        rdd_ok = comb["rdd_is"] > e22_is["rdd_is"]
        if not (dd_ok or rdd_ok):
            reasons.append("carteira: DD +15% e Ret/DD não melhora")
    return reasons


def main():
    t0 = time.time()
    log = []

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        log.append(s)

    P("== carregando WIN ==")
    win, DSw = build_days("WIN")
    E22, e22per = e22_trades(win)
    P(f"WIN pregões {len(win)} · E22 produção {len(E22)} trades · R$ {E22.brl.sum():.0f}")
    st_e22 = stats_table(E22.rename(columns={}), "brl", "xt")
    P("E22", json.dumps({k: st_e22[k] for k in ("ops", "pf", "net", "dd", "rdd", "rdd_is", "rdd_oos", "meses")}, ensure_ascii=False))
    P("== WIN Walls deslocadas (P3) ==")
    win_sh, _ = build_days("WIN", shift=SHIFT["WIN"])
    E22sh, e22per_sh = e22_trades(win_sh)
    P("== carregando WDO ==")
    wdo, DSd = build_days("WDO")
    wdo_sh, _ = build_days("WDO", shift=SHIFT["WDO"])
    P(f"WDO pregões {len(wdo)}  ({time.time()-t0:.0f}s)")

    configs = []
    for tese, gats in (("T1", ("G1", "G2")), ("T2", ("G3", "G4"))):
        for g in gats:
            for tp in ("S2a", "S2b"):
                configs.append(("WIN", tese, g, tp))
    for tese in ("T3A", "T3B"):
        for g in ("G1", "G2"):
            for tp in ("S2a", "S2b"):
                configs.append(("WDO", tese, g, tp))

    name = {"T1": "ADD_WIN_EXT_REC", "T2": "ADD_WIN_REJ_NWE", "T3A": "ADD_WDO_V32_CORE·Wall", "T3B": "ADD_WDO_V32_CORE·Wall+Ext"}
    res = []
    trades_all = {}
    for asset, tese, g, tp in configs:
        days = win if asset == "WIN" else wdo
        days_sh = win_sh if asset == "WIN" else wdo_sh
        per = e22per if asset == "WIN" else {}
        per_sh = e22per_sh if asset == "WIN" else {}
        opd = tese == "T1"
        S = gen_signals(asset, days, per, tese, g)
        T = execute(asset, days, S, per, tp, one_per_dir=opd)
        st = stats_table(T)
        S1 = gen_signals(asset, days, per, tese, g, source="p1")
        p1 = stats_table(execute(asset, days, S1, per, tp, one_per_dir=opd))
        inv = stats_table(execute(asset, days, S, per, tp, invert=True, one_per_dir=opd))
        Ssh = gen_signals(asset, days_sh, per_sh, tese, g)
        p3 = stats_table(execute(asset, days_sh, Ssh, per_sh, tp, one_per_dir=opd))
        stress = stats_table(execute(asset, days, S, per, tp, cost_mult=2.0, slip_ticks=2, one_per_dir=opd))
        corr = daily_corr(T, E22) if asset == "WIN" else float("nan")
        comb = None
        if asset == "WIN" and len(T):
            C = pd.concat([E22[["date", "tm", "xt", "brl"]], T[["date", "tm", "xt", "brl"]]], ignore_index=True)
            comb = stats_table(C)
        same = 0
        if asset == "WIN" and len(T):
            for r in T.itertuples():
                for e in e22per.get(r.date, []):
                    if e["d"] == r.d and abs(e["tm"] - r.tm) <= 30:
                        same += 1
                        break
        fails = gate(st, p1, p3 if g != "G4" or True else None, inv, stress,
                     corr if asset == "WIN" else None, comb, st_e22 if asset == "WIN" else None)
        key = f"{asset}|{tese}|{g}|{tp}"
        trades_all[key] = T
        row = dict(key=key, asset=asset, setup=name[tese], tese=tese, gat=g, saida=tp, n_sinais=len(S),
                   **{f"r_{k}": v for k, v in st.items() if not isinstance(v, (bool, np.bool_))},
                   p1_pf_is=p1["pf_is"], p1_rdd_is=p1["rdd_is"], p1_n_is=p1["n_is"],
                   p2_net_is=inv["net_is"], p2_rdd_is=inv["rdd_is"],
                   p3_pf_is=p3["pf_is"], p3_rdd_is=p3["rdd_is"], p3_n_is=p3["n_is"],
                   st_pf_is=stress["pf_is"], st_rdd_is=stress["rdd_is"],
                   corr_e22=None if corr != corr else round(corr, 3), perto_e22_30min=same,
                   comb_rdd_is=comb["rdd_is"] if comb else None, comb_dd_is=comb["dd_is"] if comb else None,
                   comb_rdd=comb["rdd"] if comb else None, comb_net=comb["net"] if comb else None,
                   comb_rdd_oos=comb["rdd_oos"] if comb else None,
                   gate_ok=len(fails) == 0, gate_falhas="; ".join(fails))
        res.append(row)
        P(f"{key:28} N={st['ops']:3d} (IS {st['n_is']:3d} H1 {st['n_h1']} H2 {st['n_h2']} OOS {st['n_oos']}) "
          f"PF_IS={st['pf_is']} RDD_IS={st['rdd_is']} H1={st['h1']:.0f} H2={st['h2']:.0f} OOS={st['oos']:.0f} RDD_OOS={st['rdd_oos']} "
          f"| P1 {p1['pf_is']}/{p1['rdd_is']} P2 {inv['net_is']:.0f} P3 {p3['pf_is']}/{p3['rdd_is']} STRESS {stress['pf_is']} "
          f"corr {row['corr_e22']} | GATE {'OK' if not fails else 'X'} {'; '.join(fails)}")
    R = pd.DataFrame(res)
    R.to_csv(os.path.join(OUT, "grade.csv"), index=False)

    # walk-forward: escolhe o melhor por ativo em jan–abr, mede mai–jul (e reporta OOS)
    wf = []
    for asset in ("WIN", "WDO"):
        sub = R[R.asset == asset]
        if len(sub) == 0:
            continue
        best = sub.sort_values("r_rdd_h1", ascending=False).iloc[0]
        wf.append(dict(asset=asset, escolhido_jan_abr=best.key, rdd_jan_abr=best.r_rdd_h1, rdd_mai_jul=best.r_rdd_h2,
                       net_mai_jul=best.r_h2, rdd_oos_report=best.r_rdd_oos, n_h1=best.r_n_h1, n_h2=best.r_n_h2,
                       mediana_mai_jul=float(sub.r_rdd_h2.median()), positivos_mai_jul=f"{int((sub.r_h2>0).sum())}/{len(sub)}"))
        P("WF", json.dumps(wf[-1], ensure_ascii=False, default=float))
    pd.DataFrame(wf).to_csv(os.path.join(OUT, "walkforward.csv"), index=False)
    for k, T in trades_all.items():
        if len(T):
            T.assign(key=k).to_csv(os.path.join(OUT, "trades_" + k.replace("|", "_") + ".csv"), index=False)
    E22.to_csv(os.path.join(OUT, "e22_producao.csv"), index=False)
    json.dump(dict(e22=st_e22), open(os.path.join(OUT, "e22_stats.json"), "w"), default=float, indent=1)
    open(os.path.join(OUT, "avaliar.log"), "w", encoding="utf-8").write("\n".join(log))
    P(f"fim {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
