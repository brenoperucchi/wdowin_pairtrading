import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from datetime import time

from research.test_supreme_longterm import fetch_local_history
from core.signals import calc_nwe_with_bands

def rolling_ols(y, x, window):
    s_y = pd.Series(y)
    s_x = pd.Series(x)
    cov = s_y.rolling(window=window).cov(s_x)
    var = s_x.rolling(window=window).var()
    beta = cov / var
    beta = beta.bfill().fillna(1.0).values
    spread = y - (beta * x)
    s_spread = pd.Series(spread)
    mean_spread = s_spread.rolling(window=window).mean().bfill().fillna(0).values.copy()
    std_spread = s_spread.rolling(window=window).std().bfill().fillna(1).values.copy()
    std_spread = np.where(std_spread == 0, 1.0, std_spread)
    z_score = (spread - mean_spread) / std_spread
    return beta, spread, z_score

def run_validation():
    print("=" * 80)
    print("  AUDIT: WDO ISOLADO - TRADE-BY-TRADE VALIDATION")
    print("=" * 80)
    
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    
    print("Calculating OLS 40...")
    beta_arr, spread_arr, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    # Setup vencedor: BW=3, LB=200, MAE=4.0
    bw = 3
    lb = 200
    mae_mult = 4.0
    z_val = 2.2
    sl = 300
    tp = 500
    
    print(f"NWE Config: BW={bw}, Lookback={lb}, MAE_Mult={mae_mult}")
    print(f"Z-Score: {z_val} | SL: {sl} | TP: {tp}")
    
    nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb, mult_mae=1.0)
    mae = upper_nwe - nwe
    upper = nwe + mae * mae_mult
    lower = nwe - mae * mae_mult
    
    sig_buy = (z_wdo <= -z_val)
    sig_sell = (z_wdo >= z_val)
    valid_buy_nwe = (~is_up) & (win_prices <= lower)
    valid_sell_nwe = (is_up) & (win_prices >= upper)
    
    df_base['signal'] = 0
    df_base.loc[sig_buy & valid_buy_nwe, 'signal'] = 1
    df_base.loc[sig_sell & valid_sell_nwe, 'signal'] = -1
    
    # --- BACKTEST COM LOG DETALHADO ---
    trades = []
    open_trade = None
    cooldown_until = None
    
    win_high = df_base['win_high'].values
    win_low = df_base['win_low'].values
    win_close = df_base['win'].values
    signals = df_base['signal'].values
    times = df_base.index
    
    eod_time = time(17, 30)
    t_start = time(9, 0)
    t_end = time(16, 0)
    wait_bars = 2
    
    for i in range(len(df_base)):
        dt = times[i]
        t = dt.time()
        
        # Check Exits
        if open_trade is not None:
            open_trade['bars_held'] += 1
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
            
            hit_exit = False
            exit_price = None
            exit_reason = None
            
            if direction == 1:  # BUY
                if win_high[i] >= entry_price + tp:
                    hit_exit, exit_price, exit_reason = True, entry_price + tp, "TP"
                elif win_low[i] <= entry_price - sl:
                    hit_exit, exit_price, exit_reason = True, entry_price - sl, "SL"
            else:  # SELL
                if win_low[i] <= entry_price - tp:
                    hit_exit, exit_price, exit_reason = True, entry_price - tp, "TP"
                elif win_high[i] >= entry_price + sl:
                    hit_exit, exit_price, exit_reason = True, entry_price + sl, "SL"
            
            if not hit_exit and t >= eod_time:
                hit_exit, exit_price, exit_reason = True, win_close[i], "EOD"
                
            if hit_exit:
                pnl = (exit_price - entry_price) * direction
                open_trade['exit_dt'] = dt
                open_trade['exit_price'] = exit_price
                open_trade['exit_reason'] = exit_reason
                open_trade['pnl'] = pnl
                open_trade['z_at_entry'] = open_trade['z_entry']
                open_trade['nwe_at_entry'] = open_trade['nwe_entry']
                open_trade['win_at_entry'] = open_trade['win_entry']
                trades.append(open_trade)
                open_trade = None
                cooldown_until = i + wait_bars
                continue
                
        # Check Entries
        if open_trade is None and signals[i] != 0:
            if cooldown_until is not None and i <= cooldown_until:
                continue
                
            if t >= t_start and t < t_end:
                open_trade = {
                    'direction': signals[i],
                    'entry_price': win_close[i],
                    'entry_dt': dt,
                    'bars_held': 0,
                    'z_entry': z_wdo[i],
                    'nwe_entry': nwe[i],
                    'win_entry': win_prices[i],
                    'wdo_entry': wdo_prices[i],
                    'beta_entry': beta_arr[i],
                    'nwe_upper': upper[i],
                    'nwe_lower': lower[i],
                    'is_up_entry': is_up[i],
                }
    
    # --- PRINT DETALHADO ---
    df_trades = pd.DataFrame(trades)
    
    if df_trades.empty:
        print("\nNENHUM TRADE ENCONTRADO!")
        return
    
    df_trades['cum_pnl'] = df_trades['pnl'].cumsum()
    df_trades['peak'] = df_trades['cum_pnl'].cummax()
    df_trades['dd'] = df_trades['peak'] - df_trades['cum_pnl']
    
    total = len(df_trades)
    winners = len(df_trades[df_trades['pnl'] > 0])
    losers = len(df_trades[df_trades['pnl'] < 0])
    eod_exits = len(df_trades[df_trades['exit_reason'] == 'EOD'])
    tp_exits = len(df_trades[df_trades['exit_reason'] == 'TP'])
    sl_exits = len(df_trades[df_trades['exit_reason'] == 'SL'])
    
    print(f"\n{'=' * 80}")
    print(f"  RESUMO GERAL")
    print(f"{'=' * 80}")
    print(f"Total Trades: {total}")
    print(f"Winners: {winners} ({winners/total*100:.1f}%)")
    print(f"Losers: {losers} ({losers/total*100:.1f}%)")
    print(f"Saídas TP: {tp_exits} | Saídas SL: {sl_exits} | Saídas EOD: {eod_exits}")
    print(f"PnL Total: {df_trades['pnl'].sum():.0f} pts")
    print(f"Max Drawdown: {df_trades['dd'].max():.0f} pts")
    print(f"Ret/DD: {df_trades['pnl'].sum() / df_trades['dd'].max():.2f}" if df_trades['dd'].max() > 0 else "N/A")
    print(f"PnL Médio/Trade: {df_trades['pnl'].mean():.1f} pts")
    print(f"Bars Médio/Trade: {df_trades['bars_held'].mean():.1f}")
    
    # Por ano
    df_trades['year'] = pd.to_datetime(df_trades['entry_dt']).dt.year
    print(f"\n{'=' * 80}")
    print(f"  PnL POR ANO")
    print(f"{'=' * 80}")
    for year, grp in df_trades.groupby('year'):
        yr_pnl = grp['pnl'].sum()
        yr_trades = len(grp)
        yr_wr = len(grp[grp['pnl'] > 0]) / yr_trades * 100 if yr_trades > 0 else 0
        print(f"  {year}: {yr_trades:>4} trades | WR: {yr_wr:>5.1f}% | PnL: {yr_pnl:>+8.0f} pts")
    
    # Trade-by-trade log (últimos 30 trades para auditoria visual)
    print(f"\n{'=' * 80}")
    print(f"  ÚLTIMOS 30 TRADES (para verificação no MT5)")
    print(f"{'=' * 80}")
    print(f"{'#':>3} | {'Entrada':>19} | {'Saída':>19} | {'Dir':>4} | {'Entry':>8} | {'Exit':>8} | {'Reason':>6} | {'PnL':>7} | {'Z':>6} | {'Bars':>4} | {'CumPnL':>8}")
    print("-" * 130)
    
    for idx, row in df_trades.tail(30).iterrows():
        dir_str = "BUY" if row['direction'] == 1 else "SELL"
        entry_dt_str = row['entry_dt'].strftime('%Y-%m-%d %H:%M')
        exit_dt_str = row['exit_dt'].strftime('%Y-%m-%d %H:%M')
        print(f"{idx+1:>3} | {entry_dt_str:>19} | {exit_dt_str:>19} | {dir_str:>4} | {row['entry_price']:>8.0f} | {row['exit_price']:>8.0f} | {row['exit_reason']:>6} | {row['pnl']:>+7.0f} | {row['z_entry']:>+6.2f} | {row['bars_held']:>4} | {row['cum_pnl']:>+8.0f}")
    
    # Salvar CSV completo
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "hybrid_v1", "phase5_wdo_nwe_grid")
    os.makedirs(out_dir, exist_ok=True)
    
    cols_export = ['entry_dt', 'exit_dt', 'direction', 'entry_price', 'exit_price', 
                   'exit_reason', 'pnl', 'cum_pnl', 'z_at_entry', 'bars_held',
                   'wdo_entry', 'beta_entry', 'nwe_at_entry', 'win_at_entry',
                   'nwe_upper', 'nwe_lower', 'is_up_entry']
    
    csv_path = os.path.join(out_dir, "wdo_trade_audit.csv")
    df_trades[cols_export].to_csv(csv_path, index=False)
    print(f"\nCSV completo salvo em: {csv_path}")
    print("Use este CSV para cruzar cada trade com o gráfico M5 do WIN no MT5.")

if __name__ == "__main__":
    run_validation()
