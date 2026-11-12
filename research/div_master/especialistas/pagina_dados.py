# -*- coding: utf-8 -*-
"""Dados da página de resultados: curvas de capital (regra nova 2c WIN + Sniper 5176 corrigido) e exemplos reais de
entrada/saída da regra ESP_DIV_V21_WIN com o caminho do trade reconstruído tick a tick (mesma lógica de bt.sim)."""
import json, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import bt, modulo as M, robust as R
from research.div_wall.data import load_asset

ROOT = M.ROOT


def replay(D, e, ep, d, sl=200.0, be=(180.0, 20.0), tmax=12, tick=5.0):
    """Cópia de bt.sim (sem alvo) que registra o caminho: ativação do BE e motivo da saída."""
    stop, mfe, be_at = ep - d * sl, 0.0, None
    for k in range(e, len(D["o5"])):
        if k > e:
            if D["tm5"][k] >= 1045:
                return dict(k=k, px=float(D["o5"][k]), why="17:25", be_k=be_at, stop=stop)
            if k - e > tmax:
                return dict(k=k, px=float(D["o5"][k]), why="TEMPO", be_k=be_at, stop=stop)
            if mfe >= be[0]:
                cand = ep + d * be[1]
                if (D["o5"][k] - cand) * d > 0 and (cand - stop) * d > 0:
                    stop, be_at = cand, k
        nt = D["nn"][k] if D["fb"][k] == 0 else 4
        for j in range(nt):
            p, op = bt._tick(D["px"], D["op"], D["off"], D["fb"], D["o5"], D["h5"], D["l5"], D["c5"], k, j, d)
            if (p - stop) * d <= 0:
                return dict(k=k, px=float(p if op else stop - d * tick), why="BE" if be_at is not None else "STOP",
                            be_k=be_at, stop=stop)
            mfe = max(mfe, (p - ep) * d)
    k = len(D["o5"]) - 1
    return dict(k=k, px=float(D["c5"][k]), why="FIM", be_k=be_at, stop=stop)


def curves():
    s = pd.read_csv(os.path.join(ROOT, "research", "sniper_v3", "results", "trades.csv"))
    s = s[(s.detector == "antigo (atual)") & (s.tol == 2) & (s.date <= bt.END)]
    n = pd.read_csv(os.path.join(HERE, "results", "trades_escolhida.csv"))
    n["brl"] = n.pnl_X * 2
    n["t_out"] = [f"{int(x) // 60:02d}:{int(x) % 60:02d}" for x in n.xt_X]
    A = pd.concat([
        pd.DataFrame(dict(date=n.date, t_in=n.time_in, t_out=n.t_out, brl=n.brl, strat="ESP_DIV_V21_WIN", esp=n.esp)),
        pd.DataFrame(dict(date=s.date, t_in=s.time, t_out=s.exit_time, brl=s.brl_1c, strat=s.asset + "_DIV_WALL", esp="")),
    ], ignore_index=True).sort_values(["date", "t_out", "t_in"]).reset_index(drop=True)
    days = sorted(A.date.unique())
    series = {}
    groups = {"PORTFOLIO": A, "ESP_DIV_V21_WIN": A[A.strat == "ESP_DIV_V21_WIN"],
              "WIN_DIV_WALL": A[A.strat == "WIN_DIV_WALL"], "WDO_DIV_WALL": A[A.strat == "WDO_DIV_WALL"],
              "V21_WALL": A[(A.strat == "ESP_DIV_V21_WIN") & (A.esp == "WALL")],
              "V21_EXTREMO": A[(A.strat == "ESP_DIV_V21_WIN") & (A.esp == "EXTREMO")]}
    stats = {}
    for k, g in groups.items():
        dd_ = g.groupby("date").brl.sum().reindex(days, fill_value=0.0)
        eq = dd_.cumsum()
        series[k] = [round(float(v), 2) for v in eq.values]
        p = g.brl.values
        e = np.cumsum(p)
        mdd = float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e))
        gl, ls = p[p > 0].sum(), -p[p < 0].sum()
        mon = g.groupby(g.date.str[:7]).brl.sum()
        isv = (g.date <= bt.IS_END).values
        stats[k] = dict(n=int(len(p)), wr=round(100 * float((p > 0).mean()), 1), pf=round(float(gl / ls), 2),
                        net=round(float(e[-1])), dd=round(mdd), rdd=round(float(e[-1]) / mdd, 2),
                        mpos=f"{int((mon > 0).sum())}/{len(mon)}", net_is=round(float(p[isv].sum())),
                        net_oos=round(float(p[~isv].sum())),
                        months={m: round(float(v)) for m, v in mon.items()})
    peq = np.array(series["PORTFOLIO"])
    series["PORTFOLIO_DD"] = [round(float(v), 2) for v in (peq - np.maximum.accumulate(np.r_[0, peq])[1:])]
    daily = A.pivot_table(index="date", columns="strat", values="brl", aggfunc="sum").fillna(0)
    corr = daily.corr().round(2)
    return dict(days=days, series=series, stats=stats,
                corr={a: {b: float(corr.loc[a, b]) for b in corr.columns} for a in corr.index})


