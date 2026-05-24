"""
AUDIT DO MOTOR DE BACKTEST — run_backtest_cooldown()

Checklist de vieses conhecidos em backtests de barra (candlestick):

1. ENTRY: Entra no CLOSE da barra de sinal.
   - OK: O close é o último preço da barra. Em M5, é factível.
   - Premissa: zero slippage. Aceitável para M5 no WIN (alta liquidez).

2. EXIT — TP/SL PRIORITY BIAS (*** BUG ENCONTRADO ***):
   O código checa TP ANTES do SL:
     if win_high[i] >= entry + tp:   # TP primeiro
         ...
     elif win_low[i] <= entry - sl:  # SL só se TP não bateu
   
   Quando a barra é grande o suficiente para atingir AMBOS (TP e SL),
   o backtest SEMPRE assume que o TP foi atingido primeiro.
   Isso INFLA artificialmente o PnL.
   
   Correção conservadora: se ambos podem ser atingidos na mesma barra,
   assumir que o SL foi atingido primeiro (pessimista).
   Correção neutra: checar a distância do OPEN até cada nível.

3. SAME-BAR EXIT:
   O trade abre no CLOSE da barra i. Na barra i+1, já checa H/L.
   OK: Não há exit na mesma barra de entrada (entry é no close).

4. bars_held BIAS:
   bars_held é incrementado ANTES de checar exits. Portanto o
   primeiro candle pós-entrada já conta como bars_held=1. OK.

5. EOD EXIT:
   Se nenhum TP/SL foi atingido, fecha no close às 17:30. OK.

Vamos quantificar o impacto do viés #2.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from datetime import time as dt_time

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

def backtest_pessimista(df, sl_pts, tp_pts, start_h, end_h, wait_bars):
    """
    Versão PESSIMISTA: quando ambos TP e SL podem ser atingidos
    na mesma barra, assume que o SL bateu primeiro.
    """
    trades = []
    open_trade = None
    cooldown_until = None
    
    win_high = df['win_high'].values
    win_low = df['win_low'].values
    win_open = df['win'].values  # close of previous = approx open of current
    win_close = df['win'].values
    signals = df['signal'].values
    times = df.index
    
    eod_time = dt_time(17, 30)
    t_start = dt_time(start_h, 0)
    t_end = dt_time(end_h, 0)
    
    for i in range(len(df)):
        dt = times[i]
        t = dt.time()
        
        if open_trade is not None:
            open_trade['bars_held'] += 1
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
            
            hit_exit = False
            exit_price = None
            exit_reason = None
            
            if direction == 1:  # BUY
                can_tp = win_high[i] >= entry_price + tp_pts
                can_sl = win_low[i] <= entry_price - sl_pts
                
                if can_tp and can_sl:
                    # AMBOS atingidos — PESSIMISTA: SL primeiro
                    hit_exit, exit_price, exit_reason = True, entry_price - sl_pts, "SL*"
                elif can_tp:
                    hit_exit, exit_price, exit_reason = True, entry_price + tp_pts, "TP"
                elif can_sl:
                    hit_exit, exit_price, exit_reason = True, entry_price - sl_pts, "SL"
                    
            else:  # SELL
                can_tp = win_low[i] <= entry_price - tp_pts
                can_sl = win_high[i] >= entry_price + sl_pts
                
                if can_tp and can_sl:
                    # AMBOS atingidos — PESSIMISTA: SL primeiro
                    hit_exit, exit_price, exit_reason = True, entry_price + sl_pts, "SL*"
                elif can_tp:
                    hit_exit, exit_price, exit_reason = True, entry_price - tp_pts, "TP"
                elif can_sl:
                    hit_exit, exit_price, exit_reason = True, entry_price + sl_pts, "SL"
            
            if not hit_exit and t >= eod_time:
                hit_exit, exit_price, exit_reason = True, win_close[i], "EOD"
                
            if hit_exit:
                open_trade['exit_price'] = exit_price
                open_trade['exit_reason'] = exit_reason
                open_trade['pnl'] = (exit_price - entry_price) * direction
                trades.append(open_trade)
                open_trade = None
                cooldown_until = i + wait_bars
                continue
                
        if open_trade is None and signals[i] != 0:
            if cooldown_until is not None and i <= cooldown_until:
                continue
            if t >= t_start and t < t_end:
                open_trade = {
                    'direction': signals[i],
                    'entry_price': win_close[i],
                    'entry_dt': dt,
                    'bars_held': 0,
                }
            
    return trades

def backtest_otimista(df, sl_pts, tp_pts, start_h, end_h, wait_bars):
    """
    Versão OTIMISTA (código atual): quando ambos TP e SL podem ser 
    atingidos na mesma barra, assume que o TP bateu primeiro.
    """
    trades = []
    open_trade = None
    cooldown_until = None
    
    win_high = df['win_high'].values
    win_low = df['win_low'].values
    win_close = df['win'].values
    signals = df['signal'].values
    times = df.index
    
    eod_time = dt_time(17, 30)
    t_start = dt_time(start_h, 0)
    t_end = dt_time(end_h, 0)
    
    for i in range(len(df)):
        dt = times[i]
        t = dt.time()
        
        if open_trade is not None:
            open_trade['bars_held'] += 1
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
            
            hit_exit = False
            exit_price = None
            exit_reason = None
            
            if direction == 1:
                if win_high[i] >= entry_price + tp_pts:
                    hit_exit, exit_price, exit_reason = True, entry_price + tp_pts, "TP"
                elif win_low[i] <= entry_price - sl_pts:
                    hit_exit, exit_price, exit_reason = True, entry_price - sl_pts, "SL"
            else:
                if win_low[i] <= entry_price - tp_pts:
                    hit_exit, exit_price, exit_reason = True, entry_price - tp_pts, "TP"
                elif win_high[i] >= entry_price + sl_pts:
                    hit_exit, exit_price, exit_reason = True, entry_price + sl_pts, "SL"
            
            if not hit_exit and t >= eod_time:
                hit_exit, exit_price, exit_reason = True, win_close[i], "EOD"
                
            if hit_exit:
                open_trade['exit_price'] = exit_price
                open_trade['exit_reason'] = exit_reason
                open_trade['pnl'] = (exit_price - entry_price) * direction
                trades.append(open_trade)
                open_trade = None
                cooldown_until = i + wait_bars
                continue
                
        if open_trade is None and signals[i] != 0:
            if cooldown_until is not None and i <= cooldown_until:
                continue
            if t >= t_start and t < t_end:
                open_trade = {
                    'direction': signals[i],
                    'entry_price': win_close[i],
                    'entry_dt': dt,
                    'bars_held': 0,
                }
            
    return trades

def evaluate(trades):
    if not trades:
        return 0, 0, 0, 0, 0
    df_t = pd.DataFrame(trades)
    pnl = df_t['pnl'].sum()
    df_t['cum'] = df_t['pnl'].cumsum()
    df_t['peak'] = df_t['cum'].cummax()
    df_t['dd'] = df_t['peak'] - df_t['cum']
    max_dd = df_t['dd'].max()
    ret_dd = pnl / max_dd if max_dd > 0 else 0
    wr = len(df_t[df_t['pnl'] > 0]) / len(df_t) * 100
    
    # Contar barras ambíguas (SL*)
    ambiguous = len(df_t[df_t['exit_reason'] == 'SL*']) if 'exit_reason' in df_t.columns else 0
    
    return pnl, max_dd, ret_dd, len(trades), wr, ambiguous

def main():
    print("=" * 80)
    print("  BACKTEST ENGINE AUDIT: OTIMISTA VS PESSIMISTA")
    print("=" * 80)
    
    df_base = fetch_local_history()
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    # Setup vencedor
    bw, lb_nwe, mae_mult = 3, 200, 4.0
    z_val, sl, tp = 2.2, 300, 500
    
    nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb_nwe, mult_mae=1.0)
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
    
    print(f"\nConfig: Z={z_val} | NWE(BW={bw}, LB={lb_nwe}, MAE={mae_mult}) | SL={sl} | TP={tp}")
    
    # Rodar ambos
    trades_opt = backtest_otimista(df_base, sl, tp, 9, 16, 2)
    trades_pes = backtest_pessimista(df_base, sl, tp, 9, 16, 2)
    
    pnl_o, dd_o, rd_o, tc_o, wr_o, _ = evaluate(trades_opt)
    pnl_p, dd_p, rd_p, tc_p, wr_p, amb_p = evaluate(trades_pes)
    
    print(f"\n{'Métrica':<25} | {'OTIMISTA (atual)':<20} | {'PESSIMISTA':<20} | {'Delta':<15}")
    print("-" * 85)
    print(f"{'Trades':<25} | {tc_o:<20} | {tc_p:<20} | {tc_p - tc_o:<15}")
    print(f"{'Win Rate':<25} | {wr_o:<20.1f} | {wr_p:<20.1f} | {wr_p - wr_o:<15.1f}")
    print(f"{'PnL':<25} | {pnl_o:<20.0f} | {pnl_p:<20.0f} | {pnl_p - pnl_o:<15.0f}")
    print(f"{'Max Drawdown':<25} | {dd_o:<20.0f} | {dd_p:<20.0f} | {dd_p - dd_o:<15.0f}")
    print(f"{'Ret/DD':<25} | {rd_o:<20.2f} | {rd_p:<20.2f} | {rd_p - rd_o:<15.2f}")
    print(f"{'Barras Ambíguas (SL*)':<25} | {'N/A':<20} | {amb_p:<20} | {'---':<15}")
    
    print(f"\n{'=' * 80}")
    print(f"  INTERPRETAÇÃO")
    print(f"{'=' * 80}")
    
    if amb_p > 0:
        pct_amb = amb_p / tc_p * 100
        print(f"  Em {amb_p} de {tc_p} trades ({pct_amb:.1f}%), tanto o TP quanto o SL")
        print(f"  poderiam ter sido atingidos na MESMA barra M5.")
        print(f"  O motor atual (otimista) assume TP primeiro — viés positivo.")
        print(f"  O motor pessimista assume SL primeiro — viés negativo.")
        print(f"  A REALIDADE está entre os dois valores.")
        inflacao = pnl_o - pnl_p
        print(f"\n  >>> INFLAÇÃO MÁXIMA POSSÍVEL: {inflacao:.0f} pts ({inflacao/pnl_o*100:.1f}% do PnL otimista)")
    else:
        print(f"  ZERO barras ambíguas! O motor está limpo de viés TP/SL.")
    
if __name__ == "__main__":
    main()
