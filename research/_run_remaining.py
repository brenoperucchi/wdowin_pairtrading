"""
Orquestrador: roda LSTM (se ainda rodando, espera) → dedup → HMM → dedup final.
Uso: python research/_run_remaining.py
"""
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEDUP = ROOT / "research" / "_dedup_csv.py"
TUNE  = ROOT / "research" / "tune_single.py"

def run(cmd, label):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}\n", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = (time.time() - t0) / 60
    print(f"\n✓ {label} finalizado em {elapsed:.1f} min (exit={result.returncode})\n", flush=True)
    return result.returncode

# 1) LSTM (345 configs restantes — checkpoint skip automático)
run([sys.executable, str(TUNE), "--model", "LSTM", "--workers", "28"], "FASE 1/2: LSTM Grid Search")

# 2) Dedup intermediário
run([sys.executable, str(DEDUP)], "Dedup pós-LSTM")

# 3) HMM (296 configs restantes)  
run([sys.executable, str(TUNE), "--model", "HMM", "--workers", "28"], "FASE 2/2: HMM Grid Search")

# 4) Dedup final
run([sys.executable, str(DEDUP)], "Dedup final")

# 5) Resumo
import pandas as pd
csv_path = ROOT / "data" / "reports" / "grid_search_all_models.csv"
df = pd.read_csv(csv_path)
print(f"\n{'='*70}")
print(f"  GRID SEARCH COMPLETO!")
print(f"{'='*70}")
print(f"  Total: {len(df)} configs")
print(df["model"].value_counts().to_string())
print(f"\n  Esperado: HMM=300, LSTM=500, XGBoost=1000 = 1800 total")
missing = 1800 - len(df)
if missing == 0:
    print("  ✅ Todas as 1800 combinações completadas!")
else:
    print(f"  ⚠️  {missing} configs faltando")
