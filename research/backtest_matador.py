import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, time

from core.config import MT5_PATH, SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME
from core.kalman_filter import KalmanBetaFilter
from core.signals import calc_beta_ols, calc_zscore

# ─── Configuration ──────────────────────────────────────────────────────────
WDO_KALMAN_W = 40
WDO_KALMAN_Q = 1e-4
WDO_KALMAN_R = 1e2
DI_KALMAN_W = 40
DI_BETA_REF_BARS = 2240

Z_ENTRY_DEFAULT = 2.0
Z_ATTENTION_DEFAULT = 1.4

BARS_TO_FETCH = 50000  # Aproximadamente 1 ano de barras M5

SCENARIOS = [
    {"name": "Matador Original", "sl": 300, "tp": 800, "be_act": 300, "be_lock": 0, "max_bars": None, "end_of_day": True, "z_entry": 1.4, "z_att": 1.2},
    {"name": "Scalp (Novo)", "sl": 250, "tp": 300, "be_act": 0, "be_lock": 0, "max_bars": None, "end_of_day": False, "z_entry": 2.0, "z_att": 1.4},
    {"name": "Tempo de Tela (Novo)", "sl": 510, "tp": 600, "be_act": 0, "be_lock": 0, "max_bars": 5, "end_of_day": False, "z_entry": 2.0, "z_att": 1.4},
    {"name": "Carregamento Intraday (Novo)", "sl": 560, "tp": 99999, "be_act": 0, "be_lock": 0, "max_bars": None, "end_of_day": True, "z_entry": 2.0, "z_att": 1.4},
]

def fetch_data():
    print(f"Connecting to MT5 at {MT5_PATH}...")
    if not mt5.initialize(path=MT5_PATH):
        print(f"MT5 Init Failed: {mt5.last_error()}")
        return None
    
    for sym in [SYMBOL_A, SYMBOL_B, DI_SYMBOL]:
        mt5.symbol_select(sym, True)
        
    print(f"Fetching {BARS_TO_FETCH} bars for {SYMBOL_A}, {SYMBOL_B}, and {DI_SYMBOL}...")
    win_rates = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, BARS_TO_FETCH)
    wdo_rates = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, BARS_TO_FETCH)
    di_rates = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, BARS_TO_FETCH)
    
    if win_rates is None or wdo_rates is None or di_rates is None:
        print("Error fetching data. Check symbols and MT5 connection.")
        return None
        
    df_win = pd.DataFrame(win_rates)
    df_win['time'] = pd.to_datetime(df_win['time'], unit='s')
    df_win.set_index('time', inplace=True)
    
    df_wdo = pd.DataFrame(wdo_rates)
    df_wdo['time'] = pd.to_datetime(df_wdo['time'], unit='s')
    df_wdo.set_index('time', inplace=True)
    
    df_di = pd.DataFrame(di_rates)
    df_di['time'] = pd.to_datetime(df_di['time'], unit='s')
    df_di.set_index('time', inplace=True)
    
    # Align data
    df = pd.DataFrame({
        'win': df_win['close'],
        'win_high': df_win['high'],
        'win_low': df_win['low'],
        'wdo': df_wdo['close'],
        'di': df_di['close']
    }).dropna()
    
    print(f"Data aligned: {len(df)} bars.")
    return df

