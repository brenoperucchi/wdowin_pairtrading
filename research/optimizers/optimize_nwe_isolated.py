import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

BARS_FETCH = 15000
WIN_PV = 0.20

# Setup Matador Core Parameters
K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60

# Setup Matador Rules
Z_ENT = 1.4
TP, SL = 800, 300

def init_mt5():
    mt5.initialize(path=MT5_PATH)

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    return np.array([r[4] for r in rates], dtype=float)

def get_base_zscores(win_c, wdo_c, di_c):
    print("Calculando matrizes base WDO e DI...")
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    spreads = []
    for y, x in zip(win_c, wdo_c):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))
    
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

def calc_nwe(prices, bandwidth, lookback):
    n = len(prices)
    nwe = np.zeros(n)
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            nwe[t] = prices[t]
            continue
        i_arr = np.arange(lb + 1)
        w = np.exp(-(i_arr * i_arr) / (2 * bandwidth * bandwidth))
        p_slice = prices[t - lb : t + 1][::-1]
        nwe[t] = np.sum(p_slice * w) / np.sum(w)
    return nwe

def simulate_isolated(z_array, win_c, nwe_is_up, filter_mode):
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(1000, len(win_c)):
        z, price = z_array[i], win_c[i]
        
        # Sinais isolados
        sig_buy = z <= -Z_ENT
        sig_sell = z >= Z_ENT
        
        up = nwe_is_up[i]
        if filter_mode == "fader":
            # Contra tendencia: so compra se tendencia estiver VERMELHA (down)
            if sig_buy and up: sig_buy = False
            # so vende se tendencia estiver VERDE (up)
            if sig_sell and not up: sig_sell = False
            
        if position == 0:
            if sig_buy:
                position = 1
                entry_price = price
            elif sig_sell:
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
    if not trades: return {"pnl": 0, "dd": 0, "trades": 0, "wr": 0, "pf": 0, "sharpe": 0}
    cum_pnl = np.cumsum(trades)
    max_dd, peak = 0, 0
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
        "sharpe": sharpe
    }

def main():
    init_mt5()
    win = fetch(SYMBOL_A, BARS_FETCH)
    wdo = fetch(SYMBOL_B, BARS_FETCH)
    di = fetch(DI_SYMBOL, BARS_FETCH)
    mt5.shutdown()

    k_z, j_z = get_base_zscores(win, wdo, di)

    print("\nCalculando NWE (Bandwidth=8, Lookback=20)...")
    bw = 8
    lb = 20
    nwe = calc_nwe(win, bw, lb)
    is_up = np.zeros(len(nwe), dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True
    
    # Base sem NWE
    t_wdo_base = simulate_isolated(k_z, win, is_up, "none")
    s_wdo_base = calc_stats(t_wdo_base)
    t_di_base = simulate_isolated(j_z, win, is_up, "none")
    s_di_base = calc_stats(t_di_base)

    # Com Filtro Contra-Tendencia
    t_wdo_fader = simulate_isolated(k_z, win, is_up, "fader")
    s_wdo_fader = calc_stats(t_wdo_fader)
    
    t_di_fader = simulate_isolated(j_z, win, is_up, "fader")
    s_di_fader = calc_stats(t_di_fader)

    print("\n=== WDO (Kalman) ISOLADO ===")
    print(f"Sem Filtro NWE: PnL R${s_wdo_base['pnl']:.2f} | Trades {s_wdo_base['trades']} | WR {s_wdo_base['wr']:.1f}% | DD R${s_wdo_base['dd']:.2f} | Sharpe {s_wdo_base['sharpe']:.2f}")
    print(f"Com NWE Fader : PnL R${s_wdo_fader['pnl']:.2f} | Trades {s_wdo_fader['trades']} | WR {s_wdo_fader['wr']:.1f}% | DD R${s_wdo_fader['dd']:.2f} | Sharpe {s_wdo_fader['sharpe']:.2f}")

    print("\n=== DI (Johansen) ISOLADO ===")
    print(f"Sem Filtro NWE: PnL R${s_di_base['pnl']:.2f} | Trades {s_di_base['trades']} | WR {s_di_base['wr']:.1f}% | DD R${s_di_base['dd']:.2f} | Sharpe {s_di_base['sharpe']:.2f}")
    print(f"Com NWE Fader : PnL R${s_di_fader['pnl']:.2f} | Trades {s_di_fader['trades']} | WR {s_di_fader['wr']:.1f}% | DD R${s_di_fader['dd']:.2f} | Sharpe {s_di_fader['sharpe']:.2f}")

if __name__ == "__main__":
    main()
