import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from research.backtest_matador import generate_signals
from research.optimize_phase6_cooldown import run_backtest_cooldown
from research.optimize_phase1_zscores import evaluate_trades
from core.signals import calc_nwe_with_bands

def load_and_resample(file_path):
    print(f"Loading {file_path}...")
    df = pd.read_csv(file_path, sep='\t') # Often MT5 exports are tab-separated. Let's try parsing.
    
    # If standard comma, let's just use read_csv without sep if it fails.
    if len(df.columns) <= 1:
        df = pd.read_csv(file_path)
    
    # Let's check MT5 standard format: <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>
    # or time open high low close
    if '<DATE>' in df.columns and '<TIME>' in df.columns:
        df['datetime'] = pd.to_datetime(df['<DATE>'] + ' ' + df['<TIME>'])
        df.set_index('datetime', inplace=True)
        df.rename(columns={'<OPEN>': 'open', '<HIGH>': 'high', '<LOW>': 'low', '<CLOSE>': 'close'}, inplace=True)
    elif 'time' in df.columns:
        df['datetime'] = pd.to_datetime(df['time'])
        df.set_index('datetime', inplace=True)
    
    # Resample to 5 minutes
    resampled = df[['open', 'high', 'low', 'close']].resample('5Min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    return resampled

def fetch_local_history():
    win_path = r"C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\historical\WIN$N_M1_202103100900_202603261831.csv"
    wdo_path = r"C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\historical\WDO$N_M1_202103100900_202603261829.csv"
    di_path = r"C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\historical\DI1$N_M1_202105060900_202603261759.csv"
    
    df_win = load_and_resample(win_path)
    df_wdo = load_and_resample(wdo_path)
    df_di = load_and_resample(di_path)
    
    print("Aligning data...")
    df = pd.DataFrame({
        'win': df_win['close'],
        'win_high': df_win['high'],
        'win_low': df_win['low'],
        'wdo': df_wdo['close'],
        'di': df_di['close']
    }).dropna()
    
    print(f"Total aligned M5 bars: {len(df)}")
    return df

def test_supreme():
    print("--- 5 YEAR SUPREME BACKTEST ---")
    df_base = fetch_local_history()
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
    print("Calculating NWE (might take a minute for 130k bars)...")
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
    
    print("\n--- RESULTADOS GLOBAIS (5 ANOS) ---")
    print(f"Supremo BASE (Sem NWE): Trades={t_base}, WR={wr_base:.1f}%, PnL={pnl_base}, MaxDD={dd_base}, Ret/DD={ret_base:.2f}")
    print(f"Supremo COM NWE:        Trades={t_nwe}, WR={wr_nwe:.1f}%, PnL={pnl_nwe}, MaxDD={dd_nwe}, Ret/DD={ret_nwe:.2f}")
    
    # Plotting
    df_tb = pd.DataFrame(trades_base)
    df_tn = pd.DataFrame(trades_nwe)
    
    plt.figure(figsize=(14, 7))
    if not df_tb.empty:
        df_tb['cum'] = df_tb['pnl'].cumsum()
        plt.plot(df_tb['cum'].tolist(), label=f'Supremo Sem NWE (PnL: {pnl_base} | DD: {dd_base})', color='purple', alpha=0.8)
    if not df_tn.empty:
        df_tn['cum'] = df_tn['pnl'].cumsum()
        plt.plot(df_tn['cum'].tolist(), label=f'Supremo COM NWE (PnL: {pnl_nwe} | DD: {dd_nwe})', color='green', linewidth=2)
        
    plt.title('Backtest Mestre (5 Anos): Impacto do NWE no Setup Supremo')
    plt.xlabel('Número de Trades')
    plt.ylabel('PnL (Pontos)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2")
    out_path = os.path.join(out_dir, "master_5_years_nwe.png")
    plt.savefig(out_path)
    print(f"Plot saved to {out_path}")

if __name__ == "__main__":
    test_supreme()
