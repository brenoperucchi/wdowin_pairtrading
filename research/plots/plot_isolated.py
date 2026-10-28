import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
import matplotlib.pyplot as plt
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL
from core.kalman_filter import KalmanBetaFilter

# Configurações Ótimas já definidas
BARS_FETCH = 15000
WIN_PV = 0.20

K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60

Z_ENT = 1.4
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

def simulate_isolated(z_scores, win_c):
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(1000, len(win_c)):
        z, price = z_scores[i], win_c[i]
        
        if position == 0:
            if z <= -Z_ENT:
                position = 1
                entry_price = price
            elif z >= Z_ENT:
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
            elif position == 1 and z >= -0.8:
                trades.append(diff * WIN_PV)
                position = 0
            elif position == -1 and z <= 0.8:
                trades.append(diff * WIN_PV)
                position = 0
    return trades

def calc_stats(trades):
    cum_pnl = np.cumsum(trades)
    max_dd = 0
    peak = 0
    for pnl in cum_pnl:
        if pnl > peak: peak = pnl
        dd = peak - pnl
        if dd > max_dd: max_dd = dd
        
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    sharpe = 0
    if len(trades) > 1 and np.std(trades) > 0:
        sharpe = np.mean(trades) / np.std(trades) * np.sqrt(252)
        
    return {
        "pnl": sum(trades),
        "dd": max_dd,
        "trades": len(trades),
        "wr": len(wins)/len(trades)*100 if trades else 0,
        "pf": profit_factor,
        "sharpe": sharpe,
        "cum": cum_pnl
    }

init_mt5()
win = fetch(SYMBOL_A, BARS_FETCH)
wdo = fetch(SYMBOL_B, BARS_FETCH)
di = fetch(DI_SYMBOL, BARS_FETCH)
mt5.shutdown()

k_z, j_z = get_base_zscores(win, wdo, di)

print("Simulando WDO Isolado...")
t_wdo = simulate_isolated(k_z, win)
s_wdo = calc_stats(t_wdo)

print("Simulando DI Isolado...")
t_di = simulate_isolated(j_z, win)
s_di = calc_stats(t_di)

print("\n=== ESTATISTICAS ISOLADAS ===")
print(f"[WDO/Kalman] PnL: R${s_wdo['pnl']:.2f} | Trades: {s_wdo['trades']} | WR: {s_wdo['wr']:.1f}% | DD: R${s_wdo['dd']:.2f} | Sharpe: {s_wdo['sharpe']:.2f}")
print(f"[DI/Johansen] PnL: R${s_di['pnl']:.2f} | Trades: {s_di['trades']} | WR: {s_di['wr']:.1f}% | DD: R${s_di['dd']:.2f} | Sharpe: {s_di['sharpe']:.2f}")

fig, axs = plt.subplots(2, 1, figsize=(10, 8))

axs[0].plot(s_wdo['cum'], color='#00b4d8', linewidth=2)
axs[0].fill_between(range(len(s_wdo['cum'])), s_wdo['cum'], alpha=0.1, color='#00b4d8')
axs[0].set_title(f"Apenas WDO (Kalman) | PnL: R${s_wdo['pnl']:.0f} | DD: R${s_wdo['dd']:.0f} | Sharpe: {s_wdo['sharpe']:.2f}", color='white')
axs[0].set_ylabel("PnL (R$)", color='white')
axs[0].grid(True, alpha=0.2)
axs[0].set_facecolor('#1c2e3a')
axs[0].tick_params(colors='white')

axs[1].plot(s_di['cum'], color='#ffb703', linewidth=2)
axs[1].fill_between(range(len(s_di['cum'])), s_di['cum'], alpha=0.1, color='#ffb703')
axs[1].set_title(f"Apenas DI (Johansen) | PnL: R${s_di['pnl']:.0f} | DD: R${s_di['dd']:.0f} | Sharpe: {s_di['sharpe']:.2f}", color='white')
axs[1].set_ylabel("PnL (R$)", color='white')
axs[1].set_xlabel("Trade ID", color='white')
axs[1].grid(True, alpha=0.2)
axs[1].set_facecolor('#1c2e3a')
axs[1].tick_params(colors='white')

fig.patch.set_facecolor('#1c2e3a')
plt.tight_layout()
plt.savefig('C:/Users/ryzen/.gemini/antigravity/brain/fc6451b4-bddf-4818-a66a-3ab76bd4e8ac/isolated_curves.png')
print("Grafico salvo.")
