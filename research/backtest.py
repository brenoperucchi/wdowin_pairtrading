"""
RESEARCH EXPLORATÓRIO — NÃO USAR COMO VALIDAÇÃO DE PRODUÇÃO
============================================================
Este script diverge do motor live (core/config.py + core/trade_engine.py).
Ver docs/PARAM_PROFILE.md §2 (divergent hardcoded values).
Validação operacional: research/run_matador_v5_johansen.py (TASK-3 AC #15).

Backtest V1 (OLS) vs V2 (Kalman) — WIN/WDO Legs Separados
==========================================================
Compara os dois modelos de z-score em 5 anos de dados M1 agregados para M5.
Testa cada ativo (WDO, WIN) como leg separado para identificar qual performa melhor.
"""

import numpy as np
import pandas as pd
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter
import os

# ─── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"

WINDOW = 40        # janela rolling para z-score e correlação
BETA_INITIAL = -22.5  # beta OLS de referência (WIN/WDO)

# Trade params
Z_ENTRY_MIN = 2.0
Z_ENTRY_MAX = 4.0
Z_TARGET = 0.5
Z_STOP = 4.5
RHO_STOP = -0.40
BETA_REF_WINDOW = 80  # barras para Δβ reference (safe_to_trade)
BETA_DELTA_MAX = 25.0  # % max de variacao do beta

# Sizing
WDO_CONTRACTS = 1
WIN_CONTRACTS = 2
WDO_POINT_VALUE = 10.0    # R$ por ponto WDO
WIN_POINT_VALUE = 0.20    # R$ por ponto WIN (por contrato)

# Sessão
ENTRY_START = time(9, 15)
ENTRY_END = time(16, 0)
FORCE_CLOSE = time(17, 40)


# ─── FUNÇÕES AUXILIARES ─────────────────────────────────────────────────────────

def load_and_merge_m5():
    """Carrega CSVs M1, parseia timestamps, agrega para M5, e faz inner-join."""
    print("[1/5] Carregando CSVs...")
    
    wdo = pd.read_csv(WDO_CSV, sep='\t', 
                       names=['date','time','open','high','low','close','tickvol','vol','spread'],
                       skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t',
                       names=['date','time','open','high','low','close','tickvol','vol','spread'],
                       skiprows=1)
    
    print(f"    WDO: {len(wdo):,} barras M1")
    print(f"    WIN: {len(win):,} barras M1")
    
    # Parsear datetime
    wdo['dt'] = pd.to_datetime(wdo['date'] + ' ' + wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date'] + ' ' + win['time'], format='%Y.%m.%d %H:%M:%S')
    
    wdo.set_index('dt', inplace=True)
    win.set_index('dt', inplace=True)
    
    # Agregar M1 → M5
    print("[2/5] Agregando para M5...")
    agg_rules = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'}
    
    wdo_m5 = wdo.resample('5min').agg(agg_rules).dropna()
    win_m5 = win.resample('5min').agg(agg_rules).dropna()
    
    # Inner join por timestamp
    merged = wdo_m5[['close']].rename(columns={'close': 'wdo'}).join(
             win_m5[['close']].rename(columns={'close': 'win'}), how='inner')
    merged.dropna(inplace=True)
    
    print(f"    M5 alinhadas: {len(merged):,} barras")
    print(f"    Período: {merged.index[0]} → {merged.index[-1]}")
    
    return merged


def calc_indicators_v1(win_prices, wdo_prices):
    """Calcula z-scores e rho com OLS rolling (V1)."""
    n = len(win_prices)
    betas = np.zeros(n)
    z_scores = np.zeros(n)
    rho_arr = np.zeros(n)
    spreads = np.zeros(n)
    
    for i in range(WINDOW, n):
        w_win = win_prices[i - WINDOW:i]
        w_wdo = wdo_prices[i - WINDOW:i]
        
        # OLS beta rolling: WIN = beta * WDO + alpha
        # beta = Cov(WIN, WDO) / Var(WDO)
        cov = np.cov(w_win, w_wdo)
        beta = cov[0, 1] / (cov[1, 1] + 1e-10)
        betas[i] = beta
        
        # Spread e z-score
        spread_window = win_prices[max(0, i-WINDOW):i] - beta * wdo_prices[max(0, i-WINDOW):i]
        current_spread = win_prices[i] - beta * wdo_prices[i]
        spreads[i] = current_spread
        
        mu = spread_window.mean()
        sd = spread_window.std() + 1e-6
        z_scores[i] = (current_spread - mu) / sd
        
        # Rho correlation
        if w_win.std() > 0 and w_wdo.std() > 0:
            rho_arr[i] = np.corrcoef(w_win, w_wdo)[0, 1]
    
    return betas, z_scores, rho_arr, spreads


def calc_indicators_v2(win_prices, wdo_prices):
    """Calcula z-scores e rho com Filtro de Kalman (V2)."""
    n = len(win_prices)
    
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL)
    kf_spreads = []
    kf_betas = []
    
    for i in range(n):
        beta, spread, var = kf.update(float(win_prices[i]), float(wdo_prices[i]))
        kf_spreads.append(spread)
        kf_betas.append(beta)
    
    betas = np.array(kf_betas)
    z_scores = np.array(KalmanBetaFilter.rolling_zscore(kf_spreads, window=WINDOW))
    
    # Rho: mesmo cálculo que V1 (Pearson em preços, janela 40)
    rho_arr = np.zeros(n)
    for i in range(WINDOW, n):
        w_win = win_prices[i - WINDOW:i]
        w_wdo = wdo_prices[i - WINDOW:i]
        if w_win.std() > 0 and w_wdo.std() > 0:
            rho_arr[i] = np.corrcoef(w_win, w_wdo)[0, 1]
    
    return betas, z_scores, rho_arr, np.array(kf_spreads)


