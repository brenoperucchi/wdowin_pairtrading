"""
Backtest de Otimização de Z-Score Thresholds
=============================================
Testa todas combinações de z_entry (entrada) e z_exit (saída)
para WIN×WDO (Kalman) e WIN×DI (Johansen).

Uso: python research/optimize_zscore_thresholds.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from itertools import product
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from core.config import (
    SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, WINDOW,
    BETA_INITIAL, MT5_PATH, JOH_WINDOW,
)
from core.kalman_filter import KalmanBetaFilter

# ─── Config ──────────────────────────────────────────────────────────────────
BARS_FETCH = 5000          # ~2 meses M5
WIN_PV = 0.20              # R$/ponto/contrato WIN
DI_PV = 1.0                # R$/tick DI (simplificado)

# Thresholds a testar
Z_ENTRIES = [1.2, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.5, 3.0]
Z_EXITS   = [0.0, 0.2, 0.5, 0.8]
Z_ANOMALY_OPTIONS = [3.0, 3.5, 4.0, 5.0]

# ─── MT5 ─────────────────────────────────────────────────────────────────────
def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        print(f"ERRO: MT5 init falhou: {mt5.last_error()}")
        sys.exit(1)
    print(f"MT5 conectado: {mt5.terminal_info().name}")

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    if rates is None or len(rates) == 0:
        return None, None
    return np.array([r[4] for r in rates], dtype=float), np.array([r[0] for r in rates])

# ─── Backtest Engine ─────────────────────────────────────────────────────────
def backtest_pair(z_scores, prices_win, z_entry, z_exit, z_anomaly, pv):
    """
    Mean-reversion backtest:
    - COMPRA WIN quando z <= -z_entry (spread comprimido)
    - VENDE WIN quando z >= z_entry (spread esticado)
    - Sai quando z cruza z_exit (reversão ao equilibrio)
    - Não opera se |z| >= z_anomaly
    
    Returns dict with metrics.
    """
    position = 0  # 0=flat, 1=long, -1=short
    entry_price = 0
    trades = []
    
    for i in range(1, len(z_scores)):
        z = z_scores[i]
        price = prices_win[i]
        
        # Skip anomalies
        if abs(z) >= z_anomaly:
            if position != 0:
                # Force close on anomaly
                pnl = (price - entry_price) * position * pv
                trades.append({"pnl": pnl, "type": "anomaly_exit", "bars": 0})
                position = 0
            continue
        
        if position == 0:
            # Entry
            if z <= -z_entry:
                position = 1  # Long WIN
                entry_price = price
            elif z >= z_entry:
                position = -1  # Short WIN
                entry_price = price
        else:
            # Exit check
            if position == 1 and z >= -z_exit:
                pnl = (price - entry_price) * pv
                trades.append({"pnl": pnl, "type": "buy"})
                position = 0
            elif position == -1 and z <= z_exit:
                pnl = (entry_price - price) * pv
                trades.append({"pnl": pnl, "type": "sell"})
                position = 0
    
    # Close any open position at end
    if position != 0:
        pnl = (prices_win[-1] - entry_price) * position * pv
        trades.append({"pnl": pnl, "type": "eod"})
    
    if not trades:
        return {
            "total_pnl": 0, "n_trades": 0, "win_rate": 0,
            "avg_pnl": 0, "sharpe": 0, "max_dd": 0,
            "n_buys": 0, "n_sells": 0,
        }
    
    pnls = [t["pnl"] for t in trades]
    total_pnl = sum(pnls)
    n_trades = len(trades)
    wins = sum(1 for p in pnls if p > 0)
    win_rate = wins / n_trades * 100 if n_trades > 0 else 0
    avg_pnl = total_pnl / n_trades if n_trades > 0 else 0
    
    # Sharpe
    if len(pnls) > 1 and np.std(pnls) > 0:
        sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252)
    else:
        sharpe = 0
    
    # Max drawdown
    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    dd = peak - cumulative
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0
    
    n_buys = sum(1 for t in trades if t["type"] == "buy")
    n_sells = sum(1 for t in trades if t["type"] == "sell")
    
    return {
        "total_pnl": round(total_pnl, 2),
        "n_trades": n_trades,
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(avg_pnl, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "n_buys": n_buys,
        "n_sells": n_sells,
    }


# ─── Z-Score Generators ─────────────────────────────────────────────────────
def calc_kalman_zscore(closes_a, closes_b, window=WINDOW):
    """Kalman z-scores for WIN×WDO."""
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL)
    spreads = []
    for y, x in zip(closes_a, closes_b):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    return KalmanBetaFilter.rolling_zscore(spreads, window=window)


def calc_johansen_zscore(closes_a, closes_b, joh_window=JOH_WINDOW, z_window=WINDOW):
    """Johansen z-scores for WIN×DI."""
    n = len(closes_a)
    z_scores = np.zeros(n)
    
    # Compute cointegrating vector from full sample
    if n >= joh_window:
        y = np.column_stack([closes_a[-joh_window:], closes_b[-joh_window:]])
        result = coint_johansen(y, det_order=0, k_ar_diff=1)
        vec = result.evec[:, 0]
        vec = vec / vec[0]
        joh_beta = float(vec[1])
    else:
        # Fallback: simple OLS
        joh_beta = -float(np.cov(closes_a, closes_b)[0, 1] / np.var(closes_b))
    
    # Rolling z-score using Johansen spread
    spread = closes_a + joh_beta * closes_b
    for i in range(z_window, n):
        window_spread = spread[i - z_window:i]
        mu = np.mean(window_spread)
        sd = np.std(window_spread)
        if sd < 1e-10:
            sd = 1.0
        z_scores[i] = (spread[i] - mu) / sd
    
    return z_scores


# ─── Main ────────────────────────────────────────────────────────────────────
def run_optimization(pair_name, z_scores, prices_win, pv):
    """Run grid search over all threshold combinations."""
    print(f"\n{'='*70}")
    print(f"  OTIMIZAÇÃO: {pair_name}")
    print(f"  Barras: {len(z_scores)} | Z range: [{min(z_scores):.2f}, {max(z_scores):.2f}]")
    print(f"{'='*70}")
    
    results = []
    
    for z_entry, z_exit, z_anom in product(Z_ENTRIES, Z_EXITS, Z_ANOMALY_OPTIONS):
        r = backtest_pair(z_scores, prices_win, z_entry, z_exit, z_anom, pv)
        r["z_entry"] = z_entry
        r["z_exit"] = z_exit
        r["z_anomaly"] = z_anom
        results.append(r)
    
    # Filter: at least 5 trades
    valid = [r for r in results if r["n_trades"] >= 5]
    
    if not valid:
        print("  NENHUM resultado com >= 5 trades!")
        return
    
    # Sort by total PnL
    by_pnl = sorted(valid, key=lambda x: x["total_pnl"], reverse=True)
    
    # Sort by Sharpe
    by_sharpe = sorted(valid, key=lambda x: x["sharpe"], reverse=True)
    
    # Sort by win rate (with min trades)
    by_wr = sorted([r for r in valid if r["n_trades"] >= 10], key=lambda x: x["win_rate"], reverse=True)
    
    # Print top results
    print(f"\n{'─'*70}")
    print(f"  TOP 10 POR LUCRO TOTAL (R$)")
    print(f"{'─'*70}")
    print(f"  {'Z_ENTRY':>7} {'Z_EXIT':>6} {'Z_ANOM':>6} | {'PnL(R$)':>10} {'Trades':>6} {'WR%':>5} {'Sharpe':>7} {'MaxDD':>8} {'Buys':>5} {'Sells':>5}")
    print(f"  {'-'*7} {'-'*6} {'-'*6} | {'-'*10} {'-'*6} {'-'*5} {'-'*7} {'-'*8} {'-'*5} {'-'*5}")
    for r in by_pnl[:10]:
        print(f"  {r['z_entry']:>7.1f} {r['z_exit']:>6.1f} {r['z_anomaly']:>6.1f} | {r['total_pnl']:>10.2f} {r['n_trades']:>6} {r['win_rate']:>5.1f} {r['sharpe']:>7.2f} {r['max_dd']:>8.2f} {r['n_buys']:>5} {r['n_sells']:>5}")
    
    print(f"\n{'─'*70}")
    print(f"  TOP 10 POR SHARPE RATIO")
    print(f"{'─'*70}")
    print(f"  {'Z_ENTRY':>7} {'Z_EXIT':>6} {'Z_ANOM':>6} | {'PnL(R$)':>10} {'Trades':>6} {'WR%':>5} {'Sharpe':>7} {'MaxDD':>8}")
    print(f"  {'-'*7} {'-'*6} {'-'*6} | {'-'*10} {'-'*6} {'-'*5} {'-'*7} {'-'*8}")
    for r in by_sharpe[:10]:
        print(f"  {r['z_entry']:>7.1f} {r['z_exit']:>6.1f} {r['z_anomaly']:>6.1f} | {r['total_pnl']:>10.2f} {r['n_trades']:>6} {r['win_rate']:>5.1f} {r['sharpe']:>7.2f} {r['max_dd']:>8.2f}")
    
    if by_wr:
        print(f"\n{'─'*70}")
        print(f"  TOP 5 POR WIN RATE (min 10 trades)")
        print(f"{'─'*70}")
        print(f"  {'Z_ENTRY':>7} {'Z_EXIT':>6} {'Z_ANOM':>6} | {'PnL(R$)':>10} {'Trades':>6} {'WR%':>5} {'Sharpe':>7} {'AvgPnL':>8}")
        for r in by_wr[:5]:
            print(f"  {r['z_entry']:>7.1f} {r['z_exit']:>6.1f} {r['z_anomaly']:>6.1f} | {r['total_pnl']:>10.2f} {r['n_trades']:>6} {r['win_rate']:>5.1f} {r['sharpe']:>7.2f} {r['avg_pnl']:>8.2f}")
    
    # Best overall recommendation
    best = by_pnl[0]
    print(f"\n  ★ RECOMENDAÇÃO: z_entry={best['z_entry']}, z_exit={best['z_exit']}, z_anomaly={best['z_anomaly']}")
    print(f"    PnL: R${best['total_pnl']:.2f} | {best['n_trades']} trades | WR: {best['win_rate']:.1f}% | Sharpe: {best['sharpe']:.2f}")
    
    return by_pnl[0]


if __name__ == "__main__":
    init_mt5()
    
    # Fetch data
    print(f"\nFetching {BARS_FETCH} barras M5...")
    win_c, win_t = fetch(SYMBOL_A, BARS_FETCH)
    wdo_c, wdo_t = fetch(SYMBOL_B, BARS_FETCH)
    di_c, di_t = fetch(DI_SYMBOL, BARS_FETCH)
    
    if win_c is None or wdo_c is None or di_c is None:
        print("ERRO: sem dados para algum símbolo")
        sys.exit(1)
    
    print(f"  WIN: {len(win_c)} barras | WDO: {len(wdo_c)} barras | DI: {len(di_c)} barras")
    
    # ── WDO (Kalman) ─────────────────────────────────────────────────
    min_wdo = min(len(win_c), len(wdo_c))
    win_wdo = win_c[-min_wdo:]
    wdo = wdo_c[-min_wdo:]
    
    z_wdo = calc_kalman_zscore(win_wdo, wdo)
    # Skip warmup period (first 50 bars)
    warmup = 50
    best_wdo = run_optimization(
        "WIN × WDO (Kalman)",
        z_wdo[warmup:], win_wdo[warmup:], WIN_PV
    )
    
    # ── DI (Johansen) ────────────────────────────────────────────────
    min_di = min(len(win_c), len(di_c))
    win_di = win_c[-min_di:]
    di = di_c[-min_di:]
    
    z_di = calc_johansen_zscore(win_di, di)
    best_di = run_optimization(
        "WIN × DI (Johansen)",
        z_di[warmup:], win_di[warmup:], WIN_PV
    )
    
    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  RESUMO FINAL")
    print(f"{'='*70}")
    if best_wdo:
        print(f"  WDO: entry=±{best_wdo['z_entry']}, exit=±{best_wdo['z_exit']}, anomaly=±{best_wdo['z_anomaly']}")
        print(f"        PnL=R${best_wdo['total_pnl']:.2f} | {best_wdo['n_trades']} trades | Sharpe={best_wdo['sharpe']:.2f}")
    if best_di:
        print(f"  DI:  entry=±{best_di['z_entry']}, exit=±{best_di['z_exit']}, anomaly=±{best_di['z_anomaly']}")
        print(f"        PnL=R${best_di['total_pnl']:.2f} | {best_di['n_trades']} trades | Sharpe={best_di['sharpe']:.2f}")
    
    mt5.shutdown()
    print("\nDone.")
