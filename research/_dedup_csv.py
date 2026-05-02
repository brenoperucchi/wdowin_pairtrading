"""Deduplicate grid_search_all_models.csv keeping last occurrence."""
import pandas as pd
from pathlib import Path

csv_path = Path(r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\reports\grid_search_all_models.csv")

df = pd.read_csv(csv_path)
before = len(df)

# Dedup on model + all 3 param values
df = df.drop_duplicates(subset=["model", "param1_value", "param2_value", "param3_value"], keep="last")
after = len(df)

df.to_csv(csv_path, index=False)
print(f"Dedup: {before} -> {after} rows (removed {before - after} duplicates)")
