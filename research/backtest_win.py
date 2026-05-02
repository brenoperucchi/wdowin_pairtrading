"""
Backtest WIN Only — Entry a mercado, SL 560 / TP 600
=====================================================
Sinal: |z| >= 2.0 e < 4.0, safe_to_trade=True
Entrada imediata no close da barra de sinal.
SL = 560 pontos | TP = 600 pontos | Force close 17:40
WIN: 2 contratos x R$0.20/ponto = R$0.40/ponto
"""

import numpy as np
import pandas as pd
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"

WINDOW = 40
BETA_INITIAL = -22.5
Z_ENTRY_MIN = 2.0
Z_ENTRY_MAX = 4.0
RHO_MIN = -0.40
BETA_REF_WINDOW = 80
BETA_DELTA_MAX = 25.0

# Risk
SL_POINTS = 560.0
TP_POINTS = 600.0

# Sizing WIN
WIN_CONTRACTS = 2
WIN_PV = 0.20  # R$/ponto/contrato

# Sessao
ENTRY_START = time(9, 15)
ENTRY_END = time(16, 0)
FORCE_CLOSE_TIME = time(17, 40)


def load_m5():
    print("[1/5] Carregando CSVs...")
    cols = ['date', 'time', 'open', 'high', 'low', 'close', 'tickvol', 'vol', 'spread']
    wdo = pd.read_csv(WDO_CSV, sep='\t', names=cols, skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    print(f"    WDO: {len(wdo):,} M1 | WIN: {len(win):,} M1")
    
    wdo['dt'] = pd.to_datetime(wdo['date'] + ' ' + wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date'] + ' ' + win['time'], format='%Y.%m.%d %H:%M:%S')
    wdo.set_index('dt', inplace=True)
    win.set_index('dt', inplace=True)
    
    print("[2/5] Agregando M5...")
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'}
    wdo5 = wdo.resample('5min').agg(agg).dropna()
    win5 = win.resample('5min').agg(agg).dropna()
    
    merged = wdo5[['close']].rename(columns={'close': 'wdo'}).join(
        win5.rename(columns={'open': 'win_open', 'high': 'win_high', 'low': 'win_low', 'close': 'win'}),
        how='inner').dropna()
    
    print(f"    M5: {len(merged):,} barras | {merged.index[0]} -> {merged.index[-1]}")
    return merged


def calc_indicators(win_close, wdo_close, model='v1'):
    n = len(win_close)
    betas = np.zeros(n)
    z_scores = np.zeros(n)
    rho_arr = np.zeros(n)
    
    if model == 'v1':
        for i in range(WINDOW, n):
            w_win = win_close[i-WINDOW:i]
            w_wdo = wdo_close[i-WINDOW:i]
            cov = np.cov(w_win, w_wdo)
            beta = cov[0, 1] / (cov[1, 1] + 1e-10)
            betas[i] = beta
            spread_w = win_close[max(0, i-WINDOW):i] - beta * wdo_close[max(0, i-WINDOW):i]
            cs = win_close[i] - beta * wdo_close[i]
            mu = spread_w.mean(); sd = spread_w.std() + 1e-6
            z_scores[i] = (cs - mu) / sd
            if w_win.std() > 0 and w_wdo.std() > 0:
                rho_arr[i] = np.corrcoef(w_win, w_wdo)[0, 1]
    else:
        kf = KalmanBetaFilter(initial_beta=BETA_INITIAL)
        kf_spreads = []
        for i in range(n):
            beta, spread, var = kf.update(float(win_close[i]), float(wdo_close[i]))
            kf_spreads.append(spread); betas[i] = beta
        z_scores = np.array(KalmanBetaFilter.rolling_zscore(kf_spreads, window=WINDOW))
        for i in range(WINDOW, n):
            w_win = win_close[i-WINDOW:i]; w_wdo = wdo_close[i-WINDOW:i]
            if w_win.std() > 0 and w_wdo.std() > 0:
                rho_arr[i] = np.corrcoef(w_win, w_wdo)[0, 1]
    return betas, z_scores, rho_arr


def is_safe(betas, idx, rho):
    if rho > RHO_MIN: return False
    if idx < BETA_REF_WINDOW: return True
    ref = np.mean(betas[idx-BETA_REF_WINDOW:idx-WINDOW]) if idx > BETA_REF_WINDOW else betas[max(0, idx-1)]
    if abs(ref) < 1e-6: return True
    return abs((betas[idx] - ref) / abs(ref) * 100) < BETA_DELTA_MAX


def simulate(data, z_scores, rho_arr, betas, model_name):
    n = len(z_scores)
    ts_arr = data.index
    
    # Posicoes: win_buy e win_sell
    pos_buy = None
    pos_sell = None
    trades_buy = []
    trades_sell = []
    
    for i in range(WINDOW, n):
        ts = ts_arr[i]
        t = ts.time()
        z = z_scores[i]
        rho = rho_arr[i]
        win_h = data.iloc[i]['win_high']
        win_l = data.iloc[i]['win_low']
        win_c = data.iloc[i]['win']
        safe = is_safe(betas, i, rho)
        
        # ═══ Checar saidas WIN BUY ═══
        if pos_buy is not None:
            reason = None; exit_px = 0
            tp = pos_buy['entry_price'] + TP_POINTS
            sl = pos_buy['entry_price'] - SL_POINTS
            
            if win_h >= tp:
                reason = 'TP'; exit_px = tp
            elif win_l <= sl:
                reason = 'SL'; exit_px = sl
            elif t >= FORCE_CLOSE_TIME:
                reason = 'FC'; exit_px = win_c
            
            if reason:
                pnl = (exit_px - pos_buy['entry_price']) * WIN_CONTRACTS * WIN_PV
                trades_buy.append({
                    'model': model_name, 'leg': 'win_buy',
                    'entry_time': str(pos_buy['ts']), 'exit_time': str(ts),
                    'entry_price': pos_buy['entry_price'], 'exit_price': round(exit_px, 1),
                    'entry_z': round(pos_buy['z'], 3),
                    'exit_reason': reason, 'pnl': round(pnl, 2),
                    'bars_held': i - pos_buy['bar']
                })
                pos_buy = None
        
        # ═══ Checar saidas WIN SELL ═══
        if pos_sell is not None:
            reason = None; exit_px = 0
            tp = pos_sell['entry_price'] - TP_POINTS
            sl = pos_sell['entry_price'] + SL_POINTS
            
            if win_l <= tp:
                reason = 'TP'; exit_px = tp
            elif win_h >= sl:
                reason = 'SL'; exit_px = sl
            elif t >= FORCE_CLOSE_TIME:
                reason = 'FC'; exit_px = win_c
            
            if reason:
                pnl = (pos_sell['entry_price'] - exit_px) * WIN_CONTRACTS * WIN_PV
                trades_sell.append({
                    'model': model_name, 'leg': 'win_sell',
                    'entry_time': str(pos_sell['ts']), 'exit_time': str(ts),
                    'entry_price': pos_sell['entry_price'], 'exit_price': round(exit_px, 1),
                    'entry_z': round(pos_sell['z'], 3),
                    'exit_reason': reason, 'pnl': round(pnl, 2),
                    'bars_held': i - pos_sell['bar']
                })
                pos_sell = None
        
        # ═══ Entradas ═══
        if t < ENTRY_START or t > ENTRY_END or not safe:
            continue
        if abs(z) < Z_ENTRY_MIN or abs(z) >= Z_ENTRY_MAX:
            continue
        
        # z < -2: WIN barato -> COMPRA WIN
        if z < -Z_ENTRY_MIN and pos_buy is None:
            pos_buy = {'ts': ts, 'entry_price': win_c, 'z': z, 'bar': i}
        
        # z > +2: WIN caro -> VENDE WIN
        if z > Z_ENTRY_MIN and pos_sell is None:
            pos_sell = {'ts': ts, 'entry_price': win_c, 'z': z, 'bar': i}
    
    return trades_buy, trades_sell


def print_results(label, trades):
    if not trades:
        print(f'  {label}: 0 trades')
        return
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins)/len(trades)*100
    gp = sum(wins) if wins else 0
    gl = abs(sum(losses)) if losses else 0.001
    
    # Max drawdown
    eq = np.cumsum(pnls)
    pk = np.maximum.accumulate(eq)
    dd = (pk - eq).max()
    
    tp = sum(1 for t in trades if t['exit_reason']=='TP')
    sl = sum(1 for t in trades if t['exit_reason']=='SL')
    fc = sum(1 for t in trades if t['exit_reason']=='FC')
    bars = np.mean([t['bars_held'] for t in trades])
    
    print(f'  {label}: {len(trades)} trd | wr={wr:.1f}% | pnl=R${sum(pnls):.0f} | avg=R${np.mean(pnls):.1f} | pf={gp/gl:.2f} | dd=R${dd:.0f} | bars={bars:.1f} | tp={tp} sl={sl} fc={fc}')


def main():
    start = datetime.now()
    data = load_m5()
    
    win_c = data['win'].values.astype(float)
    wdo_c = data['wdo'].values.astype(float)
    
    print("[3/5] V1 (OLS)...")
    b1, z1, r1 = calc_indicators(win_c, wdo_c, 'v1')
    print("[4/5] V2 (Kalman)...")
    b2, z2, r2 = calc_indicators(win_c, wdo_c, 'v2')
    
    print("[5/5] Simulando...")
    buy1, sell1 = simulate(data, z1, r1, b1, 'V1_OLS')
    buy2, sell2 = simulate(data, z2, r2, b2, 'V2_KALMAN')
    
    print(f'\n{"="*80}')
    print(f'  WIN ONLY | SL={SL_POINTS:.0f}pts TP={TP_POINTS:.0f}pts | 2 contratos')
    print(f'{"="*80}')
    
    print('\nV1 OLS:')
    print_results('win_buy ', buy1)
    print_results('win_sell', sell1)
    combined1 = buy1 + sell1
    print_results('COMBINED', combined1)
    
    print('\nV2 KALMAN:')
    print_results('win_buy ', buy2)
    print_results('win_sell', sell2)
    combined2 = buy2 + sell2
    print_results('COMBINED', combined2)
    
    # Salvar CSV
    all_trades = buy1 + sell1 + buy2 + sell2
    if all_trades:
        pd.DataFrame(all_trades).to_csv('backtest_win_trades.csv', index=False)
        print(f'\n[OK] {len(all_trades)} trades -> backtest_win_trades.csv')
    
    print(f'[OK] {(datetime.now()-start).total_seconds():.1f}s')


if __name__ == '__main__':
    main()