def examples():
    DS = R.bt.market("WIN")
    S = bt.signals("WIN", "v2.1")
    T = R.run_exit(bt.simulate("WIN", S, DS, exits=()), DS)
    _, q = R.evaluate(T)
    data = load_asset("WIN", "M5")
    rows = []
    for r in q.itertuples():
        D = DS[r.date]
        rp = replay(D, int(r.e), r.ep, r.dir)
        pts = (rp["px"] - r.ep) * r.dir
        brl = (pts - 10.0) * 0.2
        assert abs(brl - getattr(r, "pnl_X")) < 1e-6, (r.date, r.time_in, brl, r.pnl_X)
        rows.append((r, rp, brl))
    print("replay confere com o backtest em", len(rows), "trades")
    whys = pd.Series([x[1]["why"] for x in rows]).value_counts().to_dict()

    def pick(cond):
        c = [x for x in rows if cond(x)]
        return c

    chosen = []
    best = sorted(pick(lambda x: x[1]["why"] == "TEMPO" and x[1]["be_k"] is not None and x[0].esp == "WALL"),
                  key=lambda x: -x[2])
    chosen.append(("Ganho: BE armado e saída por tempo", best[min(3, len(best) - 1)]))
    st = sorted(pick(lambda x: x[1]["why"] == "STOP" and x[0].esp == "WALL"), key=lambda x: x[0].date)
    chosen.append(("Perda: stop de 200 pts", st[len(st) // 2]))
    be = sorted(pick(lambda x: x[1]["why"] == "BE"), key=lambda x: x[0].date)
    chosen.append(("Empate: BE devolve +20 pts", be[len(be) // 2]))
    ex = sorted(pick(lambda x: x[0].esp == "EXTREMO" and x[2] > 0), key=lambda x: -x[2])
    chosen.append(("EXTREMO: nova mínima/máxima do dia", ex[min(2, len(ex) - 1)]))
    out = []
    for title, (r, rp, brl) in chosen:
        bars, walls, _ = data[r.date]
        fb = M.compute_flow([dict(b) for b in bars], "WIN")
        tmap = {b["time"]: i for i, b in enumerate(bars)}
        D = DS[r.date]
        e, k_out = int(r.e), rp["k"]
        f1 = int(r.k) if hasattr(r, "k") else None
        lo_i = max(0, min(f1 if f1 is not None else r.j, r.j) - 4)
        t_lo = bars[lo_i]["time"]
        t_hi = f"{int(D['tm5'][min(k_out + 3, len(D['tm5']) - 1)]) // 60:02d}:{int(D['tm5'][min(k_out + 3, len(D['tm5']) - 1)]) % 60:02d}"
        cand = [i for i, t in enumerate(D["tm5"]) if bt.hm(t_lo) <= t <= bt.hm(t_hi)]
        b5 = [dict(t=f"{int(D['tm5'][i]) // 60:02d}:{int(D['tm5'][i]) % 60:02d}", o=float(D["o5"][i]), h=float(D["h5"][i]),
                   l=float(D["l5"][i]), c=float(D["c5"][i]), c50=float(D["c50"][i]), u50=float(D["u50"][i]),
                   l50=float(D["l50"][i])) for i in cand]
        wave = {b["time"]: float(b["wave"]) for b in fb if bt.hm(t_lo) <= bt.hm(b["time"]) <= bt.hm(t_hi)}
        pmin, pmax = min(x["l"] for x in b5), max(x["h"] for x in b5)
        lv = [dict(type=w["type"], price=float(w["price"])) for w in walls if w.get("type") in M.LEVEL_TYPES
              and pmin - 400 <= float(w["price"]) <= pmax + 400]
        tt = lambda i: f"{int(D['tm5'][i]) // 60:02d}:{int(D['tm5'][i]) % 60:02d}"
        out.append(dict(
            title=title, date=r.date, dir=int(r.dir), esp=r.esp, sub=r.sub, bars=b5, wave=wave, levels=lv,
            f1=dict(t=bars[int(r.k)]["time"], px=float(bars[int(r.k)]["low" if r.dir == 1 else "high"]),
                    w=float(fb[int(r.k)]["wave"])),
            f2=dict(t=bars[int(r.j)]["time"], px=float(r.piv), w=float(fb[int(r.j)]["wave"])),
            conf_t=bars[int(r.conf)]["time"] if hasattr(r, "conf") else None,
            trig=dict(t=bars[int(r.t)]["time"], c=float(bars[int(r.t)]["close"])),
            entry=dict(t=tt(e), px=float(r.ep)), sl=float(r.ep - r.dir * 200.0),
            be=dict(t=tt(rp["be_k"]) if rp["be_k"] is not None else None, px=float(r.ep + r.dir * 20.0),
                    trig_px=float(r.ep + r.dir * 180.0)),
            exit=dict(t=tt(k_out), px=rp["px"], why=rp["why"], tmax_t=tt(min(e + 13, len(D["tm5"]) - 1))),
            pts=round((rp["px"] - r.ep) * r.dir), brl2=round(brl * 2, 2),
            ctx=dict(ext50=round(float(r.ext50), 2), slope50=round(float(r.slope50), 2), seq=int(r.seq), lag=int(r.lag),
                     wd_ratio=round(float(r.wd_ratio), 1))))
    return out, whys


if __name__ == "__main__":
    C = curves()
    for k, v in C["stats"].items():
        print(k, {a: b for a, b in v.items() if a != "months"})
    print(C["corr"])
    X, whys = examples()
    print("motivos de saída:", whys)
    for x in X:
        print(x["title"], x["date"], x["entry"], x["exit"], x["pts"], x["brl2"], x["f1"]["t"], x["f2"]["t"], x["trig"]["t"])
    json.dump(dict(curves=C, examples=X, exit_reasons=whys), open(os.path.join(HERE, "results", "pagina.json"), "w",
                                                                  encoding="utf-8"), ensure_ascii=False)