def is_safe_to_trade(betas, idx, rho):
    """Verifica se é seguro operar: ρ saudável e Δβ dentro do limite."""
    if rho > RHO_STOP:
        return False
    
    if idx < BETA_REF_WINDOW:
        return True  # Sem dados suficientes para checar drift
    
    beta_ref = np.mean(betas[idx - BETA_REF_WINDOW:idx - WINDOW]) if idx > BETA_REF_WINDOW else betas[max(0, idx-1)]
    if abs(beta_ref) < 1e-6:
        return True
    delta_pct = abs((betas[idx] - beta_ref) / abs(beta_ref) * 100)
    return delta_pct < BETA_DELTA_MAX


def simulate_trades(timestamps, z_scores, rho_arr, betas, win_prices, wdo_prices, model_name):
    """
    Simula trades por leg separado (WDO e WIN).
    Retorna dict com 4 listas de trades: wdo_buy, wdo_sell, win_buy, win_sell.
    """
    n = len(z_scores)
    
    # Estado por leg: None ou dict com info do trade aberto
    legs = {
        'wdo_buy': {'position': None, 'trades': []},
        'wdo_sell': {'position': None, 'trades': []},
        'win_buy': {'position': None, 'trades': []},
        'win_sell': {'position': None, 'trades': []},
    }
    
    for i in range(WINDOW, n):
        ts = timestamps[i]
        t = ts.time()
        z = z_scores[i]
        rho = rho_arr[i]
        wdo_px = wdo_prices[i]
        win_px = win_prices[i]
        safe = is_safe_to_trade(betas, i, rho)
        
        # ═══ Checar saídas em TODOS os legs abertos ═══
        for leg_name, leg in legs.items():
            pos = leg['position']
            if pos is None:
                continue
            
            reason = None
            
            # Force close
            if t >= FORCE_CLOSE:
                reason = "FORCE_CLOSE"
            # Target
            elif abs(z) < Z_TARGET:
                reason = "TARGET"
            # Stop Z
            elif abs(z) >= Z_STOP:
                reason = "STOP_Z"
            # Stop Rho
            elif rho > RHO_STOP:
                reason = "STOP_RHO"
            
            if reason:
                # Calcular PnL
                if 'wdo' in leg_name:
                    direction = 1 if 'buy' in leg_name else -1
                    pnl = direction * (wdo_px - pos['entry_price']) * WDO_CONTRACTS * WDO_POINT_VALUE
                else:
                    direction = 1 if 'buy' in leg_name else -1
                    pnl = direction * (win_px - pos['entry_price']) * WIN_CONTRACTS * WIN_POINT_VALUE
                
                trade = {
                    'model': model_name,
                    'leg': leg_name,
                    'entry_time': pos['entry_time'],
                    'exit_time': ts,
                    'entry_z': pos['entry_z'],
                    'exit_z': z,
                    'entry_price': pos['entry_price'],
                    'exit_price': wdo_px if 'wdo' in leg_name else win_px,
                    'entry_rho': pos['entry_rho'],
                    'exit_rho': rho,
                    'pnl': round(pnl, 2),
                    'exit_reason': reason,
                    'bars_held': i - pos['entry_bar'],
                }
                leg['trades'].append(trade)
                leg['position'] = None
        
        # ═══ Checar entradas ═══
        if t < ENTRY_START or t > ENTRY_END:
            continue
        if not safe:
            continue
        if abs(z) < Z_ENTRY_MIN or abs(z) >= Z_ENTRY_MAX:
            continue
        
        # z > +2: WIN caro → compra WDO, vende WIN
        if z > Z_ENTRY_MIN:
            # WDO BUY
            if legs['wdo_buy']['position'] is None:
                legs['wdo_buy']['position'] = {
                    'entry_time': ts, 'entry_price': wdo_px,
                    'entry_z': z, 'entry_rho': rho, 'entry_bar': i
                }
            # WIN SELL
            if legs['win_sell']['position'] is None:
                legs['win_sell']['position'] = {
                    'entry_time': ts, 'entry_price': win_px,
                    'entry_z': z, 'entry_rho': rho, 'entry_bar': i
                }
        
        # z < -2: WIN barato → vende WDO, compra WIN
        elif z < -Z_ENTRY_MIN:
            # WDO SELL
            if legs['wdo_sell']['position'] is None:
                legs['wdo_sell']['position'] = {
                    'entry_time': ts, 'entry_price': wdo_px,
                    'entry_z': z, 'entry_rho': rho, 'entry_bar': i
                }
            # WIN BUY
            if legs['win_buy']['position'] is None:
                legs['win_buy']['position'] = {
                    'entry_time': ts, 'entry_price': win_px,
                    'entry_z': z, 'entry_rho': rho, 'entry_bar': i
                }
    
    return {name: leg['trades'] for name, leg in legs.items()}


