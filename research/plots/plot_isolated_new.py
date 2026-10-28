"""
Fase 3: Verificação Anti-Overfitting (Isolados vs Consenso)
Rodar os modelos separadamente e provar a robustez estrutural do Consenso.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
import matplotlib.pyplot as plt
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL
from datetime import datetime

TIME_OFFSET = 3 * 3600
FORCE_CLOSE_MIN = 17 * 60 + 40

def bar_minute_of_day(ts):
    local_ts = ts + TIME_OFFSET
    dt = datetime.utcfromtimestamp(local_ts)
    return dt.hour * 60 + dt.minute

# ─── Configuração (Resultado da Fase 1 e 2) ─────────────────────────────────
BARS_FETCH = 15000         # ~6 Meses M5
WIN_PV = 0.20

K_Q = 1e-4
K_R = 1e2
K_W = 40

J_JW = 150
J_ZW = 60

Z_ENTRY = 1.4
Z_ATTENTION = 1.2
TP = 800
SL = 300
BE = 300

# ─── Funções ───────────────────────────────────────────────────────────────
def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        sys.exit(1)

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    closes = np.array([r[4] for r in rates], dtype=float)
    times = np.array([r[0] for r in rates], dtype=np.int64)
    return closes, times

def simulate_isolated(k_z, j_z, prices, times, mode):
    position = 0
    entry_price = 0
    trades = []
    pnl_array = np.zeros(len(prices))
    be_hit = False
    
    bar_mins = np.array([bar_minute_of_day(t) for t in times])
    
    for i in range(1000, len(prices)):
        zk, zj, price = k_z[i], j_z[i], prices[i]
        t_min = bar_mins[i]
        
        # ── Force Close at 17:40 ──
        if position != 0 and t_min >= FORCE_CLOSE_MIN:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            pnl_array[i] = diff * WIN_PV
            position = 0
            continue
        
        if position == 0:
            buy_sig = False
            sell_sig = False
            
            if mode == "wdo":
                buy_sig = (zk <= -Z_ENTRY)
                sell_sig = (zk >= Z_ENTRY)
            elif mode == "di":
                buy_sig = (zj <= -Z_ENTRY)
                sell_sig = (zj >= Z_ENTRY)
            elif mode == "consensus":
                buy_sig = (zk <= -Z_ENTRY and zj <= -Z_ATTENTION) or (zk <= -Z_ATTENTION and zj <= -Z_ENTRY)
                sell_sig = (zk >= Z_ENTRY and zj >= Z_ATTENTION) or (zk >= Z_ATTENTION and zj >= Z_ENTRY)
                
            if buy_sig:
                position = 1
                entry_price = price
                be_hit = False
            elif sell_sig:
                position = -1
                entry_price = price
                be_hit = False
        else:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            
            if not be_hit and diff >= BE:
                be_hit = True
                
            if diff >= TP:
                pnl_array[i] = TP * WIN_PV
                position = 0
            elif be_hit and diff <= 0:
                pnl_array[i] = 0
                position = 0
            elif not be_hit and diff <= -SL:
                pnl_array[i] = -SL * WIN_PV
                position = 0
                
    # Fechar no ultimo tick se aberto
    if position != 0:
        diff = (prices[-1] - entry_price) if position == 1 else (entry_price - prices[-1])
        pnl_array[-1] = diff * WIN_PV
        
    cum_pnl = np.cumsum(pnl_array)
    trades_list = [p for p in pnl_array if p != 0]
    n_trades = len(trades_list)
    wr = sum(1 for p in trades_list if p > 0) / n_trades * 100 if n_trades > 0 else 0
    
    peak = np.maximum.accumulate(cum_pnl)
    dd = peak - cum_pnl
    max_dd = np.max(dd) if len(dd) > 0 else 0
    
    return cum_pnl, n_trades, wr, max_dd, sum(trades_list)

def main():
    init_mt5()
    print(f"Baixando {BARS_FETCH} barras M5...")
    win, win_times = fetch(SYMBOL_A, BARS_FETCH)
    wdo, _ = fetch(SYMBOL_B, BARS_FETCH)
    di, _ = fetch(DI_SYMBOL, BARS_FETCH)
    mt5.shutdown()
    
    print("Gerando Z-Scores Base (Fase 1 params)...")
    # Kalman
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    spreads = []
    for y, x in zip(win, wdo):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))
    
    # Johansen
    n = len(win)
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
        window_spread = spread_di[i - J_ZW:i]
        mu = np.mean(window_spread)
        sd = np.std(window_spread)
        if sd < 1e-10: sd = 1.0
        j_z[i] = (spread_di[i] - mu) / sd
        
    print("Simulando...")
    c_wdo, t_wdo, wr_wdo, dd_wdo, pnl_wdo = simulate_isolated(k_z, j_z, win, win_times, "wdo")
    c_di, t_di, wr_di, dd_di, pnl_di = simulate_isolated(k_z, j_z, win, win_times, "di")
    c_cons, t_cons, wr_cons, dd_cons, pnl_cons = simulate_isolated(k_z, j_z, win, win_times, "consensus")
    
    print("\n========================================================")
    print("FASE 3: VERIFICACAO ANTI-OVERFITTING (6 Meses)")
    print("========================================================")
    print(f"1. WDO Kalman Isolado | PnL: R${pnl_wdo:.2f} | Trades: {t_wdo} | WR: {wr_wdo:.1f}% | DD: R${dd_wdo:.2f}")
    print(f"2. DI Johansen Isol | PnL: R${pnl_di:.2f} | Trades: {t_di} | WR: {wr_di:.1f}% | DD: R${dd_di:.2f}")
    print(f"3. CONSENSO CRUZADO   | PnL: R${pnl_cons:.2f} | Trades: {t_cons} | WR: {wr_cons:.1f}% | DD: R${dd_cons:.2f}")
    print("========================================================\n")
    
    plt.style.use('dark_background')
    plt.figure(figsize=(14, 7))
    plt.title(f"Isolamento de Variaveis: WDO vs DI vs Consenso (Sem Mean Reversion)\nTP {TP} | SL {SL} | Z-Ent {Z_ENTRY}")
    
    plt.plot(c_wdo, label=f"WDO Isolado (PnL R${pnl_wdo:.0f})", color='#ff3366', alpha=0.6, linewidth=1.5)
    plt.plot(c_di, label=f"DI Isolado (PnL R${pnl_di:.0f})", color='#33ccff', alpha=0.6, linewidth=1.5)
    plt.plot(c_cons, label=f"Consenso (PnL R${pnl_cons:.0f})", color='#00ffcc', linewidth=2.5)
    
    plt.axhline(0, color='gray', linestyle='--', alpha=0.5)
    plt.legend(loc='upper left', fontsize=12, framealpha=0.2)
    plt.grid(True, alpha=0.1)
    plt.tight_layout()
    
    os.makedirs(".planning/docs/assets", exist_ok=True)
    plt.savefig(".planning/docs/assets/isolated_curves_new.png", dpi=150)
    print("Grafico salvo em: .planning/docs/assets/isolated_curves_new.png")

if __name__ == "__main__":
    main()
