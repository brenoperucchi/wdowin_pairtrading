import pandas as pd
import itertools

csv_path = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\reports\grid_search_all_models.csv"
df = pd.read_csv(csv_path)

counts = df["model"].value_counts()
print("Results per model:")
print(counts)
print(f"\nTotal: {len(df)}")
print(f"Expected: HMM=300, LSTM=500, XGBoost=1000, Total=1800")
print(f"Missing: HMM={300-counts.get('HMM',0)}, LSTM={500-counts.get('LSTM',0)}, XGBoost={1000-counts.get('XGBoost',0)}")

# --- HMM coverage ---
hmm = df[df["model"] == "HMM"]
print(f"\n--- HMM coverage ---")
print(f"Completed: {len(hmm)}")

# --- XGBoost coverage ---
xgb = df[df["model"] == "XGBoost"]
print(f"\n--- XGBoost coverage ---")
print(f"Completed: {len(xgb)}")

# --- LSTM coverage ---
lstm = df[df["model"] == "LSTM"]
print(f"\n--- LSTM coverage ---")
print(f"Completed: {len(lstm)}")

LSTM_GRID = {
    "seq_len": [5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
    "hidden_dim": [32, 64, 96, 128, 160, 192, 224, 256, 288, 320],
    "dropout": [0.1, 0.3, 0.5, 0.7, 0.9],
}

HMM_GRID = {
    "ret_threshold": [0.0001, 0.0005, 0.001, 0.002, 0.0025, 0.003, 0.0035, 0.004, 0.0045, 0.005],
    "covariance_type": ["full", "diag", "tied"],
    "n_iter": [50, 100, 150, 200, 250, 300, 350, 400, 450, 500],
}

# Find missing LSTM combos
completed_lstm = set()
for _, r in lstm.iterrows():
    completed_lstm.add((r["param1_value"], r["param2_value"], r["param3_value"]))

all_lstm = set()
for s, h, d in itertools.product(LSTM_GRID["seq_len"], LSTM_GRID["hidden_dim"], LSTM_GRID["dropout"]):
    all_lstm.add((s, h, d))

missing_lstm = all_lstm - completed_lstm
print(f"Missing LSTM combos: {len(missing_lstm)}")

# Show which seq_len are missing
missing_seq_lens = sorted(set(s for s, h, d in missing_lstm))
print(f"Missing seq_len values: {missing_seq_lens}")

# Count missing per seq_len
for sl in missing_seq_lens:
    missing_for_sl = [(s, h, d) for s, h, d in missing_lstm if s == sl]
    print(f"  seq_len={sl}: {len(missing_for_sl)} missing")

# Find missing HMM combos
completed_hmm = set()
for _, r in hmm.iterrows():
    completed_hmm.add((r["param1_value"], r["param2_value"], r["param3_value"]))

all_hmm = set()
for rt, ct, ni in itertools.product(HMM_GRID["ret_threshold"], HMM_GRID["covariance_type"], HMM_GRID["n_iter"]):
    all_hmm.add((rt, ct, ni))

missing_hmm = all_hmm - completed_hmm
print(f"\nMissing HMM combos: {len(missing_hmm)}")
