"""
Fase 2b + 3: escolha no IS (platô), gate invertido, placebo aleatório, OOS uma vez e carteira.
Regras congeladas em research/div_gate/PLANO.md (seção 6). O OOS só roda para gates aprovados no IS e
`results/oos_log.json` impede uma segunda execução.
Uso: python -m research.div_gate.select_oos [workers]
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import zlib
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.div_gate import bt_gate_grid as B  # noqa: E402

OUT = B.OUT
FULL_END = "2026-11-06"
MIN_IS_TRADES, GAIN, P_MAX, N_PLACEBO = 40, 1.2, 0.10, 200
ORD = {"N": (3, 6, 12), "k": (0.5, 1.0, 1.5), "L": (30, 50, 80, 100)}


def score(r):
    return float(r["ret_dd"]) if (r["ops"] >= MIN_IS_TRADES and r["net"] > 0) else 0.0


def plateau(G):
    """Mediana do score da combinação e das vizinhas de 1 parâmetro (N, k, R, L), mesmo modo, confirmação e filtro."""
    G = G.copy()
    G["score"] = G.apply(score, axis=1)
    idx = {}
    for i, r in G.iterrows():
        idx[(r["vid"], r["mode"], r["conf"], bool(r["flow"]), r["N"], r["k"], r["R"], r["L"])] = r["score"]
    radii = {v: sorted(G[G["vid"] == v]["R"].unique()) for v in G["vid"].unique()}
    pl = []
    for _, r in G.iterrows():
        vals = [r["score"]]
        base = dict(N=r["N"], k=r["k"], R=r["R"], L=r["L"])
        for p in ("N", "k", "R", "L"):
            seq = list(radii[r["vid"]]) if p == "R" else list(ORD[p])
            j = seq.index(base[p])
            for jj in (j - 1, j + 1):
                if 0 <= jj < len(seq):
                    nb = dict(base, **{p: seq[jj]})
                    key = (r["vid"], r["mode"], r["conf"], bool(r["flow"]), nb["N"], nb["k"], nb["R"], nb["L"])
                    if key in idx:
                        vals.append(idx[key])
        pl.append(float(np.median(vals)))
    G["plateau"] = pl
    return G


# ───────────── trabalhos IS (processo com corte em 01/08) ─────────────

def _job_is(job):
    from research.setup_parity.bt_32_slots import stats
    vid, spec, kind = job["vid"], dict(job["spec"]), job["kind"]
    if kind == "inverted":
        spec["inverted"] = True
        return job, stats(B.run_one(vid, spec, spec["flow"]))
    if kind == "rates":  # taxa de passagem do gate por (mês, direção), entre as consultas que passaram cobertura+fluxo
        from research.div_gate import gate as G
        from research.div_gate.versions import VERSIONS
        asset = VERSIONS[vid][0]
        g = G.make_gate(asset, (spec["k"], spec["R"], spec["L"], spec["conf"]), spec["N"], spec["mode"])
        cnt = defaultdict(lambda: [0, 0])

        def rec(d, t, s):
            ok = g(d, t, s)
            c = cnt[(str(d)[:7], int(s))]
            c[0] += 1
            c[1] += int(ok)
            return ok
        spec["placebo"] = rec
        B.run_one(vid, spec, spec["flow"])
        return job, {f"{m}|{s}": (v[1] / v[0]) for (m, s), v in cnt.items()}
    if kind == "placebo":
        rates, rep = job["rates"], job["rep"]

        def rnd(d, t, s):
            p = rates.get(f"{str(d)[:7]}|{int(s)}", 1.0)
            return (zlib.crc32(f"{rep}|{d}|{t}|{s}".encode()) / 4294967296.0) < p
        spec["placebo"] = rnd
        return job, stats(B.run_one(vid, spec, spec["flow"]))
    raise ValueError(kind)


# ───────────── trabalhos período inteiro (OOS) ─────────────

def _init_full():
    import pandas as pd_  # noqa: F401
    from core.setups_runner import _load_market, _window
    from research.flow_window_asg.flow_filters import load_flow_tables
    ctx = _window(B.START, FULL_END, None, None)
    ctx.__enter__()
    B._MK = _load_market()
    B._FT, _ = load_flow_tables("min")
    B.IS_END = FULL_END  # run_one filtra por [START, IS_END]; aqui = período inteiro


def _job_full(job):
    trs = B.run_one(job["vid"], job["spec"], job["flow"])
    return job, trs


def main(workers=6):
    from research.div_gate.versions import ELITE_8, VERSIONS
    from research.setup_parity.bt_32_slots import stats
    lock = os.path.join(OUT, "oos_log.json")
    if os.path.exists(lock):
        raise SystemExit(f"OOS já executado ({lock}). Não se roda o OOS duas vezes.")
    grid = pd.read_csv(os.path.join(OUT, "grid_is.csv"))
    base = grid[grid["kind"] != "GATE"].copy()
    base["score"] = base.apply(score, axis=1)
    G = plateau(grid[grid["kind"] == "GATE"])
    G.to_csv(os.path.join(OUT, "grid_is_plateau.csv"), index=False)

    # 1) melhor gate por versão (platô) e critério (a)
    sel = {}
    for vid in VERSIONS:
        b = base[base["vid"] == vid]
        b_best = float(b["score"].max()) if len(b) else 0.0
        g = G[G["vid"] == vid].sort_values(["plateau", "ops"], ascending=False)
        top = g.iloc[0]
        spec = dict(mode=top["mode"], N=int(top["N"]), k=float(top["k"]), R=float(top["R"]), L=int(top["L"]),
                    conf=str(top["conf"]), flow=bool(top["flow"]))
        crit_a = top["plateau"] > 0 and top["plateau"] >= GAIN * b_best
        sel[vid] = dict(spec=spec, plateau=float(top["plateau"]), point=float(top["score"]), is_ops=int(top["ops"]),
                        base_best=b_best, crit_a=bool(crit_a))
        print(f"{vid}: base RetDD {b_best:.2f} | gate {spec} platô {top['plateau']:.2f} ponto {top['score']:.2f} "
              f"({int(top['ops'])} tr) → (a) {'OK' if crit_a else 'não'}", flush=True)

    cand = [v for v in sel if sel[v]["crit_a"]]
    with mp.Pool(workers, initializer=B._init) as pool:
        # 2) invertido + taxas para o placebo
        jobs = [dict(vid=v, spec=sel[v]["spec"], kind=k) for v in cand for k in ("inverted", "rates")]
        for job, res in pool.imap_unordered(_job_is, jobs):
            if job["kind"] == "inverted":
                sel[job["vid"]]["inv_score"] = score(res)
                sel[job["vid"]]["inv_ops"] = res["ops"]
            else:
                sel[job["vid"]]["rates"] = res
        # 3) placebo
        jobs = [dict(vid=v, spec=sel[v]["spec"], kind="placebo", rep=r, rates=sel[v]["rates"])
                for v in cand for r in range(N_PLACEBO)]
        pl = defaultdict(list)
        for job, res in pool.imap_unordered(_job_is, jobs, chunksize=4):
            pl[job["vid"]].append(score(res))
    for v in cand:
        s = sel[v]
        s["placebo_p"] = (1 + sum(x >= s["point"] for x in pl[v])) / (1 + len(pl[v]))
        s["placebo_med"] = float(np.median(pl[v]))
        s["crit_b"] = s["placebo_p"] < P_MAX
        s["crit_c"] = s["inv_score"] < GAIN * s["base_best"]
        s["accepted_is"] = s["crit_b"] and s["crit_c"]
        print(f"{v}: invertido {s['inv_score']:.2f} · placebo mediana {s['placebo_med']:.2f} p={s['placebo_p']:.3f} "
              f"→ {'APROVADO NO IS' if s['accepted_is'] else 'reprovado'}", flush=True)
    acc = [v for v in sel if sel[v].get("accepted_is")]

    # 4) trava do OOS (antes de rodar)
    json.dump({"executed_at": datetime.now().isoformat(timespec="seconds"), "accepted_is": acc,
               "selection": {v: {k: x for k, x in s.items() if k != "rates"} for v, s in sel.items()}},
              open(lock, "w", encoding="utf-8"), indent=1, default=str)

    # 5) período inteiro: bases de todas as versões + gates aprovados
    jobs = []
    for v, (asset, fam, _, _, _, flt) in VERSIONS.items():
        jobs.append(dict(vid=v, col="sem_filtro", spec=None, flow=False))
        if flt:
            jobs.append(dict(vid=v, col="filtro_atual", spec=None, flow=True))
        if v in acc:
            jobs.append(dict(vid=v, col="gate", spec=sel[v]["spec"], flow=sel[v]["spec"]["flow"]))
    trades = {}
    with mp.Pool(workers, initializer=_init_full) as pool:
        for job, trs in pool.imap_unordered(_job_full, jobs):
            trades[(job["vid"], job["col"])] = trs

    rows, all_tr = [], []
    for (v, col), trs in sorted(trades.items()):
        s_is, s_oos = stats(trs, hi=B.IS_END), stats(trs, lo=B.IS_END)
        rows.append(dict(vid=v, family=VERSIONS[v][1], asset=VERSIONS[v][0], col=col,
                         gate=json.dumps(sel[v]["spec"]) if col == "gate" else "",
                         **{f"is_{k}": x for k, x in s_is.items()}, **{f"oos_{k}": x for k, x in s_oos.items()}))
        all_tr += [dict(t, vid=v, col=col) for t in trs]
    R = pd.DataFrame(rows)
    # aprovação OOS do gate
    for v in acc:
        g = R[(R.vid == v) & (R.col == "gate")].iloc[0]
        b = R[(R.vid == v) & (R.col.isin(["sem_filtro", "filtro_atual"]))]
        b_oos = float(b["oos_ret_dd"].max())
        n_pos, n_m = map(int, str(g["oos_pos_m"]).split("/"))
        ok = g["oos_pf"] >= 1.2 and g["oos_net"] > 0 and n_pos * 2 >= n_m and g["oos_ret_dd"] >= b_oos
        sel[v]["oos_ok"] = bool(ok)
        R.loc[(R.vid == v) & (R.col == "gate"), "oos_aprovado"] = ok
    R.to_csv(os.path.join(OUT, "oos_versions.csv"), index=False)
    T = pd.DataFrame(all_tr)
    T.to_csv(os.path.join(OUT, "oos_trades.csv"), index=False)

    # 6) carteira escolhida no IS (uma opção por família)
    pick = {}
    for fam, g in R.groupby("family"):
        g = g[(g.col != "gate") | (g.vid.isin(acc))]
        top = g.sort_values("is_ret_dd", ascending=False).iloc[0]
        if top["is_ret_dd"] >= 3 and top["is_pf"] >= 1.2:
            pick[fam] = (top["vid"], top["col"])
    port = [t for (v, c) in pick.values() for t in trades[(v, c)]]
    elite = [t for v in ELITE_8 for t in trades[(v, "sem_filtro")]]
    elite_g = [t for v in ELITE_8 for t in trades[(v, "gate" if (v, "gate") in trades else "sem_filtro")]]
    summ = {"carteira_IS": {f: list(x) for f, x in pick.items()},
            "carteira": {"is": stats(port, hi=B.IS_END), "oos": stats(port, lo=B.IS_END), "all": stats(port)},
            "elite8_sem_filtro": {"is": stats(elite, hi=B.IS_END), "oos": stats(elite, lo=B.IS_END), "all": stats(elite)},
            "elite8_com_gate_aprovado": {"is": stats(elite_g, hi=B.IS_END), "oos": stats(elite_g, lo=B.IS_END),
                                         "all": stats(elite_g)}}
    log = json.load(open(lock, encoding="utf-8"))
    log.update({"oos_result": {v: sel[v].get("oos_ok") for v in acc}, "portfolio": summ})
    json.dump(log, open(lock, "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(summ, indent=1, default=str))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
