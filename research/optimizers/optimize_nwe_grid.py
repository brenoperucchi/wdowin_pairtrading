"""
NWE Grid Optimization — Lookback × Band Multiplier
===================================================
Lookback: 50 a 100 (step 5)
Band Mult: 0.05 a 0.30 (step 0.05)

Filtro adaptativo:
  BUY  → price < lower + band_width * mult  (preço perto da banda inferior)
  SELL → price > upper - band_width * mult  (preço perto da banda superior)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

# ── Setup Matador Parameters ──
K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60
Z_ENT, Z_ATT = 1.4, 1.2
TP, SL, BE = 800, 300, 300
WIN_PV = 0.20
FORCE_CLOSE_MIN = 17 * 60 + 40
START_M = 9 * 60
END_M = 15 * 60
BW = 8  # bandwidth fixed
MAE_MULT = 3.0

def bar_minute_of_day(ts):
    dt = datetime.utcfromtimestamp(ts)
    return dt.hour * 60 + dt.minute

def calc_nwe_with_bands(prices, bandwidth, lookback, mult_mae):
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
        err = np.abs(prices[t - lb : t + 1] - nwe[t - lb : t + 1])
        mae[t] = np.mean(err) * mult_mae
    upper = nwe + mae
    lower = nwe - mae
    return nwe, upper, lower

def simulate_portfolio(k_z, j_z, win_c, bar_mins, is_up, upper, lower, band_mult):
    """Simulates WDO + DI with adaptive band multiplier filter."""
    n = len(win_c)
    pnl_wdo = np.zeros(n)
    pnl_di = np.zeros(n)

    for mode_idx, (pnl_arr, z_fn) in enumerate([(pnl_wdo, lambda i: k_z[i]), (pnl_di, lambda i: j_z[i])]):
        position = 0
        entry_price = 0.0
        be_hit = False

        for i in range(1000, n):
            price = win_c[i]
            t_min = bar_mins[i]

            # Force Close
            if position != 0 and t_min >= FORCE_CLOSE_MIN:
                diff = (price - entry_price) if position == 1 else (entry_price - price)
                pnl_arr[i] = diff * WIN_PV
                position = 0
                continue

            z_val = z_fn(i)
            sig_buy = (z_val <= -Z_ENT)
            sig_sell = (z_val >= Z_ENT)

            # Adaptive band filter
            up = is_up[i]
            band_width = upper[i] - lower[i]
            if band_width < 1e-10:
                band_width = 1.0

            if sig_buy:
                if up:
                    sig_buy = False
                else:
                    # Price must be near lower band: within mult * band_width from lower
                    if price > lower[i] + band_width * band_mult:
                        sig_buy = False
            if sig_sell:
                if not up:
                    sig_sell = False
                else:
                    # Price must be near upper band: within mult * band_width from upper
                    if price < upper[i] - band_width * band_mult:
                        sig_sell = False

            if position == 0:
                if t_min < START_M or t_min > END_M:
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
                    pnl_arr[i] = TP * WIN_PV
                    position = 0
                elif be_hit and diff <= 0:
                    pnl_arr[i] = 0
                    position = 0
                elif not be_hit and diff <= -SL:
                    pnl_arr[i] = -SL * WIN_PV
                    position = 0

    return pnl_wdo, pnl_di

def calc_stats(pnl_array):
    trades = pnl_array[pnl_array != 0]
    total = len(trades)
    if total == 0:
        return {"pnl": 0, "trades": 0, "wr": 0.0, "dd": 0.0, "ret_dd": 0.0}
    total_pnl = np.sum(trades)
    wins = np.sum(trades > 0)
    wr = (wins / total) * 100.0
    cum = np.cumsum(trades)
    mx = np.maximum.accumulate(cum)
    dd = np.max(mx - cum)
    if dd < 1e-5:
        dd = 1.0
    return {"pnl": total_pnl, "trades": total, "wr": wr, "dd": dd, "ret_dd": total_pnl / dd}

def main():
    print("Carregando dados do MT5 (100k barras)...")
    mt5.initialize(path=MT5_PATH)
    rates_w = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 100000)
    rates_d = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, 100000)
    rates_di = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, 100000)
    mt5.shutdown()

    win = np.array([r[4] for r in rates_w], dtype=float)
    wdo = np.array([r[4] for r in rates_d], dtype=float)
    di  = np.array([r[4] for r in rates_di], dtype=float)
    times = np.array([r[0] for r in rates_w], dtype=np.int64)

    n = min(len(win), len(wdo), len(di))
    win, wdo, di, times = win[:n], wdo[:n], di[:n], times[:n]
    print(f"Barras alinhadas: {n}")

    # Pre-compute Z-scores (fixed, doesn't change with NWE params)
    print("Calculando Z-scores Kalman + Johansen...")
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    spreads = []
    for y, x in zip(win, wdo):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=K_W))

    betas = np.zeros(n)
    for i in range(J_JW, n, 12):
        y_data = np.column_stack([win[i - J_JW:i], di[i - J_JW:i]])
        try:
            res = coint_johansen(y_data, det_order=0, k_ar_diff=1)
            vec = res.evec[:, 0]
            betas[i] = float(vec[1] / vec[0])
        except:
            betas[i] = betas[i - 1] if i > 0 else 0
    for i in range(J_JW, n):
        if betas[i] == 0:
            betas[i] = betas[i - 1]
    spread_di = win + betas * di
    j_z = np.zeros(n)
    for i in range(J_JW + J_ZW, n):
        ws = spread_di[i - J_ZW:i]
        mu, sd = np.mean(ws), np.std(ws)
        j_z[i] = (spread_di[i] - mu) / (sd if sd > 1e-10 else 1.0)

    bar_mins = np.array([bar_minute_of_day(t) for t in times])

    # Grid search
    lookbacks = list(range(50, 105, 5))
    band_mults = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

    print(f"\nGrid: Lookback {lookbacks[0]}-{lookbacks[-1]} x BandMult {band_mults[0]}-{band_mults[-1]}")
    print(f"Total combinações: {len(lookbacks) * len(band_mults)}\n")

    # Header
    header = f"{'LB':>4} | {'MULT':>5} | {'PNL':>10} | {'DD':>8} | {'RET/DD':>7} | {'TRADES':>6} | {'WR':>5} | {'PNL_WDO':>9} | {'PNL_DI':>8}"
    print(header)
    print("-" * len(header))

    results = []

    for lb in lookbacks:
        # Compute NWE for this lookback
        nwe, upper, lower = calc_nwe_with_bands(win, BW, lb, MAE_MULT)
        is_up = np.zeros(n, dtype=bool)
        is_up[1:] = nwe[1:] >= nwe[:-1]
        is_up[0] = True

        for bm in band_mults:
            pnl_wdo, pnl_di = simulate_portfolio(k_z, j_z, win, bar_mins, is_up, upper, lower, bm)
            pnl_port = pnl_wdo + pnl_di

            s_port = calc_stats(pnl_port)
            s_wdo = calc_stats(pnl_wdo)
            s_di = calc_stats(pnl_di)

            results.append({
                "lb": lb, "bm": bm,
                "pnl": s_port["pnl"], "dd": s_port["dd"], "ret_dd": s_port["ret_dd"],
                "trades": s_port["trades"], "wr": s_port["wr"],
                "pnl_wdo": s_wdo["pnl"], "pnl_di": s_di["pnl"],
            })

            print(f"{lb:4d} | {bm:5.2f} | R${s_port['pnl']:8.0f} | R${s_port['dd']:6.0f} | {s_port['ret_dd']:7.2f} | {s_port['trades']:6d} | {s_port['wr']:4.1f}% | R${s_wdo['pnl']:7.0f} | R${s_di['pnl']:6.0f}")

    # Top 10 by Ret/DD
    results.sort(key=lambda r: r["ret_dd"], reverse=True)
    print("\n" + "=" * 80)
    print("TOP 10 POR RETORNO / DRAWDOWN")
    print("=" * 80)
    print(f"{'#':>2} | {'LB':>4} | {'MULT':>5} | {'PNL':>10} | {'DD':>8} | {'RET/DD':>7} | {'TRADES':>6} | {'WR':>5}")
    print("-" * 70)
    for i, r in enumerate(results[:10]):
        print(f"{i+1:2d} | {r['lb']:4d} | {r['bm']:5.2f} | R${r['pnl']:8.0f} | R${r['dd']:6.0f} | {r['ret_dd']:7.2f} | {r['trades']:6d} | {r['wr']:4.1f}%")

    # Top 10 by PnL
    results.sort(key=lambda r: r["pnl"], reverse=True)
    print("\n" + "=" * 80)
    print("TOP 10 POR PNL ABSOLUTO")
    print("=" * 80)
    print(f"{'#':>2} | {'LB':>4} | {'MULT':>5} | {'PNL':>10} | {'DD':>8} | {'RET/DD':>7} | {'TRADES':>6} | {'WR':>5}")
    print("-" * 70)
    for i, r in enumerate(results[:10]):
        print(f"{i+1:2d} | {r['lb']:4d} | {r['bm']:5.2f} | R${r['pnl']:8.0f} | R${r['dd']:6.0f} | {r['ret_dd']:7.2f} | {r['trades']:6d} | {r['wr']:4.1f}%")

if __name__ == "__main__":
    main()
