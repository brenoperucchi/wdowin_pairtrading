"""
Otimização das Regras de Trade com Break-Even
==================================================================
Testa diferentes limites de Break-Even (BE) mantendo a matemática base fixa.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from datetime import datetime

from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL
from core.kalman_filter import KalmanBetaFilter

TIME_OFFSET = 3 * 3600
FORCE_CLOSE_MIN = 17 * 60 + 40

def bar_minute_of_day(ts):
    local_ts = ts + TIME_OFFSET
    dt = datetime.utcfromtimestamp(local_ts)
    return dt.hour * 60 + dt.minute

# ─── Configuração ────────────────────────────────────────────────────────────
BARS_FETCH = 15000         # ~6 meses M5
WIN_PV = 0.20

# Core Fixo (Matador Setup)
K_Q = 1e-4
K_R = 1e2
K_W = 40
J_JW = 150
J_ZW = 60

# Parâmetros de Trade Matador
Z_ENTRIES = [1.4]
Z_ATTENTIONS = [1.2]
TPS = [800]
SLS = [300]
BES = list(range(300, 850, 50))  # BE tests from 300 to 800

# ─── Funções Auxiliares ──────────────────────────────────────────────────────
def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        print(f"ERRO: MT5 init falhou: {mt5.last_error()}")
        sys.exit(1)
    print(f"MT5 conectado: {mt5.terminal_info().name}")

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    if rates is None or len(rates) == 0:
        return None, None
    closes = np.array([r[4] for r in rates], dtype=float)
    times = np.array([r[0] for r in rates], dtype=np.int64)
    return closes, times

def get_base_zscores(win_c, wdo_c, di_c):
    print("Gerando Z-Scores Base...")
    # Kalman
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    spreads = []
    for y, x in zip(win_c, wdo_c):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))
    
    # Johansen
    n = len(win_c)
    betas = np.zeros(n)
    for i in range(J_JW, n, 12):
        y = np.column_stack([win_c[i-J_JW:i], di_c[i-J_JW:i]])
        try:
            res = coint_johansen(y, det_order=0, k_ar_diff=1)
            vec = res.evec[:, 0]
            vec = vec / vec[0]
            betas[i] = float(vec[1])
        except:
            betas[i] = betas[i-1] if i > 0 else 0
            
    for i in range(J_JW, n):
        if betas[i] == 0:
            betas[i] = betas[i-1]
            
    spread_di = win_c + betas * di_c
    j_z = np.zeros(n)
    for i in range(J_JW + J_ZW, n):
        window_spread = spread_di[i - J_ZW:i]
        mu = np.mean(window_spread)
        sd = np.std(window_spread)
        if sd < 1e-10: sd = 1.0
        j_z[i] = (spread_di[i] - mu) / sd
        
    return k_z, j_z

def backtest_rules(k_z, j_z, prices_win, times_win, z_ent, z_att, tp, sl, be, pv=WIN_PV):
    position = 0
    entry_price = 0
    trades = []
    pnl_array = np.zeros(len(prices_win))
    be_hit = False
    
    bar_mins = np.array([bar_minute_of_day(t) for t in times_win])
    
    for i in range(1000, len(prices_win)):
        zk = k_z[i]
        zj = j_z[i]
        price = prices_win[i]
        t_min = bar_mins[i]
        
        # ── Force Close at 17:40 ──
        if position != 0 and t_min >= FORCE_CLOSE_MIN:
            points_diff = (price - entry_price) if position == 1 else (entry_price - price)
            pnl_array[i] = points_diff * pv
            trades.append(points_diff * pv)
            position = 0
            continue
            
        if position == 0:
            if (zk <= -z_ent and zj <= -z_att) or (zk <= -z_att and zj <= -z_ent):
                position = 1
                entry_price = price
                be_hit = False
            elif (zk >= z_ent and zj >= z_att) or (zk >= z_att and zj >= z_ent):
                position = -1
                entry_price = price
                be_hit = False
        else:
            points_diff = (price - entry_price) if position == 1 else (entry_price - price)
            
            if not be_hit and points_diff >= be:
                be_hit = True
                
            if points_diff >= tp:
                pnl_array[i] = tp * pv
                trades.append(tp * pv)
                position = 0
            elif be_hit and points_diff <= 0:
                pnl_array[i] = 0
                trades.append(0)
                position = 0
            elif not be_hit and points_diff <= -sl:
                pnl_array[i] = -sl * pv
                trades.append(-sl * pv)
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

def optimize():
    init_mt5()
    print(f"\nBaixando {BARS_FETCH} barras M5...")
    win, win_times = fetch(SYMBOL_A, BARS_FETCH)
    wdo, _ = fetch(SYMBOL_B, BARS_FETCH)
    di, _ = fetch(DI_SYMBOL, BARS_FETCH)
    mt5.shutdown()
    
    k_z, j_z = get_base_zscores(win, wdo, di)
    
    results = []
    print("\nTestando Regras de Break-Even...")
    for ze in Z_ENTRIES:
        for za in Z_ATTENTIONS:
            for tp in TPS:
                for sl in SLS:
                    for be in BES:
                        metrics = backtest_rules(k_z, j_z, win, win_times, ze, za, tp, sl, be)
                        if metrics['trades'] >= 10:
                            metrics.update({'ze': ze, 'za': za, 'tp': tp, 'sl': sl, 'be': be})
                            results.append(metrics)
                        
    results.sort(key=lambda x: x['ret_dd'], reverse=True)
    
    print("\n=========================================================================")
    print("TOP 15 REGRAS DE BREAK-EVEN POR RET/DD (TP 800 / SL 300 / 15k barras)")
    print("=========================================================================")
    header = f"{'BE_Trig':>7} | {'PnL(R$)':>9} | {'DD(R$)':>7} | {'Ret/DD':>7} | {'Trades':>6} | {'WR%':>5}"
    print(header)
    print("-" * len(header))
    for r in results[:15]:
        print(f"{r['be']:>7} | {r['pnl']:>9.2f} | {r['dd']:>7.2f} | {r['ret_dd']:>7.2f} | {r['trades']:>6} | {r['wr']:>5.1f}")

if __name__ == "__main__":
    optimize()
