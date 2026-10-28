import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

WIN_PV = 0.20

# Setup Matador Core Parameters
K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60

Z_ENT = 1.4
Z_ATT = 1.2
TP, SL = 800, 300
BE = 300

# Force Close: 17h40
FORCE_CLOSE_MIN = 17 * 60 + 40
TIME_OFFSET = 0

def init_mt5():
    mt5.initialize(path=MT5_PATH)

def fetch_with_times(symbol, start_pos, count):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, start_pos, count)
    if rates is None or len(rates) == 0:
        return np.array([]), np.array([])
    closes = np.array([r[4] for r in rates], dtype=float)
    times = np.array([r[0] for r in rates], dtype=np.int64)
    return closes, times

def bar_minute_of_day(ts):
    local_ts = ts + TIME_OFFSET
    dt = datetime.utcfromtimestamp(local_ts)
    return dt.hour * 60 + dt.minute

def get_base_zscores(win_c, wdo_c, di_c):
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

def simulate(k_z, j_z, win_c, bar_times, mode,
             nwe_is_up=None, upper=None, lower=None, threshold_pct=None, start_m=9*60, end_m=15*60):
    n = len(win_c)
    pnl_array = np.zeros(n)
    
    position = 0
    entry_price = 0
    be_hit = False
    
    bar_mins = np.array([bar_minute_of_day(t) for t in bar_times])
    
    for i in range(1000, n):
        zw, zd, price = k_z[i], j_z[i], win_c[i]
        t_min = bar_mins[i]
        
        # ── Force Close at 17:40 ──
        if position != 0 and t_min >= FORCE_CLOSE_MIN:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            pnl_array[i] = diff * WIN_PV
            position = 0
            continue
        
        sig_buy = False
        sig_sell = False
        
        if mode == "consensus":
            sig_buy = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
            sig_sell = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)
        elif mode == "wdo":
            sig_buy = (zw <= -Z_ENT)
            sig_sell = (zw >= Z_ENT)
        elif mode == "di":
            sig_buy = (zd <= -Z_ENT)
            sig_sell = (zd >= Z_ENT)
            
        # Apply NWE Fader Band Filter
        if nwe_is_up is not None and upper is not None and lower is not None and threshold_pct is not None:
            up = nwe_is_up[i]
            if sig_buy:
                if up: 
                    sig_buy = False
                else:
                    dist_pct = (price - lower[i]) / lower[i] * 100.0
                    if dist_pct > threshold_pct: 
                        sig_buy = False
            if sig_sell:
                if not up:
                    sig_sell = False
                else:
                    dist_pct = (upper[i] - price) / upper[i] * 100.0
                    if dist_pct > threshold_pct:
                        sig_sell = False

        if position == 0:
            if t_min < start_m or t_min > end_m:
                sig_buy = False
                sig_sell = False
                
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
                position = 0
            elif be_hit and diff <= 0:
                pnl_array[i] = 0
                position = 0
            elif not be_hit and diff <= -SL:
                pnl_array[i] = -SL * WIN_PV
                position = 0
                
    return pnl_array

def calc_stats_from_pnl_array(pnl_array):
    trades = pnl_array[pnl_array != 0]
    if len(trades) == 0: 
        return {"pnl": 0, "dd": 0, "trades": 0, "wr": 0, "pf": 0, "sharpe": 0, "ret_dd": 0}
        
    cum_pnl = np.cumsum(pnl_array)
    max_dd, peak = 0, 0
    for pnl in cum_pnl:
        if pnl > peak: peak = pnl
        dd = peak - pnl
        if dd > max_dd: max_dd = dd
        
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    sharpe = 0
    if len(trades) > 1 and np.std(trades) > 0:
        sharpe = np.mean(trades) / np.std(trades) * np.sqrt(252)
        
    ret_dd = sum(trades) / max_dd if max_dd > 0 else (999.0 if sum(trades) > 0 else 0)
    
    return {
        "pnl": sum(trades),
        "dd": max_dd,
        "trades": len(trades),
        "wr": len(wins)/len(trades)*100 if len(trades) > 0 else 0,
        "pf": profit_factor,
        "sharpe": sharpe,
        "ret_dd": ret_dd
    }

def print_result(name, s):
    print(f"{name:30s} | PnL: R${s['pnl']:7.2f} | Trades: {s['trades']:4d} | WR: {s['wr']:4.1f}% | DD: R${s['dd']:7.2f} | Ret/DD: {s['ret_dd']:5.2f}")

