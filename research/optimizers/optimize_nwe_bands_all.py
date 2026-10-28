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
Z_ATT = 1.2
TP, SL = 800, 300

def init_mt5():
    mt5.initialize(path=MT5_PATH)

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    return np.array([r[4] for r in rates], dtype=float)

def get_base_zscores(win_c, wdo_c, di_c):
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

def calc_nwe_with_bands(prices, bandwidth, lookback, mult_mae=3.0):
    n = len(prices)
    nwe = np.zeros(n)
    mae = np.zeros(n)
    
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            nwe[t] = prices[t]
            continue
        i_arr = np.arange(lb + 1)
        w = np.exp(-(i_arr * i_arr) / (2 * bandwidth * bandwidth))
        p_slice = prices[t - lb : t + 1][::-1]
        nwe[t] = np.sum(p_slice * w) / np.sum(w)
        
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            continue
        nwe_slice = nwe[t - lb : t + 1]
        p_slice = prices[t - lb : t + 1]
        err = np.abs(p_slice - nwe_slice)
        mae[t] = np.mean(err) * mult_mae
        
    upper = nwe + mae
    lower = nwe - mae
    return nwe, upper, lower

def simulate_nwe_bands(k_z, j_z, win_c, nwe_is_up, upper, lower, threshold_pct, mode="consensus"):
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(1000, len(win_c)):
        zw, zd, price = k_z[i], j_z[i], win_c[i]
        
        sig_buy = False
        sig_sell = False
        
        if mode == "consensus":
            sig_buy = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
            sig_sell = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)
        elif mode == "wdo":
            sig_buy = (zw <= -Z_ENT)
            sig_sell = (zw >= Z_ENT)
        elif mode == "di":
            sig_buy = (zd <= -Z_ENT)
            sig_sell = (zd >= Z_ENT)
        
        up = nwe_is_up[i]
        
        # Filtro de Banda Fader (Contra-tendencia e na beira da banda)
        if sig_buy:
            if up: 
                sig_buy = False # O NWE tem que estar vermelho
            else:
                dist_pct = (price - lower[i]) / lower[i] * 100.0
                if dist_pct > threshold_pct: 
                    sig_buy = False # Muito longe da banda inferior
                    
        if sig_sell:
            if not up:
                sig_sell = False # O NWE tem que estar verde
            else:
                dist_pct = (upper[i] - price) / upper[i] * 100.0
                if dist_pct > threshold_pct:
                    sig_sell = False # Muito longe da banda superior
                    
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
            # Mean reversion logica
            elif position == 1:
                if mode == "consensus" and (zw >= -0.8 or zd >= -0.8): trades.append(diff * WIN_PV); position = 0
                elif mode == "wdo" and zw >= -0.8: trades.append(diff * WIN_PV); position = 0
                elif mode == "di" and zd >= -0.8: trades.append(diff * WIN_PV); position = 0
            elif position == -1:
                if mode == "consensus" and (zw <= 0.8 or zd <= 0.8): trades.append(diff * WIN_PV); position = 0
                elif mode == "wdo" and zw <= 0.8: trades.append(diff * WIN_PV); position = 0
                elif mode == "di" and zd <= 0.8: trades.append(diff * WIN_PV); position = 0
                
    return trades

def calc_stats(trades):
    if not trades: return {"pnl": 0, "dd": 0, "trades": 0, "wr": 0, "pf": 0, "sharpe": 0, "ret_dd": 0}
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
        
    # Recovery Factor (Retorno Absoluto sobre Drawdown Maximo)
    ret_dd = sum(trades) / max_dd if max_dd > 0 else (999.0 if sum(trades) > 0 else 0)
    
    return {
        "pnl": sum(trades),
        "dd": max_dd,
        "trades": len(trades),
        "wr": len(wins)/len(trades)*100 if trades else 0,
        "pf": profit_factor,
        "sharpe": sharpe,
        "ret_dd": ret_dd
    }

def print_result(s, th):
    print(f"DistMax: {th:5.2f}% | PnL: R${s['pnl']:7.2f} | Trades: {s['trades']:3d} | WR: {s['wr']:4.1f}% | DD: R${s['dd']:6.2f} | Ret/DD: {s['ret_dd']:5.2f}")

def main():
    print("Iniciando coleta de dados (MT5)...")
    init_mt5()
    win = fetch(SYMBOL_A, BARS_FETCH)
    wdo = fetch(SYMBOL_B, BARS_FETCH)
    di = fetch(DI_SYMBOL, BARS_FETCH)
    mt5.shutdown()

    k_z, j_z = get_base_zscores(win, wdo, di)
    
    bw, lb = 8, 20
    print(f"Calculando NWE (BW={bw}, LB={lb})...")
    nwe, upper, lower = calc_nwe_with_bands(win, bw, lb, mult_mae=3.0)
    is_up = np.zeros(len(nwe), dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True

    thresholds = np.arange(-0.06, 0.13, 0.02)
    
    print("\n" + "="*80)
    print(" 1. Setup CONSENSO (WDO + DI) + Filtro Banda NWE")
    print("="*80)
    for th in thresholds:
        t = simulate_nwe_bands(k_z, j_z, win, is_up, upper, lower, th, mode="consensus")
        print_result(calc_stats(t), th)

    print("\n" + "="*80)
    print(" 2. Setup ISOLADO: Apenas WDO + Filtro Banda NWE")
    print("="*80)
    for th in thresholds:
        t = simulate_nwe_bands(k_z, j_z, win, is_up, upper, lower, th, mode="wdo")
        print_result(calc_stats(t), th)

    print("\n" + "="*80)
    print(" 3. Setup ISOLADO: Apenas DI + Filtro Banda NWE")
    print("="*80)
    for th in thresholds:
        t = simulate_nwe_bands(k_z, j_z, win, is_up, upper, lower, th, mode="di")
        print_result(calc_stats(t), th)

if __name__ == "__main__":
    main()
