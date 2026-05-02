"""
Otimizacao Z-Score: V2 Kalman WIN BUY + V1 OLS WIN SELL
========================================================
Grid search: z_entry_min (1.0 a 3.5) e z_entry_max (3.0 a 6.0)
Mantendo SL=560, TP=600, 2 contratos WIN
"""

import numpy as np
import pandas as pd
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# ─── CONFIG FIXO ────────────────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40
BETA_INITIAL = -22.5
RHO_MIN = -0.40
BETA_REF_WINDOW = 80
BETA_DELTA_MAX = 25.0
SL_POINTS = 560.0
TP_POINTS = 600.0
WIN_CONTRACTS = 2
WIN_PV = 0.20
ENTRY_START = time(9, 15)
ENTRY_END = time(16, 0)
FORCE_CLOSE_TIME = time(17, 40)

# Grid
Z_MIN_RANGE = np.arange(1.0, 3.75, 0.25)   # 1.0, 1.25, 1.5, ..., 3.5
Z_MAX_RANGE = np.arange(3.0, 6.5, 0.5)     # 3.0, 3.5, 4.0, ..., 6.0


def load_m5():
    cols = ['date', 'time', 'open', 'high', 'low', 'close', 'tickvol', 'vol', 'spread']
    wdo = pd.read_csv(WDO_CSV, sep='\t', names=cols, skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    wdo['dt'] = pd.to_datetime(wdo['date'] + ' ' + wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date'] + ' ' + win['time'], format='%Y.%m.%d %H:%M:%S')
    wdo.set_index('dt', inplace=True)
    win.set_index('dt', inplace=True)
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'}
    wdo5 = wdo.resample('5min').agg(agg).dropna()
    win5 = win.resample('5min').agg(agg).dropna()
    merged = wdo5[['close']].rename(columns={'close': 'wdo'}).join(
        win5.rename(columns={'open': 'win_o', 'high': 'win_h', 'low': 'win_l', 'close': 'win'}),
        how='inner').dropna()
    return merged


def calc_v1(win_c, wdo_c):
    n = len(win_c)
    betas = np.zeros(n); z_scores = np.zeros(n); rho = np.zeros(n)
    for i in range(WINDOW, n):
        ww = win_c[i-WINDOW:i]; wd = wdo_c[i-WINDOW:i]
        cov = np.cov(ww, wd)
        b = cov[0,1]/(cov[1,1]+1e-10); betas[i] = b
        sw = win_c[max(0,i-WINDOW):i] - b*wdo_c[max(0,i-WINDOW):i]
        cs = win_c[i] - b*wdo_c[i]
        z_scores[i] = (cs - sw.mean())/(sw.std()+1e-6)
        if ww.std()>0 and wd.std()>0: rho[i] = np.corrcoef(ww,wd)[0,1]
    return betas, z_scores, rho


def calc_v2(win_c, wdo_c):
    n = len(win_c)
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL)
    sp = []; bt = []
    for i in range(n):
        b, s, v = kf.update(float(win_c[i]), float(wdo_c[i]))
        sp.append(s); bt.append(b)
    betas = np.array(bt)
    z_scores = np.array(KalmanBetaFilter.rolling_zscore(sp, window=WINDOW))
    rho = np.zeros(n)
    for i in range(WINDOW, n):
        ww = win_c[i-WINDOW:i]; wd = wdo_c[i-WINDOW:i]
        if ww.std()>0 and wd.std()>0: rho[i] = np.corrcoef(ww,wd)[0,1]
    return betas, z_scores, rho


def is_safe(betas, idx, rho_val):
    if rho_val > RHO_MIN: return False
    if idx < BETA_REF_WINDOW: return True
    ref = np.mean(betas[idx-BETA_REF_WINDOW:idx-WINDOW]) if idx > BETA_REF_WINDOW else betas[max(0,idx-1)]
    if abs(ref)<1e-6: return True
    return abs((betas[idx]-ref)/abs(ref)*100) < BETA_DELTA_MAX


def run_single(data, z_scores, rho_arr, betas, z_min, z_max, direction):
    """
    direction='buy': entra quando z < -z_min (WIN barato)
    direction='sell': entra quando z > +z_min (WIN caro)
    """
    n = len(z_scores)
    ts_arr = data.index
    win_h = data['win_h'].values
    win_l = data['win_l'].values
    win_c = data['win'].values
    
    pos = None
    trades = []
    
    for i in range(WINDOW, n):
        t = ts_arr[i].time()
        z = z_scores[i]
        
        # Checar saida
        if pos is not None:
            reason = None; exit_px = 0
            if direction == 'buy':
                tp = pos['px'] + TP_POINTS; sl = pos['px'] - SL_POINTS
                if win_h[i] >= tp: reason='TP'; exit_px=tp
                elif win_l[i] <= sl: reason='SL'; exit_px=sl
            else:
                tp = pos['px'] - TP_POINTS; sl = pos['px'] + SL_POINTS
                if win_l[i] <= tp: reason='TP'; exit_px=tp
                elif win_h[i] >= sl: reason='SL'; exit_px=sl
            
            if reason is None and t >= FORCE_CLOSE_TIME:
                reason='FC'; exit_px=win_c[i]
            
            if reason:
                d = 1 if direction=='buy' else -1
                pnl = d*(exit_px-pos['px'])*WIN_CONTRACTS*WIN_PV
                trades.append({'pnl': pnl, 'reason': reason})
                pos = None
        
        # Checar entrada
        if pos is not None: continue
        if t < ENTRY_START or t > ENTRY_END: continue
        if not is_safe(betas, i, rho_arr[i]): continue
        
        az = abs(z)
        if az < z_min or az >= z_max: continue
        
        if direction == 'buy' and z < -z_min:
            pos = {'px': win_c[i]}
        elif direction == 'sell' and z > z_min:
            pos = {'px': win_c[i]}
    
    return trades


def metrics(trades):
    if not trades: return 0, 0, 0, 0, 0
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins)/len(trades)*100
    pnl = sum(pnls)
    gp = sum(wins) if wins else 0
    gl = abs(sum(losses)) if losses else 0.001
    pf = gp/gl
    # Max dd
    eq = np.cumsum(pnls)
    pk = np.maximum.accumulate(eq)
    dd = (pk-eq).max() if len(eq)>0 else 0
    return len(trades), wr, pnl, pf, dd