def main():
    print("Iniciando coleta de dados (MT5)...")
    init_mt5()
    
    start_pos = 0
    count = 100000
    
    win, win_times = fetch_with_times(SYMBOL_A, start_pos, count)
    wdo, _ = fetch_with_times(SYMBOL_B, start_pos, count)
    di, _ = fetch_with_times(DI_SYMBOL, start_pos, count)
    mt5.shutdown()
    
    min_len = min(len(win), len(wdo), len(di))
    win = win[:min_len]
    wdo = wdo[:min_len]
    di = di[:min_len]
    win_times = win_times[:min_len]
    
    print(f"Barras carregadas e alinhadas: {min_len}")

    k_z, j_z = get_base_zscores(win, wdo, di)
    
    bw, lb = 8, 20
    print(f"Calculando NWE (BW={bw}, LB={lb})...")
    nwe, upper, lower = calc_nwe_with_bands(win, bw, lb, mult_mae=3.0)
    is_up = np.zeros(len(nwe), dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True

    print("\nSimulando Portfólio com NWE 0.14% e BE 300...")
    
    pnl_wdo = simulate(k_z, j_z, win, win_times, mode="wdo",
                       nwe_is_up=is_up, upper=upper, lower=lower, threshold_pct=0.14)
    
    pnl_di = simulate(k_z, j_z, win, win_times, mode="di",
                      nwe_is_up=is_up, upper=upper, lower=lower, threshold_pct=0.14)
    pnl_cons = simulate(k_z, j_z, win, win_times, mode="consensus",
                        nwe_is_up=is_up, upper=upper, lower=lower, threshold_pct=0.14)
                      
    pnl_portfolio = pnl_wdo + pnl_di + pnl_cons
    
    s_wdo = calc_stats_from_pnl_array(pnl_wdo)
    s_di = calc_stats_from_pnl_array(pnl_di)
    s_cons = calc_stats_from_pnl_array(pnl_cons)
    s_port = calc_stats_from_pnl_array(pnl_portfolio)
    
    print("\n=========================================================================")
    print("RESULTADO DO PORTFOLIO MATADOR S/ CONSENSO (JANELA COMPLETA - 3.5 ANOS)")
    print("=========================================================================")
    print_result("1. WDO Kalman + NWE 0.14", s_wdo)
    print_result("2. DI Johansen + NWE 0.14", s_di)
    print_result("3. Consenso + NWE 0.14", s_cons)
    print("-------------------------------------------------------------------------")
    print_result("=> PORTFOLIO GLOBAL (WDO+DI+CONS)", s_port)
    print("=========================================================================\n")

    # Plot
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14, 7))
    
    ax.plot(np.cumsum(pnl_wdo), color='dodgerblue', alpha=0.6, label=f"WDO (R${s_wdo['pnl']:.0f})")
    ax.plot(np.cumsum(pnl_di), color='mediumspringgreen', alpha=0.6, label=f"DI (R${s_di['pnl']:.0f})")
    ax.plot(np.cumsum(pnl_cons), color='violet', alpha=0.6, label=f"CONSENSO (R${s_cons['pnl']:.0f})")
    
    ax.plot(np.cumsum(pnl_portfolio), color='white', linewidth=2.5, 
            label=f"PORTFOLIO TOTAL (PnL R${s_port['pnl']:.0f} | DD R${s_port['dd']:.0f} | Ret/DD {s_port['ret_dd']:.1f})")
    
    ax.set_title("Desempenho WDO + DI Isolados com Banda NWE 0.14% (Período Completo OOS)", fontsize=14, pad=15)
    ax.set_ylabel("PnL (R$)")
    ax.set_xlabel("Barras M5")
    ax.grid(True, alpha=0.15)
    ax.legend(loc='upper left', fontsize=11)
    
    # Preenchimento verde para lucro global
    cum_port = np.cumsum(pnl_portfolio)
    ax.fill_between(range(len(cum_port)), 0, cum_port, where=(cum_port > 0), color='mediumspringgreen', alpha=0.1)
    ax.fill_between(range(len(cum_port)), 0, cum_port, where=(cum_port < 0), color='crimson', alpha=0.1)

    plt.tight_layout()
    os.makedirs(".planning/docs/assets", exist_ok=True)
    plt.savefig(".planning/docs/assets/portfolio_curves_nwe_no_consensus.png", dpi=150)
    print("Grafico salvo em: .planning/docs/assets/portfolio_curves_nwe_no_consensus.png")

if __name__ == "__main__":
    main()
