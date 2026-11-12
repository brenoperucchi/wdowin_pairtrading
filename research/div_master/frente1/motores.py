# -*- coding: utf-8 -*-
"""
Frente 1 do PLANO_UNIFICACAO_ROMPIMENTO_LIMITE.md — um motor só de divergência para o Sniper 5176 e o especialista.

A. Sniper (versão B corrigida: pool de setups, gate 3 motores no WIN, saída 2 lotes WIN, horários, meta diária) com o
   filtro de divergência vindo de cada motor: B (cache original e dataset), v3, v2.1, v3.1.
   Eixos: momento (conf = confirmação do pivô | trig = gatilho Opção C) · janela (1, 2, 3 barras; "ativo" 6/12 barras
   sem novo extremo além do F2) · âncora (sem | com a da regra nova).
B. Especialista (regra ESP_DIV_V21_WIN congelada: filtros, saída e gestão) com cada motor.
C. Carteira Sniper + especialista com o MESMO motor. Configuração do Sniper por motor escolhida pelo critério
   pré-registrado (PF > 1,3 em jan–abr, mai–jul e ago–nov; maior Ret/DD em jan–jul).
Uso: python research/div_master/frente1/motores.py → research/div_master/frente1/results/
"""
import json, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ESP = os.path.join(ROOT, "research", "div_master", "especialistas")
sys.path[:0] = [ROOT, ESP]
import numpy as np, pandas as pd

import research.flow_window_asg.inject_unified_div_opt2 as S  # noqa: E402
from research.sniper_add.bt_add import BASE_WDO, BASE_WIN, m2  # noqa: E402
from research.div_wall.data import load_asset  # noqa: E402
import modulo as M, bt, robust as R  # noqa: E402
from bt import mgmt  # noqa: E402

OUT = os.path.join(HERE, "results")
H1, IS_END = "2026-04-30", "2026-07-31"
PERIODS = (("jan–abr", "", H1), ("mai–jul", H1, IS_END), ("ago–nov", IS_END, "9999"), ("completo", "", "9999"))
SN = dict(WIN=("09:05", "16:45", [("12:00", "12:55")], 180.0), WDO=("09:00", "17:00", [("11:00", "11:55")], 120.0))
WINDOWS = (("tol", 1), ("tol", 2), ("tol", 3), ("ativo", 6), ("ativo", 12))


# ───────────────────────── métricas ─────────────────────────

def stats_brl(rows):
    """rows: lista de (date, t_in, t_out, brl). DD trade a trade na ordem de saída."""
    if not rows:
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, dd=0.0, rdd=0.0, meses="0/0")
    rows = sorted(rows, key=lambda x: (x[0], x[2], x[1]))
    p = np.array([r[3] for r in rows], float)
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mon = pd.Series(p).groupby([r[0][:7] for r in rows]).sum()
    return dict(ops=len(p), wr=round(100 * float((p > 0).mean()), 1), pf=round(float(g / l), 2) if l else 99.0,
                net=round(float(eq[-1])), dd=round(dd), rdd=round(float(eq[-1]) / dd, 2) if dd else 99.0,
                meses=f"{int((mon > 0).sum())}/{len(mon)}")


def by_period(rows):
    out = {}
    for lab, a, b in PERIODS:
        out[lab] = stats_brl([r for r in rows if a < r[0] <= b])
    return out


def ok_rule(per):
    return all(per[k]["pf"] > 1.3 and per[k]["ops"] > 0 for k in ("jan–abr", "mai–jul", "ago–nov"))


# ───────────────────────── Sniper ─────────────────────────