def main():
    start = datetime.now()
    print("Carregando e calculando indicadores...")
    data = load_m5()
    win_c = data['win'].values.astype(float)
    wdo_c = data['wdo'].values.astype(float)
    
    print("  V1 OLS...")
    b1, z1, r1 = calc_v1(win_c, wdo_c)
    print("  V2 Kalman...")
    b2, z2, r2 = calc_v2(win_c, wdo_c)
    
    print(f"\nGrid: z_min {Z_MIN_RANGE[0]}-{Z_MIN_RANGE[-1]} x z_max {Z_MAX_RANGE[0]}-{Z_MAX_RANGE[-1]}")
    print(f"Combinacoes: {len(Z_MIN_RANGE)*len(Z_MAX_RANGE)} por leg\n")
    
    # ═══ V2 KALMAN WIN BUY ═══
    print("=" * 70)
    print("  V2 KALMAN — WIN BUY (z < -X)")
    print("=" * 70)
    print(f"{'z_min':>6} {'z_max':>6} {'trades':>7} {'wr%':>6} {'pnl':>10} {'pf':>6} {'maxdd':>8} {'RF':>6}")
    print("-" * 78)
    
    best_buy = {'rf': -999999}
    
    for z_min in Z_MIN_RANGE:
        for z_max in Z_MAX_RANGE:
            if z_max <= z_min: continue
            trades = run_single(data, z2, r2, b2, z_min, z_max, 'buy')
            n, wr, pnl, pf, dd = metrics(trades)
            if n < 10: continue
            rf = pnl / dd if dd > 0 else 0
            print(f"{z_min:>6.2f} {z_max:>6.1f} {n:>7} {wr:>5.1f}% {pnl:>10.0f} {pf:>6.2f} {dd:>8.0f} {rf:>6.2f}")
            if rf > best_buy['rf'] and pnl > 0:
                best_buy = {'z_min': z_min, 'z_max': z_max, 'n': n, 'wr': wr, 'pnl': pnl, 'pf': pf, 'dd': dd, 'rf': rf}
    
    print(f"\n>>> BEST BUY: z=[{best_buy.get('z_min','?')}, {best_buy.get('z_max','?')}] "
          f"trades={best_buy.get('n',0)} pnl=R${best_buy.get('pnl',0):.0f} pf={best_buy.get('pf',0):.2f} RF={best_buy.get('rf',0):.2f} dd=R${best_buy.get('dd',0):.0f}\n")
    
    # ═══ V1 OLS WIN SELL ═══
    print("=" * 70)
    print("  V1 OLS — WIN SELL (z > +X)")
    print("=" * 70)
    print(f"{'z_min':>6} {'z_max':>6} {'trades':>7} {'wr%':>6} {'pnl':>10} {'pf':>6} {'maxdd':>8} {'RF':>6}")
    print("-" * 78)
    
    best_sell = {'rf': -999999}
    
    for z_min in Z_MIN_RANGE:
        for z_max in Z_MAX_RANGE:
            if z_max <= z_min: continue
            trades = run_single(data, z1, r1, b1, z_min, z_max, 'sell')
            n, wr, pnl, pf, dd = metrics(trades)
            if n < 10: continue
            rf = pnl / dd if dd > 0 else 0
            print(f"{z_min:>6.2f} {z_max:>6.1f} {n:>7} {wr:>5.1f}% {pnl:>10.0f} {pf:>6.2f} {dd:>8.0f} {rf:>6.2f}")
            if rf > best_sell['rf'] and pnl > 0:
                best_sell = {'z_min': z_min, 'z_max': z_max, 'n': n, 'wr': wr, 'pnl': pnl, 'pf': pf, 'dd': dd, 'rf': rf}
    
    print(f"\n>>> BEST SELL: z=[{best_sell.get('z_min','?')}, {best_sell.get('z_max','?')}] "
          f"trades={best_sell.get('n',0)} pnl=R${best_sell.get('pnl',0):.0f} pf={best_sell.get('pf',0):.2f} RF={best_sell.get('rf',0):.2f} dd=R${best_sell.get('dd',0):.0f}\n")
    
    # ═══ COMBINADO ═══
    print("=" * 70)
    print("  COMBINADO: V2 BUY + V1 SELL (melhores params)")
    print("=" * 70)
    
    buy_t = run_single(data, z2, r2, b2, best_buy['z_min'], best_buy['z_max'], 'buy')
    sell_t = run_single(data, z1, r1, b1, best_sell['z_min'], best_sell['z_max'], 'sell')
    
    nb, wrb, pb, pfb, ddb = metrics(buy_t)
    ns, wrs, ps, pfs, dds = metrics(sell_t)
    
    combined = buy_t + sell_t
    nc, wrc, pc, pfc, ddc = metrics(combined)
    
    print(f"  BUY:  {nb} trades | wr={wrb:.1f}% | pnl=R${pb:.0f} | pf={pfb:.2f} | dd=R${ddb:.0f}")
    print(f"  SELL: {ns} trades | wr={wrs:.1f}% | pnl=R${ps:.0f} | pf={pfs:.2f} | dd=R${dds:.0f}")
    print(f"  TOTAL: {nc} trades | wr={wrc:.1f}% | pnl=R${pc:.0f} | pf={pfc:.2f} | dd=R${ddc:.0f}")
    
    elapsed = (datetime.now()-start).total_seconds()
    print(f"\n[OK] {elapsed:.0f}s")


if __name__ == '__main__':
    main()
