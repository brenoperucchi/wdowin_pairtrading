"""
RESEARCH EXPLORATÓRIO — NÃO USAR COMO VALIDAÇÃO DE PRODUÇÃO
============================================================
Este script diverge do motor live (core/config.py + core/trade_engine.py).
Ver docs/PARAM_PROFILE.md §2 (divergent hardcoded values).
Validação operacional: research/run_matador_v5_johansen.py (TASK-3 AC #15).

Otimização de Consenso (Kalman + Johansen)
========================================================
Testa a regra de entrada combinada:
- Sinal (1.6) em um modelo E Atenção (1.2) no outro (no mesmo sentido)
- TP fixo = 350, SL fixo = 500
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL
from core.kalman_filter import KalmanBetaFilter

# ─── Configuração ────────────────────────────────────────────────────────────
BARS_FETCH = 15000         # ~6 meses M5
WIN_PV = 0.20
Z_ENTRY = 1.8
Z_ATTENTION = 1.5

# Grids Granulares (reduzidos levemente para agilizar cruzamento)
KALMAN_TRANS_COV = [1e-5, 5e-5, 1e-4, 5e-4, 1e-3, 5e-3]
KALMAN_OBS_COV   = [1e2, 1e3, 5e3, 1e4]
KALMAN_Z_WINDOW  = [40, 60, 90, 150, 200]

JOH_WINDOWS      = [100, 150, 200, 250, 300]
DI_Z_WINDOWS     = [40, 60, 90, 120, 150]

# Total Kalman = 6 * 4 * 5 = 120 combinacoes
# Total Johansen = 5 * 5 = 25 combinacoes
# Total Cruzamentos = 120 * 25 = 3.000 combinacoes

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

# ─── Pré-Cálculos ────────────────────────────────────────────────────────────

def precalc_kalman(win_c, wdo_c):
    print("Pre-calculando matrizes Kalman...")
    variations = []
    for q in KALMAN_TRANS_COV:
        for r in KALMAN_OBS_COV:
            kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=q, obs_cov=r)
            spreads = []
            for y, x in zip(win_c, wdo_c):
                _, spread, _ = kf.update(float(y), float(x))
                spreads.append(spread)
                
            for w in KALMAN_Z_WINDOW:
                z_scores = KalmanBetaFilter.rolling_zscore(spreads, window=w)
                variations.append({
                    'q': q, 'r': r, 'w': w,
                    'z': np.array(z_scores)
                })
    print(f"Kalman variations: {len(variations)}")
    return variations

def precalc_johansen(win_c, di_c):
    print("Pre-calculando matrizes Johansen...")
    variations = []
    n = len(win_c)
    
    for jw in JOH_WINDOWS:
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
                
        for i in range(jw, n):
            if betas[i] == 0:
                betas[i] = betas[i-1]
                
        spread = win_c + betas * di_c
        
        for zw in DI_Z_WINDOWS:
            z_scores = np.zeros(n)
            for i in range(jw + zw, n):
                window_spread = spread[i - zw:i]
                mu = np.mean(window_spread)
                sd = np.std(window_spread)
                if sd < 1e-10: sd = 1.0
                z_scores[i] = (spread[i] - mu) / sd
                
            variations.append({
                'jw': jw, 'zw': zw,
                'z': z_scores
            })
    print(f"Johansen variations: {len(variations)}")
    return variations

# ─── Backtest de Consenso ────────────────────────────────────────────────────
def run_consensus_backtest(k_z, j_z, prices_win, pv=WIN_PV):
    position = 0
    entry_price = 0
    trades = []
    pnl_array = np.zeros(len(prices_win))
    
    # Inicia a partir de 1000 pra evitar periodo de warmup dos z-scores
    for i in range(1000, len(prices_win)):
        zk = k_z[i]
        zj = j_z[i]
        price = prices_win[i]
        
        if position == 0:
            # COMPRA
            if (zk <= -Z_ENTRY and zj <= -Z_ATTENTION) or (zk <= -Z_ATTENTION and zj <= -Z_ENTRY):
                position = 1
                entry_price = price
            # VENDA
            elif (zk >= Z_ENTRY and zj >= Z_ATTENTION) or (zk >= Z_ATTENTION and zj >= Z_ENTRY):
                position = -1
                entry_price = price
        else:
            points_diff = (price - entry_price) if position == 1 else (entry_price - price)
            
            # 1. Stop Loss / Take Profit Fixos (Baseline da Fase 1)
            if points_diff >= 600:
                pnl_array[i] = 600 * pv
                trades.append(600 * pv)
                position = 0
            elif points_diff <= -300:
                pnl_array[i] = -300 * pv
                trades.append(-300 * pv)
                position = 0
                
    if position != 0:
        points_diff = (prices_win[-1] - entry_price) if position == 1 else (entry_price - prices_win[-1])
        pnl_array[-1] = points_diff * pv
        trades.append(points_diff * pv)
        
    n_trades = len(trades)
    if n_trades == 0:
        return {"pnl": 0, "trades": 0, "wr": 0, "sharpe": 0, "dd": 0, "ret_dd": 0}
        
    total_pnl = sum(trades)
    wins = sum(1 for p in trades if p > 0)
    wr = wins / n_trades * 100
    
    sharpe = 0
    if n_trades > 1 and np.std(trades) > 0:
        sharpe = np.mean(trades) / np.std(trades) * np.sqrt(252)
        
    cum_pnl = np.cumsum(pnl_array)
    peak = np.maximum.accumulate(cum_pnl)
    drawdowns = peak - cum_pnl
    max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0
    if max_dd < 1: max_dd = 1
    
    ret_dd = total_pnl / max_dd if total_pnl > 0 else 0
        
    return {
        "pnl": round(total_pnl, 2),
        "trades": n_trades,
        "wr": round(wr, 1),
        "sharpe": round(sharpe, 2),
        "dd": round(max_dd, 2),
        "ret_dd": round(ret_dd, 2)
    }

def optimize_consensus(win, wdo, di):
    k_vars = precalc_kalman(win, wdo)
    j_vars = precalc_johansen(win, di)
    
    total = len(k_vars) * len(j_vars)
    print(f"\n--- INICIANDO BACKTEST CRUZADO DE CONSENSO ---")
    print(f"Total de simulacoes: {total}")
    
    results = []
    start_t = time.time()
    
    count = 0
    for kv in k_vars:
        for jv in j_vars:
            metrics = run_consensus_backtest(kv['z'], jv['z'], win)
            
            if metrics['trades'] >= 10:  # Filtro de significancia
                metrics.update({
                    'k_q': kv['q'], 'k_r': kv['r'], 'k_w': kv['w'],
                    'j_w': jv['jw'], 'j_zw': jv['zw']
                })
                results.append(metrics)
                
            count += 1
            if count % 500 == 0:
                print(f"[{count}/{total}] Progresso...")
                
    elap = time.time() - start_t
    print(f"Simulacao concluida em {elap:.1f}s")
    
    # Filtrar apenas WR > 40%
    results = [r for r in results if r['wr'] >= 40.0]
    
    # Ordenar por Ret/DD
    results.sort(key=lambda x: x['ret_dd'], reverse=True)
    
    print("\n=========================================================================")
    print("TOP 10 CONSENSO POR RET/DD (Min WR 40%) - SL 300 / TP 600")
    print("=========================================================================")
    header = f"{'K_Q':>7} | {'K_R':>5} | {'K_W':>4} | {'J_W':>4} | {'J_ZW':>4} | {'PnL(R$)':>9} | {'DD(R$)':>7} | {'Ret/DD':>7} | {'Trades':>6} | {'WR%':>5}"
    print(header)
    print("-" * len(header))
    for r in results[:10]:
        print(f"{r['k_q']:>7.1e} | {r['k_r']:>5.0e} | {r['k_w']:>4} | {r['j_w']:>4} | {r['j_zw']:>4} | {r['pnl']:>9.2f} | {r['dd']:>7.2f} | {r['ret_dd']:>7.2f} | {r['trades']:>6} | {r['wr']:>5.1f}")


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
        
    optimize_consensus(win, wdo, di)
    print("\nPronto.")
