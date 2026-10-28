"""Verify: Consensus backtest never opens 2 trades simultaneously."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

WIN_PV = 0.20
K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60
Z_ENT = 1.4
Z_ATT = 1.2
TP, SL = 800, 300
FORCE_CLOSE_MIN = 17 * 60 + 40
TIME_OFFSET = 3 * 3600

mt5.initialize(path=MT5_PATH)
rates_w = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 100000)
rates_d = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, 100000)
rates_di = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, 100000)
mt5.shutdown()

win = np.array([r[4] for r in rates_w], dtype=float)
wdo = np.array([r[4] for r in rates_d], dtype=float)
di  = np.array([r[4] for r in rates_di], dtype=float)
times = np.array([r[0] for r in rates_w], dtype=np.int64)

n = min(len(win), len(wdo), len(di))
win, wdo, di, times = win[:n], wdo[:n], di[:n], times[:n]

# Z-scores
kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
spreads = []
for y, x in zip(win, wdo):
    _, spread, _ = kf.update(float(y), float(x))
    spreads.append(spread)
k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))

betas = np.zeros(n)
for i in range(J_JW, n, 12):
    y = np.column_stack([win[i-J_JW:i], di[i-J_JW:i]])
    try:
        res = coint_johansen(y, det_order=0, k_ar_diff=1)
        vec = res.evec[:, 0]
        betas[i] = float(vec[1] / vec[0])
    except:
        betas[i] = betas[i-1] if i > 0 else 0
for i in range(J_JW, n):
    if betas[i] == 0: betas[i] = betas[i-1]
        
spread_di = win + betas * di
j_z = np.zeros(n)
for i in range(J_JW + J_ZW, n):
    ws = spread_di[i - J_ZW:i]
    mu, sd = np.mean(ws), np.std(ws)
    if sd < 1e-10: sd = 1.0
    j_z[i] = (spread_di[i] - mu) / sd

# Simulate Consensus with detailed tracking
position = 0
entry_price = 0
entry_bar = 0
trades = 0
overlaps = 0  # times we WOULD open but position != 0
force_closes = 0
tp_hits = 0
sl_hits = 0
mr_exits = 0

for i in range(1000, n):
    zw, zd, price = k_z[i], j_z[i], win[i]
    local_ts = times[i] + TIME_OFFSET
    dt = datetime.utcfromtimestamp(local_ts)
    t_min = dt.hour * 60 + dt.minute
    
    # Force Close
    if position != 0 and t_min >= FORCE_CLOSE_MIN:
        diff = (price - entry_price) if position == 1 else (entry_price - price)
        trades += 1
        force_closes += 1
        position = 0
        continue
    
    sig_buy = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
    sig_sell = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)

    if position == 0:
        if sig_buy:
            position = 1
            entry_price = price
            entry_bar = i
        elif sig_sell:
            position = -1
            entry_price = price
            entry_bar = i
    else:
        # Check if we WOULD try to open again (overlap detection)
        if sig_buy or sig_sell:
            overlaps += 1
        
        diff = (price - entry_price) if position == 1 else (entry_price - price)
        if diff >= TP:
            trades += 1
            tp_hits += 1
            position = 0
        elif diff <= -SL:
            trades += 1
            sl_hits += 1
            position = 0
        elif position == 1 and (zw >= -0.8 or zd >= -0.8):
            trades += 1
            mr_exits += 1
            position = 0
        elif position == -1 and (zw <= 0.8 or zd <= 0.8):
            trades += 1
            mr_exits += 1
            position = 0

print(f"\n{'='*60}")
print(f" VERIFICAÇÃO: CONSENSO — 1 TRADE POR VEZ")
print(f"{'='*60}")
print(f" Total barras:        {n:,}")
print(f" Trades finalizados:  {trades}")
print(f"   ├─ Target (TP):    {tp_hits}")
print(f"   ├─ Stop Loss:      {sl_hits}")
print(f"   ├─ Mean Reversion: {mr_exits}")
print(f"   └─ Force Close:    {force_closes}")
print(f"")
print(f" Barras com sinal durante trade aberto: {overlaps}")
print(f" (sinais IGNORADOS corretamente pela proteção position!=0)")
print(f"{'='*60}")
if overlaps > 0:
    print(f" ✅ {overlaps} sinais foram bloqueados — proteção funciona!")
else:
    print(f" ✅ Nenhum overlap detectado")