def calc_metrics(trades):
    """Calcula métricas de performance para uma lista de trades."""
    if not trades:
        return {
            'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'pnl_total': 0, 'pnl_avg': 0, 'pnl_median': 0,
            'max_win': 0, 'max_loss': 0, 'profit_factor': 0,
            'max_drawdown': 0, 'avg_bars': 0,
            'by_reason': {}
        }
    
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    
    # Max drawdown
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = drawdown.max() if len(drawdown) > 0 else 0
    
    # Breakdown por exit_reason
    reasons = {}
    for t in trades:
        r = t['exit_reason']
        if r not in reasons:
            reasons[r] = {'count': 0, 'pnl': 0}
        reasons[r]['count'] += 1
        reasons[r]['pnl'] += t['pnl']
    
    return {
        'total': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(trades) * 100 if trades else 0,
        'pnl_total': round(sum(pnls), 2),
        'pnl_avg': round(np.mean(pnls), 2),
        'pnl_median': round(np.median(pnls), 2),
        'max_win': round(max(pnls), 2),
        'max_loss': round(min(pnls), 2),
        'profit_factor': round(gross_profit / gross_loss, 2) if gross_loss > 0 else float('inf'),
        'max_drawdown': round(max_dd, 2),
        'avg_bars': round(np.mean([t['bars_held'] for t in trades]), 1),
        'by_reason': {r: {'count': v['count'], 'pnl': round(v['pnl'], 2)} for r, v in reasons.items()}
    }


