"""
Pool de entradas do Sniper v2: as 31 versões de research/div_gate/versions.py pelo runner, sem filtro de fluxo,
nos dias cobertos pelo dataset div_wall_v1 (período inteiro; o IS/OOS é separado depois).
Saída: research/sniper2/results/pool_{WIN,WDO}.csv
Uso: python -m research.sniper2.build_pool
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.div_gate import bt_gate_grid as B  # noqa: E402
from research.div_gate import select_oos as SO  # noqa: E402

OUT = os.path.join(ROOT, "research", "sniper2", "results")


def _job(args):
    vid, flow = args
    return (vid, flow), B.run_one(vid, None, flow)


def main():
    from research.div_gate.versions import VERSIONS
    os.makedirs(OUT, exist_ok=True)
    order = list(VERSIONS)
    with mp.Pool(6, initializer=SO._init_full) as pool:
        res = dict(pool.imap_unordered(_job, [(v, f) for v in order for f in (False, True)]))
    for asset, flow in (("WIN", False), ("WDO", False), ("WIN", True), ("WDO", True)):
        rows, seen = [], set()
        for prio, vid in enumerate(order):
            if VERSIONS[vid][0] != asset:
                continue
            for t in res[(vid, flow)]:
                key = (t["date"], t["time"], t["direction"])
                dup = key in seen
                seen.add(key)
                rows.append(dict(date=t["date"], time=t["time"], direction=1 if t["direction"] == "COMPRA" else -1,
                                 entry_price=float(t["entry_price"]), native_brl=float(t["brl_1c"]),
                                 native_exit=t.get("exit_time", ""), vid=vid, prio=prio, dup=dup))
        df = pd.DataFrame(rows)
        df.to_csv(os.path.join(OUT, f"pool_{asset}{'_fluxo' if flow else ''}.csv"), index=False)
        u = df[~df.dup]
        print(f"{asset} {'com fluxo' if flow else 'sem fluxo'}: {len(df)} trades das versões → {len(u)} entradas únicas "
              f"(IS {int((u.date <= '2026-07-31').sum())} · OOS {int((u.date > '2026-07-31').sum())})")


if __name__ == "__main__":
    main()
