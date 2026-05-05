"""Inject simulated trades for target date into the live dashboard database."""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

TARGET_DATES = [
    "2026-04-22", "2026-04-23", "2026-04-24", "2026-04-25",
    "2026-04-28", "2026-04-29", "2026-04-30", "2026-05-04"
]
DB_PATH = "trades.db"

WIN_PV = 0.20
K_Q, K_R, K_W = 1e-4, 1e2, 40          # WDO Kalman
DI_KQ, DI_KR, DI_KW = 1e-3, 1e1, 60    # DI Kalman
Z_ENT = 1.4
Z_ATT = 1.2
TP, SL, BE = 800, 300, 300
FORCE_CLOSE_MIN = 17 * 60 + 40
ENTRY_START_MIN = 9 * 60
ENTRY_END_MIN = 15 * 60
TIME_OFFSET = 0


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

def simulate_trades(k_z, j_z, win_c, wdo_c, bar_times, mode, nwe_is_up, upper, lower, band_mult):
    n = len(win_c)
    trades = []
    position = 0
    entry_price_win = 0
    entry_price_wdo = 0
    entry_time = None
    entry_z_w = 0.0
    entry_z_d = 0.0
    be_hit = False
    
    for i in range(1000, n):
        zw, zd, price_win, price_wdo = k_z[i], j_z[i], win_c[i], wdo_c[i]
        local_ts = bar_times[i] + TIME_OFFSET
        dt = datetime.utcfromtimestamp(local_ts)
        t_min = dt.hour * 60 + dt.minute
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        date_str = dt.strftime("%Y-%m-%d")
        
        # Force Close
        if position != 0 and t_min >= FORCE_CLOSE_MIN:
            diff = (price_win - entry_price_win) if position == 1 else (entry_price_win - price_win)
            pnl = diff * WIN_PV * 2 # 2 contracts
            trades.append({
                "strategy": mode.upper(),
                "direction": "BUY" if position == 1 else "SELL",
                "timestamp_in": entry_time,
                "timestamp_out": dt_str,
                "price_win_in": entry_price_win,
                "price_wdo_in": entry_price_wdo,
                "price_win_out": price_win,
                "price_wdo_out": price_wdo,
                "z_in_w": entry_z_w,
                "z_in_d": entry_z_d,
                "pnl": pnl,
                "exit_reason": "FORCE_CLOSE",
                "date_in": entry_time.split()[0]
            })
            position = 0
            continue
        
        sig_buy = False
        sig_sell = False
        
        if mode == "wdo_nwe":
            sig_buy = (zw <= -Z_ENT)
            sig_sell = (zw >= Z_ENT)
        elif mode == "di_nwe":
            sig_buy = (zd <= -Z_ENT)
            sig_sell = (zd >= Z_ENT)
        elif mode == "cons_base":
            # Consensus: both z-scores aligned, NO NWE filter
            sig_buy = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
            sig_sell = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)
            
        # NWE filter (only for wdo_nwe and di_nwe, NOT for cons_base)
        if mode != "cons_base":
            band_width = upper[i] - lower[i]
            if band_width < 1e-10: band_width = 1.0
            up = nwe_is_up[i]
            if sig_buy:
                if up: sig_buy = False
                else:
                    if price_win > lower[i] + band_width * band_mult: sig_buy = False
            if sig_sell:
                if not up: sig_sell = False
                else:
                    if price_win < upper[i] - band_width * band_mult: sig_sell = False

        if position == 0:
            if t_min < ENTRY_START_MIN or t_min > ENTRY_END_MIN:
                sig_buy = False
                sig_sell = False
                
            if sig_buy:
                position = 1
                entry_price_win = price_win
                entry_price_wdo = price_wdo
                entry_time = dt_str
                entry_z_w = round(float(zw), 2)
                entry_z_d = round(float(zd), 2)
                be_hit = False
            elif sig_sell:
                position = -1
                entry_price_win = price_win
                entry_price_wdo = price_wdo
                entry_time = dt_str
                entry_z_w = round(float(zw), 2)
                entry_z_d = round(float(zd), 2)
                be_hit = False
        else:
            diff = (price_win - entry_price_win) if position == 1 else (entry_price_win - price_win)
            
            if not be_hit and diff >= BE:
                be_hit = True
                
            pnl = None
            reason = None
            if diff >= TP:
                pnl = TP * WIN_PV * 2
                reason = "TARGET"
            elif be_hit and diff <= 0:
                pnl = 0
                reason = "BE_STOP"
            elif not be_hit and diff <= -SL:
                pnl = -SL * WIN_PV * 2
                reason = "STOP_LOSS"
            
            if pnl is not None:
                trades.append({
                    "strategy": mode.upper(),
                    "direction": "BUY" if position == 1 else "SELL",
                    "timestamp_in": entry_time,
                    "timestamp_out": dt_str,
                    "price_win_in": entry_price_win,
                    "price_wdo_in": entry_price_wdo,
                    "price_win_out": price_win,
                    "price_wdo_out": price_wdo,
                    "z_in_w": entry_z_w,
                    "z_in_d": entry_z_d,
                    "pnl": pnl,
                    "exit_reason": reason,
                    "date_in": entry_time.split()[0]
                })
                position = 0
                
    return trades

