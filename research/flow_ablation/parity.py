# -*- coding: utf-8 -*-
"""Paridade do recálculo M1 (fórmula com pavio) contra o div_wall_v1 e da variante base contra core.compute_flow."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import flows as FL
from research.div_wall.data import load_asset
res = {}
for asset in ("WIN", "WDO"):
    data = load_asset(asset, "M5")
    p = FL.parity(asset, data)
    pm = FL.pas_mean(asset)
    print(asset, "barras", p["bars"], "ok", p["ok"], "dias sem M1", p["miss_days"], "dias c/ diferença", len(p["bad_days"]), p["bad_days"][:10], "pas_const", round(pm, 4))
    res[asset] = dict(p, pas_const=pm)
    # pipeline próprio = core (sem arredondamento) na base
    import numpy as np
    from core.div_wall_signal import compute_flow
    mx = 0
    for d in sorted(data)[:20]:
        bars = data[d][0]
        a = compute_flow([dict(b) for b in bars], asset)
        P = [FL._parts(b, asset) for b in bars]
        b = FL._pipeline(bars, [0.45 * x["wyk"] + 0.25 * x["porte"] + 0.30 * x["inst"] for x in P])
        sc = np.median([abs(x["wave"]) for x in a]) or 1
        mx = max(mx, max(abs(x["wave"] - y["wave"]) for x, y in zip(a, b)) / sc)
    print(asset, "max |onda core − pipeline sem arredondar| / mediana|onda| (20 pregões):", round(mx, 4))
json.dump(res, open(os.path.join(HERE, "results", "paridade.json"), "w"), indent=1, default=str)
