"""
RESEARCH EXPLORATÓRIO — NÃO USAR COMO VALIDAÇÃO DE PRODUÇÃO
============================================================
Este script diverge do motor live (core/config.py + core/trade_engine.py).
Ver docs/PARAM_PROFILE.md §2 (divergent hardcoded values).
Validação operacional: research/run_matador_v5_johansen.py (TASK-3 AC #15).

Otimização Granular dos Modelos Core (Kalman e Johansen)
========================================================
Este script testa parâmetros fundamentais dos modelos:
- Kalman: trans_cov (Q), obs_cov (R), e z_window
- Johansen: joh_window (lookback de cointegração), e z_window

Thresholds de trade fixos em: z_entry=1.6, z_exit=0.8, z_anom=4.0
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from itertools import product
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL
from core.kalman_filter import KalmanBetaFilter

# ─── Configuração ────────────────────────────────────────────────────────────
BARS_FETCH = 15000         # ~6 meses M5
WIN_PV = 0.20
Z_ENTRY = 1.6
Z_EXIT = 0.8
Z_ANOMALY = 4.0

# Grids Granulares
KALMAN_TRANS_COV = [1e-6, 5e-6, 1e-5, 5e-5, 1e-4, 5e-4, 1e-3, 5e-3]
KALMAN_OBS_COV   = [1e2, 1e3, 5e3, 1e4, 5e4, 1e5]
KALMAN_Z_WINDOW  = [40, 60, 90, 120, 150, 200, 250]

JOH_WINDOWS      = [100, 150, 200, 250, 300, 400, 500, 750, 1000]
DI_Z_WINDOWS     = [40, 60, 90, 120, 150, 200, 250]

# ─── Funções Auxiliares ──────────────────────────────────────────────────────
def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        print(f"ERRO: MT5 init falhou: {mt5.last_error()}")
        sys.exit(1)
    print(f"MT5 conectado: {mt5.terminal_info().name}")

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    if rates is None or len(rates) == 0:
        return None
    return np.array([r[4] for r in rates], dtype=float)

# ─── Backtest Engine Simples ─────────────────────────────────────────────────
def backtest(z_scores, prices_win, pv=WIN_PV):
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(1, len(z_scores)):
        z = z_scores[i]
        price = prices_win[i]
        
        if abs(z) >= Z_ANOMALY:
            if position != 0:
                pnl = (price - entry_price) * position * pv
                trades.append(pnl)
                position = 0
            continue
            
        if position == 0:
            if z <= -Z_ENTRY:
                position = 1
                entry_price = price
            elif z >= Z_ENTRY:
                position = -1
                entry_price = price
        else:
            points_diff = (price - entry_price) if position == 1 else (entry_price - price)
            
            # SL = 500, TP = 350
            if points_diff >= 350:
                trades.append(350 * pv)
                position = 0
            elif points_diff <= -500:
                trades.append(-500 * pv)
                position = 0
            # Exit normal via reversão do z-score
            elif position == 1 and z >= -Z_EXIT:
                trades.append(points_diff * pv)
                position = 0
            elif position == -1 and z <= Z_EXIT:
                trades.append(points_diff * pv)
                position = 0
                
    if position != 0:
        trades.append((prices_win[-1] - entry_price) * position * pv)
        
    n_trades = len(trades)
    if n_trades == 0:
        return {"pnl": 0, "trades": 0, "wr": 0, "sharpe": 0}
        
    total_pnl = sum(trades)
    wins = sum(1 for p in trades if p > 0)
    wr = wins / n_trades * 100
    
    sharpe = 0
    if n_trades > 1 and np.std(trades) > 0:
        sharpe = np.mean(trades) / np.std(trades) * np.sqrt(252)
        
    return {
        "pnl": round(total_pnl, 2),
        "trades": n_trades,
        "wr": round(wr, 1),
        "sharpe": round(sharpe, 2)
    }

# ─── Otimização Kalman ───────────────────────────────────────────────────────
def optimize_kalman(win_c, wdo_c):
    print(f"\n--- OTIMIZANDO KALMAN (WIN x WDO) ---")
    print(f"Testando {len(KALMAN_TRANS_COV) * len(KALMAN_OBS_COV) * len(KALMAN_Z_WINDOW)} combinacoes...")
    
    results = []
    
    for q in KALMAN_TRANS_COV:
        for r in KALMAN_OBS_COV:
            # Roda filtro apenas uma vez por par Q/R
            kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=q, obs_cov=r)
            spreads = []
            for y, x in zip(win_c, wdo_c):
                _, spread, _ = kf.update(float(y), float(x))
                spreads.append(spread)
                
            for w in KALMAN_Z_WINDOW:
                z_scores = KalmanBetaFilter.rolling_zscore(spreads, window=w)
                # Pula warmup
                metrics = backtest(z_scores[w:], win_c[w:])
                if metrics['trades'] >= 10:
                    metrics.update({'q': q, 'r': r, 'w': w})
                    results.append(metrics)
                    
    results.sort(key=lambda x: x['pnl'], reverse=True)
    print("\nTOP 10 POR MAIOR LUCRO (PnL):")
    print(f"{'TRANS_COV':>10} | {'OBS_COV':>8} | {'WINDOW':>6} | {'PnL(R$)':>10} | {'Trades':>6} | {'WR%':>5} | {'Sharpe':>7}")
    for r in results[:10]:
        print(f"{r['q']:>10.1e} | {r['r']:>8.1e} | {r['w']:>6} | {r['pnl']:>10.2f} | {r['trades']:>6} | {r['wr']:>5.1f} | {r['sharpe']:>7.2f}")

# ─── Otimização Johansen ─────────────────────────────────────────────────────
def optimize_johansen(win_c, di_c):
    print(f"\n--- OTIMIZANDO JOHANSEN (WIN x DI) ---")
    print(f"Testando {len(JOH_WINDOWS) * len(DI_Z_WINDOWS)} combinacoes...")
    
    results = []
    n = len(win_c)
    
    for jw in JOH_WINDOWS:
        # Pre-calcula os betas usando a janela jw (salto de 12 em 12 barras = 1 hora)
        betas = np.zeros(n)
        for i in range(jw, n, 12):
            y = np.column_stack([win_c[i-jw:i], di_c[i-jw:i]])
            try:
                res = coint_johansen(y, det_order=0, k_ar_diff=1)
                vec = res.evec[:, 0]
                vec = vec / vec[0]
                betas[i] = float(vec[1])
            except:
                betas[i] = betas[i-1] if i > 0 else 0
                
        # Forward fill dos betas
        for i in range(jw, n):
            if betas[i] == 0:
                betas[i] = betas[i-1]
                
        # Calcula spread
        spread = win_c + betas * di_c
        
        for zw in DI_Z_WINDOWS:
            z_scores = np.zeros(n)
            for i in range(jw + zw, n):
                window_spread = spread[i - zw:i]
                mu = np.mean(window_spread)
                sd = np.std(window_spread)
                if sd < 1e-10: sd = 1.0
                z_scores[i] = (spread[i] - mu) / sd
                
            metrics = backtest(z_scores[jw+zw:], win_c[jw+zw:])
            if metrics['trades'] >= 10:
                metrics.update({'jw': jw, 'zw': zw})
                results.append(metrics)
                
    results.sort(key=lambda x: x['pnl'], reverse=True)
    print("\nTOP 10 POR MAIOR LUCRO (PnL):")
    print(f"{'JOH_WINDOW':>10} | {'Z_WINDOW':>8} | {'PnL(R$)':>10} | {'Trades':>6} | {'WR%':>5} | {'Sharpe':>7}")
    for r in results[:10]:
        print(f"{r['jw']:>10} | {r['zw']:>8} | {r['pnl']:>10.2f} | {r['trades']:>6} | {r['wr']:>5.1f} | {r['sharpe']:>7.2f}")


if __name__ == "__main__":
    init_mt5()
    print(f"\nBaixando {BARS_FETCH} barras M5...")
    win = fetch(SYMBOL_A, BARS_FETCH)
    wdo = fetch(SYMBOL_B, BARS_FETCH)
    di = fetch(DI_SYMBOL, BARS_FETCH)
    mt5.shutdown()
    
    if win is None or wdo is None or di is None:
        print("Erro ao baixar dados.")
        sys.exit(1)
        
    optimize_kalman(win, wdo)
    optimize_johansen(win, di)
    print("\nPronto.")
