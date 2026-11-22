"""Diagnóstico complementar de V1a (open=True vs False por faixa horária), V2 e V3 (v3.2 >=100 trades)."""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import modulo as M
from research.div_master.wdo_especialista.robustez_final import make_P
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32, eval_v32, OPT_OPEN

print("=== 1. V1a: Breakdown por hora (open=True vs open=False) ===")
for lbl, om in [("open=True", OPT_OPEN), ("open=False", M.V32_PROD)]:
    r = run_v32(make_P(zone=3.5, pierce_max=6.0), "wall", "common", om, "CONF",
                lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
    st, df_v = eval_v32(r, 14.0, "nw", 0.0, 24)
    print(f"\n{lbl}: {st}")
    print(df_v.groupby("hh")["pnl"].agg(["count", "sum", "mean", lambda x: round(100 * (x > 0).mean(), 1)]))
    print("  src:", df_v.groupby("src")["pnl"].agg(["count", "sum", "mean"]))

print("\n=== 2. V1a Plateau SL x TP x tm (SL=12..16, TP=10..15/NW, tm=12..24) ===")
r_v1a = run_v32(make_P(zone=3.5, pierce_max=6.0), "wall", "common", OPT_OPEN, "CONF",
                lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
for sl in (12.0, 13.0, 14.0, 15.0, 16.0):
    row = []
    for tk, tv in [("nw", 0.0), ("fix", 10.0), ("fix", 12.0), ("fix", 15.0)]:
        st, _ = eval_v32(r_v1a, sl, tk, tv, 24)
        lbl = "NW" if tk == "nw" else f"{tv:.0f}"
        row.append(f"{lbl}:{st['rdd']:4.2f}({st['meses']})")
    print(f"  SL={sl:4.1f} | " + " ".join(row))

print("\n=== 3. V2 Plateau (PROD open=False | CONF | Wall-only | 09h-12h | ext30 > 0.0 vs 0.2) ===")
for zp in ((3.5, 6.0), (4.0, 6.5), (5.0, 8.0), (6.0, 9.0)):
    for e3 in (0.0, 0.2):
        r = run_v32(make_P(zone=zp[0], pierce_max=zp[1]), "wall", "common", M.V32_PROD, "CONF",
                    lambda r: r["has_w"], lambda r: r["tm"] <= 720, lambda r, t=e3: r["ext30"] > t)
        s8 = eval_v32(r, 12.0, "fix", 8.0, 8)[0]
        s12 = eval_v32(r, 14.0, "fix", 12.0, 8)[0]
        print(f"  z={zp[0]:.1f} e30>{e3:.1f} | 12/8t8: ops={s8['ops']:3d} rdd={s8['rdd']:5.2f} [{s8['h1']}/{s8['h2']}/{s8['oos']}] {s8['meses']} | 14/12t8: ops={s12['ops']:3d} rdd={s12['rdd']:5.2f} {s12['meses']}")

print("\n=== 4. V3 Plateau (PROD open=False | CONF | COMMON | pass>0) ===")
for f1m in ("flow", "flow_k1"):
    print(f"  -- f1={f1m} --")
    for tend in (690, 720, 780, 900):
        r = run_v32(make_P(zone=3.5, pierce_max=6.0), "wall", "common", {**M.V32_PROD, "f1": f1m}, "CONF",
                    lambda r: (r["has_w"] or r["has_d"]), lambda r, te=tend: r["tm"] <= te, lambda r: r["pass_"] > 0.0)
        outs = []
        for sl, tp in ((10.0, 10.0), (12.0, 10.0), (12.0, 12.0), (14.0, 12.0), (14.0, 15.0)):
            st, _ = eval_v32(r, sl, "fix", tp, 12)
            outs.append(f"{sl:.0f}/{tp:.0f}:{st['rdd']:4.2f}({st['ops']},{st['meses']})")
        print(f"    tm<={tend}: " + " | ".join(outs))