def main():
    mt5.initialize(path=MT5_PATH)
    rates_w = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 15000)
    rates_d = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, 15000)
    rates_di = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, 15000)
    mt5.shutdown()

    win = np.array([r[4] for r in rates_w], dtype=float)
    wdo = np.array([r[4] for r in rates_d], dtype=float)
    di  = np.array([r[4] for r in rates_di], dtype=float)
    times = np.array([r[0] for r in rates_w], dtype=np.int64)

    # Align WIN and WDO by taking the newest N bars (matching server.py logic)
    n_wdo = min(len(win), len(wdo))
    win = win[-n_wdo:]
    wdo = wdo[-n_wdo:]
    times = times[-n_wdo:]

    # Calculate WDO Kalman Z-Score
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    spreads = []
    for y, x in zip(win, wdo):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))

    # Align WIN and DI for the DI Kalman filter (matching server.py logic)
    n_di = min(len(win), len(di))
    win_for_di = win[-n_di:]
    di_c = di[-n_di:]
    times_di = np.array([r[0] for r in rates_di], dtype=np.int64)[-n_di:]

    # Calculate DI Kalman Z-Score
    kf_di = KalmanBetaFilter(initial_beta=-10000.0, trans_cov=DI_KQ, obs_cov=DI_KR)
    spreads_di = []
    for y, x in zip(win_for_di, di_c):
        _, spread, _ = kf_di.update(float(y), float(x))
        spreads_di.append(spread)
    z_di_arr = np.array(KalmanBetaFilter.rolling_zscore(spreads_di, window=DI_KW))

    # Map DI z-scores by exact timestamp
    z_di_map = {}
    for i, t in enumerate(times_di):
        z_di_map[t] = float(z_di_arr[i]) if i < len(z_di_arr) else 0.0

    # Align DI z-scores to the WIN timeline
    di_z = np.zeros(n_wdo)
    for i, t in enumerate(times):
        val = z_di_map.get(t)
        di_z[i] = val if val is not None else 0.0
    nwe, upper, lower = calc_nwe_with_bands(win, 8, 95, 3.0)
    is_up = np.zeros(len(nwe), dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True

    t_wdo = simulate_trades(k_z, di_z, win, wdo, times, "wdo_nwe", is_up, upper, lower, 0.10)
    t_di = simulate_trades(k_z, di_z, win, wdo, times, "di_nwe", is_up, upper, lower, 0.10)
    t_cons = simulate_trades(k_z, di_z, win, wdo, times, "cons_base", is_up, upper, lower, 0.10)

    all_trades = t_wdo + t_di + t_cons

    # Inject into DB for all target dates
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    total_injected = 0
    for target_date in TARGET_DATES:
        date_trades = [t for t in all_trades if t["date_in"] == target_date]
        # Clear existing trades for this date
        c.execute("DELETE FROM matador_ops WHERE timestamp_in LIKE ?", (f"{target_date}%",))

        for t in date_trades:
            c.execute('''
                INSERT INTO matador_ops (
                    timestamp_in, status, direction, z_in, z_source, strategy,
                    rho_in, beta_in, qty_win, price_win_in, price_wdo_in,
                    timestamp_out, price_win_out, price_wdo_out, pnl_brl, exit_reason
                ) VALUES (?, 'CLOSED', ?, ?, 'V2_KALMAN', ?, ?, -20.0, 2, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                t["timestamp_in"], t["direction"], t["z_in_w"], t["strategy"],
                t["z_in_d"], t["price_win_in"], t["price_wdo_in"],
                t["timestamp_out"], t["price_win_out"], t["price_wdo_out"], t["pnl"], t["exit_reason"]
            ))

        if date_trades:
            pnl_day = sum(t["pnl"] for t in date_trades)
            print(f"  {target_date}: {len(date_trades)} trades | PnL: R${pnl_day:.2f}")
            for t in date_trades:
                print(f"    [{t['strategy']:>10s}] {t['direction']:4s} {t['timestamp_in']} -> {t['timestamp_out']} | R${t['pnl']:.2f} ({t['exit_reason']})")
        else:
            print(f"  {target_date}: 0 trades")
        total_injected += len(date_trades)

    conn.commit()
    conn.close()
    print(f"\nTotal injected: {total_injected} trades across {len(TARGET_DATES)} days")

if __name__ == "__main__":
    main()
