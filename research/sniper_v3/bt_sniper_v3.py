"""
Sniper 5176 corrigido (base B, idêntica a research/sniper_add) trocando o detector de divergência:
antigo `detect_visual_swing_divergences` -> v3 `detect_divergences_v3` (definição aprovada em 11/11/2026).
Tudo o mais igual: entradas de setup, gate 3 motores no WIN, saída WIN 2 lotes NWE30+750 com BE, janela causal
(divergência entre bi-tol-1 e bi-1), horários, pausas e meta diária.
Uso: python -m research.sniper_v3.bt_sniper_v3
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
from research.sniper_add.bt_add import BASE_WDO, BASE_WIN, m2, stats  # noqa: E402
from research.div_wall.data import load_asset  # noqa: E402
from core.div_wall_signal import DivParamsV2, compute_flow, detect_divergences_v3  # noqa: E402

SPLIT, H1 = "2026-07-31", "2026-04-30"
OUT = os.path.join(ROOT, "research", "sniper_v3", "results")


def v3_map(asset, only_near=False):
    vm = {}
    for d, (bars, walls, nwe) in load_asset(asset, "M5").items():
        fb = compute_flow(bars, asset)
        sg = detect_divergences_v3(fb, walls, nwe, DivParamsV2.default(asset, nwe_filter="none"))
        vm[d] = [(s.idx, s.direction) for s in sg if (not only_near or s.wall_type == "perto")]
        vm[(d, "tmap")] = {b["time"]: i for i, b in enumerate(bars)}
    return vm


def union(a, b):
    out = {}
    for k in set(a) | set(b):
        if isinstance(k, tuple):
            out[k] = a.get(k) or b.get(k)
    for d in {k for k in set(a) | set(b) if not isinstance(k, tuple)}:
        ta, tb = a.get((d, "tmap"), {}), b.get((d, "tmap"), {})
        inv_b = {i: t for t, i in tb.items()}
        sb = [(ta.get(inv_b.get(i), -99), dr) for i, dr in b.get(d, [])] if ta else b.get(d, [])
        out[d] = list(a.get(d, [])) + sb
        out[(d, "tmap")] = ta or tb
    return out


def part(trs, a, b):
    return [t for t in trs if a < t["date"] <= b]


def main():
    os.makedirs(OUT, exist_ok=True)
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
                    base_w += [dict(r[0], src="BASE")] if r else []
            elif t.get("asset") == "WDO" and sid in BASE_WDO and key not in kd:
                kd.add(key)
                base_d.append(dict(t, src="BASE"))
    days = sorted({d["date"] for d in p4["days"]})
    v3w, v3d = v3_map("WIN"), v3_map("WDO")
    v3w_n, v3d_n = v3_map("WIN", True), v3_map("WDO", True)
    cov = {a: sum(1 for d in days if d in m) for a, m in (("WIN", v3w), ("WDO", v3d))}
    print(f"dias do Sniper: {len(days)} | com dados v3: WIN {cov['WIN']} WDO {cov['WDO']}")
    print(f"pool de entradas de setup: WIN {len(base_w)} WDO {len(base_d)}")

    variants = {"antigo (atual)": (vis_win, vis_wdo), "v3": (v3w, v3d), "v3 só perto da Wall": (v3w_n, v3d_n),
                "antigo OU v3": (union(vis_win, v3w), union(vis_wdo, v3d))}
    rows, keep = [], {}
    for name, (vw, vd) in variants.items():
        for tol in (1, 2, 3, 4):
            fw = sniper(base_w, vw, tol, True, "09:05", "16:45", [("12:00", "12:55")], 180.0)
            fd = sniper(base_d, vd, tol, True, "09:00", "17:00", [("11:00", "11:55")], 120.0)
            for lab, trs in (("WIN", fw), ("WDO", fd), ("Carteira", fw + fd)):
                for per, a, b in (("jan–abr", "", H1), ("mai–jul", H1, SPLIT), ("jan–jul", "", SPLIT),
                                  ("ago–nov", SPLIT, "9999"), ("completo", "", "9999")):
                    s = stats(part(trs, a, b))
                    rows.append(dict(detector=name, tol=tol, ativo=lab, periodo=per, **s))
            keep[(name, tol)] = fw + fd
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, "comparacao.csv"), index=False)
    pd.DataFrame([dict(t, detector=k[0], tol=k[1]) for k, v in keep.items() for t in v]).to_csv(
        os.path.join(OUT, "trades.csv"), index=False)
    cols = ["detector", "tol", "ops", "wr", "pf", "net", "dd", "rdd", "meses"]
    for per in ("jan–jul", "ago–nov", "completo"):
        print(f"\n### Carteira {per}")
        print(R[(R.ativo == "Carteira") & (R.periodo == per)][cols].to_string(index=False))
    for a in ("WIN", "WDO"):
        print(f"\n### {a} por período (tol 2)")
        print(R[(R.ativo == a) & (R.tol == 2)][["detector", "periodo"] + cols[2:]].to_string(index=False))


if __name__ == "__main__":
    main()
