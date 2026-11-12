"""
Painel "só divergência": toda estratégia entra apenas com divergência v2 na Wall (modo EXIGIR).
1. Por família, a melhor regra EXIGIR pelo platô do IS (`grid_is_plateau.csv`); exige platô > 0 (≥ 40 trades IS e lucro).
2. Combinação escolhida SÓ no IS: seleção gulosa que soma a estratégia que mais aumenta o Ret/DD da carteira,
   até nenhuma aumentar.
3. OOS (ago–6/nov) uma vez, travado em `results/oos_log_portfolio_div.json`.
Uso: python -m research.div_gate.portfolio_div [workers]
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.div_gate import bt_gate_grid as B  # noqa: E402
from research.div_gate import select_oos as SO  # noqa: E402

OUT = B.OUT
LOCK = os.path.join(OUT, "oos_log_portfolio_div.json")


def candidates():
    G = pd.read_csv(os.path.join(OUT, "grid_is_plateau.csv"))
    E = G[(G["mode"] == "EXIGIR") & (G["plateau"] > 0)]
    best = {}
    for vid, g in E.groupby("vid"):
        t = g.sort_values(["plateau", "ops"], ascending=False).iloc[0]
        if t["family"] not in best or t["plateau"] > best[t["family"]]["plateau"]:
            best[t["family"]] = dict(vid=vid, plateau=float(t["plateau"]),
                                     spec=dict(mode="EXIGIR", N=int(t["N"]), k=float(t["k"]), R=float(t["R"]),
                                               L=int(t["L"]), conf=str(t["conf"]), flow=bool(t["flow"])))
    return {b["vid"]: b for b in best.values()}


def _job(job):
    return job["vid"], B.run_one(job["vid"], job["spec"], job["spec"]["flow"])


def greedy(trs_by, stats, hi=None):
    chosen, cur = [], -1e9
    while True:
        best = None
        for v in trs_by:
            if v in chosen:
                continue
            s = stats([t for x in chosen + [v] for t in trs_by[x]], hi=hi)["ret_dd"]
            if best is None or s > best[1]:
                best = (v, s)
        if best is None or best[1] <= cur:
            return chosen, cur
        chosen.append(best[0])
        cur = best[1]
        print(f"  + {best[0]:10s} → Ret/DD IS da carteira {cur:.2f}", flush=True)


def main(workers=6):
    from research.div_gate.versions import ELITE_8
    from research.setup_parity.bt_32_slots import stats
    if os.path.exists(LOCK):
        raise SystemExit(f"OOS desta carteira já executado ({LOCK}).")
    C = candidates()
    print(f"{len(C)} candidatas:", ", ".join(C))
    with mp.Pool(workers, initializer=B._init) as pool:
        is_tr = dict(pool.imap_unordered(_job, [dict(vid=v, spec=c["spec"]) for v, c in C.items()]))
    chosen, rd = greedy(is_tr, stats)
    json.dump({"executed_at": datetime.now().isoformat(timespec="seconds"), "candidates": C,
               "chosen_is": chosen, "is_ret_dd": rd}, open(LOCK, "w", encoding="utf-8"), indent=1)

    jobs = [dict(vid=v, spec=c["spec"]) for v, c in C.items()]
    with mp.Pool(workers, initializer=SO._init_full) as pool:
        full = dict(pool.imap_unordered(_job, jobs))
    oos = pd.read_csv(os.path.join(OUT, "oos_trades.csv"))
    elite = oos[(oos["col"] == "sem_filtro") & (oos["vid"].isin(ELITE_8))].to_dict("records")

    rows = []
    for v in C:
        s_is, s_oos = stats(full[v], hi=B.IS_END), stats(full[v], lo=B.IS_END)
        rows.append(dict(vid=v, na_carteira=v in chosen, regra=json.dumps(C[v]["spec"]),
                         **{f"is_{k}": x for k, x in s_is.items()}, **{f"oos_{k}": x for k, x in s_oos.items()}))
    R = pd.DataFrame(rows).sort_values(["na_carteira", "is_ret_dd"], ascending=False)
    R.to_csv(os.path.join(OUT, "portfolio_div_versions.csv"), index=False)
    pd.DataFrame([dict(t, vid=v) for v in C for t in full[v]]).to_csv(
        os.path.join(OUT, "portfolio_div_trades.csv"), index=False)

    def block(trs):
        return {"is": stats(trs, hi=B.IS_END), "oos": stats(trs, lo=B.IS_END), "all": stats(trs)}
    summ = {"carteira_div_escolhida": block([t for v in chosen for t in full[v]]),
            "todas_candidatas_div": block([t for v in C for t in full[v]]),
            "elite8_sem_filtro": block(elite)}
    log = json.load(open(LOCK, encoding="utf-8"))
    log["result"] = summ
    json.dump(log, open(LOCK, "w", encoding="utf-8"), indent=1)
    with pd.option_context("display.width", 250):
        print(R[["vid", "na_carteira", "is_ops", "is_pf", "is_net", "is_mdd", "is_ret_dd",
                 "oos_ops", "oos_wr", "oos_pf", "oos_net", "oos_mdd", "oos_ret_dd", "oos_pos_m"]].to_string(index=False))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
