import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

BARS_FETCH = 15000
WIN_PV = 0.20
K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60
Z_ENT, Z_ATT, TP, SL = 1.4, 1.2, 800, 300

def init_mt5(): mt5.initialize(path=MT5_PATH)

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
    nwe, mae = np.zeros(n), np.zeros(n)
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
        if lb == 0: continue
        err = np.abs(prices[t - lb : t + 1] - nwe[t - lb : t + 1])
        mae[t] = np.mean(err) * mult_mae
    return nwe, nwe + mae, nwe - mae

def simulate(k_z, j_z, win_c, mode, nwe_is_up=None, upper=None, lower=None, threshold_pct=None):
    n = len(win_c)
    pnl_array = np.zeros(n)
    position = 0
    entry_price = 0
    for i in range(1000, n):
        zw, zd, price = k_z[i], j_z[i], win_c[i]
        sig_buy, sig_sell = False, False
        if mode == "consensus":
            sig_buy = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
            sig_sell = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)
        elif mode == "wdo":
            sig_buy, sig_sell = (zw <= -Z_ENT), (zw >= Z_ENT)
        elif mode == "di":
            sig_buy, sig_sell = (zd <= -Z_ENT), (zd >= Z_ENT)
            
        if nwe_is_up is not None:
            up = nwe_is_up[i]
            if sig_buy:
                if up: sig_buy = False
                elif ((price - lower[i]) / lower[i] * 100.0) > threshold_pct: sig_buy = False
            if sig_sell:
                if not up: sig_sell = False
                elif ((upper[i] - price) / upper[i] * 100.0) > threshold_pct: sig_sell = False

        if position == 0:
            if sig_buy: position, entry_price = 1, price
            elif sig_sell: position, entry_price = -1, price
        else:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            if diff >= TP: pnl_array[i], position = TP * WIN_PV, 0
            elif diff <= -SL: pnl_array[i], position = -SL * WIN_PV, 0
            elif position == 1:
                if mode == "consensus" and (zw >= -0.8 or zd >= -0.8): pnl_array[i], position = diff * WIN_PV, 0
                elif mode == "wdo" and zw >= -0.8: pnl_array[i], position = diff * WIN_PV, 0
                elif mode == "di" and zd >= -0.8: pnl_array[i], position = diff * WIN_PV, 0
            elif position == -1:
                if mode == "consensus" and (zw <= 0.8 or zd <= 0.8): pnl_array[i], position = diff * WIN_PV, 0
                elif mode == "wdo" and zw <= 0.8: pnl_array[i], position = diff * WIN_PV, 0
                elif mode == "di" and zd <= 0.8: pnl_array[i], position = diff * WIN_PV, 0
    return pnl_array

def main():
    init_mt5()
    win = fetch(SYMBOL_A, BARS_FETCH)
    wdo = fetch(SYMBOL_B, BARS_FETCH)
    di = fetch(DI_SYMBOL, BARS_FETCH)
    mt5.shutdown()

    k_z, j_z = get_base_zscores(win, wdo, di)
    nwe, upper, lower = calc_nwe_with_bands(win, 8, 20)
    is_up = np.zeros(len(nwe), dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True

    p_cons = simulate(k_z, j_z, win, mode="consensus")
    p_wdo = simulate(k_z, j_z, win, mode="wdo", nwe_is_up=is_up, upper=upper, lower=lower, threshold_pct=0.04)
    p_di = simulate(k_z, j_z, win, mode="di", nwe_is_up=is_up, upper=upper, lower=lower, threshold_pct=0.04)

    # 1 bar = 5 mins. 100 bars = 1 trading day (approx)
    # We aggregate PnL into 1-day bins
    bins = 150
    p_cons_daily = [np.sum(p_cons[i*100:(i+1)*100]) for i in range(bins)]
    p_wdo_daily = [np.sum(p_wdo[i*100:(i+1)*100]) for i in range(bins)]
    p_di_daily = [np.sum(p_di[i*100:(i+1)*100]) for i in range(bins)]

    matrix = np.corrcoef([p_cons_daily, p_wdo_daily, p_di_daily])
    
    import pandas as pd
    df = pd.DataFrame(matrix, columns=["Consenso", "WDO Isolado", "DI Isolado"], index=["Consenso", "WDO Isolado", "DI Isolado"])
    print("\nMATRIZ DE CORRELACAO (Retornos Diarios - Janela de 100 Barras)")
    print(df.round(2))

if __name__ == "__main__":
    main()
