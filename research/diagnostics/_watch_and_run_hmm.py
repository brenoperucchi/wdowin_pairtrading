"""
Watcher: aguarda o LSTM terminar (monitorando CSV) → dedup → lança HMM → dedup final.
Roda em paralelo ao tune_single.py --model LSTM que já está executando.
"""
import subprocess, sys, time, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV  = ROOT / "data" / "reports" / "grid_search_all_models.csv"
DEDUP = ROOT / "research" / "_dedup_csv.py"
TUNE  = ROOT / "research" / "tune_single.py"

def count_lstm():
    import pandas as pd
    df = pd.read_csv(CSV)
    return len(df[df["model"] == "LSTM"])

def run(cmd, label):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}\n", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = (time.time() - t0) / 60
    print(f"\n>> {label} finalizado em {elapsed:.1f} min (exit={result.returncode})\n", flush=True)

# ── FASE 1: Aguardar LSTM (já rodando em outro terminal) ──
print("Aguardando LSTM grid search concluir (rodando em outro terminal)...")
print(f"Alvo: 500 configs LSTM")

last_count = 0
stable_checks = 0
while True:
    try:
        n = count_lstm()
        if n != last_count:
            print(f"  LSTM: {n}/500 configs completas", flush=True)
            last_count = n
            stable_checks = 0
        else:
            stable_checks += 1
        
        if n >= 500:
            print("  ✅ LSTM atingiu 500 configs!")
            break
        
        # Se ficou estável por 5 checks (5 min) e tem >400, provavelmente terminou
        if stable_checks >= 5 and n > 400:
            print(f"  ⚠️ LSTM parou em {n} configs (sem progresso por 5 min). Prosseguindo...")
            break
            
    except Exception as e:
        print(f"  Erro lendo CSV: {e}")
    
    time.sleep(60)

# ── Dedup pós-LSTM ──
run([sys.executable, str(DEDUP)], "Dedup pos-LSTM")

# ── FASE 2: HMM ──
run([sys.executable, str(TUNE), "--model", "HMM", "--workers", "28"], "HMM Grid Search (296 configs)")

# ── Dedup final ──
run([sys.executable, str(DEDUP)], "Dedup final")

# ── Resumo ──
import pandas as pd
df = pd.read_csv(CSV)
print(f"\n{'='*70}")
print(f"  GRID SEARCH COMPLETO!")
print(f"{'='*70}")
print(df["model"].value_counts().to_string())
print(f"Total: {len(df)}/1800")
