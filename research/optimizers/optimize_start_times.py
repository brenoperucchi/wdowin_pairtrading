import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

def calc_stats_from_pnl_array(pnl_array):
    trades = pnl_array[pnl_array != 0]
    total_trades = len(trades)
    if total_trades == 0:
        return {"pnl": 0, "trades": 0, "wr": 0.0, "dd": 0.0, "ret_dd": 0.0}
    
    total_pnl = np.sum(trades)
    wins = np.sum(trades > 0)
    wr = (wins / total_trades) * 100.0
    
    cum_pnl = np.cumsum(trades)
    max_cum = np.maximum.accumulate(cum_pnl)
    drawdowns = max_cum - cum_pnl
    max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0
    if max_dd < 1e-5: max_dd = 1.0
    
    ret_dd = total_pnl / max_dd
    
    return {
        "pnl": total_pnl,
        "trades": total_trades,
        "wr": wr,
        "dd": max_dd,
        "ret_dd": ret_dd
    }

def simulate(k_z, j_z, win_c, bar_times, mode, nwe_is_up, upper, lower, threshold_pct, start_m, end_m):
    n = len(win_c)
    pnl_array = np.zeros(n)
    
    position = 0
    entry_price = 0
    
    for i in range(1000, n):
        zw, zd, price = k_z[i], j_z[i], win_c[i]
        
        dt = datetime.utcfromtimestamp(bar_times[i])
        t_min = dt.hour * 60 + dt.minute
        
        if position != 0 and t_min >= 17*60+40:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            pnl_array[i] = diff * 0.20
            position = 0
            continue
        
        sig_buy = False
        sig_sell = False
        
        if mode == "wdo":
            sig_buy = (zw <= -1.4)
            sig_sell = (zw >= 1.4)
        elif mode == "di":
            sig_buy = (zd <= -1.4)
            sig_sell = (zd >= 1.4)
            
        up = nwe_is_up[i]
        if sig_buy:
            if up: sig_buy = False
            else:
                dist_pct = (price - lower[i]) / lower[i] * 100.0
                if dist_pct > threshold_pct: sig_buy = False
        if sig_sell:
            if not up: sig_sell = False
            else:
                dist_pct = (upper[i] - price) / upper[i] * 100.0
                if dist_pct > threshold_pct: sig_sell = False

        if position == 0:
            if t_min < start_m or t_min > end_m:
                sig_buy = False
                sig_sell = False
                
            if sig_buy:
                position = 1
                entry_price = price
                be_hit = False
            elif sig_sell:
                position = -1
                entry_price = price
                be_hit = False
        else:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            
            # BE Logic
            if not be_hit and diff >= 300:
                be_hit = True
                
            if diff >= 800:
                pnl_array[i] = 800 * 0.20
                position = 0
            elif be_hit and diff <= 0:
                pnl_array[i] = 0
                position = 0
            elif not be_hit and diff <= -300:
                pnl_array[i] = -300 * 0.20
                position = 0
                
    return pnl_array

def main():
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

    # Calc z-scores
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=1e-4, obs_cov=1e2)
    spreads = []
    for y, x in zip(win, wdo):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=40))

    betas = np.zeros(n)
    for i in range(150, n, 12):
        y_data = np.column_stack([win[i-150:i], di[i-150:i]])
        try:
            res = coint_johansen(y_data, det_order=0, k_ar_diff=1)
            vec = res.evec[:, 0]
            betas[i] = float(vec[1] / vec[0])
        except:
            betas[i] = betas[i-1] if i > 0 else 0
    for i in range(150, n):
        if betas[i] == 0: betas[i] = betas[i-1]
            
    spread_di = win + betas * di
    j_z = np.zeros(n)
    for i in range(150 + 60, n):
        ws = spread_di[i - 60:i]
        mu, sd = np.mean(ws), np.std(ws)
        j_z[i] = (spread_di[i] - mu) / (sd if sd > 1e-10 else 1.0)
        
    # Calc NWE
    nwe = np.zeros(n)
    mae = np.zeros(n)
    bandwidth = 8
    lookback = 20
    mult_mae = 3.0
    
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            nwe[t] = win[t]
            continue
        i_arr = np.arange(lb + 1)
        w = np.exp(-(i_arr * i_arr) / (2 * bandwidth * bandwidth))
        p_slice = win[t - lb : t + 1][::-1]
        nwe[t] = np.sum(p_slice * w) / np.sum(w)
        
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0: continue
        err = np.abs(win[t - lb : t + 1] - nwe[t - lb : t + 1])
        mae[t] = np.mean(err) * mult_mae
        
    upper = nwe + mae
    lower = nwe - mae
    is_up = np.zeros(n, dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True

    print(f"{'START':<8} | {'PNL':<10} | {'DD':<8} | {'RET/DD':<8} | {'TRADES':<8} | {'WIN RATE'}")
    print("-" * 65)

    starts = [0, 5, 10, 15, 30]
    for start in starts:
        start_m = 9 * 60 + start
        end_m = 15 * 60
        pnl_wdo = simulate(k_z, j_z, win, times, "wdo", is_up, upper, lower, 0.14, start_m, end_m)
        pnl_di = simulate(k_z, j_z, win, times, "di", is_up, upper, lower, 0.14, start_m, end_m)
        pnl_portfolio = pnl_wdo + pnl_di
        
        s_port = calc_stats_from_pnl_array(pnl_portfolio)
        start_str = f"09:{start:02d}"
        print(f"{start_str:<8} | R${s_port['pnl']:<8.2f} | R${s_port['dd']:<6.2f} | {s_port['ret_dd']:<8.2f} | {s_port['trades']:<8d} | {s_port['wr']:.1f}%")

if __name__ == "__main__":
    main()
