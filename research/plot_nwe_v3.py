"""
Plot equity curves for LB=95, Mult=0.10 — WDO + DI (with and without Consensus)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60
Z_ENT, Z_ATT = 1.4, 1.2
TP, SL, BE = 800, 300, 300
WIN_PV = 0.20
FORCE_CLOSE_MIN = 17 * 60 + 40
START_M, END_M = 9 * 60, 15 * 60
BW, LB, MAE_MULT = 8, 95, 3.0
BAND_MULT = 0.10

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".planning", "docs", "assets")

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
        if lb == 0: continue
        err = np.abs(prices[t - lb : t + 1] - nwe[t - lb : t + 1])
        mae[t] = np.mean(err) * mult_mae
    return nwe, nwe + mae, nwe - mae

def simulate(k_z, j_z, win_c, bar_mins, mode, is_up, upper, lower, band_mult):
    n = len(win_c)
    pnl = np.zeros(n)
    position = 0
    entry_price = 0.0
    be_hit = False

    for i in range(1000, n):
        price = win_c[i]
        t_min = bar_mins[i]

        if position != 0 and t_min >= FORCE_CLOSE_MIN:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            pnl[i] = diff * WIN_PV
            position = 0
            continue

        zw, zd = k_z[i], j_z[i]
        if mode == "wdo":
            sig_buy, sig_sell = (zw <= -Z_ENT), (zw >= Z_ENT)
        elif mode == "di":
            sig_buy, sig_sell = (zd <= -Z_ENT), (zd >= Z_ENT)
        elif mode == "consensus":
            sig_buy = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
            sig_sell = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)
        else:
            sig_buy = sig_sell = False

        bw = upper[i] - lower[i]
        if bw < 1e-10: bw = 1.0
        up = is_up[i]

        if sig_buy:
            if up: sig_buy = False
            elif price > lower[i] + bw * band_mult: sig_buy = False
        if sig_sell:
            if not up: sig_sell = False
            elif price < upper[i] - bw * band_mult: sig_sell = False

        if position == 0:
            if t_min < START_M or t_min > END_M:
                sig_buy = sig_sell = False
            if sig_buy:
                position, entry_price, be_hit = 1, price, False
            elif sig_sell:
                position, entry_price, be_hit = -1, price, False
        else:
            diff = (price - entry_price) if position == 1 else (entry_price - price)
            if not be_hit and diff >= BE: be_hit = True
            if diff >= TP:
                pnl[i] = TP * WIN_PV; position = 0
            elif be_hit and diff <= 0:
                pnl[i] = 0; position = 0
            elif not be_hit and diff <= -SL:
                pnl[i] = -SL * WIN_PV; position = 0
    return pnl

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
    if dd < 1e-5: dd = 1.0
    return {"pnl": total_pnl, "trades": total, "wr": wr, "dd": dd, "ret_dd": total_pnl / dd}

def main():
    print("Carregando dados MT5...")
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
    print(f"Barras: {n}")

    print("Calculando Z-scores...")
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
        except: betas[i] = betas[i - 1] if i > 0 else 0
    for i in range(J_JW, n):
        if betas[i] == 0: betas[i] = betas[i - 1]
    spread_di = win + betas * di
    j_z = np.zeros(n)
    for i in range(J_JW + J_ZW, n):
        ws = spread_di[i - J_ZW:i]
        mu, sd = np.mean(ws), np.std(ws)
        j_z[i] = (spread_di[i] - mu) / (sd if sd > 1e-10 else 1.0)

    print(f"Calculando NWE (BW={BW}, LB={LB}, BandMult={BAND_MULT})...")
    nwe, upper, lower = calc_nwe_with_bands(win, BW, LB, MAE_MULT)
    is_up = np.zeros(n, dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True
    bar_mins = np.array([bar_minute_of_day(t) for t in times])

    print("Simulando...")
    pnl_wdo = simulate(k_z, j_z, win, bar_mins, "wdo", is_up, upper, lower, BAND_MULT)
    pnl_di = simulate(k_z, j_z, win, bar_mins, "di", is_up, upper, lower, BAND_MULT)
    pnl_cons = simulate(k_z, j_z, win, bar_mins, "consensus", is_up, upper, lower, BAND_MULT)

    pnl_no_cons = pnl_wdo + pnl_di
    pnl_with_cons = pnl_wdo + pnl_di + pnl_cons

    s_wdo = calc_stats(pnl_wdo)
    s_di = calc_stats(pnl_di)
    s_cons = calc_stats(pnl_cons)
    s_no = calc_stats(pnl_no_cons)
    s_with = calc_stats(pnl_with_cons)

    print(f"\n{'='*75}")
    print(f"RESULTADO LB={LB}, BandMult={BAND_MULT} (09h-15h, FC 17h40)")
    print(f"{'='*75}")
    print(f"{'Estratégia':<25} | {'PnL':>10} | {'DD':>8} | {'Ret/DD':>7} | {'Trades':>6} | {'WR':>5}")
    print(f"{'-'*75}")
    print(f"{'WDO Kalman':<25} | R${s_wdo['pnl']:>8.0f} | R${s_wdo['dd']:>5.0f} | {s_wdo['ret_dd']:>7.2f} | {s_wdo['trades']:>6} | {s_wdo['wr']:>4.1f}%")
    print(f"{'DI Johansen':<25} | R${s_di['pnl']:>8.0f} | R${s_di['dd']:>5.0f} | {s_di['ret_dd']:>7.2f} | {s_di['trades']:>6} | {s_di['wr']:>4.1f}%")
    print(f"{'Consenso':<25} | R${s_cons['pnl']:>8.0f} | R${s_cons['dd']:>5.0f} | {s_cons['ret_dd']:>7.2f} | {s_cons['trades']:>6} | {s_cons['wr']:>4.1f}%")
    print(f"{'-'*75}")
    print(f"{'PORT s/ Consenso':<25} | R${s_no['pnl']:>8.0f} | R${s_no['dd']:>5.0f} | {s_no['ret_dd']:>7.2f} | {s_no['trades']:>6} | {s_no['wr']:>4.1f}%")
    print(f"{'PORT c/ Consenso':<25} | R${s_with['pnl']:>8.0f} | R${s_with['dd']:>5.0f} | {s_with['ret_dd']:>7.2f} | {s_with['trades']:>6} | {s_with['wr']:>4.1f}%")
    print(f"{'='*75}")

    # ── PLOT: Equity Curves ──
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(18, 7))

    # Left: SEM Consenso
    ax = axes[0]
    ax.plot(np.cumsum(pnl_wdo), color='#c8a444', alpha=0.7, label=f"WDO (R${s_wdo['pnl']:.0f})")
    ax.plot(np.cumsum(pnl_di), color='#8a6dff', alpha=0.7, label=f"DI (R${s_di['pnl']:.0f})")
    ax.plot(np.cumsum(pnl_no_cons), color='white', linewidth=2.5,
            label=f"PORT (R${s_no['pnl']:.0f} | DD R${s_no['dd']:.0f} | {s_no['ret_dd']:.1f}x)")
    ax.set_title(f"SEM Consenso — LB={LB}, BM={BAND_MULT}", fontsize=12, pad=10)
    ax.set_ylabel("PnL (R$)")
    ax.set_xlabel("Barras (M5)")
    ax.legend(fontsize=8, framealpha=0.7)
    ax.grid(alpha=0.12)

    # Right: COM Consenso
    ax = axes[1]
    ax.plot(np.cumsum(pnl_wdo), color='#c8a444', alpha=0.7, label=f"WDO (R${s_wdo['pnl']:.0f})")
    ax.plot(np.cumsum(pnl_di), color='#8a6dff', alpha=0.7, label=f"DI (R${s_di['pnl']:.0f})")
    ax.plot(np.cumsum(pnl_cons), color='#ff69b4', alpha=0.7, label=f"CONS (R${s_cons['pnl']:.0f})")
    ax.plot(np.cumsum(pnl_with_cons), color='white', linewidth=2.5,
            label=f"PORT (R${s_with['pnl']:.0f} | DD R${s_with['dd']:.0f} | {s_with['ret_dd']:.1f}x)")
    ax.set_title(f"COM Consenso — LB={LB}, BM={BAND_MULT}", fontsize=12, pad=10)
    ax.set_ylabel("PnL (R$)")
    ax.set_xlabel("Barras (M5)")
    ax.legend(fontsize=8, framealpha=0.7)
    ax.grid(alpha=0.12)

    fig.suptitle("Setup Matador v3 — Comparação com/sem Consenso", fontsize=14, y=0.98)
    fig.tight_layout()

    path1 = os.path.join(OUT_DIR, "equity_lb95_comparison.png")
    fig.savefig(path1, dpi=130)
    plt.close(fig)
    print(f"\nGráfico salvo: {path1}")

    # ── PLOT 2: NWE Bands + Entry Zones (últimas 500 barras) ──
    WINDOW = 500
    sl = slice(-WINDOW, None)
    p = win[sl]; u = upper[sl]; lo = lower[sl]; nw = nwe[sl]
    bw_arr = u - lo
    buy_zone_top = lo + bw_arr * BAND_MULT
    sell_zone_bot = u - bw_arr * BAND_MULT
    x = np.arange(WINDOW)

    fig2, ax2 = plt.subplots(figsize=(16, 8))
    ax2.plot(x, p, color='white', linewidth=0.8, alpha=0.9, label='WIN Price', zorder=5)
    ax2.plot(x, nw, color='#00d4ff', linewidth=1.2, alpha=0.6, label='NWE Center', zorder=4)
    ax2.plot(x, u, color='#ff3860', linewidth=0.8, alpha=0.5, label='Upper Band')
    ax2.plot(x, lo, color='#00e87a', linewidth=0.8, alpha=0.5, label='Lower Band')
    ax2.fill_between(x, lo, u, color='#ffffff', alpha=0.03)
    ax2.fill_between(x, lo, buy_zone_top, color='#00e87a', alpha=0.15,
                     label=f'Zona COMPRA (10% da banda)')
    ax2.fill_between(x, sell_zone_bot, u, color='#ff3860', alpha=0.15,
                     label=f'Zona VENDA (10% da banda)')
    ax2.plot(x, buy_zone_top, color='#00e87a', linewidth=0.6, linestyle='--', alpha=0.4)
    ax2.plot(x, sell_zone_bot, color='#ff3860', linewidth=0.6, linestyle='--', alpha=0.4)
    ax2.set_title(f"NWE Bands + Zonas de Entrada — LB={LB}, BandMult={BAND_MULT} (últimas {WINDOW} barras)",
                  fontsize=13, pad=12)
    ax2.set_ylabel("Preço WIN"); ax2.set_xlabel("Barras (M5)")
    ax2.legend(loc="upper left", fontsize=8, framealpha=0.7)
    ax2.grid(alpha=0.12)
    fig2.tight_layout()

    path2 = os.path.join(OUT_DIR, "nwe_bands_lb95.png")
    fig2.savefig(path2, dpi=130)
    plt.close(fig2)
    print(f"Bandas salvo: {path2}")

if __name__ == "__main__":
    main()
