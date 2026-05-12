import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from research.backtest_matador import fetch_data, generate_signals
from research.optimize_phase4_breakeven import run_backtest_be
from research.optimize_phase1_zscores import evaluate_trades

def plot_final():
    print("Loading data...")
    df_base = fetch_data()
    df_base = generate_signals(df_base)
    
    z_wdo_val = 2.0
    z_di_val = 3.0
    z_att_val = 1.6
    
    df_base['sig_wdo_strong'] = np.where(df_base['z_wdo'] <= -z_wdo_val, 1, np.where(df_base['z_wdo'] >= z_wdo_val, -1, 0))
    df_base['sig_di_strong'] = np.where(df_base['z_di'] <= -z_di_val, 1, np.where(df_base['z_di'] >= z_di_val, -1, 0))
    df_base['sig_wdo'] = np.where(df_base['z_wdo'] <= -z_att_val, 1, np.where(df_base['z_wdo'] >= z_att_val, -1, 0))
    df_base['sig_di'] = np.where(df_base['z_di'] <= -z_att_val, 1, np.where(df_base['z_di'] >= z_att_val, -1, 0))
    
    buy_mask = ((df_base['sig_wdo_strong'] == 1) & (df_base['sig_di'] == 1)) | ((df_base['sig_wdo'] == 1) & (df_base['sig_di_strong'] == 1))
    sell_mask = ((df_base['sig_wdo_strong'] == -1) & (df_base['sig_di'] == -1)) | ((df_base['sig_wdo'] == -1) & (df_base['sig_di_strong'] == -1))
    
    df_sig = df_base.copy()
    df_sig['signal'] = 0
    df_sig.loc[buy_mask, 'signal'] = 1
    df_sig.loc[sell_mask, 'signal'] = -1
    
    trades = run_backtest_be(df_sig, sl_pts=200, tp_pts=500, be_act=9999, be_lock=0)
    pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
    
    df_trades = pd.DataFrame(trades)
    df_trades['cum_pnl'] = df_trades['pnl'].cumsum()
    
    plt.figure(figsize=(12, 6))
    plt.plot(df_trades['cum_pnl'].tolist(), color='purple', linewidth=2)
    plt.title(f'Curva de Capital Vencedora - Consenso Puro\n(WDO: 2.0 | DI: 3.0 | SL: 200 | TP: 500 | BE: Desligado)\nRet/DD: {ret_dd:.2f} | PnL: {pnl} | Max DD: {max_dd}')
    plt.xlabel('Número de Trades')
    plt.ylabel('PnL (Pontos)')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "final_equity_curve.png")
    plt.savefig(out_path)
    print(f"Plot saved to {out_path}")

if __name__ == "__main__":
    plot_final()
