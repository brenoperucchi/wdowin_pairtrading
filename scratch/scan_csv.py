import pandas as pd
import os
import glob

# Encontrar o mais recente
gex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_dir = os.path.join(gex_dir, 'data')
candidates = glob.glob(os.path.join(data_dir, "Posições em aberto-*.csv"))
candidates.sort(key=os.path.getmtime, reverse=True)
file_path = candidates[0]

print(f"Lendo {os.path.basename(file_path)}...")

header_idx = 0
with open(file_path, 'r', encoding='latin1') as f:
    for i, line in enumerate(f):
        if line.startswith("Instrumento financeiro"):
            header_idx = i
            break
            
pos = pd.read_csv(file_path, sep=';', encoding='latin1', skiprows=header_idx, low_memory=False)

segments = pos.iloc[:, 4].unique()
print("Unique segments found in B3 CSV:")
print(list(segments))

prefixes = set()
for _, row in pos.iterrows():
    ticker = str(row.iloc[0]).strip()
    segment = str(row.iloc[4]).strip()
    if ("DOL" in ticker or "WDO" in ticker) and ("EQUITY" in segment):
        prefixes.add((ticker, segment, row.iloc[11]))

print("DOL/WDO rows found in EQUITY segments:")
for t, s, oi in sorted(list(prefixes))[:20]:
    print(f"  Ticker: {t} | Segment: {s} | OI: {oi}")
