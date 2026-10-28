import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from research.backtest_matador import fetch_data, generate_signals
from research.optimize_phase1_zscores import run_backtest_fast
from core.signals import calc_nwe_with_bands

def calculate_metrics(trades):
    if not trades:
        return 0, 0, 0, 0, []
    df_trades = pd.DataFrame(trades)
    net_pnl = df_trades['pnl'].sum()
    
    # Drawdown
    df_trades['cum_pnl'] = df_trades['pnl'].cumsum()
    df_trades['peak'] = df_trades['cum_pnl'].cummax()
    df_trades['drawdown'] = df_trades['peak'] - df_trades['cum_pnl']
    max_dd = df_trades['drawdown'].max()
    
    wins = len(df_trades[df_trades['pnl'] > 0])
    win_rate = (wins / len(df_trades)) * 100
    
    return net_pnl, max_dd, win_rate, len(trades), df_trades['cum_pnl'].tolist()

def compare_scenarios():
    print("Loading data...")
    df_base = fetch_data()
    df_base = generate_signals(df_base)
    
    z_wdo_val = 1.9
    z_di_val = 2.8
    z_att_val = 1.6
    
    df_base['sig_wdo_strong'] = np.where(df_base['z_wdo'] <= -z_wdo_val, 1, np.where(df_base['z_wdo'] >= z_wdo_val, -1, 0))
    df_base['sig_di_strong'] = np.where(df_base['z_di'] <= -z_di_val, 1, np.where(df_base['z_di'] >= z_di_val, -1, 0))
    df_base['sig_wdo'] = np.where(df_base['z_wdo'] <= -z_att_val, 1, np.where(df_base['z_wdo'] >= z_att_val, -1, 0))
    df_base['sig_di'] = np.where(df_base['z_di'] <= -z_att_val, 1, np.where(df_base['z_di'] >= z_att_val, -1, 0))
    
    buy_mask = ((df_base['sig_wdo_strong'] == 1) & (df_base['sig_di'] == 1)) | ((df_base['sig_wdo'] == 1) & (df_base['sig_di_strong'] == 1))
    sell_mask = ((df_base['sig_wdo_strong'] == -1) & (df_base['sig_di'] == -1)) | ((df_base['sig_wdo'] == -1) & (df_base['sig_di_strong'] == -1))
    
    win_prices = df_base['win'].values
    
    # 1. Base (Sem NWE)
    df_sig_base = df_base.copy()
    df_sig_base['signal'] = 0
    df_sig_base.loc[buy_mask, 'signal'] = 1
    df_sig_base.loc[sell_mask, 'signal'] = -1
    
    trades_base = run_backtest_fast(df_sig_base)
    pnl_base, dd_base, wr_base, total_base, curve_base = calculate_metrics(trades_base)
    
    # 2. NWE Opcao 1: LB=150, BW=5, MULT=5.0, PCT=0.0
    nwe, upper_1, lower_1, is_up = calc_nwe_with_bands(win_prices, bandwidth=5, lookback=150, mult_mae=1.0)
    mae = upper_1 - nwe
    upper = nwe + mae * 5.0
    lower = nwe - mae * 5.0
    bw = upper - lower
    valid_buy = (~is_up) & (win_prices <= lower + bw * 0.0)
    valid_sell = (is_up) & (win_prices >= upper - bw * 0.0)
    df_sig_1 = df_base.copy()
    df_sig_1['signal'] = 0
    df_sig_1.loc[buy_mask & valid_buy, 'signal'] = 1
    df_sig_1.loc[sell_mask & valid_sell, 'signal'] = -1
    trades_1 = run_backtest_fast(df_sig_1)
    pnl_1, dd_1, wr_1, total_1, curve_1 = calculate_metrics(trades_1)
    
    # 3. NWE Opcao 2: LB=150, BW=8, MULT=5.0, PCT=0.1
    nwe2, upper_2, lower_2, is_up2 = calc_nwe_with_bands(win_prices, bandwidth=8, lookback=150, mult_mae=1.0)
    mae2 = upper_2 - nwe2
    upper2 = nwe2 + mae2 * 5.0
    lower2 = nwe2 - mae2 * 5.0
    bw2 = upper2 - lower2
    valid_buy2 = (~is_up2) & (win_prices <= lower2 + bw2 * 0.1)
    valid_sell2 = (is_up2) & (win_prices >= upper2 - bw2 * 0.1)
    df_sig_2 = df_base.copy()
    df_sig_2['signal'] = 0
    df_sig_2.loc[buy_mask & valid_buy2, 'signal'] = 1
    df_sig_2.loc[sell_mask & valid_sell2, 'signal'] = -1
    trades_2 = run_backtest_fast(df_sig_2)
    pnl_2, dd_2, wr_2, total_2, curve_2 = calculate_metrics(trades_2)
    
    print("--- RESULTADOS ---")
    print(f"Base: Trades={total_base}, WR={wr_base:.1f}%, PnL={pnl_base}, MaxDD={dd_base}")
    print(f"Opc1: Trades={total_1}, WR={wr_1:.1f}%, PnL={pnl_1}, MaxDD={dd_1}")
    print(f"Opc2: Trades={total_2}, WR={wr_2:.1f}%, PnL={pnl_2}, MaxDD={dd_2}")
    
    # Plotting
    plt.figure(figsize=(12, 6))
    plt.plot(curve_base, label=f'Sem NWE (Ret/DD: {pnl_base/dd_base if dd_base>0 else 0:.2f})', color='gray', linestyle='--')
    plt.plot(curve_1, label=f'Opção 1 NWE (Ret/DD: {pnl_1/dd_1 if dd_1>0 else 0:.2f})', color='blue')
    plt.plot(curve_2, label=f'Opção 2 NWE (Ret/DD: {pnl_2/dd_2 if dd_2>0 else 0:.2f})', color='green')
    plt.title('Comparativo de Curvas de Capital: Antes vs Depois do NWE')
    plt.xlabel('Número de Trades')
    plt.ylabel('PnL (Pontos)')
    plt.legend()
    plt.grid(True)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_2_nwe")
    os.makedirs(out_dir, exist_ok=True)
    plt.savefig(os.path.join(out_dir, "equity_curves.png"))
    print(f"Plot saved to {os.path.join(out_dir, 'equity_curves.png')}")

if __name__ == "__main__":
    compare_scenarios()
