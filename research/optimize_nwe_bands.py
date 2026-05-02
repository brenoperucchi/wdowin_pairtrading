import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL
from datetime import datetime

TIME_OFFSET = 3 * 3600
FORCE_CLOSE_MIN = 17 * 60 + 40

def bar_minute_of_day(ts):
    local_ts = ts + TIME_OFFSET
    dt = datetime.utcfromtimestamp(local_ts)
    return dt.hour * 60 + dt.minute

BARS_FETCH = 15000
WIN_PV = 0.20

# Setup Matador Core Parameters
K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60

# Setup Matador Rules
Z_ENT = 1.4
Z_ATT = 1.2
TP, SL = 800, 300
BE = 300

def init_mt5():
    mt5.initialize(path=MT5_PATH)

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    closes = np.array([r[4] for r in rates], dtype=float)
    times = np.array([r[0] for r in rates], dtype=np.int64)
    return closes, times

def get_base_zscores(win_c, wdo_c, di_c):
    print("Calculando matrizes base WDO e DI...")
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    spreads = []
    for y, x in zip(win_c, wdo_c):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))
    
    n = len(win_c)
    betas = np.zeros(n)
    for i in range(J_JW, n, 12):
        y = np.column_stack([win_c[i-J_JW:i], di_c[i-J_JW:i]])
        try:
            res = coint_johansen(y, det_order=0, k_ar_diff=1)
            vec = res.evec[:, 0]
            betas[i] = float(vec[1] / vec[0])
        except:
            betas[i] = betas[i-1] if i > 0 else 0
    for i in range(J_JW, n):
        if betas[i] == 0: betas[i] = betas[i-1]
            
    spread_di = win_c + betas * di_c
    j_z = np.zeros(n)
    for i in range(J_JW + J_ZW, n):
        window_spread = spread_di[i - J_ZW:i]
        mu, sd = np.mean(window_spread), np.std(window_spread)
        if sd < 1e-10: sd = 1.0
        j_z[i] = (spread_di[i] - mu) / sd
        
    return k_z, j_z

def calc_nwe_with_bands(prices, bandwidth, lookback, mult_mae=3.0):
    n = len(prices)
    nwe = np.zeros(n)
    mae = np.zeros(n)
    
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            nwe[t] = prices[t]
            continue
        i_arr = np.arange(lb + 1)
        w = np.exp(-(i_arr * i_arr) / (2 * bandwidth * bandwidth))
        p_slice = prices[t - lb : t + 1][::-1]
        nwe[t] = np.sum(p_slice * w) / np.sum(w)
        
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            continue
        nwe_slice = nwe[t - lb : t + 1]
        p_slice = prices[t - lb : t + 1]
        err = np.abs(p_slice - nwe_slice)
        mae[t] = np.mean(err) * mult_mae
        
    upper = nwe + mae
    lower = nwe - mae
    return nwe, upper, lower

def simulate_nwe_bands(k_z, j_z, win_c, win_times, nwe_is_up, upper, lower, threshold_pct, mode):
    position = 0
    entry_price = 0
    trades = []
    pnl_array = np.zeros(len(win_c))
    be_hit = False
    
    bar_mins = np.array([bar_minute_of_day(t) for t in win_times])
    
    for i in range(1000, len(win_c)):
        zw, zd, price = k_z[i], j_z[i], win_c[i]
        t_min = bar_mins[i]
        
        # ── Force Close at 17:40 ──
        if position != 0 and t_min >= FORCE_CLOSE_MIN:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            pnl_array[i] = diff * WIN_PV
            trades.append(diff * WIN_PV)
            position = 0
            continue
            
        sig_buy = False
        sig_sell = False
        
        if mode == "wdo":
            sig_buy = (zw <= -Z_ENT)
            sig_sell = (zw >= Z_ENT)
        elif mode == "di":
            sig_buy = (zd <= -Z_ENT)
            sig_sell = (zd >= Z_ENT)
        elif mode == "consensus":
            sig_buy = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
            sig_sell = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)
        
        up = nwe_is_up[i]
        
        # Filtro de Banda Fader
        if sig_buy:
            if up: 
                sig_buy = False # NWE deve estar vermelho (contra-tendencia)
            else:
                dist_pct = (price - lower[i]) / lower[i] * 100.0
                if dist_pct > threshold_pct: 
                    sig_buy = False # Muito longe da banda inferior
                    
        if sig_sell:
            if not up:
                sig_sell = False # NWE deve estar verde (contra-tendencia)
            else:
                dist_pct = (upper[i] - price) / upper[i] * 100.0
                if dist_pct > threshold_pct:
                    sig_sell = False # Muito longe da banda superior
                    
        if position == 0:
            if sig_buy:
                position = 1
                entry_price = price
                be_hit = False
            elif sig_sell:
                position = -1
                entry_price = price
                be_hit = False
        else:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            
            if not be_hit and diff >= BE:
                be_hit = True
                
            if diff >= TP:
                pnl_array[i] = TP * WIN_PV
                trades.append(TP * WIN_PV)
                position = 0
            elif be_hit and diff <= 0:
                pnl_array[i] = 0
                trades.append(0)
                position = 0
            elif not be_hit and diff <= -SL:
                pnl_array[i] = -SL * WIN_PV
                trades.append(-SL * WIN_PV)
                position = 0
                
    return trades

