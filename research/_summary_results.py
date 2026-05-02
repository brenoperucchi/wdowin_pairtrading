import pandas as pd

csv_path = r"data\reports\grid_search_all_models.csv"
df = pd.read_csv(csv_path)
df = df.sort_values("calmar_ratio", ascending=False)

SEP = "=" * 80

print(SEP)
print("TOP 10 OVERALL (all models) by Calmar Ratio")
print(SEP)
for _, r in df.head(10).iterrows():
    print(f"  [{r.model:7s}] {r.param1_name}={r.param1_value} {r.param2_name}={r.param2_value} "
          f"{r.param3_name}={r.param3_value} | "
          f"Calmar={r.calmar_ratio:6.2f} PnL=R${r.total_pnl:9.0f} DD=R${r.max_drawdown:9.0f} "
          f"PF={r.profit_factor:.2f} Trades={int(r.total_trades)} Acc={r.oos_accuracy}%")

for model_name in ["HMM", "LSTM", "XGBoost"]:
    subset = df[df["model"] == model_name].head(5)
    print(f"\n{SEP}")
    print(f"TOP 5 -- {model_name} (by Calmar)")
    print(SEP)
    for _, r in subset.iterrows():
        print(f"  {r.param1_name}={r.param1_value} {r.param2_name}={r.param2_value} "
              f"{r.param3_name}={r.param3_value} | "
              f"Calmar={r.calmar_ratio:6.2f} PnL=R${r.total_pnl:9.0f} DD=R${r.max_drawdown:9.0f} "
              f"PF={r.profit_factor:.2f} Trades={int(r.total_trades)} Acc={r.oos_accuracy}%")

print(f"\n{SEP}")
print("STATISTICS PER MODEL")
print(SEP)
for m in ["HMM", "LSTM", "XGBoost"]:
    sub = df[df["model"] == m]
    pos = sub[sub["calmar_ratio"] > 0]
    print(f"  {m:8s}: median_calmar={sub.calmar_ratio.median():.2f}  max={sub.calmar_ratio.max():.2f}  "
          f"positive={len(pos)}/{len(sub)} ({len(pos)/len(sub)*100:.0f}%)  "
          f"median_acc={sub.oos_accuracy.median():.1f}%")
