"""
AUDIT M1 v2: Versão corrigida.

A entrada é decidida no M5. Mas a resolução do exit percorre 
TODAS as barras M1 subsequentes (não apenas as que caem dentro
de uma única barra M5) até que TP, SL ou EOD seja atingido.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from datetime import time as dt_time, timedelta

from core.signals import calc_nwe_with_bands

def load_m1(path):
    print(f"Loading {os.path.basename(path)} ({os.path.getsize(path)/(1024*1024):.0f} MB)...")
    df = pd.read_csv(path, sep='\t')
    if len(df.columns) <= 1:
        df = pd.read_csv(path)
    if '<DATE>' in df.columns:
        df['datetime'] = pd.to_datetime(df['<DATE>'] + ' ' + df['<TIME>'])
        df.set_index('datetime', inplace=True)
        df.rename(columns={'<OPEN>':'open','<HIGH>':'high','<LOW>':'low','<CLOSE>':'close'}, inplace=True)
    elif 'time' in df.columns:
        df['datetime'] = pd.to_datetime(df['time'])
        df.set_index('datetime', inplace=True)
    return df[['open','high','low','close']]

def resample_m5(df_m1):
    return df_m1.resample('5min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

def rolling_ols(y, x, window):
    s_y, s_x = pd.Series(y), pd.Series(x)
    cov = s_y.rolling(window=window).cov(s_x)
    var = s_x.rolling(window=window).var()
    beta = (cov / var).bfill().fillna(1.0).values
    spread = y - (beta * x)
    s = pd.Series(spread)
    mu = s.rolling(window=window).mean().bfill().fillna(0).values.copy()
    sd = s.rolling(window=window).std().bfill().fillna(1).values.copy()
    sd = np.where(sd == 0, 1.0, sd)
    return beta, spread, (spread - mu) / sd

def resolve_trade_m1(df_m1, entry_dt, entry_price, direction, sl, tp):
    """Percorre M1 barra a barra a partir da barra SEGUINTE à entrada."""
    # Começar na próxima barra M1 após o close da barra M5 de entrada
    start = entry_dt + timedelta(minutes=5)
    eod_limit = entry_dt.replace(hour=17, minute=30, second=0)
    
    m1_after = df_m1.loc[start:]
    
    for dt_m1, bar in m1_after.iterrows():
        if dt_m1 > eod_limit:
            return bar['close'], "EOD", dt_m1
        
        if direction == 1:  # BUY — check SL first (pessimista)
            if bar['low'] <= entry_price - sl:
                return entry_price - sl, "SL", dt_m1
            if bar['high'] >= entry_price + tp:
                return entry_price + tp, "TP", dt_m1
        else:  # SELL
            if bar['high'] >= entry_price + sl:
                return entry_price + sl, "SL", dt_m1
            if bar['low'] <= entry_price - tp:
                return entry_price - tp, "TP", dt_m1
    
    return None, "OPEN", None  # Trade ficou aberto (fim dos dados)

def resolve_trade_m5(df_m5, entry_idx, entry_price, direction, sl, tp):
    """Motor M5 original (TP-first bias) para comparação."""
    eod_time = dt_time(17, 30)
    m5_high = df_m5['win_high'].values
    m5_low = df_m5['win_low'].values
    m5_close = df_m5['win'].values
    times = df_m5.index
    
    for j in range(entry_idx + 1, len(df_m5)):
        t = times[j].time()
        
        if direction == 1:
            if m5_high[j] >= entry_price + tp:
                return entry_price + tp, "TP", times[j]
            if m5_low[j] <= entry_price - sl:
                return entry_price - sl, "SL", times[j]
        else:
            if m5_low[j] <= entry_price - tp:
                return entry_price - tp, "TP", times[j]
            if m5_high[j] >= entry_price + sl:
                return entry_price + sl, "SL", times[j]
        
        if t >= eod_time:
            return m5_close[j], "EOD", times[j]
    
    return None, "OPEN", None

def main():
    print("=" * 80)
    print("  AUDIT M1 v2: RESOLUÇÃO COMPLETA M1 VS M5")
    print("=" * 80)
    
    # Load M1
    win_m1 = load_m1(r"C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\historical\WIN$N_M1_202103100900_202603261831.csv")
    wdo_m1 = load_m1(r"C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\historical\WDO$N_M1_202103100900_202603261829.csv")
    di_m1 = load_m1(r"C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\historical\DI1$N_M1_202105060900_202603261759.csv")
    
    print(f"M1 WIN bars: {len(win_m1):,}")
    
    # Build M5
    win_m5 = resample_m5(win_m1)
    wdo_m5 = resample_m5(wdo_m1)
    di_m5 = resample_m5(di_m1)
    
    df_m5 = pd.DataFrame({
        'win': win_m5['close'], 'win_high': win_m5['high'], 'win_low': win_m5['low'],
        'wdo': wdo_m5['close'], 'di': di_m5['close']
    }).dropna()
    
    print(f"M5 bars: {len(df_m5):,}")
    
    # Signals
    win_p = df_m5['win'].values
    wdo_p = df_m5['wdo'].values
    _, _, z_wdo = rolling_ols(win_p, wdo_p, 40)
    
    bw, lb, mae_m = 3, 200, 4.0
    z_val, sl, tp = 2.2, 300, 500
    
    nwe, upper_nwe, _, is_up = calc_nwe_with_bands(win_p, bandwidth=bw, lookback=lb, mult_mae=1.0)
    mae = upper_nwe - nwe
    upper = nwe + mae * mae_m
    lower = nwe - mae * mae_m
    
    sig_buy = (z_wdo <= -z_val)
    sig_sell = (z_wdo >= z_val)
    valid_buy = (~is_up) & (win_p <= lower)
    valid_sell = (is_up) & (win_p >= upper)
    
    df_m5['signal'] = 0
    df_m5.loc[sig_buy & valid_buy, 'signal'] = 1
    df_m5.loc[sig_sell & valid_sell, 'signal'] = -1
    
    signals = df_m5['signal'].values
    m5_times = df_m5.index
    m5_close = df_m5['win'].values
    
    # Collect entry points
    entries = []
    cooldown_until = -1
    t_start, t_end = dt_time(9,0), dt_time(16,0)
    
    # Simulate to get same entry points as original engine
    open_idx = None
    for i in range(len(df_m5)):
        t = m5_times[i].time()
        
        if open_idx is not None:
            # Check if M5 exit happens
            _, reason_m5, _ = resolve_trade_m5(df_m5, open_idx, m5_close[open_idx], signals[open_idx], sl, tp)
            # We need to track bar-by-bar... let me just collect entries with cooldown
            pass
        
        if signals[i] != 0 and i > cooldown_until and t >= t_start and t < t_end:
            entries.append(i)
            # Simulate forward to find when this trade closes (M5) for cooldown
            _, _, exit_dt = resolve_trade_m5(df_m5, i, m5_close[i], signals[i], sl, tp)
            if exit_dt is not None:
                # Find the M5 index of exit_dt
                try:
                    exit_idx = df_m5.index.get_loc(exit_dt)
                    cooldown_until = exit_idx + 2
                except:
                    cooldown_until = i + 10
            else:
                cooldown_until = i + 10
    
    print(f"\nTotal entries: {len(entries)}")
    print(f"\nResolvendo cada trade em M5 e M1...")
    
    results = []
    for idx, entry_i in enumerate(entries):
        entry_dt = m5_times[entry_i]
        entry_price = m5_close[entry_i]
        direction = signals[entry_i]
        
        # M5 resolution (TP-first, como o motor atual)
        exit_m5, reason_m5, dt_m5 = resolve_trade_m5(df_m5, entry_i, entry_price, direction, sl, tp)
        pnl_m5 = ((exit_m5 - entry_price) * direction) if exit_m5 else 0
        
        # M1 resolution (SL-first, pessimista)
        exit_m1, reason_m1, dt_m1 = resolve_trade_m1(win_m1, entry_dt, entry_price, direction, sl, tp)
        pnl_m1 = ((exit_m1 - entry_price) * direction) if exit_m1 else 0
        
        results.append({
            'entry_dt': entry_dt,
            'dir': direction,
            'entry': entry_price,
            'm5_exit': exit_m5, 'm5_reason': reason_m5, 'm5_pnl': pnl_m5,
            'm1_exit': exit_m1, 'm1_reason': reason_m1, 'm1_pnl': pnl_m1,
            'match': reason_m5 == reason_m1,
        })
    
    df_r = pd.DataFrame(results)
    
    # Summary
    print(f"\n{'=' * 80}")
    print(f"  RESULTADO FINAL")
    print(f"{'=' * 80}")
    
    m5_pnl = df_r['m5_pnl'].sum()
    m1_pnl = df_r['m1_pnl'].sum()
    
    df_r['m5_cum'] = df_r['m5_pnl'].cumsum()
    df_r['m5_peak'] = df_r['m5_cum'].cummax()
    df_r['m5_dd'] = df_r['m5_peak'] - df_r['m5_cum']
    m5_maxdd = df_r['m5_dd'].max()
    
    df_r['m1_cum'] = df_r['m1_pnl'].cumsum()
    df_r['m1_peak'] = df_r['m1_cum'].cummax()
    df_r['m1_dd'] = df_r['m1_peak'] - df_r['m1_cum']
    m1_maxdd = df_r['m1_dd'].max()
    
    m5_wr = len(df_r[df_r['m5_pnl'] > 0]) / len(df_r) * 100
    m1_wr = len(df_r[df_r['m1_pnl'] > 0]) / len(df_r) * 100
    
    m5_tp = len(df_r[df_r['m5_reason'] == 'TP'])
    m5_sl = len(df_r[df_r['m5_reason'] == 'SL'])
    m1_tp = len(df_r[df_r['m1_reason'] == 'TP'])
    m1_sl = len(df_r[df_r['m1_reason'] == 'SL'])
    
    matches = df_r['match'].sum()
    divergent = len(df_r) - matches
    
    print(f"\n{'Métrica':<20} | {'M5 (TP-first)':<18} | {'M1 (SL-first)':<18} | {'Delta':<10}")
    print("-" * 72)
    print(f"{'Trades':<20} | {len(df_r):<18} | {len(df_r):<18} | {'0':<10}")
    print(f"{'Win Rate':<20} | {m5_wr:<18.1f} | {m1_wr:<18.1f} | {m1_wr-m5_wr:<+10.1f}")
    print(f"{'PnL':<20} | {m5_pnl:<18.0f} | {m1_pnl:<18.0f} | {m1_pnl-m5_pnl:<+10.0f}")
    print(f"{'Max DD':<20} | {m5_maxdd:<18.0f} | {m1_maxdd:<18.0f} | {m1_maxdd-m5_maxdd:<+10.0f}")
    print(f"{'Ret/DD':<20} | {m5_pnl/m5_maxdd if m5_maxdd>0 else 0:<18.2f} | {m1_pnl/m1_maxdd if m1_maxdd>0 else 0:<18.2f} |")
    print(f"{'TP exits':<20} | {m5_tp:<18} | {m1_tp:<18} | {m1_tp-m5_tp:<+10}")
    print(f"{'SL exits':<20} | {m5_sl:<18} | {m1_sl:<18} | {m1_sl-m5_sl:<+10}")
    print(f"{'Concordância':<20} | {matches}/{len(df_r)} ({matches/len(df_r)*100:.1f}%)")
    
    # Show divergent trades
    df_div = df_r[~df_r['match']]
    if len(df_div) > 0:
        print(f"\n  TRADES DIVERGENTES ({len(df_div)}):")
        print(f"  {'#':>3} | {'Data':>16} | {'Dir':>4} | {'M5':>4} | {'M1':>4} | {'M5_PnL':>7} | {'M1_PnL':>7}")
        print("  " + "-" * 60)
        for _, row in df_div.iterrows():
            d = "BUY" if row['dir']==1 else "SELL"
            dt = row['entry_dt'].strftime('%Y-%m-%d %H:%M')
            print(f"  {_+1:>3} | {dt:>16} | {d:>4} | {row['m5_reason']:>4} | {row['m1_reason']:>4} | {row['m5_pnl']:>+7.0f} | {row['m1_pnl']:>+7.0f}")

if __name__ == "__main__":
    main()
