"""
Backtest 3 meses — Parâmetros EXATOS de produção (config.py)
============================================================
Testa as 3 estratégias: WDO-NWE, DI-NWE, Consenso
Usa Kalman Filter + NWE contra-tendência
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, time, timedelta

from statsmodels.tsa.vector_ar.vecm import coint_johansen

from core.config import (
    MT5_PATH, SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME,
    BETA_INITIAL, DI_BETA_INITIAL,
    WDO_KALMAN_Q, WDO_KALMAN_R, WDO_KALMAN_W,
    DI_KALMAN_Q, DI_KALMAN_R, DI_KALMAN_W,
    Z_ENTRY, Z_ATTENTION, Z_ANOMALY,
    NWE_BANDWIDTH, NWE_LOOKBACK, NWE_MULT_MAE, NWE_BAND_MULT,
    BUY_SL, BUY_TP, BUY_BE_ACT, BUY_BE_LOCK,
    SELL_SL, SELL_TP, SELL_BE_ACT, SELL_BE_LOCK,
    WIN_CONTRACTS, WIN_PV,
    ENTRY_START_H, ENTRY_START_M, ENTRY_END_H, ENTRY_END_M,
    FORCE_CLOSE_H, FORCE_CLOSE_M,
    JOH_WINDOW, JOH_RECHECK_BARS,
    BETA_ALERT_PCT,
)
from core.kalman_filter import KalmanBetaFilter
from core.signals import calc_nwe_with_bands

# ─── Data Fetch ──────────────────────────────────────────────────────────────
BARS_3M = 8500  # ~3 meses de M5 (22 dias × 112 bars × 3.5 meses)
BURN_IN = 500   # Barras para aquecer Kalman antes de contar trades

def fetch_data():
    print(f"Conectando ao MT5: {MT5_PATH}")
    if not mt5.initialize(path=MT5_PATH):
        print(f"ERRO MT5: {mt5.last_error()}")
        return None
    
    for sym in [SYMBOL_A, SYMBOL_B, DI_SYMBOL]:
        mt5.symbol_select(sym, True)
    
    print(f"Buscando {BARS_3M} barras M5 (~3 meses)...")
    win_r = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, BARS_3M + BURN_IN)
    wdo_r = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, BARS_3M + BURN_IN)
    di_r  = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, BARS_3M + BURN_IN)
    mt5.shutdown()
    
    if win_r is None or wdo_r is None or di_r is None:
        print("ERRO: sem dados para um dos símbolos.")
        return None
    
    df_win = pd.DataFrame(win_r)
    df_win['time'] = pd.to_datetime(df_win['time'], unit='s')
    df_win.set_index('time', inplace=True)
    
    df_wdo = pd.DataFrame(wdo_r)
    df_wdo['time'] = pd.to_datetime(df_wdo['time'], unit='s')
    df_wdo.set_index('time', inplace=True)
    
    df_di = pd.DataFrame(di_r)
    df_di['time'] = pd.to_datetime(df_di['time'], unit='s')
    df_di.set_index('time', inplace=True)
    
    df = pd.DataFrame({
        'win': df_win['close'], 'win_high': df_win['high'], 'win_low': df_win['low'],
        'wdo': df_wdo['close'], 'di': df_di['close'],
    }).dropna()
    
    print(f"Dados alinhados: {len(df)} barras | {df.index[0]} → {df.index[-1]}")
    return df

# ─── Kalman Z-Scores ─────────────────────────────────────────────────────────
def compute_kalman_zscores(df):
    win, wdo, di = df['win'].values, df['wdo'].values, df['di'].values
    n = len(win)
    
    # WDO Kalman (window override: 240)
    ZSCORE_W = 240
    print(f"  Kalman WDO: Q={WDO_KALMAN_Q}, R={WDO_KALMAN_R}, W={ZSCORE_W} (override)")
    kf_wdo = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
    sp_wdo = []
    for y, x in zip(win, wdo):
        _, spread, _ = kf_wdo.update(float(y), float(x))
        sp_wdo.append(spread)
    z_wdo = np.array(KalmanBetaFilter.rolling_zscore(sp_wdo, window=ZSCORE_W))
    
    # DI Kalman
    print(f"  Kalman DI:  Q={DI_KALMAN_Q}, R={DI_KALMAN_R}, W={ZSCORE_W} (override)")
    b_init, a_init = np.polyfit(di[:100], win[:100], 1)
    kf_di = KalmanBetaFilter(initial_beta=b_init, initial_alpha=a_init, trans_cov=DI_KALMAN_Q, obs_cov=DI_KALMAN_R)
    sp_di = []
    for y, x in zip(win, di):
        _, spread, _ = kf_di.update(float(y), float(x))
        sp_di.append(spread)
    z_di = np.array(KalmanBetaFilter.rolling_zscore(sp_di, window=ZSCORE_W))
    
    df['z_wdo'] = z_wdo
    df['z_di'] = z_di
    return df

# ─── NWE Filter ──────────────────────────────────────────────────────────────
def compute_nwe(df):
    win = df['win'].values
    print(f"  NWE: BW={NWE_BANDWIDTH}, LB={NWE_LOOKBACK}, MAE={NWE_MULT_MAE}, Band={NWE_BAND_MULT}")
    nwe_line, nwe_upper, nwe_lower, nwe_is_up = calc_nwe_with_bands(
        win, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
    )
    df['nwe'] = nwe_line
    df['nwe_upper'] = nwe_upper
    df['nwe_lower'] = nwe_lower
    df['nwe_is_up'] = nwe_is_up
    return df

# ─── Johansen Gate + Beta Stability (per-bar) ────────────────────────────────
def compute_johansen_beta(df):
    """Compute rolling Johansen gate and beta stability per bar."""
    win = df['win'].values
    wdo = df['wdo'].values
    n = len(win)
    
    joh_open = np.zeros(n, dtype=bool)
    joh_ratio = np.zeros(n)
    beta_stable = np.ones(n, dtype=bool)  # True = safe
    beta_ref = np.full(n, np.nan)
    beta_delta = np.zeros(n)
    
    last_check = -999
    gate_open = False
    trace_r = 0.0
    
    # Use kf_betas from z_wdo computation — recalculate for beta ref
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
    kf_betas = []
    for y, x in zip(win, wdo):
        beta, _, _ = kf.update(float(y), float(x))
        kf_betas.append(beta)
    
    print(f"  Johansen: window={JOH_WINDOW}, recheck_bars={JOH_RECHECK_BARS}")
    print(f"  Beta:     alert_pct={BETA_ALERT_PCT}%")
    
    for i in range(n):
        # Johansen gate (recheck every JOH_RECHECK_BARS)
        if i - last_check >= JOH_RECHECK_BARS and i >= JOH_WINDOW:
            try:
                y_mat = np.column_stack([win[i-JOH_WINDOW:i], wdo[i-JOH_WINDOW:i]])
                result = coint_johansen(y_mat, det_order=0, k_ar_diff=1)
                trace_stat = float(result.lr1[0])
                crit_95 = float(result.cvt[0, 1])
                gate_open = bool(trace_stat > crit_95)
                trace_r = round(trace_stat / crit_95, 3) if crit_95 > 0 else 0.0
                last_check = i
            except Exception:
                pass
        
        joh_open[i] = gate_open
        joh_ratio[i] = trace_r
        
        # Beta stability (compare current vs ref 20d)
        if i >= 80:
            ref = float(np.mean(kf_betas[i-80:i-40]))
            curr = kf_betas[i]
            delta_pct = ((curr - ref) / abs(ref) * 100) if ref != 0 else 0
            beta_ref[i] = ref
            beta_delta[i] = delta_pct
            beta_stable[i] = abs(delta_pct) < BETA_ALERT_PCT
    
    df['joh_open'] = joh_open
    df['joh_ratio'] = joh_ratio
    df['beta_stable'] = beta_stable
    df['beta_delta'] = beta_delta
    
    # Rolling Rho (correlation WIN vs WDO, window=40)
    RHO_WINDOW = 40
    rho = pd.Series(df['win'].values).rolling(RHO_WINDOW).corr(pd.Series(df['wdo'].values))
    df['rho'] = rho.values
    
    # Stats
    joh_pct = joh_open[BURN_IN:].sum() / max(1, len(joh_open[BURN_IN:])) * 100
    beta_pct = beta_stable[BURN_IN:].sum() / max(1, len(beta_stable[BURN_IN:])) * 100
    rho_mean = df['rho'].iloc[BURN_IN:].mean()
    print(f"  Johansen ABERTO: {joh_pct:.1f}% do tempo")
    print(f"  Beta ESTAVEL:    {beta_pct:.1f}% do tempo")
    print(f"  Rho medio:       {rho_mean:.3f}")
    return df

# ─── Backtest Engine ─────────────────────────────────────────────────────────
def run_strategy(df, strat_name, get_signal_fn, sl, tp, be_act, be_lock, rho_min=None, use_joh=True):
    """Run a single strategy backtest with optional rho and johansen filters."""
    trades = []
    open_trade = None
    entry_start = time(ENTRY_START_H, ENTRY_START_M)
    entry_end = time(ENTRY_END_H, ENTRY_END_M)
    force_close = time(FORCE_CLOSE_H, FORCE_CLOSE_M)
    
    for i in range(BURN_IN, len(df)):
        row = df.iloc[i]
        dt = df.index[i]
        t = dt.time()
        
        # ── Check exits ──
        if open_trade is not None:
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
            
            # Update max favorable
            if direction == 1:
                favor = row['win_high'] - entry_price
            else:
                favor = entry_price - row['win_low']
            if favor > open_trade['max_favor']:
                open_trade['max_favor'] = favor
            
            if be_act > 0 and open_trade['max_favor'] >= be_act:
                open_trade['be_active'] = True
            
            hit = False
            exit_price = None
            reason = ""
            
            if direction == 1:  # BUY
                if row['win_low'] <= entry_price - sl:
                    hit, exit_price, reason = True, entry_price - sl, "SL"
                elif open_trade['be_active'] and row['win_low'] <= entry_price + be_lock:
                    hit, exit_price, reason = True, entry_price + be_lock, "BE"
                elif row['win_high'] >= entry_price + tp:
                    hit, exit_price, reason = True, entry_price + tp, "TP"
            else:  # SELL
                if row['win_high'] >= entry_price + sl:
                    hit, exit_price, reason = True, entry_price + sl, "SL"
                elif open_trade['be_active'] and row['win_high'] >= entry_price - be_lock:
                    hit, exit_price, reason = True, entry_price - be_lock, "BE"
                elif row['win_low'] <= entry_price - tp:
                    hit, exit_price, reason = True, entry_price - tp, "TP"
            
            # Force close
            if not hit and t >= force_close:
                hit, exit_price, reason = True, row['win'], "EOD"
            
            if hit:
                pnl_pts = (exit_price - entry_price) * direction
                open_trade['exit_price'] = exit_price
                open_trade['exit_time'] = dt
                open_trade['reason'] = reason
                open_trade['pnl_pts'] = pnl_pts
                open_trade['pnl_brl'] = pnl_pts * WIN_PV * WIN_CONTRACTS
                trades.append(open_trade)
                open_trade = None
                continue
        
        # ── Check entries ──
        if open_trade is None and entry_start <= t < entry_end:
            # Johansen gate
            if use_joh and not row.get('joh_open', True):
                continue
            # Beta gate
            if not row.get('beta_stable', True):
                continue
            # Rho gate
            if rho_min is not None:
                rho_val = row.get('rho', -1.0)
                if np.isnan(rho_val) or rho_val > rho_min:
                    continue  # rho not negative enough, skip
            
            signal = get_signal_fn(df, i)
            if signal != 0:
                open_trade = {
                    'strategy': strat_name,
                    'entry_time': dt,
                    'direction': signal,
                    'entry_price': row['win'],
                    'max_favor': 0,
                    'be_active': False,
                }
    
    return trades

# ─── Signal Functions (per strategy) ─────────────────────────────────────────

def signal_wdo_nwe(df, i):
    """WDO-NWE: Z-Score WDO com filtro NWE contra-tendência."""
    row = df.iloc[i]
    z = row['z_wdo']
    win_price = row['win']
    nwe_up = row['nwe_is_up']
    nwe_u = row['nwe_upper']
    nwe_l = row['nwe_lower']
    nwe_c = row['nwe']
    
    if abs(z) >= Z_ANOMALY:
        return 0
    
    # NWE proximity filter (contra-tendência)
    env_w = nwe_u - nwe_c
    prox_upper = nwe_u - (2 * env_w) * NWE_BAND_MULT
    prox_lower = nwe_l + (2 * env_w) * NWE_BAND_MULT
    
    # BUY: z <= -Z_ENTRY AND (tendência de baixa OR preço abaixo da banda)
    if z <= -Z_ENTRY:
        buy_blocked = nwe_up or (win_price > prox_lower)
        if not buy_blocked:
            return 1
    
    # SELL: z >= Z_ENTRY AND (tendência de alta OR preço acima da banda)
    if z >= Z_ENTRY:
        sell_blocked = (not nwe_up) or (win_price < prox_upper)
        if not sell_blocked:
            return -1
    
    return 0

def signal_di_nwe(df, i):
    """DI-NWE: Z-Score DI com filtro NWE contra-tendência."""
    row = df.iloc[i]
    z = row['z_di']
    win_price = row['win']
    nwe_up = row['nwe_is_up']
    nwe_u = row['nwe_upper']
    nwe_l = row['nwe_lower']
    nwe_c = row['nwe']
    
    if abs(z) >= Z_ANOMALY:
        return 0
    
    env_w = nwe_u - nwe_c
    prox_upper = nwe_u - (2 * env_w) * NWE_BAND_MULT
    prox_lower = nwe_l + (2 * env_w) * NWE_BAND_MULT
    
    if z <= -Z_ENTRY:
        buy_blocked = nwe_up or (win_price > prox_lower)
        if not buy_blocked:
            return 1
    
    if z >= Z_ENTRY:
        sell_blocked = (not nwe_up) or (win_price < prox_upper)
        if not sell_blocked:
            return -1
    
    return 0

def signal_consenso(df, i):
    """Consenso: WDO Entry+DI Attention OU DI Entry+WDO Attention (SEM NWE)."""
    row = df.iloc[i]
    zw = row['z_wdo']
    zd = row['z_di']
    
    if abs(zw) >= Z_ANOMALY or abs(zd) >= Z_ANOMALY:
        return 0
    
    # BUY consensus
    buy = (zw <= -Z_ENTRY and zd <= -Z_ATTENTION) or (zd <= -Z_ENTRY and zw <= -Z_ATTENTION)
    if buy:
        return 1
    
    # SELL consensus
    sell = (zw >= Z_ENTRY and zd >= Z_ATTENTION) or (zd >= Z_ENTRY and zw >= Z_ATTENTION)
    if sell:
        return -1
    
    return 0

# ─── Report ──────────────────────────────────────────────────────────────────
def print_report(trades, name):
    if not trades:
        print(f"\n{'='*60}")
        print(f"  {name}: NENHUM TRADE")
        print(f"{'='*60}")
        return
    
    df_t = pd.DataFrame(trades)
    wins = df_t[df_t['pnl_pts'] > 0]
    losses = df_t[df_t['pnl_pts'] < 0]
    breakevens = df_t[df_t['pnl_pts'] == 0]
    
    total = len(df_t)
    wr = len(wins) / total * 100 if total > 0 else 0
    
    gross_p = wins['pnl_brl'].sum() if len(wins) > 0 else 0
    gross_l = abs(losses['pnl_brl'].sum()) if len(losses) > 0 else 0
    net = gross_p - gross_l
    
    avg_win = wins['pnl_pts'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['pnl_pts'].mean()) if len(losses) > 0 else 0
    payoff = avg_win / avg_loss if avg_loss > 0 else float('inf')
    pf = gross_p / gross_l if gross_l > 0 else float('inf')
    
    df_t['cum'] = df_t['pnl_brl'].cumsum()
    df_t['peak'] = df_t['cum'].cummax()
    df_t['dd'] = df_t['peak'] - df_t['cum']
    max_dd = df_t['dd'].max()
    ret_dd = net / max_dd if max_dd > 0 else float('inf')
    
    # Exit reasons
    reasons = df_t['reason'].value_counts()
    
    # Days with trades
    df_t['date'] = df_t['entry_time'].dt.date
    days_traded = df_t['date'].nunique()
    trades_per_day = total / days_traded if days_traded > 0 else 0
    
    # Period
    start_date = df_t['entry_time'].iloc[0].strftime('%d/%m/%Y')
    end_date = df_t['entry_time'].iloc[-1].strftime('%d/%m/%Y')
    
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  Período: {start_date} → {end_date}")
    print(f"{'='*60}")
    print(f"  Trades:         {total}")
    print(f"  Dias operados:  {days_traded} ({trades_per_day:.1f} trades/dia)")
    print(f"  Win Rate:       {wr:.1f}%")
    print(f"  Payoff:         {payoff:.2f}x")
    print(f"  Profit Factor:  {pf:.2f}")
    print(f"  {'─'*40}")
    print(f"  PnL Bruto:      R$ {net:,.2f}")
    print(f"  Max Drawdown:   R$ {max_dd:,.2f}")
    print(f"  Ret/DD:         {ret_dd:.2f}x")
    print(f"  {'─'*40}")
    print(f"  Média Ganho:    {avg_win:.0f} pts (R$ {avg_win * WIN_PV * WIN_CONTRACTS:.2f})")
    print(f"  Média Perda:    {avg_loss:.0f} pts (R$ {avg_loss * WIN_PV * WIN_CONTRACTS:.2f})")
    print(f"  {'─'*40}")
    print(f"  Saídas:")
    for reason, count in reasons.items():
        pct = count / total * 100
        print(f"    {reason:6s}: {count:3d} ({pct:.0f}%)")
    print(f"{'='*60}")

# ─── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*60)
    print("  BACKTEST 3 MESES — PARÂMETROS DE PRODUÇÃO")
    print("="*60)
    print(f"\nParâmetros:")
    print(f"  WDO Kalman: Q={WDO_KALMAN_Q}, R={WDO_KALMAN_R}, W={WDO_KALMAN_W}")
    print(f"  DI  Kalman: Q={DI_KALMAN_Q}, R={DI_KALMAN_R}, W={DI_KALMAN_W}")
    print(f"  Z-Score:    Entry=±{Z_ENTRY}, Attention=±{Z_ATTENTION}, Anomaly=±{Z_ANOMALY}")
    print(f"  NWE:        BW={NWE_BANDWIDTH}, LB={NWE_LOOKBACK}, MAE={NWE_MULT_MAE}, Band={NWE_BAND_MULT}")
    print(f"  SL/TP:      SL={BUY_SL}, TP=300, BE_ACT=0 (OFF), BE_LOCK=0")
    print(f"  Sizing:     {WIN_CONTRACTS} contratos × R${WIN_PV}/pt")
    print(f"  Horário:    {ENTRY_START_H:02d}:{ENTRY_START_M:02d} → {ENTRY_END_H:02d}:{ENTRY_END_M:02d}")
    print(f"  Force Close: {FORCE_CLOSE_H:02d}:{FORCE_CLOSE_M:02d}")
    print()
    
    df = fetch_data()
    if df is None:
        sys.exit(1)
    
    print("\nCalculando Z-Scores...")
    df = compute_kalman_zscores(df)
    
    print("\nCalculando NWE...")
    df = compute_nwe(df)
    
    print("\nCalculando Johansen + Beta + Rho...")
    df = compute_johansen_beta(df)
    
    # ── Grid de Rho ──────────────────────────────────────────────────────────
    rho_levels = [None, -0.30, -0.40, -0.50, -0.60, -0.70, -0.80]
    joh_modes = [False, True]  # False = sem Johansen, True = com Johansen
    
    print(f"\n{'='*90}")
    print(f"  GRID SCAN: Rho x Johansen (SL=300, TP=300, BE=OFF)")
    print(f"{'='*90}")
    print(f"  {'Rho':<8s} {'JOH':<5s} | {'WDO-NWE':>20s} | {'DI-NWE':>20s} | {'CONSENSO':>20s} | {'TOTAL':>20s}")
    print(f"  {'':8s} {'':5s} | {'Trd  WR%   PnL':>20s} | {'Trd  WR%   PnL':>20s} | {'Trd  WR%   PnL':>20s} | {'Trd  WR%   PnL':>20s}")
    print(f"  {'─'*84}")
    
    best_pnl = -999999
    best_config = ""
    
    for use_joh in joh_modes:
        for rho_min in rho_levels:
            t1 = run_strategy(df, "WDO", signal_wdo_nwe, BUY_SL, 300, 0, 0, rho_min=rho_min, use_joh=use_joh)
            t2 = run_strategy(df, "DI", signal_di_nwe, BUY_SL, 300, 0, 0, rho_min=rho_min, use_joh=use_joh)
            t3 = run_strategy(df, "CON", signal_consenso, BUY_SL, 300, 0, 0, rho_min=rho_min, use_joh=use_joh)
            
            def _stats(trades):
                if not trades:
                    return 0, 0.0, 0.0
                n = len(trades)
                w = sum(1 for t in trades if t['pnl_pts'] > 0)
                pnl = sum(t['pnl_brl'] for t in trades)
                return n, w/n*100, pnl
            
            n1, wr1, p1 = _stats(t1)
            n2, wr2, p2 = _stats(t2)
            n3, wr3, p3 = _stats(t3)
            nt = n1+n2+n3
            wrt = (sum(1 for t in t1+t2+t3 if t['pnl_pts']>0)/nt*100) if nt>0 else 0
            pt = p1+p2+p3
            
            rho_str = f"{rho_min:.2f}" if rho_min is not None else "OFF"
            joh_str = "ON" if use_joh else "OFF"
            
            def _fmt(n, wr, p):
                sign = "+" if p >= 0 else ""
                return f"{n:3d} {wr:5.1f}% {sign}{p:>7,.0f}"
            
            marker = ""
            if pt > best_pnl:
                best_pnl = pt
                best_config = f"Rho={rho_str}, JOH={joh_str}"
                marker = " <-- BEST"
            
            print(f"  {rho_str:<8s} {joh_str:<5s} | {_fmt(n1,wr1,p1):>20s} | {_fmt(n2,wr2,p2):>20s} | {_fmt(n3,wr3,p3):>20s} | {_fmt(nt,wrt,pt):>20s}{marker}")
    
    print(f"  {'─'*84}")
    print(f"  MELHOR CONFIG: {best_config}  ->  PnL = R$ {best_pnl:,.2f}")
    print(f"{'='*90}")
    
    print("\n[OK] Backtest concluido.")

