"""
Prova que `core/profit_min_decomp.py` (por minuto) soma exatamente nas barras M5 do motor
(`_build_from_profit_min_m1_m5`). Uso: python -m research.div_wall.test_m1_decomp
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.profit_min_decomp import decompose_min_bars  # noqa: E402
from core.profit_wall_players_engine import _build_from_profit_min_m1_m5, _load_profit_min_index  # noqa: E402

FIELDS = ("inst_aggr_delta", "inst_pass_delta", "ret_delta_bar")


def main():
    ok = True
    for asset in ("WIN", "WDO"):
        idx = _load_profit_min_index(asset)
        days = [d for d in sorted(idx) if "2026-01-02" <= d <= "2026-11-09" and idx[d]["m1"] is not None][::7]
        worst, n_cmp = 0.0, 0
        for d in days:
            m1 = decompose_min_bars(idx[d]["m1"], asset, d)
            pay = _build_from_profit_min_m1_m5(idx[d], asset, d, [], 60.0, 5.0 if asset == "WIN" else 0.5)
            m5 = {int(b["time"]): b for b in pay["m5_cvd_series"]}
            agg = {}
            for b in m1:
                k = (b["ts"] // 300) * 300
                s = agg.setdefault(k, {f: 0.0 for f in FIELDS})
                for f in FIELDS:
                    s[f] += b[f]
            for k, s in agg.items():
                if k not in m5:
                    continue
                for f in FIELDS:
                    diff = abs(round(s[f], 0) - float(m5[k][f]))
                    worst = max(worst, diff)
                    n_cmp += 1
        status = "OK" if worst <= 1.0 else "FALHA"
        ok &= worst <= 1.0
        print(f"{asset}: {len(days)} dias, {n_cmp} comparações, maior diferença {worst:.0f} lote(s) → {status}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
