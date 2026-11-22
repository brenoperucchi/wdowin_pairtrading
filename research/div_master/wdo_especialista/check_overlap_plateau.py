"""Checa platôs completos de C2 e C4, decomposição por âncora, e sobreposição/correlação com Sniper WDO e ESP_DIV_V22_WIN."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import modulo as M
from research.div_master.especialistas import bt
from research.div_master.wdo_especialista.robustez_final import run_strategy, eval_rows, make_P

# 1. Plateau de C2 (v3.1 Wall only + ext30)
print("=== PLATEAU C2 (v3.1 Wall only | OPC | ANY_WALL | ext30) ===")
for zp in ((2.0, 3.5), (2.5, 4.0), (3.0, 5.0), (3.5, 6.0)):
    r_z = run_strategy("v3.1", make_P(zone=zp[0], pierce_max=zp[1]), "wall", "common",
                       lambda r: r["ext30"] > 0.0, lambda r: r["has_w"])
    st, _ = eval_rows(r_z, 12.0, 6.5, 24)
    print(f"  z={zp[0]:.1f}/p={zp[1]:.1f} -> {st}")

print("\n[Plateau C2: ext30_thr x SL x TP]")
for e3 in (-0.2, 0.0, 0.1, 0.2):
    r_e = run_strategy("v3.1", make_P(zone=2.5, pierce_max=4.0), "wall", "common",
                       lambda r, t=e3: r["ext30"] > t, lambda r: r["has_w"])
    line = []
    for sl in (8.5, 10.0, 12.0, 14.0):
        for tp in (5.5, 6.5, 8.0, 10.0):
            st, _ = eval_rows(r_e, sl, tp, 24)
            line.append(f"{sl:.0f}/{tp:.1f}:{st['rdd']:4.2f}")
    print(f"  e30>{e3:+.1f} (n={len(r_e):3d}) | " + " ".join(line))

# 2. Decomposição e plateau de C4 (v3.2 Wall only z=2.5/p=4.0 | OPC | EXT_OR_FURO | ext50)
print("\n=== DECOMPOSICAO & PLATEAU C4 (v3.2 Wall only z=2.5/p=4.0 | OPC | EXT_OR_FURO) ===")
for e5 in (0.0, 0.1, 0.2, 0.3, 0.4):
    r_e = run_strategy("v3.2", make_P(zone=2.5, pierce_max=4.0), "wall", "all",
                       lambda r, t=e5: r["ext50"] > t, lambda r: (r["has_d"] or r["has_c1"]))
    st, df_e = eval_rows(r_e, 12.0, 12.0, 12)
    print(f"  ext50>{e5:.1f} -> ops={st['ops']} wr={st['wr']} pf={st['pf']} net={st['net']} dd={st['dd']} rdd={st['rdd']} h1={st['h1']} h2={st['h2']} oos={st['oos']} {st['meses']}")

r_c4 = run_strategy("v3.2", make_P(zone=2.5, pierce_max=4.0), "wall", "all",
                    lambda r: r["ext50"] > 0.3, lambda r: (r["has_d"] or r["has_c1"]))
_, df_c4 = eval_rows(r_c4, 12.0, 12.0, 12)
print("\nC4 por esp:")
print(df_c4.groupby("esp")["pnl"].agg(["count", "sum", "mean", lambda x: round(100 * (x > 0).mean(), 1)]))
print("C4 onde has_c1 (FURO_WALL) vs só EXTREMO:")
print(df_c4.groupby("has_c1")["pnl"].agg(["count", "sum", "mean", lambda x: round(100 * (x > 0).mean(), 1)]))

# 3. C1, C2, C4 Tradeframes + Sobreposição com WDO_DIV_WALL e ESP_DIV_V22_WIN
r_c1 = run_strategy("v3.1", make_P(zone=3.5, pierce_max=6.0), "wall", "common",
                    ctx_fn=lambda r: r["ext50"] > 0.3, anc_fn=lambda r: r["has_w"])
_, df_c1 = eval_rows(r_c1, 12.0, 6.5, 24)
r_c2 = run_strategy("v3.1", make_P(zone=2.5, pierce_max=4.0), "wall", "common",
                    ctx_fn=lambda r: r["ext30"] > 0.0, anc_fn=lambda r: r["has_w"])
_, df_c2 = eval_rows(r_c2, 12.0, 6.5, 24)

# Sniper WDO_DIV_WALL from JSON
eq_path = ROOT / "data" / "processed" / "portfolio_4_sistematicas_equity_v1.json"
with open(eq_path, "r", encoding="utf-8") as f:
    pj = json.load(f)

trades_json = pj.get("trades", pj.get("trade_ledger", []))
if not trades_json and isinstance(pj, dict):
    for k, v in pj.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and ("strategy_id" in v[0] or "strategy" in v[0]):
            trades_json = v
            break
sniper_wdo = [t for t in trades_json if (t.get("strategy_id") or t.get("strategy")) == "WDO_DIV_WALL"]
print(f"\nSniper WDO_DIV_WALL no JSON: {len(sniper_wdo)} trades (keys={list(sniper_wdo[0].keys()) if sniper_wdo else []})")
if sniper_wdo:
    df_sn = pd.DataFrame(sniper_wdo)
    tcol = "entry_time" if "entry_time" in df_sn.columns else ("time" if "time" in df_sn.columns else "time_in")
    pcol = "net_pnl" if "net_pnl" in df_sn.columns else ("pnl" if "pnl" in df_sn.columns else "pnl_brl")
    sn_keys = set(zip(df_sn["date"].astype(str), df_sn[tcol].astype(str).str[:5]))
    for cname, cdf in [("C1 (v3.1 ext50)", df_c1), ("C2 (v3.1 ext30)", df_c2), ("C4 (v3.2 ext50)", df_c4)]:
        exact = sum((r.date, f"{r.tm//60:02d}:{r.tm%60:02d}") in sn_keys for r in cdf.itertuples())
        same_day = len(set(cdf["date"]).intersection(set(df_sn["date"].astype(str))))
        d_c = cdf.groupby("date")["pnl"].sum()
        d_s = df_sn.groupby("date")[pcol].sum()
        idx_u = sorted(set(d_c.index) | set(d_s.index))
        corr = d_c.reindex(idx_u, fill_value=0.0).corr(d_s.reindex(idx_u, fill_value=0.0))
        print(f"  {cname}: {len(cdf)} ops | exact_bar_overlap={exact} | same_day={same_day}/{cdf['date'].nunique()} | daily_corr={corr:+.3f}")

# WIN Especialista v3.2
S_win = bt.simulate("WIN", bt.signals("WIN", "v3.2"), bt.market("WIN"), exits=("A",))
S_win = S_win[S_win.ok & (S_win.tm >= 600) & (S_win.tm <= 955) & (S_win.ext50 > -0.5) & (S_win.slope50 > -0.5)]
S_win = bt.mgmt(S_win, "pnl_A", "xt_A", "UM_POR_VEZ")
print("\nESP_DIV_V22_WIN (1 ct, referência até 11/11/2026):", bt.stats(S_win, "pnl_A", "xt_A"))
for cname, cdf in [("C1 (v3.1 ext50)", df_c1), ("C2 (v3.1 ext30)", df_c2), ("C4 (v3.2 ext50)", df_c4)]:
    d_c = cdf.groupby("date")["pnl"].sum()
    d_w = S_win.groupby("date")["pnl_A"].sum()
    idx_u = sorted(set(d_c.index) | set(d_w.index))
    corr_w = d_c.reindex(idx_u, fill_value=0.0).corr(d_w.reindex(idx_u, fill_value=0.0))
    comb = bt.portfolio(S_win, cdf, "pnl_A", "pnl", "xt_A", "xt", mult_w=1.0)
    print(f"  {cname} vs WIN v3.2: daily_corr={corr_w:+.3f} | portfolio 1L WIN + 1L WDO -> rdd={comb['rdd']} net={comb['net']} dd={comb['dd']}")
