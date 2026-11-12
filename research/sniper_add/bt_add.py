"""
Sniper 5176 corrigido (base B) + candidatas das versões do runner. Protocolo: research/sniper_add/PLANO.md.
Uso: python -m research.sniper_add.bt_add
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import research.flow_window_asg.inject_unified_div_opt2 as S  # noqa: E402
from research.audit_5176.audit_sniper import sniper  # noqa: E402

SPLIT, H1 = "2026-07-31", "2026-04-30"
OUT = os.path.join(ROOT, "research", "sniper_add", "results")
POOL = os.path.join(ROOT, "research", "sniper2", "results")
BASE_WIN = ("EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "EST_16", "WIN_E2")
BASE_WDO = ("WDO_01", "WDO_05", "WDO_07", "WDO_10")


def m2(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m


def stats(trs):
    if not trs:
        return dict(ops=0, wr=0, pf=0, net=0, dd=0, rdd=0, meses="0/0")
    trs = sorted(trs, key=lambda x: (x["date"], x["time"], x["exit_time"]))
    p = np.array([t["brl_1c"] for t in trs])
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    m = {}
    for t in trs:
        m[t["date"][:7]] = m.get(t["date"][:7], 0) + t["brl_1c"]
    return dict(ops=len(trs), wr=round(100 * float((p > 0).mean()), 1), pf=round(g / l, 2) if l else 99.0,
                net=round(float(eq[-1])), dd=round(dd), rdd=round(float(eq[-1]) / dd, 2) if dd else 99.0,
                meses=f"{sum(1 for v in m.values() if v > 0)}/{len(m)}")


def main():
    os.makedirs(OUT, exist_ok=True)
    p4 = json.load(open(os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json"), encoding="utf-8"))
    win_bars, nwe = S.load_mt5_win_bars_and_nwe30()
    win_lkp, vis_win, vis_wdo = S.build_win_3motor_and_visual_maps([d["date"] for d in p4["days"]])

    def ok3m(d, t, direction):
        info = win_lkp.get((d, m2(t) - 5)) or {}
        return info.get("bull_3motor" if direction == "COMPRA" else "bear_3motor", False)

    def sim_win(t, src):
        r = S.simulate_win_div_2lots_opt2([t], win_bars, nwe)
        return [dict(r[0], src=src)] if r else []

    # ---- base (idêntica à auditoria B) ----
    base_w, base_d, kw, kd = [], [], set(), set()
    for day in p4["days"]:
        d = day["date"]
        for t in day.get("trades", []):
            sid = t.get("strategy_id")
            key = (d, t["time"], t["direction"])
            if t.get("asset") == "WIN" and sid in BASE_WIN:
                if key not in kw and ok3m(d, t["time"], t["direction"]):
                    kw.add(key)
                    base_w += sim_win(t, "BASE")
            elif t.get("asset") == "WDO" and sid in BASE_WDO and key not in kd:
                kd.add(key)
                base_d.append(dict(t, src="BASE"))
    # chaves que já estão no pool da base (inclusive WIN reprovado no 3 motores, que continuaria reprovado)
    seen_w = {(t["date"], t["time"], t["direction"]) for day in p4["days"] for t in day.get("trades", [])
              if t.get("asset") == "WIN" and t.get("strategy_id") in BASE_WIN}

    # ---- candidatas ----
    cands = {}
    for asset, base_ids, seen in (("WIN", BASE_WIN, seen_w), ("WDO", BASE_WDO, kd)):
        for flow in (True, False):
            df = pd.read_csv(os.path.join(POOL, f"pool_{asset}{'_fluxo' if flow else ''}.csv"))
            for vid, g in df.groupby("vid"):
                if vid in base_ids and flow:
                    continue  # já é a base
                name = f"{vid}|{'com_fluxo' if flow else 'sem_fluxo'}"
                lst, ks = [], set()
                for r in g.itertuples(index=False):
                    dirn = "COMPRA" if r.direction == 1 else "VENDA"
                    key = (r.date, r.time, dirn)
                    if key in seen or key in ks:
                        continue
                    ks.add(key)
                    t = dict(date=r.date, time=r.time, direction=dirn, entry_price=float(r.entry_price), asset=asset,
                             strategy_id=vid, brl_1c=float(r.native_brl), exit_time=str(r.native_exit or "23:59"))
                    if asset == "WIN":
                        if ok3m(r.date, r.time, dirn):
                            lst += sim_win(t, name)
                    else:
                        lst.append(dict(t, src=name))
                cands[name] = (asset, lst)

    def portfolio(sel):
        w = list(base_w)
        dd = list(base_d)
        ks = {"WIN": set(), "WDO": set()}
        for name in sel:
            asset, lst = cands[name]
            tgt = w if asset == "WIN" else dd
            for t in lst:
                k = (t["date"], t["time"], t["direction"])
                if k not in ks[asset]:
                    ks[asset].add(k)
                    tgt.append(t)
        fw = sniper(w, vis_win, 2, True, "09:05", "16:45", [("12:00", "12:55")], 180.0)
        fd = sniper(dd, vis_wdo, 2, True, "09:00", "17:00", [("11:00", "11:55")], 120.0)
        return fw + fd

    def part(trs, a, b):
        return [t for t in trs if a < t["date"] <= b]

    base_all = portfolio([])
    base_is = stats(part(base_all, "", SPLIT))
    print("BASE total", stats(base_all), "| IS", base_is, "| OOS", stats(part(base_all, SPLIT, "9999")))

    # ---- tabela de cada candidata sozinha (IS) ----
    rows = []
    for name in sorted(cands):
        pf_ = portfolio([name])
        add = [t for t in pf_ if t["src"] == name]
        add_is = part(add, "", SPLIT)
        s_is = stats(part(pf_, "", SPLIT))
        rows.append(dict(cand=name, asset=cands[name][0], pool=len(cands[name][1]),
                         add_is_ops=len(add_is), add_is_pf=stats(add_is)["pf"], add_is_net=stats(add_is)["net"],
                         add_h1=stats(part(add, "", H1))["net"], add_h2=stats(part(add, H1, SPLIT))["net"],
                         cart_is_net=s_is["net"], cart_is_dd=s_is["dd"], cart_is_rdd=s_is["rdd"]))
    tab = pd.DataFrame(rows)
    tab["elegivel"] = (tab.add_is_ops >= 15) & (tab.add_is_pf >= 1.3) & (tab.add_h1 > 0) & (tab.add_h2 > 0)
    tab.to_csv(os.path.join(OUT, "candidatas_is.csv"), index=False)
    print(tab.sort_values("cart_is_rdd", ascending=False).to_string(index=False))

    # ---- seleção gulosa no IS ----
    elig = list(tab[tab.elegivel].cand)
    sel, cur = [], base_is
    while True:
        best = None
        for c in elig:
            if c in sel:
                continue
            trial = portfolio(sel + [c])
            add = [t for t in trial if t["src"] in sel + [c]]
            add_is = part(add, "", SPLIT)
            s = stats(part(trial, "", SPLIT))
            ok = (stats(add_is)["pf"] >= 1.3 and stats(part(add, "", H1))["net"] > 0
                  and stats(part(add, H1, SPLIT))["net"] > 0)
            if ok and s["rdd"] > cur["rdd"] and s["net"] > cur["net"] and (best is None or s["rdd"] > best[1]["rdd"]):
                best = (c, s)
        if best is None:
            break
        sel.append(best[0])
        cur = best[1]
        print("entra", best[0], "→ IS", cur)
    print("ESCOLHIDAS:", sel)

    # ---- OOS uma vez ----
    log = os.path.join(OUT, "oos_log.json")
    if os.path.exists(log):
        print("OOS já rodado:", open(log, encoding="utf-8").read())
        return
    fin = portfolio(sel)
    add = [t for t in fin if t["src"] != "BASE"]
    res = dict(escolhidas=sel,
               base=dict(IS=base_is, OOS=stats(part(base_all, SPLIT, "9999")), total=stats(base_all)),
               final=dict(IS=stats(part(fin, "", SPLIT)), OOS=stats(part(fin, SPLIT, "9999")), total=stats(fin)),
               acrescimo=dict(IS=stats(part(add, "", SPLIT)), OOS=stats(part(add, SPLIT, "9999")), total=stats(add)),
               por_candidata_oos={c: stats(part([t for t in fin if t["src"] == c], SPLIT, "9999")) for c in sel})
    json.dump(res, open(log, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    pd.DataFrame(fin).to_csv(os.path.join(OUT, "trades_final.csv"), index=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
