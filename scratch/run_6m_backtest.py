import sys, os
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

def fetch_bars(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    if rates is None: return None, None
    return rates['close'], rates['time']

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
        if lb == 0: continue
        err = np.abs(prices[t - lb : t + 1] - nwe[t - lb : t + 1])
        mae[t] = np.mean(err) * mult_mae
    return nwe, nwe + mae, nwe - mae

def main():
    if not mt5.initialize(path=MT5_PATH):
        print("MT5 Init Failed")
        return

    # Fetch ~6 months (approx 130 days * 108 bars/day = 14,040 bars). Fetching 20,000 to be safe.
    n_bars = 20000
    print(f"Fetching {n_bars} bars...")
    win_c, times = fetch_bars(SYMBOL_A, n_bars)
    wdo_c, _ = fetch_bars(SYMBOL_B, n_bars)
    di_c, _ = fetch_bars(DI_SYMBOL, n_bars)
    
    if win_c is None or wdo_c is None or di_c is None:
        print("Failed to fetch data.")
        return

    print("Running Continuous Kalman Filters...")
    # WDO
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=1e-4, obs_cov=1e2)
    spreads_wdo = []
    for y, x in zip(win_c, wdo_c):
        _, s, _ = kf.update(float(y), float(x))
        spreads_wdo.append(s)
    z_wdo = np.array(KalmanBetaFilter.rolling_zscore(spreads_wdo, window=40))

    # DI
    kf_di = KalmanBetaFilter(initial_beta=-10000.0, trans_cov=1e-3, obs_cov=1e1)
    spreads_di = []
    for y, x in zip(win_c, di_c):
        _, s, _ = kf_di.update(float(y), float(x))
        spreads_di.append(s)
    z_di = np.array(KalmanBetaFilter.rolling_zscore(spreads_di, window=60))

    print("Calculating NWE...")
    nwe, upper, lower = calc_nwe_with_bands(win_c, bandwidth=15.0, lookback=95, mult_mae=3.0)
    nwe_is_up = np.zeros(len(win_c), dtype=bool)
    for i in range(1, len(win_c)):
        nwe_is_up[i] = nwe[i] >= nwe[i-1]

    print("Simulating trades...")
    # We will simulate the Pure No-Rho Setup:
    # WDO > 1.4 -> SELL
    # WDO < -1.4 -> BUY
    # DI > 1.4 -> SELL
    # DI < -1.4 -> BUY
    # Consensus: WDO & DI agree
    
    WIN_PV = 0.20
    TP = 800 * WIN_PV * 2
    SL = -300 * WIN_PV * 2
    
    total_trades = 0
    total_pnl = 0.0
    wins = 0
    losses = 0
    
    # We'll allow taking multiple trades if signal fires, but to simulate "one position at a time per strategy"
    # we need to track if we are positioned. We will just simulate a simplified "Portfolio" that takes
    # exactly the same entries as the live engine when flat.
    
    position = 0
    entry_price = 0
    entry_time = None
    
    for i in range(1000, len(win_c)):
        local_ts = int(times[i])
        dt = datetime.fromtimestamp(local_ts)
        t_min = dt.hour * 60 + dt.minute
        
        # Close at end of day
        if position != 0 and t_min >= 17 * 60 + 40:
            diff = (win_c[i] - entry_price) if position == 1 else (entry_price - win_c[i])
            pnl = diff * WIN_PV * 2
            total_pnl += pnl
            if pnl > 0: wins += 1
            else: losses += 1
            total_trades += 1
            position = 0
            continue
            
        # Check targets/stops
        if position != 0:
            diff = (win_c[i] - entry_price) if position == 1 else (entry_price - win_c[i])
            pnl = diff * WIN_PV * 2
            if pnl >= TP:
                total_pnl += TP
                wins += 1
                total_trades += 1
                position = 0
            elif pnl <= SL:
                total_pnl += SL
                losses += 1
                total_trades += 1
                position = 0
            continue
            
        # Entry logic (Pure No-Rho, No NWE Filter for now to see RAW, or WITH NWE Filter)
        if position == 0 and (9 * 60) <= t_min <= (15 * 60):
            # Check WDO alone
            signal_buy = False
            signal_sell = False
            
            if z_wdo[i] <= -1.4: signal_buy = True
            elif z_wdo[i] >= 1.4: signal_sell = True
            
            if z_di[i] <= -1.4: signal_buy = True
            elif z_di[i] >= 1.4: signal_sell = True
            
            # Apply NWE block
            is_buy_blocked = nwe_is_up[i] or win_c[i] > lower[i]
            is_sell_blocked = not nwe_is_up[i] or win_c[i] < upper[i]
            
            if signal_buy and not is_buy_blocked:
                position = 1
                entry_price = win_c[i]
                entry_time = dt
            elif signal_sell and not is_sell_blocked:
                position = -1
                entry_price = win_c[i]
                entry_time = dt

    print(f"\\n--- 6 MONTH BACKTEST RESULTS (No Rho Filter) ---")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win Rate: {(wins/max(1, total_trades))*100:.2f}%")
    print(f"Total PnL: R$ {total_pnl:.2f}")

if __name__ == '__main__':
    main()