def print_report(all_results):
    """Imprime relatório comparativo formatado."""
    print("\n" + "=" * 120)
    print("  BACKTEST REPORT — V1 (OLS) vs V2 (KALMAN) — WIN/WDO Legs Separados")
    print("=" * 120)
    
    # Tabela resumo
    header = f"{'Modelo':<10} {'Leg':<12} {'Trades':>7} {'Win%':>7} {'PnL (R$)':>12} {'Avg/Trade':>10} {'P.Factor':>9} {'MaxDD':>10} {'Avg Bars':>9}"
    print(f"\n{header}")
    print("-" * 120)
    
    for model in ['V1_OLS', 'V2_KALMAN']:
        for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell']:
            key = f"{model}_{leg}"
            if key not in all_results:
                continue
            m = all_results[key]
            pf = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else "∞"
            print(f"{model:<10} {leg:<12} {m['total']:>7} {m['win_rate']:>6.1f}% {m['pnl_total']:>12,.2f} {m['pnl_avg']:>10,.2f} {pf:>9} {m['max_drawdown']:>10,.2f} {m['avg_bars']:>9.1f}")
        print()
    
    # Totais por modelo
    print("-" * 120)
    for model in ['V1_OLS', 'V2_KALMAN']:
        total_pnl = sum(all_results[f"{model}_{leg}"]['pnl_total'] 
                        for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell'] 
                        if f"{model}_{leg}" in all_results)
        total_trades = sum(all_results[f"{model}_{leg}"]['total'] 
                           for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell'] 
                           if f"{model}_{leg}" in all_results)
        print(f"{model:<10} {'TOTAL':<12} {total_trades:>7} {'':>7} {total_pnl:>12,.2f}")
    
    # Breakdown por exit_reason
    print(f"\n{'─' * 80}")
    print("  EXIT REASON BREAKDOWN")
    print(f"{'─' * 80}")
    for model in ['V1_OLS', 'V2_KALMAN']:
        print(f"\n  {model}:")
        combined_reasons = {}
        for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell']:
            key = f"{model}_{leg}"
            if key not in all_results:
                continue
            for reason, data in all_results[key]['by_reason'].items():
                if reason not in combined_reasons:
                    combined_reasons[reason] = {'count': 0, 'pnl': 0}
                combined_reasons[reason]['count'] += data['count']
                combined_reasons[reason]['pnl'] += data['pnl']
        
        for reason in ['TARGET', 'STOP_Z', 'STOP_RHO', 'FORCE_CLOSE']:
            if reason in combined_reasons:
                r = combined_reasons[reason]
                print(f"    {reason:<15} {r['count']:>6} trades   PnL: R$ {r['pnl']:>12,.2f}")


def save_trades_csv(all_trades, filename='backtest_trades.csv'):
    """Salva todos os trades em CSV para auditoria."""
    rows = []
    for key, trades in all_trades.items():
        for t in trades:
            rows.append(t)
    
    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(filename, index=False)
        print(f"\n[✓] Trades salvos em: {filename} ({len(rows)} trades)")


# ─── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    start_time = datetime.now()
    
    # Carregar dados
    data = load_and_merge_m5()
    
    win_prices = data['win'].values.astype(float)
    wdo_prices = data['wdo'].values.astype(float)
    timestamps = data.index
    
    # Calcular indicadores
    print("[3/5] Calculando indicadores V1 (OLS rolling)...")
    betas_v1, z_v1, rho_v1, spreads_v1 = calc_indicators_v1(win_prices, wdo_prices)
    
    print("[4/5] Calculando indicadores V2 (Kalman)...")
    betas_v2, z_v2, rho_v2, spreads_v2 = calc_indicators_v2(win_prices, wdo_prices)
    
    # Simular trades
    print("[5/5] Simulando trades...")
    trades_v1 = simulate_trades(timestamps, z_v1, rho_v1, betas_v1, win_prices, wdo_prices, 'V1_OLS')
    trades_v2 = simulate_trades(timestamps, z_v2, rho_v2, betas_v2, win_prices, wdo_prices, 'V2_KALMAN')
    
    # Calcular métricas
    all_results = {}
    all_trades = {}
    for model_name, model_trades in [('V1_OLS', trades_v1), ('V2_KALMAN', trades_v2)]:
        for leg_name, leg_trades in model_trades.items():
            key = f"{model_name}_{leg_name}"
            all_results[key] = calc_metrics(leg_trades)
            all_trades[key] = leg_trades
    
    # Relatório
    print_report(all_results)
    save_trades_csv(all_trades)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n[✓] Backtest concluído em {elapsed:.1f}s")


if __name__ == '__main__':
    main()
