import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
import matplotlib.pyplot as plt
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL
from core.kalman_filter import KalmanBetaFilter

# Configurações Ótimas
BARS_FETCH = 15000
WIN_PV = 0.20

K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60

Z_ENT, Z_ATT = 1.4, 1.2
TP, SL = 800, 300

def init_mt5():
    mt5.initialize(path=MT5_PATH)

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    return np.array([r[4] for r in rates], dtype=float)

def get_base_zscores(win_c, wdo_c, di_c):
    # Kalman
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    spreads = []
    for y, x in zip(win_c, wdo_c):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))
    
    # Johansen
    n = len(win_c)
    betas = np.zeros(n)
    for i in range(J_JW, n, 12):
        y = np.column_stack([win_c[i-J_JW:i], di_c[i-J_JW:i]])
        try:
            res = coint_johansen(y, det_order=0, k_ar_diff=1)
            vec = res.evec[:, 0]
            betas[i] = float(vec[1] / vec[0])
        except:
            betas[i] = betas[i-1] if i > 0 else 0
    for i in range(J_JW, n):
        if betas[i] == 0: betas[i] = betas[i-1]
            
    spread_di = win_c + betas * di_c
    j_z = np.zeros(n)
    for i in range(J_JW + J_ZW, n):
        window_spread = spread_di[i - J_ZW:i]
        mu, sd = np.mean(window_spread), np.std(window_spread)
        if sd < 1e-10: sd = 1.0
        j_z[i] = (spread_di[i] - mu) / sd
        
    return k_z, j_z

def simulate(k_z, j_z, win_c):
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(1000, len(win_c)):
        zk, zj, price = k_z[i], j_z[i], win_c[i]
        
        if position == 0:
            if (zk <= -Z_ENT and zj <= -Z_ATT) or (zk <= -Z_ATT and zj <= -Z_ENT):
                position = 1
                entry_price = price
            elif (zk >= Z_ENT and zj >= Z_ATT) or (zk >= Z_ATT and zj >= Z_ENT):
                position = -1
                entry_price = price
        else:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            if diff >= TP:
                trades.append(TP * WIN_PV)
                position = 0
            elif diff <= -SL:
                trades.append(-SL * WIN_PV)
                position = 0
            elif position == 1 and (zk >= -0.8 or zj >= -0.8):
                trades.append(diff * WIN_PV)
                position = 0
            elif position == -1 and (zk <= 0.8 or zj <= 0.8):
                trades.append(diff * WIN_PV)
                position = 0
    return trades

init_mt5()
win = fetch(SYMBOL_A, BARS_FETCH)
wdo = fetch(SYMBOL_B, BARS_FETCH)
di = fetch(DI_SYMBOL, BARS_FETCH)
mt5.shutdown()

k_z, j_z = get_base_zscores(win, wdo, di)
trades = simulate(k_z, j_z, win)

cum_pnl = np.cumsum(trades)
max_drawdown = 0
peak = 0
for pnl in cum_pnl:
    if pnl > peak: peak = pnl
    dd = peak - pnl
    if dd > max_drawdown: max_drawdown = dd

wins = [t for t in trades if t > 0]
losses = [t for t in trades if t <= 0]
gross_profit = sum(wins)
gross_loss = abs(sum(losses))
profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

print(f"Total PnL: R$ {sum(trades):.2f}")
print(f"Max Drawdown: R$ {max_drawdown:.2f}")
print(f"Trades: {len(trades)}")
print(f"Win Rate: {len(wins)/len(trades)*100:.1f}%")
print(f"Profit Factor: {profit_factor:.2f}")
print(f"Avg Win: R$ {np.mean(wins):.2f}")
print(f"Avg Loss: R$ {np.mean(losses):.2f}")

plt.figure(figsize=(10,5))
plt.plot(cum_pnl, color='#00e87a', linewidth=2)
plt.fill_between(range(len(cum_pnl)), cum_pnl, alpha=0.1, color='#00e87a')
plt.title(f"Setup Matador Novo (Kalman+Johansen)\nConsenso | TP:{TP} SL:{SL} | Z_Ent:{Z_ENT} Z_Att:{Z_ATT}", color='white')
plt.ylabel("PnL Acumulado (R$)", color='white')
plt.xlabel("Trade ID", color='white')
plt.grid(True, alpha=0.2)
plt.gca().set_facecolor('#1c2e3a')
plt.gcf().set_facecolor('#1c2e3a')
plt.tick_params(colors='white')
plt.tight_layout()
os.makedirs('C:/Users/ryzen/.gemini/antigravity/brain/fc6451b4-bddf-4818-a66a-3ab76bd4e8ac', exist_ok=True)
plt.savefig('C:/Users/ryzen/.gemini/antigravity/brain/fc6451b4-bddf-4818-a66a-3ab76bd4e8ac/equity_curve.png')
print("Grafico salvo.")
