# -*- coding: utf-8 -*-
"""
Paridade das 4 novas estratégias em `core/carteira_v32_estrategias.py` × pesquisa auditada
(`sim_portfolio_4_estrategias.py`: C1a_BRK_WIN, V1a_DIV_WDO, SYM_DIV_WIN, SYM_DIV_WDO)
+ Teste de causalidade estrita barra a barra (como o motor ao vivo vê o pregão).

Uso: python research/div_master/carteira_v22/paridade_4_estrategias.py
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas")]

import numpy as np
import pandas as pd

import bt  # noqa: E402
import modulo as M  # noqa: E402
from core import carteira_v32_estrategias as C32  # noqa: E402
from research.div_wall.data import load_asset  # noqa: E402
from research.div_master.sim_portfolio_4_estrategias import build_strategies  # noqa: E402


def exec_bars(D: dict) -> list[dict]:
    n = len(D["o5"])
    out = []
    for k in range(n):
        out.append(
            {
                "time": f"{int(D['tm5'][k]) // 60:02d}:{int(D['tm5'][k]) % 60:02d}",
                "open": float(D["o5"][k]),
                "high": float(D["h5"][k]),
                "low": float(D["l5"][k]),
                "close": float(D["c5"][k]),
                "nwe30_upper": float(D["u30"][k + 1]) if k + 1 < n else float(D["u30"][k]),
                "nwe30_lower": float(D["l30"][k + 1]) if k + 1 < n else float(D["l30"][k]),
                "nwe50_line": float(D["c50"][k + 1]) if k + 1 < n else float(D["c50"][k]),
                "nwe50_upper": float(D["u50"][k + 1]) if k + 1 < n else float(D["u50"][k]),
                "nwe50_prev_line": float(D["c50"][0]) if k == 0 else None,
            }
        )
    return out


def day_inputs(DS: dict, data: dict, asset: str, d: str):
    bars, walls, _ = data[d]
    fb = M.compute_flow([dict(b) for b in bars], asset)
    return fb, walls, exec_bars(DS[d])


def _stats_list(rows: list[dict]) -> dict:
    if not rows:
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, dd=0.0, rdd=0.0)
    df = pd.DataFrame(rows).sort_values(["date", "exit_time", "time"])
    p = df["brl_1c"].values.astype(float)
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0.0, eq])[1:] - eq))
    g, l = float(p[p > 0].sum()), float(-p[p < 0].sum())
    net = float(p.sum())
    return dict(
        ops=len(p),
        wr=round(100.0 * float((p > 0).mean()), 1),
        pf=round(g / l if l > 0 else 99.9, 2),
        net=round(net, 0),
        dd=round(dd, 0),
        rdd=round(net / dd if dd > 0 else 0.0, 2),
    )


def main(check_live_days: int = 8) -> None:
    print("Carregando referência da pesquisa (M1 tick-a-tick)...")
    ref_map = build_strategies()
    ref_dfs = {
        "C1a_BRK_WIN": ref_map["C1a_WIN"],
        "V1a_DIV_WDO": ref_map["V1a_WDO"],
        "SYM_DIV_WIN": ref_map["SYM_WIN"],
        "SYM_DIV_WDO": ref_map["SYM_WDO"],
    }

    DS_map = {"WIN": bt.market("WIN"), "WDO": bt.market("WDO")}
    data_map = {
        "WIN": {d: v for d, v in load_asset("WIN", "M5").items() if d <= bt.END},
        "WDO": {d: v for d, v in load_asset("WDO", "M5").items() if d <= bt.END},
    }

    all_ok = True
    for sid, cfg in C32.STRAT_CFGS.items():
        asset = cfg["asset"]
        DS, data = DS_map[asset], data_map[asset]
        core_rows = []
        per_day = {}
        for d in sorted(data):
            if d not in DS:
                continue
            fb, walls, ex = day_inputs(DS, data, asset, d)
            trs = C32.run_strategy(sid, fb, walls, ex, is_live=False)
            per_day[d] = trs
            for t in trs:
                core_rows.append({"date": d, **t})

        ref_df = ref_dfs[sid]
        ref_keys = {(r.date, f"{int(r.tm) // 60:02d}:{int(r.tm) % 60:02d}") for r in ref_df.itertuples()}
        core_keys = {(r["date"], r["time"]) for r in core_rows}
        ref_net = float(ref_df["pnl"].sum())
        st_core = _stats_list(core_rows)

        print(f"\n[{sid}]")
        print(f"  Pesquisa (M1) : {len(ref_df):4d} ops | Net R$ {ref_net:+8.0f}")
        print(
            f"  Core     (M5) : {st_core['ops']:4d} ops | WR {st_core['wr']:5.1f}% | PF {st_core['pf']:4.2f} | "
            f"Net R$ {st_core['net']:+8.0f} | DD R$ {st_core['dd']:5.0f} | R/DD {st_core['rdd']:5.2f}"
        )
        only_ref = sorted(ref_keys - core_keys)
        only_core = sorted(core_keys - ref_keys)
        print(f"  Entradas (date, time) -> só pesquisa: {len(only_ref)} {only_ref[:5]} | só core: {len(only_core)} {only_core[:5]}")

        # Teste de causalidade barra a barra (ambos modos: fechada até t_max, e t_max + abertura da barra seguinte como live)
        bad = 0
        days = [d for d in sorted(per_day) if per_day[d]][:check_live_days]
        for d in days:
            fb, walls, ex = day_inputs(DS, data, asset, d)
            full = {(t["time"], t["exit_time"], t["brl_1c"]) for t in per_day[d]}
            for n in range(5, len(fb) + 1):
                tmax = fb[n - 1]["time"]
                ex_n = [b for b in ex if b["time"] <= tmax]
                part = C32.run_strategy(sid, fb[:n], walls, ex_n, is_live=True)
                for t in part:
                    if not t["is_open"] and (t["time"], t["exit_time"], t["brl_1c"]) not in full:
                        bad += 1
                        print(f"  [DIVERGE] {sid} {d} @ {tmax}: {t['time']}->{t['exit_time']} R${t['brl_1c']}")
                        break
                if n < len(fb):
                    tmax_open = fb[n]["time"]
                    ex_open = [b for b in ex if b["time"] <= tmax_open]
                    part_open = C32.run_strategy(sid, fb[:n], walls, ex_open, is_live=True)
                    for t in part_open:
                        if not t["is_open"] and (t["time"], t["exit_time"], t["brl_1c"]) not in full:
                            bad += 1
                            print(f"  [DIVERGE live-open] {sid} {d} @ {tmax_open}: {t['time']}->{t['exit_time']} R${t['brl_1c']}")
                            break
        print(f"  Causalidade barra-a-barra ({len(days)} pregões × 2 modos): {bad} divergências")
        if bad > 0:
            all_ok = False

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