def calc_stats(trades):
    if not trades: return {"pnl": 0, "dd": 0, "trades": 0, "wr": 0, "pf": 0, "ret_dd": 0}
    cum_pnl = np.cumsum(trades)
    max_dd, peak = 0, 0
    for pnl in cum_pnl:
        if pnl > peak: peak = pnl
        dd = peak - pnl
        if dd > max_dd: max_dd = dd
    if max_dd < 1: max_dd = 1
        
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    ret_dd = sum(trades) / max_dd if sum(trades) > 0 else 0
        
    return {
        "pnl": sum(trades),
        "dd": max_dd,
        "trades": len(trades),
        "wr": len(wins)/len(trades)*100 if trades else 0,
        "pf": profit_factor,
        "ret_dd": ret_dd
    }

def optimize_mode(k_z, j_z, win, win_times, is_up, upper, lower, mode):
    thresholds = np.arange(-0.80, 0.82, 0.02)
    results = []
    
    for th in thresholds:
        t_bands = simulate_nwe_bands(k_z, j_z, win, win_times, is_up, upper, lower, th, mode)
        s_bands = calc_stats(t_bands)
        if s_bands['trades'] > 0:
            results.append((s_bands, th))
            
    # Sort by Ret/DD
    results.sort(key=lambda x: x[0]['ret_dd'], reverse=True)
    
    print(f"\n=========================================================================")
    print(f"TOP 15 REGRAS NWE - {mode.upper()} POR RET/DD")
    print(f"=========================================================================")
    header = f"{'Band_Pct':>8} | {'PnL(R$)':>9} | {'DD(R$)':>7} | {'Ret/DD':>7} | {'Trades':>6} | {'WR%':>5}"
    print(header)
    print("-" * len(header))
    for s_bands, th in results[:15]:
        print(f"{th:8.2f}% | {s_bands['pnl']:9.2f} | {s_bands['dd']:7.2f} | {s_bands['ret_dd']:7.2f} | {s_bands['trades']:6d} | {s_bands['wr']:5.1f}")

def main():
    init_mt5()
    win, win_times = fetch(SYMBOL_A, BARS_FETCH)
    wdo, _ = fetch(SYMBOL_B, BARS_FETCH)
    di, _ = fetch(DI_SYMBOL, BARS_FETCH)
    mt5.shutdown()

    k_z, j_z = get_base_zscores(win, wdo, di)
    
    bw = 8
    lb = 20
    print(f"\nCalculando NWE Base com Bandwidth={bw}, Lookback={lb}...")
    
    nwe, upper, lower = calc_nwe_with_bands(win, bw, lb, mult_mae=3.0)
    is_up = np.zeros(len(nwe), dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True

    print("\n[OTIMIZANDO WDO ISOLADO COM BANDA NWE]")
    optimize_mode(k_z, j_z, win, win_times, is_up, upper, lower, "wdo")
    
    print("\n[OTIMIZANDO DI ISOLADO COM BANDA NWE]")
    optimize_mode(k_z, j_z, win, win_times, is_up, upper, lower, "di")
    
    print("\n[OTIMIZANDO CONSENSO COM BANDA NWE]")
    optimize_mode(k_z, j_z, win, win_times, is_up, upper, lower, "consensus")

if __name__ == "__main__":
    main()
