import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.discover_m15_deep_dive import run_experiment, load_tf_bars, compute_metrics
from research.mt5_loader import load_gex_csv, HIST_WIN
import research.discover_gex_nwe_setups as disc

df = load_tf_bars("WIN", "M15")
gex_win = load_gex_csv(HIST_WIN)

models = [
    ("NOVO EST-03 (M15 Fakeout Trap)", "M15_FAKEOUT_TRAP", 30.0, 220.0, 0.0, 0.0),
    ("NOVO EST-05 (M15 MidWall Pullback)", "M15_MIDWALL_PULLBACK", 35.0, 250.0, 4.0, 300.0),
]

print("=" * 95)
print("  WALK-FORWARD REAL DOS NOVOS ROBÔS M15 DESCOBERTOS HOJE (IS vs OOS)")
print("=" * 95)

for title, st, wbuf, min_tp, slp, bw in models:
    print(f"\n>>> {title} <<<")
    for label, d_start, d_end in [
        ("IS (Mai-Ago)", "2026-05-11", "2026-08-31"),
        ("OOS (Set-Nov)", "2026-09-01", "2026-11-04"),
        ("FULL (123 pregões)", "2026-05-11", "2026-11-04"),
    ]:
        sub_df = df[(df["session_date"] >= d_start) & (df["session_date"] <= d_end)].reset_index(drop=True)
        sub_c = sub_df["close"].values
        c, u, l, _, s = disc.compute_nwe_series(sub_c, lookback=30, bw=4.0, mult=1.8)
        sub_nwe = {"center": c, "upper": u, "lower": l, "slope": s}
        use_n = slp > 0
        tr = run_experiment(
            sub_df, gex_win, "WIN", "M15", st, "MARKET", sub_nwe,
            wall_buf=wbuf, min_tp_dist=min_tp, front_run=20.0,
            be_ratio=0.50, be_lock_pts=25.0,
            use_nwe_slope=use_n, nwe_slope_thresh=slp, min_nwe_bw=bw
        )
        m = compute_metrics(tr)
        print(f"  {label:<18}: {m['tr']:>4d} tr | WR {m['wr']:>4.1f}% | PF {m['pf']:>4.2f} | Net R$ {m['net']:>7.0f} | DD R$ {m['mdd']:>5.0f} | Ret/DD {m['ret_dd']:>5.2f}x")