def sniper_pool():
    p4 = json.load(open(os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json"), encoding="utf-8"))
    win_bars, nwe = S.load_mt5_win_bars_and_nwe30()
    win_lkp, vis_win, vis_wdo = S.build_win_3motor_and_visual_maps([d["date"] for d in p4["days"]])

    def ok3m(d, t, direction):
        info = win_lkp.get((d, m2(t) - 5)) or {}
        return info.get("bull_3motor" if direction == "COMPRA" else "bear_3motor", False)

    base_w, base_d, kw, kd = [], [], set(), set()
    for day in p4["days"]:
        d = day["date"]
        for t in day.get("trades", []):
            sid, key = t.get("strategy_id"), (d, t["time"], t["direction"])
            if t.get("asset") == "WIN" and sid in BASE_WIN:
                if key not in kw and ok3m(d, t["time"], t["direction"]):
                    kw.add(key)
                    r = S.simulate_win_div_2lots_opt2([t], win_bars, nwe)
                    base_w += [r[0]] if r else []
            elif t.get("asset") == "WDO" and sid in BASE_WDO and key not in kd:
                kd.add(key)
                base_d.append(dict(t))
    return dict(WIN=base_w, WDO=base_d), dict(WIN=vis_win, WDO=vis_wdo)


def map_from_cache(vis, cache_bars):
    """Mapa do detector B original (cache) com preço do pivô para o modo 'ativo'."""
    return vis


def engine_map(asset, engine, moment, anchor):
    """{date: [(si, d, px2)], (date,'tmap'): {...}, (date,'lo'/'hi'): arrays} com sinais do motor no dataset."""
    mp = {}
    elig = "common" if anchor else "all"
    for d, (bars, walls, _) in load_asset(asset, "M5").items():
        mp[(d, "tmap")] = {b["time"]: i for i, b in enumerate(bars)}
        mp[(d, "lo")] = [b["low"] for b in bars]
        mp[(d, "hi")] = [b["high"] for b in bars]
        if engine == "B":
            fb = M.compute_flow([dict(b) for b in bars], asset)
            ad = [dict(b, smart_swing_wave=b["wave"], wyckoff_abs_bar=b["wyckoff_abs"], effective_force_bar=b["force"],
                       lot_urgency_bar=b["lot_urgency"], swing_impulse_3b=b["impulse3"]) for b in fb]
            ws = [w for w in walls if w.get("type") in M.LEVEL_TYPES]
            sg = S.detect_visual_swing_divergences(ad, ws, asset == "WIN")
            if anchor:
                sg = [s for s in sg if s.get("near_wall")]
            mp[d] = [(s["sig_idx"], s["dir"], float(s["pivot_px"])) for s in sg]
            continue
        _, Rr = M.run_day(asset, bars, walls, engines=(engine,), elig=elig)
        if moment == "conf":
            mp[d] = [(c["conf"], c["dir"], c["px2"]) for c in Rr[engine]["cands"]]
        else:
            by = {(c["dir"], c["j"]): c for c in Rr[engine]["cands"]}
            mp[d] = [(x["idx"], x["dir"], by[(x["dir"], x["j"])]["px2"]) for x in Rr[engine]["trig"]]
    return mp


def sniper_filter(trades, mp, win, asset):
    start, end, skip, cap = SN[asset]
    kind, n = win
    out = []
    for tr in trades:
        tmap = mp.get((tr["date"], "tmap"), {})
        bi = tmap.get(tr["time"])
        if bi is None:
            continue
        sd = 1 if tr["direction"] == "COMPRA" else -1
        lo_i = bi - n - 1 if kind == "tol" else bi - n
        ok = False
        for s in mp.get(tr["date"], []):
            si, dd_ = s[0], s[1]
            if dd_ != sd or not (lo_i <= si <= bi - 1):
                continue
            if kind == "ativo" and len(s) > 2:
                px = s[2]
                rng = range(si + 1, bi)
                if sd == 1 and any(mp[(tr["date"], "lo")][k] < px for k in rng):
                    continue
                if sd == -1 and any(mp[(tr["date"], "hi")][k] > px for k in rng):
                    continue
            ok = True
            break
        if ok:
            out.append(tr)
    acc, by = [], {}
    for tr in out:
        by.setdefault(tr["date"], []).append(tr)
    for d, arr in sorted(by.items()):
        day = []
        for tr in sorted(arr, key=lambda x: x["time"]):
            tm = tr["time"]
            if tm < start or tm > end or any(a <= tm <= b for a, b in skip):
                continue
            if sum(p["brl_1c"] for p in day if p.get("exit_time", "23:59") < tm) >= cap:
                continue
            day.append(tr)
        acc += day
    return acc


def rows_sniper(trs):
    return [(t["date"], t["time"], t.get("exit_time", "23:59"), float(t["brl_1c"])) for t in trs]


# ───────────────────────── especialista ─────────────────────────

def esp_signals(engine):
    if engine != "B":
        return bt.signals("WIN", engine)
    rows = []
    P = M.PARAMS["WIN"]
    for d, (bars, walls, _) in sorted(load_asset("WIN", "M5").items()):
        if d > bt.END:
            continue
        fb = M.compute_flow([dict(b) for b in bars], "WIN")
        ad = [dict(b, smart_swing_wave=b["wave"], wyckoff_abs_bar=b["wyckoff_abs"], effective_force_bar=b["force"],
                   lot_urgency_bar=b["lot_urgency"], swing_impulse_3b=b["impulse3"]) for b in fb]
        lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
        sg = S.detect_visual_swing_divergences(ad, [w for w in walls if w.get("type") in M.LEVEL_TYPES], True)
        cands = []
        for s in sg:
            i, dr, px = s["sig_idx"], s["dir"], float(s["pivot_px"])
            js = [k for k in range(max(0, i - 4), i + 1) if (fb[k]["low"] if dr == 1 else fb[k]["high"]) == px]
            if not js:
                continue
            j = js[-1]
            a = M.anchors(fb, j, dr, lv, P)
            if a["c1"] is None and a["c2"] is None and a["day"] is None:
                continue
            cands.append(dict(engine="B", dir=dr, j=j, k=j, conf=i, px1=px, px2=px, w1=0.0, w2=0.0, wd=1.0, thr=1.0,
                              c1=a["c1"], c2=a["c2"], day=a["day"], time_j=fb[j]["time"], time_conf=fb[i]["time"],
                              micro=True))
        tr, _ = M.triggers(fb, cands, P)
        by = {(c["dir"], c["j"]): c for c in cands}
        seq = {1: 0, -1: 0}
        for x in tr:
            t = x["idx"]
            if t + 1 >= len(fb):
                continue
            c = by[(x["dir"], x["j"])]
            rows.append(dict(date=d, engine="B", esp=x["esp"], sub=x["sub"], dir=x["dir"], j=x["j"], t=t, k=c["k"],
                             conf=c["conf"], time_in=fb[t + 1]["time"], lag=x["lag"], dup=x["dup"], super=x["super"],
                             piv=c["px2"], wd_ratio=np.nan, seq=seq[x["dir"]], c1=c["c1"], c2=c["c2"], levels=lv,
                             open0=fb[0]["open"], sig_c=fb[t]["close"], sig_h=fb[t]["high"], sig_l=fb[t]["low"],
                             sig_o=fb[t]["open"]))
            seq[x["dir"]] += 1
    return pd.DataFrame(rows)


def esp_rows(engine, DS):
    T = R.run_exit(bt.simulate("WIN", esp_signals(engine), DS, exits=()), DS)
    _, q = R.evaluate(T)
    return [(r.date, r.time_in, f"{int(r.xt_X) // 60:02d}:{int(r.xt_X) % 60:02d}", 2.0 * float(r.pnl_X))
            for r in q.itertuples()]


# ───────────────────────── main ─────────────────────────

def main():
    os.makedirs(OUT, exist_ok=True)
    pool, vis = sniper_pool()
    print("pool de setups: WIN", len(pool["WIN"]), "WDO", len(pool["WDO"]), flush=True)
    rows, keep = [], {}
    # base exata (detector B do cache, janela 2) — deve reproduzir 287 trades / R$ 7.436
    base = {a: sniper_filter(pool[a], vis[a], ("tol", 2), a) for a in ("WIN", "WDO")}
    b_all = rows_sniper(base["WIN"] + base["WDO"])
    print("reprodução da base:", stats_brl(b_all), flush=True)
    configs = [("B-cache", "conf", False)]
    for e in ("B", "v3", "v2.1", "v3.1"):
        configs.append((e, "conf", False))
        configs.append((e, "conf", True))
        if e != "B":
            configs.append((e, "trig", True))
    maps = {}
    for e, mom, anc in configs:
        for a in ("WIN", "WDO"):
            maps[(e, mom, anc, a)] = vis[a] if e == "B-cache" else engine_map(a, e, mom, anc)
        print("mapa pronto:", e, mom, "âncora" if anc else "sem âncora", flush=True)
    for (e, mom, anc) in configs:
        for win in WINDOWS:
            if e == "B-cache" and win[0] == "ativo":
                continue
            trs = {a: sniper_filter(pool[a], maps[(e, mom, anc, a)], win, a) for a in ("WIN", "WDO")}
            for lab, rr in (("WIN", rows_sniper(trs["WIN"])), ("WDO", rows_sniper(trs["WDO"])),
                            ("Sniper", rows_sniper(trs["WIN"] + trs["WDO"]))):
                per = by_period(rr)
                rows.append(dict(parte="A_sniper", motor=e, momento=mom, ancora=anc, janela=f"{win[0]}{win[1]}", ativo=lab,
                                 **{f"{p}_{k}": v for p, s in per.items() for k, v in s.items()}))
            keep[(e, mom, anc, f"{win[0]}{win[1]}")] = rows_sniper(trs["WIN"] + trs["WDO"])
    A = pd.DataFrame(rows)
    A.to_csv(os.path.join(OUT, "A_sniper_motores.csv"), index=False)
    # B: especialista com cada motor
    DS = bt.market("WIN")
    esp = {}
    rowsB = []
    for e in ("B", "v3", "v2.1", "v3.1"):
        esp[e] = esp_rows(e, DS)
        per = by_period(esp[e])
        rowsB.append(dict(parte="B_especialista", motor=e, **{f"{p}_{k}": v for p, s in per.items() for k, v in s.items()}))
        print("especialista", e, per["completo"], flush=True)
    Bdf = pd.DataFrame(rowsB)
    Bdf.to_csv(os.path.join(OUT, "B_especialista_motores.csv"), index=False)
    # C: carteira com o mesmo motor
    rowsC = []
    S_ = A[A.ativo == "Sniper"].copy()
    for e in ("B", "v3", "v2.1", "v3.1"):
        cand = S_[S_.motor == e].copy()
        cand["ok"] = [ok_rule({p: {"pf": r[f"{p}_pf"], "ops": r[f"{p}_ops"]} for p in ("jan–abr", "mai–jul", "ago–nov")})
                      for _, r in cand.iterrows()]
        is_rdd = []
        for _, r in cand.iterrows():
            rr = keep[(e, r.momento, r.ancora, r.janela)]
            is_rdd.append(stats_brl([x for x in rr if x[0] <= IS_END])["rdd"])
        cand["rdd_jan_jul"] = is_rdd
        pick = cand.sort_values(["ok", "rdd_jan_jul"], ascending=False).iloc[0]
        sn = keep[(e, pick.momento, pick.ancora, pick.janela)]
        per_s, per_e, per_c = by_period(sn), by_period(esp[e]), by_period(sn + esp[e])
        dly = pd.DataFrame(sn, columns=["date", "a", "b", "s"]).groupby("date").s.sum().rename("sn").to_frame().join(
            pd.DataFrame(esp[e], columns=["date", "a", "b", "e"]).groupby("date").e.sum(), how="outer").fillna(0)
        espok = ok_rule({p: per_e[p] for p in ("jan–abr", "mai–jul", "ago–nov")})
        rowsC.append(dict(motor=e, sniper_cfg=f"{pick.momento}|{'âncora' if pick.ancora else 'sem âncora'}|{pick.janela}",
                          sniper_ok=bool(pick.ok), esp_ok=espok, corr=round(float(dly.corr().iloc[0, 1]), 2),
                          **{f"S_{p}_{k}": v for p, s in per_s.items() for k, v in s.items() if k in ("ops", "pf", "net", "dd", "rdd")},
                          **{f"E_{p}_{k}": v for p, s in per_e.items() for k, v in s.items() if k in ("ops", "pf", "net", "dd", "rdd")},
                          **{f"C_{p}_{k}": v for p, s in per_c.items() for k, v in s.items() if k in ("ops", "pf", "net", "dd", "rdd", "meses")}))
        json.dump({"sniper": sn, "esp": esp[e]}, open(os.path.join(OUT, f"trades_{e.replace('.', '')}.json"), "w"))
    C = pd.DataFrame(rowsC)
    C.to_csv(os.path.join(OUT, "C_carteira_motores.csv"), index=False)
    pd.set_option("display.width", 260)
    cols = ["motor", "momento", "ancora", "janela", "completo_ops", "completo_pf", "completo_net", "completo_dd",
            "completo_rdd", "jan–abr_pf", "mai–jul_pf", "ago–nov_pf", "completo_meses"]
    print("\nA) Sniper (WIN+WDO) por motor:")
    print(A[A.ativo == "Sniper"][cols].to_string(index=False))
    print("\nB) Especialista por motor:")
    print(Bdf[["motor", "completo_ops", "completo_pf", "completo_net", "completo_dd", "completo_rdd", "jan–abr_pf",
               "mai–jul_pf", "ago–nov_pf", "completo_meses"]].to_string(index=False))
    print("\nC) Carteira com o mesmo motor:")
    print(C[["motor", "sniper_cfg", "sniper_ok", "esp_ok", "corr", "S_completo_rdd", "E_completo_rdd", "C_completo_ops",
             "C_completo_net", "C_completo_dd", "C_completo_rdd", "C_completo_meses", "C_jan–abr_pf", "C_mai–jul_pf",
             "C_ago–nov_pf"]].to_string(index=False))


if __name__ == "__main__":
    main()
