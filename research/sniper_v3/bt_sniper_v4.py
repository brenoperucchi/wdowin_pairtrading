"""Sniper corrigido com o detector v4 (variantes escolhidas pelas marcações) × atual × v3. Uso: python -m research.sniper_v3.bt_sniper_v4"""
import json, os, sys
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
import research.flow_window_asg.inject_unified_div_opt2 as S  # noqa: E402
from research.audit_5176.audit_sniper import sniper  # noqa: E402
from research.sniper_add.bt_add import BASE_WDO, BASE_WIN, m2, stats  # noqa: E402
from research.sniper_v3.bt_sniper_v3 import part, union  # noqa: E402
from research.div_wall.data import load_asset  # noqa: E402
from core.div_wall_signal import DivParamsV2, compute_flow, detect_divergences_v3, detect_divergences_v4  # noqa: E402

SPLIT, H1 = "2026-07-31", "2026-04-30"
ZW = {"WIN": 1.0, "WDO": 0.04}          # escala WIN→WDO das distâncias (100 pts WIN ≈ 4 pts WDO, como no v2)
V4 = {"v4 (zona 200, pivô 1)": dict(rompimento=False, zone=200.0, L=1, furou=True, rom_max=400.0),
      "v4R (com rompimento, zona 100, pivô 1)": dict(rompimento=True, zone=100.0, L=1, furou=True, rom_max=400.0)}


def vmap(asset, kind, cfg=None):
    vm = {}
    for d, (bars, walls, nwe) in load_asset(asset, "M5").items():
        fb = compute_flow(bars, asset)
        if kind == "v3":
            sg = detect_divergences_v3(fb, walls, nwe, DivParamsV2.default(asset, nwe_filter="none"))
        else:
            p = DivParamsV2.default(asset, nwe_filter="none", pivot_left=cfg["L"])
            sg = detect_divergences_v4(fb, walls, nwe, p, rompimento=cfg["rompimento"], zone=cfg["zone"] * ZW[asset],
                                       furou=cfg["furou"], rom_max=cfg["rom_max"] * ZW[asset])
        vm[d] = [(s.idx, s.direction) for s in sg]
        vm[(d, "tmap")] = {b["time"]: i for i, b in enumerate(bars)}
    return vm


def main():
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
                    kw.add(key); r = S.simulate_win_div_2lots_opt2([t], win_bars, nwe)
                    base_w += [dict(r[0], src="BASE")] if r else []
            elif t.get("asset") == "WDO" and sid in BASE_WDO and key not in kd:
                kd.add(key); base_d.append(dict(t, src="BASE"))
    variants = {"antigo (atual)": (vis_win, vis_wdo), "v3": (vmap("WIN", "v3"), vmap("WDO", "v3"))}
    for name, cfg in V4.items():
        vw, vd = vmap("WIN", "v4", cfg), vmap("WDO", "v4", cfg)
        variants[name] = (vw, vd)
        variants["antigo OU " + name.split(" ")[0]] = (union(vis_win, vw), union(vis_wdo, vd))
    rows = []
    for name, (vw, vd) in variants.items():
        for tol in (2, 4):
            fw = sniper(base_w, vw, tol, True, "09:05", "16:45", [("12:00", "12:55")], 180.0)
            fd = sniper(base_d, vd, tol, True, "09:00", "17:00", [("11:00", "11:55")], 120.0)
            for lab, trs in (("WIN", fw), ("WDO", fd), ("Carteira", fw + fd)):
                for per, a, b in (("jan–jul", "", SPLIT), ("ago–nov", SPLIT, "9999"), ("completo", "", "9999")):
                    rows.append(dict(detector=name, tol=tol, ativo=lab, periodo=per, **stats(part(trs, a, b))))
    R = pd.DataFrame(rows); R.to_csv(os.path.join(ROOT, "research", "sniper_v3", "results", "comparacao_v4.csv"), index=False)
    cols = ["detector", "tol", "ops", "wr", "pf", "net", "dd", "rdd", "meses"]
    for per in ("jan–jul", "ago–nov", "completo"):
        print(f"\n### Carteira {per}"); print(R[(R.ativo == "Carteira") & (R.periodo == per)][cols].to_string(index=False))


if __name__ == "__main__":
    main()
