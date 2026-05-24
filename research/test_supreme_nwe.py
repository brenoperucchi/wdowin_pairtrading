import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from research.backtest_matador import fetch_data, generate_signals
from research.optimize_phase6_cooldown import run_backtest_cooldown
from research.optimize_phase1_zscores import evaluate_trades
from core.signals import calc_nwe_with_bands
import MetaTrader5 as mt5
from core.config import MT5_PATH, SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME

def fetch_data_long(bars=150000):
    print(f"Connecting to MT5 at {MT5_PATH}...")
    if not mt5.initialize(path=MT5_PATH):
        print(f"MT5 Init Failed: {mt5.last_error()}")
        return None
    for sym in [SYMBOL_A, SYMBOL_B, DI_SYMBOL]:
        mt5.symbol_select(sym, True)
        
    print(f"Fetching {bars} bars for {SYMBOL_A}, {SYMBOL_B}, and {DI_SYMBOL}...")
    win_rates = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, bars)
    wdo_rates = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, bars)
    di_rates = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, bars)
    
    if win_rates is None: print(f"Failed to fetch {SYMBOL_A}")
    if wdo_rates is None: print(f"Failed to fetch {SYMBOL_B}")
    if di_rates is None: print(f"Failed to fetch {DI_SYMBOL}")
    
    if win_rates is None or wdo_rates is None or di_rates is None:
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
    
    df = pd.DataFrame({
        'win': df_win['close'], 'win_high': df_win['high'], 'win_low': df_win['low'],
        'wdo': df_wdo['close'], 'di': df_di['close']
    }).dropna()
    print(f"Data aligned: {len(df)} bars.")
    return df

def test_supreme():
    print("Loading long-term data...")
    df_base = fetch_data_long(100000) # Trying 100,000 bars (~3.5 years)
    if df_base is None: return
    df_base = generate_signals(df_base)
    
    # 1. Supreme Z-Scores
    z_wdo_val = 2.0
    z_di_val = 3.0
    z_att_val = 1.6
    
    df_base['sig_wdo_strong'] = np.where(df_base['z_wdo'] <= -z_wdo_val, 1, np.where(df_base['z_wdo'] >= z_wdo_val, -1, 0))
    df_base['sig_di_strong'] = np.where(df_base['z_di'] <= -z_di_val, 1, np.where(df_base['z_di'] >= z_di_val, -1, 0))
    df_base['sig_wdo'] = np.where(df_base['z_wdo'] <= -z_att_val, 1, np.where(df_base['z_wdo'] >= z_att_val, -1, 0))
    df_base['sig_di'] = np.where(df_base['z_di'] <= -z_att_val, 1, np.where(df_base['z_di'] >= z_att_val, -1, 0))
    
    buy_mask = ((df_base['sig_wdo_strong'] == 1) & (df_base['sig_di'] == 1)) | ((df_base['sig_wdo'] == 1) & (df_base['sig_di_strong'] == 1))
    sell_mask = ((df_base['sig_wdo_strong'] == -1) & (df_base['sig_di'] == -1)) | ((df_base['sig_wdo'] == -1) & (df_base['sig_di_strong'] == -1))
    
    # Supreme Base (No NWE)
    df_sig_base = df_base.copy()
    df_sig_base['signal'] = 0
    df_sig_base.loc[buy_mask, 'signal'] = 1
    df_sig_base.loc[sell_mask, 'signal'] = -1
    
    # 2. Supreme WITH NWE (LB=150, BW=5, MULT=5.0, PCT=0.0)
    print("Calculating NWE...")
    win_prices = df_base['win'].values
    nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=5, lookback=150, mult_mae=1.0)
    mae = upper_nwe - nwe
    upper = nwe + mae * 5.0
    lower = nwe - mae * 5.0
    bw = upper - lower
    
    valid_buy = (~is_up) & (win_prices <= lower + bw * 0.0)
    valid_sell = (is_up) & (win_prices >= upper - bw * 0.0)
    
    df_sig_nwe = df_base.copy()
    df_sig_nwe['signal'] = 0
    df_sig_nwe.loc[buy_mask & valid_buy, 'signal'] = 1
    df_sig_nwe.loc[sell_mask & valid_sell, 'signal'] = -1
    
    print("Running Backtests...")
    # Supreme Parameters: SL=200, TP=500, Start=9, End=16, Cooldown=1
    sl_val = 200
    tp_val = 500
    sh = 9
    eh = 16
    wb = 1
    
    trades_base = run_backtest_cooldown(df_sig_base, sl_pts=sl_val, tp_pts=tp_val, start_h=sh, end_h=eh, wait_bars=wb)
    pnl_base, dd_base, ret_base, t_base = evaluate_trades(trades_base)
    wr_base = (len([t for t in trades_base if t['pnl'] > 0]) / len(trades_base)) * 100 if trades_base else 0
    
    trades_nwe = run_backtest_cooldown(df_sig_nwe, sl_pts=sl_val, tp_pts=tp_val, start_h=sh, end_h=eh, wait_bars=wb)
    pnl_nwe, dd_nwe, ret_nwe, t_nwe = evaluate_trades(trades_nwe)
    wr_nwe = (len([t for t in trades_nwe if t['pnl'] > 0]) / len(trades_nwe)) * 100 if trades_nwe else 0
    
    print("\n--- RESULTADOS ---")
    print(f"Supremo BASE (Sem NWE): Trades={t_base}, WR={wr_base:.1f}%, PnL={pnl_base}, MaxDD={dd_base}, Ret/DD={ret_base:.2f}")
    print(f"Supremo COM NWE:        Trades={t_nwe}, WR={wr_nwe:.1f}%, PnL={pnl_nwe}, MaxDD={dd_nwe}, Ret/DD={ret_nwe:.2f}")
    
    # Plotting
    df_tb = pd.DataFrame(trades_base)
    df_tn = pd.DataFrame(trades_nwe)
    
    plt.figure(figsize=(12, 6))
    if not df_tb.empty:
        df_tb['cum'] = df_tb['pnl'].cumsum()
        plt.plot(df_tb['cum'].tolist(), label=f'Supremo Sem NWE (PnL: {pnl_base} | DD: {dd_base})', color='purple')
    if not df_tn.empty:
        df_tn['cum'] = df_tn['pnl'].cumsum()
        plt.plot(df_tn['cum'].tolist(), label=f'Supremo COM NWE (PnL: {pnl_nwe} | DD: {dd_nwe})', color='green')
        
    plt.title('Impacto do NWE no Setup Supremo (SL 200 / TP 500)')
    plt.xlabel('Número de Trades')
    plt.ylabel('PnL (Pontos)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2")
    out_path = os.path.join(out_dir, "supreme_nwe_comparison.png")
    plt.savefig(out_path)
    print(f"Plot saved to {out_path}")

if __name__ == "__main__":
    test_supreme()