def generate_signals(df):
    print("Generating signals (Kalman for WDO, OLS for DI)...")
    win = df['win'].values
    wdo = df['wdo'].values
    di = df['di'].values
    
    # WDO Kalman Z-Score
    kf = KalmanBetaFilter(initial_beta=-22.5, trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
    spreads_wdo = []
    for y, x in zip(win, wdo):
        beta, spread, _ = kf.update(float(y), float(x))
        spreads_wdo.append(spread)
    
    z_wdo = KalmanBetaFilter.rolling_zscore(spreads_wdo, window=WDO_KALMAN_W)
    df['z_wdo'] = z_wdo
    
    # DI Kalman Z-Score
    print("Calculating rolling DI Z-Scores (Kalman Puro)...")
    b, a = np.polyfit(di[:100], win[:100], 1)
    kf_di = KalmanBetaFilter(initial_beta=b, initial_alpha=a, trans_cov=1e-3, obs_cov=1e1)
    
    spreads_di = []
    for y, x in zip(win, di):
        beta, spread, _ = kf_di.update(float(y), float(x))
        spreads_di.append(spread)
        
    z_di = KalmanBetaFilter.rolling_zscore(spreads_di, window=DI_KALMAN_W)
    df['z_di'] = z_di
    
    return df

def generate_signals_for_scenario(df, z_entry, z_att):
    df = df.copy()
    df['sig_wdo'] = np.where(df['z_wdo'] <= -z_att, 1, np.where(df['z_wdo'] >= z_att, -1, 0))
    df['sig_di'] = np.where(df['z_di'] <= -z_att, 1, np.where(df['z_di'] >= z_att, -1, 0))
    
    df['sig_wdo_strong'] = np.where(df['z_wdo'] <= -z_entry, 1, np.where(df['z_wdo'] >= z_entry, -1, 0))
    df['sig_di_strong'] = np.where(df['z_di'] <= -z_entry, 1, np.where(df['z_di'] >= z_entry, -1, 0))
    
    df['signal'] = 0
    # Buy
    buy_mask = ((df['sig_wdo_strong'] == 1) & (df['sig_di'] == 1)) | ((df['sig_wdo'] == 1) & (df['sig_di_strong'] == 1))
    df.loc[buy_mask, 'signal'] = 1
    # Sell
    sell_mask = ((df['sig_wdo_strong'] == -1) & (df['sig_di'] == -1)) | ((df['sig_wdo'] == -1) & (df['sig_di_strong'] == -1))
    df.loc[sell_mask, 'signal'] = -1
    return df

def run_backtest(df_base, scenario):
    df = generate_signals_for_scenario(df_base, scenario['z_entry'], scenario['z_att'])
    sl_pts = scenario['sl']
    tp_pts = scenario['tp']
    be_act = scenario.get('be_act', 0)
    be_lock = scenario.get('be_lock', 0)
    max_bars = scenario['max_bars']
    end_of_day = scenario['end_of_day']
    
    trades = []
    open_trade = None
    
    # Iterate row by row
    for i in range(len(df)):
        row = df.iloc[i]
        dt = df.index[i]
        
        # Check Exits
        if open_trade is not None:
            open_trade['bars_held'] += 1
            
            # Intraday High/Low approximation (using close price here for simplicity, 
            # ideally use High/Low of WIN for accurate SL/TP matching during the bar)
            # We'll use the bar's High/Low to see if SL/TP was hit within the bar.
            
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
            
            hit_sl = False
            hit_tp = False
            hit_be = False
            exit_price = None
            exit_reason = ""
            
            # Update max favor
            if direction == 1:
                pts_favor = row['win_high'] - entry_price
            else:
                pts_favor = entry_price - row['win_low']
                
            if pts_favor > open_trade['max_favor']:
                open_trade['max_favor'] = pts_favor
                
            if be_act > 0 and open_trade['max_favor'] >= be_act:
                open_trade['be_active'] = True
            
            if direction == 1: # BUY
                if row['win_low'] <= entry_price - sl_pts:
                    hit_sl, exit_price, exit_reason = True, entry_price - sl_pts, "SL"
                elif open_trade['be_active'] and row['win_low'] <= entry_price + be_lock:
                    hit_be, exit_price, exit_reason = True, entry_price + be_lock, "BE"
                elif row['win_high'] >= entry_price + tp_pts:
                    hit_tp, exit_price, exit_reason = True, entry_price + tp_pts, "TP"
            else: # SELL
                if row['win_high'] >= entry_price + sl_pts:
                    hit_sl, exit_price, exit_reason = True, entry_price + sl_pts, "SL"
                elif open_trade['be_active'] and row['win_high'] >= entry_price - be_lock:
                    hit_be, exit_price, exit_reason = True, entry_price - be_lock, "BE"
                elif row['win_low'] <= entry_price - tp_pts:
                    hit_tp, exit_price, exit_reason = True, entry_price - tp_pts, "TP"
                    
            # Time-based exits
            hit_time = False
            if max_bars and open_trade['bars_held'] >= max_bars:
                hit_time, exit_price, exit_reason = True, row['win'], "TIME_MAX_BARS"
                
            if end_of_day and dt.time() >= time(17, 30):
                hit_time, exit_price, exit_reason = True, row['win'], "TIME_EOD"
                
            if hit_sl or hit_tp or hit_be or hit_time:
                open_trade['exit_price'] = exit_price
                open_trade['exit_time'] = dt
                open_trade['exit_reason'] = exit_reason
                
                if direction == 1:
                    open_trade['pnl'] = exit_price - entry_price
                else:
                    open_trade['pnl'] = entry_price - exit_price
                    
                trades.append(open_trade)
                open_trade = None
                continue # Trade closed, look for new entries on next bar
                
        # Check Entries
        if open_trade is None and row['signal'] != 0:
            # Avoid opening entries outside of allowed hours
            # Matador original allowed hours: 09:00 to 15:00
            # For the new scenarios, let's keep the general 09:00 to 17:00
            allowed_end = time(15, 0) if scenario['name'] == "Matador Original" else time(17, 0)
            
            if dt.time() < time(9, 0) or dt.time() >= allowed_end:
                continue
                
            open_trade = {
                'entry_time': dt,
                'direction': row['signal'],
                'entry_price': row['win'],
                'bars_held': 0,
                'max_favor': 0,
                'be_active': False
            }
            
    return trades

def print_report(trades, name):
    if not trades:
        print(f"--- {name} ---")
        print("No trades executed.\n")
        return
        
    df_trades = pd.DataFrame(trades)
    wins = df_trades[df_trades['pnl'] > 0]
    losses = df_trades[df_trades['pnl'] < 0]
    
    win_rate = len(wins) / len(df_trades) * 100
    gross_profit = wins['pnl'].sum()
    gross_loss = abs(losses['pnl'].sum())
    net_profit = gross_profit - gross_loss
    
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['pnl'].mean()) if len(losses) > 0 else 0
    payoff = avg_win / avg_loss if avg_loss > 0 else float('inf')
    
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Calculate Drawdown
    df_trades['cum_pnl'] = df_trades['pnl'].cumsum()
    df_trades['peak'] = df_trades['cum_pnl'].cummax()
    df_trades['drawdown'] = df_trades['peak'] - df_trades['cum_pnl']
    max_dd = df_trades['drawdown'].max()
    
    ret_dd = net_profit / max_dd if max_dd > 0 else float('inf')
    
    print(f"=== Report: {name} ===")
    print(f"Total Trades:   {len(df_trades)}")
    print(f"Win Rate:       {win_rate:.2f}%")
    print(f"Net PnL:        {net_profit:.2f} pts")
    print(f"Max Drawdown:   {max_dd:.2f} pts")
    print(f"Ret/DD:         {ret_dd:.2f}")
    print(f"Pay-off:        {payoff:.2f}")
    print(f"Profit Factor:  {profit_factor:.2f}")
    print("-" * 25)

if __name__ == "__main__":
    df = fetch_data()
    if df is not None:
        df = generate_signals(df)
        print("\nStarting Backtest Simulations...\n")
        
        for sc in SCENARIOS:
            trades = run_backtest(df, sc)
            print_report(trades, sc['name'])
