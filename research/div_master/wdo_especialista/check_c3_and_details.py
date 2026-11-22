"""Verifica platô de C3 e estatísticas detalhadas de saída/distribuição do setup campeão C2."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.wdo_especialista.robustez_final import run_strategy, eval_rows, make_P

print("=== PLATEAU C3 (v3.1 d_wall<=3.5 & pass>0, SL12 TP6.5 tm24) ===")
for lv in ("wall", "all"):
    for el in ("common", "all"):
        r = run_strategy("v3.1", make_P(zone=3.5, pierce_max=6.0), lv, el,
                         ctx_fn=lambda r: r["pass_"] > 0.0,
                         anc_fn=lambda r, lm=lv: r["has_w"] if lm == "wall" else r["d_wall"] <= 3.5)
        st, _ = eval_rows(r, 12.0, 6.5, 24)
        print(f"  lv={lv:4s} elig={el:6s} -> {st}")

r_c3 = run_strategy("v3.1", make_P(zone=3.5, pierce_max=6.0), "all", "all",
                    ctx_fn=lambda r: r["pass_"] > 0.0, anc_fn=lambda r: r["d_wall"] <= 3.5)
print("\n[Plateau C3 SL x TP]")
for sl in (8.5, 10.0, 12.0, 14.0):
    line = []
    for tp in (5.5, 6.5, 8.0, 10.0):
        st, _ = eval_rows(r_c3, sl, tp, 24)
        line.append(f"{sl:.0f}/{tp:.1f}:{st['rdd']:4.2f}")
    print("  " + " ".join(line))

print("\n=== DETALHES DO CAMPEAO C2 (v3.1 Wall-only z=2.5/p=4.0 | OPC | ANY_WALL | ext30>0) ===")
r_c2 = run_strategy("v3.1", make_P(zone=2.5, pierce_max=4.0), "wall", "common",
                    ctx_fn=lambda r: r["ext30"] > 0.0, anc_fn=lambda r: r["has_w"])
for sl in (10.0, 10.5, 11.0, 12.0, 13.0, 14.0):
    for tp in (6.0, 6.5, 7.0, 8.0):
        for tm in (12, 18, 24):
            if sl != 12.0 and (tp != 6.5 or tm != 24):
                continue
            st, df_t = eval_rows(r_c2, sl, tp, tm)
            if tm == 24 or (sl == 12.0 and tp == 6.5):
                print(f"  SL={sl:4.1f} TP={tp:4.1f} tm={tm:2d} -> ops={st['ops']} wr={st['wr']} pf={st['pf']} net={st['net']} dd={st['dd']} rdd={st['rdd']} h1={st['h1']} h2={st['h2']} oos={st['oos']} {st['meses']}")

st_c2, df_c2 = eval_rows(r_c2, 12.0, 6.5, 24)
p = df_c2["pnl"].values
# Sequência máxima de losses
cur, max_loss_seq = 0, 0
for v in p:
    if v < 0:
        cur += 1
        max_loss_seq = max(max_loss_seq, cur)
    else:
        cur = 0
print(f"\nDistribuição C2 (SL=12, TP=6.5, tm=24):")
print(f"  ops={len(p)}, dir COMPRA={(df_c2['dir']==1).sum()}, VENDA={(df_c2['dir']==-1).sum()}")
print(f"  wins={(p>0).sum()} (avg={p[p>0].mean():.1f}, max={p[p>0].max():.1f}), losses={(p<0).sum()} (avg={p[p<0].mean():.1f}, min={p[p<0].min():.1f})")
print(f"  expectativa/op=R$ {p.mean():.2f}, max_loss_consecutivos={max_loss_seq}")
print(f"  por subtipo OPC:\n{df_c2.groupby(['esp','sub'])['pnl'].agg(['count','sum','mean',lambda x: round(100*(x>0).mean(),1)])}")
print(f"  por hora:\n{df_c2.groupby('hora')['pnl'].agg(['count','sum','mean',lambda x: round(100*(x>0).mean(),1)])}")
