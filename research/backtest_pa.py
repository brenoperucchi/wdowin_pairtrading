"""
Backtest V2 — Price Action com RR 2:1
======================================
Entrada confirmada por breakout da barra de sinal.
SL = extremo oposto da barra de sinal + 5 ticks.
TP = 2x SL.
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
RHO_MIN = -0.40       # safe_to_trade threshold
BETA_REF_WINDOW = 80
BETA_DELTA_MAX = 25.0

# Ticks de margem para SL
WIN_TICK = 5.0         # 1 tick WIN = 5 pontos
WDO_TICK = 0.5         # 1 tick WDO = 0.5 pontos
SL_TICKS = 5           # margem em ticks

# Sizing
WDO_CONTRACTS = 1
WIN_CONTRACTS = 2
WDO_PV = 10.0          # R$/ponto WDO
WIN_PV = 0.20          # R$/ponto/contrato WIN

# Sessao
ENTRY_START = time(9, 15)
ENTRY_END = time(16, 0)
FORCE_CLOSE_TIME = time(17, 40)


def load_m5_ohlc():
    """Carrega e agrega M1 para M5 com OHLC completo."""
    print("[1/5] Carregando CSVs...")
    cols = ['date', 'time', 'open', 'high', 'low', 'close', 'tickvol', 'vol', 'spread']
    
    wdo = pd.read_csv(WDO_CSV, sep='\t', names=cols, skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    print(f"    WDO: {len(wdo):,} barras M1 | WIN: {len(win):,} barras M1")
    
    wdo['dt'] = pd.to_datetime(wdo['date'] + ' ' + wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date'] + ' ' + win['time'], format='%Y.%m.%d %H:%M:%S')
    wdo.set_index('dt', inplace=True)
    win.set_index('dt', inplace=True)
    
    print("[2/5] Agregando M5...")
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'}
    
    wdo5 = wdo.resample('5min').agg(agg).dropna()
    win5 = win.resample('5min').agg(agg).dropna()
    
    # Join com sufixos
    merged = wdo5.add_suffix('_wdo').join(win5.add_suffix('_win'), how='inner').dropna()
    print(f"    M5 alinhadas: {len(merged):,} barras")
    print(f"    Periodo: {merged.index[0]} -> {merged.index[-1]}")
    
    return merged


def calc_indicators(win_close, wdo_close, model='v1'):
    """Calcula z-scores e rho para V1 (OLS) ou V2 (Kalman)."""
    n = len(win_close)
    betas = np.zeros(n)
    z_scores = np.zeros(n)
    rho_arr = np.zeros(n)
    
    if model == 'v1':
        for i in range(WINDOW, n):
            w_win = win_close[i - WINDOW:i]
            w_wdo = wdo_close[i - WINDOW:i]
            cov = np.cov(w_win, w_wdo)
            beta = cov[0, 1] / (cov[1, 1] + 1e-10)
            betas[i] = beta
            spread_w = win_close[max(0, i-WINDOW):i] - beta * wdo_close[max(0, i-WINDOW):i]
            current_spread = win_close[i] - beta * wdo_close[i]
            mu = spread_w.mean()
            sd = spread_w.std() + 1e-6
            z_scores[i] = (current_spread - mu) / sd
            if w_win.std() > 0 and w_wdo.std() > 0:
                rho_arr[i] = np.corrcoef(w_win, w_wdo)[0, 1]
    else:
        kf = KalmanBetaFilter(initial_beta=BETA_INITIAL)
        kf_spreads = []
        for i in range(n):
            beta, spread, var = kf.update(float(win_close[i]), float(wdo_close[i]))
            kf_spreads.append(spread)
            betas[i] = beta
        z_scores = np.array(KalmanBetaFilter.rolling_zscore(kf_spreads, window=WINDOW))
        for i in range(WINDOW, n):
            w_win = win_close[i - WINDOW:i]
            w_wdo = wdo_close[i - WINDOW:i]
            if w_win.std() > 0 and w_wdo.std() > 0:
                rho_arr[i] = np.corrcoef(w_win, w_wdo)[0, 1]
    
    return betas, z_scores, rho_arr


def is_safe(betas, idx, rho):
    if rho > RHO_MIN:
        return False
    if idx < BETA_REF_WINDOW:
        return True
    ref = np.mean(betas[idx - BETA_REF_WINDOW:idx - WINDOW]) if idx > BETA_REF_WINDOW else betas[max(0, idx-1)]
    if abs(ref) < 1e-6:
        return True
    return abs((betas[idx] - ref) / abs(ref) * 100) < BETA_DELTA_MAX


def simulate(data, z_scores, rho_arr, betas, model_name):
    """
    Simula trades com entry por breakout e SL/TP por preco.
    
    Para cada leg (wdo_buy, wdo_sell, win_buy, win_sell):
      - Barra de sinal: |z| cruza 2.0 (e safe_to_trade)
      - Pendente: entrada na barra seguinte se confirmar breakout
      - SL: extremo oposto + 5 ticks
      - TP: 2x SL
    """
    n = len(z_scores)
    timestamps = data.index
    
    legs = ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell']
    
    # Estado por leg
    pending = {leg: None for leg in legs}    # sinal pendente de confirmacao
    position = {leg: None for leg in legs}   # posicao aberta
    all_trades = {leg: [] for leg in legs}
    
    for i in range(WINDOW, n):
        ts = timestamps[i]
        t = ts.time()
        z = z_scores[i]
        rho = rho_arr[i]
        safe = is_safe(betas, i, rho)
        
        # OHLC da barra atual
        wdo_o, wdo_h, wdo_l, wdo_c = data.iloc[i]['open_wdo'], data.iloc[i]['high_wdo'], data.iloc[i]['low_wdo'], data.iloc[i]['close_wdo']
        win_o, win_h, win_l, win_c = data.iloc[i]['open_win'], data.iloc[i]['high_win'], data.iloc[i]['low_win'], data.iloc[i]['close_win']
        
        # ═══ 1. Checar saidas de posicoes abertas ═══
        for leg in legs:
            pos = position[leg]
            if pos is None:
                continue
            
            asset = 'wdo' if 'wdo' in leg else 'win'
            direction = 'buy' if 'buy' in leg else 'sell'
            bar_h = wdo_h if asset == 'wdo' else win_h
            bar_l = wdo_l if asset == 'wdo' else win_l
            bar_c = wdo_c if asset == 'wdo' else win_c
            
            tp = pos['tp']
            sl = pos['sl']
            reason = None
            exit_price = 0.0
            
            if direction == 'buy':
                # TP acima, SL abaixo
                if bar_h >= tp:
                    reason = 'TP'
                    exit_price = tp
                elif bar_l <= sl:
                    reason = 'SL'
                    exit_price = sl
            else:
                # TP abaixo, SL acima
                if bar_l <= tp:
                    reason = 'TP'
                    exit_price = tp
                elif bar_h >= sl:
                    reason = 'SL'
                    exit_price = sl
            
            # Force close
            if reason is None and t >= FORCE_CLOSE_TIME:
                reason = 'FORCE_CLOSE'
                exit_price = bar_c
            
            if reason:
                contracts = WDO_CONTRACTS if asset == 'wdo' else WIN_CONTRACTS
                pv = WDO_PV if asset == 'wdo' else WIN_PV
                dir_mult = 1 if direction == 'buy' else -1
                pnl = dir_mult * (exit_price - pos['entry_price']) * contracts * pv
                
                trade = {
                    'model': model_name,
                    'leg': leg,
                    'entry_time': str(pos['entry_time']),
                    'exit_time': str(ts),
                    'signal_time': str(pos['signal_time']),
                    'entry_price': pos['entry_price'],
                    'exit_price': round(exit_price, 2),
                    'sl': pos['sl'],
                    'tp': pos['tp'],
                    'sl_dist': round(pos['sl_dist'], 2),
                    'tp_dist': round(pos['tp_dist'], 2),
                    'entry_z': pos['entry_z'],
                    'exit_reason': reason,
                    'pnl': round(pnl, 2),
                    'bars_held': i - pos['entry_bar'],
                }
                all_trades[leg].append(trade)
                position[leg] = None
        
        # ═══ 2. Checar ordens pendentes (confirmacao de breakout) ═══
        for leg in legs:
            pend = pending[leg]
            if pend is None:
                continue
            
            # Se ja tem posicao, cancela pendente
            if position[leg] is not None:
                pending[leg] = None
                continue
            
            # Pendente expira se nao confirma nesta barra (validade 1 barra)
            asset = 'wdo' if 'wdo' in leg else 'win'
            direction = 'buy' if 'buy' in leg else 'sell'
            bar_h = wdo_h if asset == 'wdo' else win_h
            bar_l = wdo_l if asset == 'wdo' else win_l
            
            tick = WDO_TICK if asset == 'wdo' else WIN_TICK
            confirmed = False
            entry_price = 0.0
            sl_price = 0.0
            
            if direction == 'buy':
                # Confirma se barra atual supera HIGH da barra de sinal
                trigger = pend['signal_high']
                if bar_h > trigger:
                    confirmed = True
                    entry_price = trigger  # entrada no rompimento da maxima
                    sl_price = pend['signal_low'] - SL_TICKS * tick  # SL = minima - 5 ticks
            else:
                # Confirma se barra atual rompe LOW da barra de sinal
                trigger = pend['signal_low']
                if bar_l < trigger:
                    confirmed = True
                    entry_price = trigger  # entrada no rompimento da minima
                    sl_price = pend['signal_high'] + SL_TICKS * tick  # SL = maxima + 5 ticks
            
            if confirmed:
                sl_dist = abs(entry_price - sl_price)
                tp_dist = 2.0 * sl_dist
                
                if direction == 'buy':
                    tp_price = entry_price + tp_dist
                else:
                    tp_price = entry_price - tp_dist
                
                position[leg] = {
                    'entry_time': ts,
                    'signal_time': pend['signal_time'],
                    'entry_price': entry_price,
                    'sl': sl_price,
                    'tp': tp_price,
                    'sl_dist': sl_dist,
                    'tp_dist': tp_dist,
                    'entry_z': pend['signal_z'],
                    'entry_bar': i,
                }
            
            # Pendente consumido (confirmou ou nao)
            pending[leg] = None
        
        # ═══ 3. Gerar novos sinais ═══
        if t < ENTRY_START or t > ENTRY_END:
            continue
        if not safe:
            continue
        if abs(z) < Z_ENTRY_MIN or abs(z) >= Z_ENTRY_MAX:
            continue
        
        # z > +2: WIN caro -> compra WDO (espera subir), vende WIN (espera cair)
        if z > Z_ENTRY_MIN:
            if position['wdo_buy'] is None and pending['wdo_buy'] is None:
                pending['wdo_buy'] = {
                    'signal_time': ts, 'signal_z': z,
                    'signal_high': wdo_h, 'signal_low': wdo_l,
                }
            if position['win_sell'] is None and pending['win_sell'] is None:
                pending['win_sell'] = {
                    'signal_time': ts, 'signal_z': z,
                    'signal_high': win_h, 'signal_low': win_l,
                }
        
        # z < -2: WIN barato -> vende WDO (espera cair), compra WIN (espera subir)
        elif z < -Z_ENTRY_MIN:
            if position['wdo_sell'] is None and pending['wdo_sell'] is None:
                pending['wdo_sell'] = {
                    'signal_time': ts, 'signal_z': z,
                    'signal_high': wdo_h, 'signal_low': wdo_l,
                }
            if position['win_buy'] is None and pending['win_buy'] is None:
                pending['win_buy'] = {
                    'signal_time': ts, 'signal_z': z,
                    'signal_high': win_h, 'signal_low': win_l,
                }
    
    return all_trades


def report(all_results):
    """Gera relatorio formatado."""
    lines = []
    lines.append('=' * 100)
    lines.append('  BACKTEST V2 — Price Action + RR 2:1 — Breakout Confirmation')
    lines.append('=' * 100)
    lines.append('')
    lines.append(f'{"Modelo":<12} {"Leg":<12} {"Trades":>7} {"Win%":>7} {"PnL":>10} {"Avg":>8} {"PF":>6} {"Bars":>6} {"TP":>5} {"SL":>5} {"FC":>5}')
    lines.append('-' * 100)
    
    for model in ['V1_OLS', 'V2_KALMAN']:
        model_pnl = 0
        model_trades = 0
        for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell']:
            key = f'{model}_{leg}'
            trades = all_results.get(key, [])
            if not trades:
                continue
            
            pnls = [t['pnl'] for t in trades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]
            wr = len(wins) / len(trades) * 100
            total_pnl = sum(pnls)
            avg = np.mean(pnls)
            gp = sum(wins) if wins else 0
            gl = abs(sum(losses)) if losses else 0.001
            pf = gp / gl
            bars = np.mean([t['bars_held'] for t in trades])
            
            tp_count = sum(1 for t in trades if t['exit_reason'] == 'TP')
            sl_count = sum(1 for t in trades if t['exit_reason'] == 'SL')
            fc_count = sum(1 for t in trades if t['exit_reason'] == 'FORCE_CLOSE')
            
            lines.append(f'{model:<12} {leg:<12} {len(trades):>7} {wr:>6.1f}% {total_pnl:>10,.0f} {avg:>8,.1f} {pf:>6.2f} {bars:>6.1f} {tp_count:>5} {sl_count:>5} {fc_count:>5}')
            
            model_pnl += total_pnl
            model_trades += len(trades)
        
        lines.append(f'{model:<12} {"TOTAL":<12} {model_trades:>7} {"":>7} {model_pnl:>10,.0f}')
        lines.append('')
    
    # SL distance stats
    lines.append('-' * 100)
    lines.append('SL DISTANCE STATS (pontos do ativo):')
    for model in ['V1_OLS', 'V2_KALMAN']:
        for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell']:
            key = f'{model}_{leg}'
            trades = all_results.get(key, [])
            if trades:
                sl_dists = [t['sl_dist'] for t in trades]
                lines.append(f'  {model} {leg}: avg_sl={np.mean(sl_dists):.1f} med={np.median(sl_dists):.1f} min={np.min(sl_dists):.1f} max={np.max(sl_dists):.1f}')
    
    output = '\n'.join(lines)
    with open('backtest_v2_report.txt', 'w', encoding='utf-8') as f:
        f.write(output)
    print(output)
    return output


def main():
    start = datetime.now()
    
    data = load_m5_ohlc()
    win_close = data['close_win'].values.astype(float)
    wdo_close = data['close_wdo'].values.astype(float)
    
    print("[3/5] Calculando V1 (OLS)...")
    betas_v1, z_v1, rho_v1 = calc_indicators(win_close, wdo_close, model='v1')
    
    print("[4/5] Calculando V2 (Kalman)...")
    betas_v2, z_v2, rho_v2 = calc_indicators(win_close, wdo_close, model='v2')
    
    print("[5/5] Simulando trades...")
    trades_v1 = simulate(data, z_v1, rho_v1, betas_v1, 'V1_OLS')
    trades_v2 = simulate(data, z_v2, rho_v2, betas_v2, 'V2_KALMAN')
    
    # Combina resultados
    all_results = {}
    all_trade_rows = []
    for model_name, model_trades in [('V1_OLS', trades_v1), ('V2_KALMAN', trades_v2)]:
        for leg_name, leg_trades in model_trades.items():
            key = f'{model_name}_{leg_name}'
            all_results[key] = leg_trades
            all_trade_rows.extend(leg_trades)
    
    # Relatorio
    report(all_results)
    
    # Salvar CSV
    if all_trade_rows:
        df = pd.DataFrame(all_trade_rows)
        df.to_csv('backtest_v2_trades.csv', index=False)
        print(f'\n[OK] {len(all_trade_rows)} trades salvos em backtest_v2_trades.csv')
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f'[OK] Concluido em {elapsed:.1f}s')


if __name__ == '__main__':
    main()
