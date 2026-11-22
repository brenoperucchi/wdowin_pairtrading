"""Passo 2: Análise exploratória profunda de wdo_cands.pkl e características de Walls no WDO."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset

PKL = Path(__file__).resolve().parent / "wdo_cands.pkl"
df = pd.read_pickle(PKL)

df["period"] = np.where(df["date"] <= "2026-04-30", "H1_jan_abr",
               np.where(df["date"] <= "2026-07-31", "H2_mai_jul", "OOS_ago_nov"))
df["hora"] = df["tm"] // 60

print(f"Total rows: {len(df)}, dates: {df['date'].nunique()} ({df['date'].min()} .. {df['date'].max()})")
print("Columns:", list(df.columns))

# Inspect Wall structure in WDO
data = load_asset("WDO", "M5")
# Check wall types across all days
from collections import Counter
wt = Counter()
for d, v in data.items():
    for w in v[1]:
        wt[w.get("type")] += 1
print("\nWall types across dataset:", dict(wt))

sample_dates = sorted(data.keys())[-2:]
for d in sample_dates:
    bars, walls, _ = data[d]
    print(f"\nSample walls {d} (count={len(walls)}):")
    for w in walls[:10]:
        print(" ", {k: v for k, v in w.items()})

print("\n=== HORIZONS r3..r24 BY ENGINE x ANC (CONF) ===")
for rcol in ["r3", "r6", "r12", "r18", "r24"]:
    sub = df[df["e_conf"] >= 0].dropna(subset=[rcol])
    piv = sub.groupby(["engine", "anc", "period"])[rcol].agg(["size", "mean"]).unstack("period")
    piv["ALL"] = sub.groupby(["engine", "anc"])[rcol].mean()
    # Keep only rows where all 3 periods > 0 or ALL > 0.5
    pos3 = (piv["mean"]["H1_jan_abr"] > 0) & (piv["mean"]["H2_mai_jul"] > 0) & (piv["mean"]["OOS_ago_nov"] > 0)
    sel = piv[pos3 | (piv["ALL"] > 0.5)].round(2)
    print(f"\n--- {rcol} (all 3 periods > 0 OR ALL > 0.5) ---")
    if len(sel):
        print(sel.to_string())
    else:
        print("  (none)")

print("\n=== OPC HORIZONS o_r3..o_r24 BY ENGINE x opc_esp ===")
for rcol in ["o_r3", "o_r6", "o_r12", "o_r18", "o_r24"]:
    sub = df[df["has_opc"]].dropna(subset=[rcol])
    piv = sub.groupby(["engine", "opc_esp", "period"])[rcol].agg(["size", "mean"]).unstack("period")
    piv["ALL"] = sub.groupby(["engine", "opc_esp"])[rcol].mean()
    pos3 = (piv["mean"]["H1_jan_abr"] > 0) & (piv["mean"]["H2_mai_jul"] > 0) & (piv["mean"]["OOS_ago_nov"] > 0)
    sel = piv[pos3 | (piv["ALL"] > 0.4)].round(2)
    print(f"\n--- {rcol} ---")
    if len(sel):
        print(sel.to_string())

print("\n=== FLOW & CONTEXT FEATURES FOR CONF (v3.2, v2.1, v3, v3.1, v2.2) ===")
for eng in ["v3.2", "v3.2_ab", "v2.1", "v3", "v3.1"]:
    sub = df[(df["engine"] == eng) & (df["e_conf"] >= 0)].copy()
    sub["wyck_pos"] = sub["wyck_dir"] > 0
    sub["pass_pos"] = sub["pass_dir"] > 0
    sub["aggr_pos"] = sub["aggr_dir"] > 0
    sub["d_wall_b"] = pd.cut(sub["d_wall"], [-1, 1.5, 3.5, 6.0, 12.0, 999])
    sub["d_mid_b"] = pd.cut(sub["d_mid"], [-1, 1.5, 3.5, 6.0, 12.0, 999])
    sub["wd_b"] = pd.cut(sub["wd_ratio"], [0, 1.05, 1.25, 1.5, 2.0, 999])
    sub["e50_b"] = pd.cut(sub["ext50"], [-99, -0.5, 0.0, 0.5, 1.0, 99])
    sub["s50_b"] = pd.cut(sub["slope50"], [-99, -0.5, -0.2, 0.0, 0.3, 99])
    sub["e30_b"] = pd.cut(sub["ext30"], [-99, -0.5, 0.0, 0.5, 1.0, 99])
    print(f"\n*** Engine {eng} (r12) ***")
    for col in ["wyck_pos", "pass_pos", "aggr_pos", "has_wall", "has_day", "near_kind", "d_wall_b", "d_mid_b", "wd_b", "e50_b", "s50_b", "e30_b"]:
        g = sub.groupby([col, "period"], observed=False)["r12"].agg(["size", "mean"]).unstack("period")
        g["ALL"] = sub.groupby(col, observed=False)["r12"].mean()
        pos3 = (g["mean"]["H1_jan_abr"] > 0) & (g["mean"]["H2_mai_jul"] > 0) & (g["mean"]["OOS_ago_nov"] > 0)
        if pos3.any() or (g["ALL"] > 0.3).any():
            print(f"  [{col}]")
            print(g.round(2).to_string())
