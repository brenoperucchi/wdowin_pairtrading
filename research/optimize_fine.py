"""
Z-Score Fine Grid + Curva RF (Recovery Factor)
z_min: 1.5 a 2.5 step 0.1 | z_max: melhor para cada z_min
Gera grafico de distribuicao RF x Z para BUY e SELL
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40; BETA_INITIAL = -22.5; RHO_MIN = -0.40
BETA_REF_WINDOW = 80; BETA_DELTA_MAX = 25.0
SL_POINTS = 560.0; TP_POINTS = 600.0
WIN_CONTRACTS = 2; WIN_PV = 0.20
ENTRY_START = time(9, 15); ENTRY_END = time(16, 0)
FORCE_CLOSE_TIME = time(17, 40)

Z_MIN_RANGE = np.arange(1.5, 2.51, 0.1)
Z_MAX_RANGE = np.arange(3.0, 6.5, 0.5)

def load_m5():
    cols = ['date', 'time', 'open', 'high', 'low', 'close', 'tickvol', 'vol', 'spread']
    wdo = pd.read_csv(WDO_CSV, sep='\t', names=cols, skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    wdo['dt'] = pd.to_datetime(wdo['date'] + ' ' + wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date'] + ' ' + win['time'], format='%Y.%m.%d %H:%M:%S')
    wdo.set_index('dt', inplace=True); win.set_index('dt', inplace=True)
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'}
    wdo5 = wdo.resample('5min').agg(agg).dropna()
    win5 = win.resample('5min').agg(agg).dropna()
    return wdo5[['close']].rename(columns={'close': 'wdo'}).join(
        win5.rename(columns={'open': 'win_o', 'high': 'win_h', 'low': 'win_l', 'close': 'win'}),
        how='inner').dropna()

def calc_v1(wc, dc):
    n=len(wc); b=np.zeros(n); z=np.zeros(n); r=np.zeros(n)
    for i in range(WINDOW,n):
        ww=wc[i-WINDOW:i]; wd=dc[i-WINDOW:i]
        cv=np.cov(ww,wd); beta=cv[0,1]/(cv[1,1]+1e-10); b[i]=beta
        sw=wc[max(0,i-WINDOW):i]-beta*dc[max(0,i-WINDOW):i]
        z[i]=(wc[i]-beta*dc[i]-sw.mean())/(sw.std()+1e-6)
        if ww.std()>0 and wd.std()>0: r[i]=np.corrcoef(ww,wd)[0,1]
    return b,z,r

def calc_v2(wc, dc):
    n=len(wc); kf=KalmanBetaFilter(initial_beta=BETA_INITIAL)
    sp=[]; bt=[]
    for i in range(n):
        beta,s,v=kf.update(float(wc[i]),float(dc[i])); sp.append(s); bt.append(beta)
    b=np.array(bt); z=np.array(KalmanBetaFilter.rolling_zscore(sp,window=WINDOW))
    r=np.zeros(n)
    for i in range(WINDOW,n):
        ww=wc[i-WINDOW:i]; wd=dc[i-WINDOW:i]
        if ww.std()>0 and wd.std()>0: r[i]=np.corrcoef(ww,wd)[0,1]
    return b,z,r

def is_safe(betas,idx,rv):
    if rv>RHO_MIN: return False
    if idx<BETA_REF_WINDOW: return True
    ref=np.mean(betas[idx-BETA_REF_WINDOW:idx-WINDOW]) if idx>BETA_REF_WINDOW else betas[max(0,idx-1)]
    if abs(ref)<1e-6: return True
    return abs((betas[idx]-ref)/abs(ref)*100)<BETA_DELTA_MAX

def run(data, zs, ra, bs, zmin, zmax, direction):
    n=len(zs); ts=data.index; wh=data['win_h'].values; wl=data['win_l'].values; wc=data['win'].values
    pos=None; trades=[]
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            if direction=='buy':
                tp=pos['px']+TP_POINTS; sl=pos['px']-SL_POINTS
                if wh[i]>=tp: reason='TP'; ep=tp
                elif wl[i]<=sl: reason='SL'; ep=sl
            else:
                tp=pos['px']-TP_POINTS; sl=pos['px']+SL_POINTS
                if wl[i]<=tp: reason='TP'; ep=tp
                elif wh[i]>=sl: reason='SL'; ep=sl
            if reason is None and t>=FORCE_CLOSE_TIME: reason='FC'; ep=wc[i]
            if reason:
                d=1 if direction=='buy' else -1
                trades.append(d*(ep-pos['px'])*WIN_CONTRACTS*WIN_PV)
                pos=None
        if pos is not None: continue
        if t<ENTRY_START or t>ENTRY_END: continue
        if not is_safe(bs,i,ra[i]): continue
        az=abs(z)
        if az<zmin or az>=zmax: continue
        if direction=='buy' and z<-zmin: pos={'px':wc[i]}
        elif direction=='sell' and z>zmin: pos={'px':wc[i]}
    return trades

def calc_rf(trades):
    if not trades or len(trades)<5: return 0, 0, 0, 0, 0
    pnls=np.array(trades)
    pnl=pnls.sum()
    eq=np.cumsum(pnls); pk=np.maximum.accumulate(eq); dd=(pk-eq).max()
    rf=pnl/dd if dd>0 else 0
    wr=np.sum(pnls>0)/len(pnls)*100
    gp=pnls[pnls>0].sum(); gl=abs(pnls[pnls<=0].sum())+.001
    return rf, pnl, dd, wr, gp/gl


def main():
    start=datetime.now()
    print("Carregando...")
    data=load_m5()
    wc=data['win'].values.astype(float); dc=data['wdo'].values.astype(float)
    print("  V1 OLS..."); b1,z1,r1=calc_v1(wc,dc)
    print("  V2 Kalman..."); b2,z2,r2=calc_v2(wc,dc)
    
    # Grid fino
    print(f"\nGrid: z_min 1.5->2.5 step 0.1, z_max {Z_MAX_RANGE[0]}-{Z_MAX_RANGE[-1]}")
    
    buy_results = []  # (z_min, best_rf, best_zmax, n, pnl, dd, wr, pf)
    sell_results = []
    
    # V2 Kalman BUY
    print("\n--- V2 KALMAN WIN BUY ---")
    print(f"{'z_min':>5} {'z_max':>5} {'n':>5} {'wr':>5} {'pnl':>8} {'dd':>7} {'pf':>5} {'RF':>6}")
    for zmin in Z_MIN_RANGE:
        best_rf = -999; best_row = None
        for zmax in Z_MAX_RANGE:
            if zmax<=zmin: continue
            t = run(data, z2, r2, b2, zmin, zmax, 'buy')
            rf, pnl, dd, wr, pf = calc_rf(t)
            if rf > best_rf and pnl > 0:
                best_rf = rf; best_row = (zmin, zmax, len(t), wr, pnl, dd, pf, rf)
        if best_row:
            buy_results.append(best_row)
            r = best_row
            print(f"{r[0]:>5.1f} {r[1]:>5.1f} {r[2]:>5} {r[3]:>4.0f}% {r[4]:>8.0f} {r[5]:>7.0f} {r[6]:>5.2f} {r[7]:>6.2f}")
        else:
            buy_results.append((zmin, 0, 0, 0, 0, 0, 0, 0))
    
    # V1 OLS SELL
    print("\n--- V1 OLS WIN SELL ---")
    print(f"{'z_min':>5} {'z_max':>5} {'n':>5} {'wr':>5} {'pnl':>8} {'dd':>7} {'pf':>5} {'RF':>6}")
    for zmin in Z_MIN_RANGE:
        best_rf = -999; best_row = None
        for zmax in Z_MAX_RANGE:
            if zmax<=zmin: continue
            t = run(data, z1, r1, b1, zmin, zmax, 'sell')
            rf, pnl, dd, wr, pf = calc_rf(t)
            if rf > best_rf and pnl > 0:
                best_rf = rf; best_row = (zmin, zmax, len(t), wr, pnl, dd, pf, rf)
        if best_row:
            sell_results.append(best_row)
            r = best_row
            print(f"{r[0]:>5.1f} {r[1]:>5.1f} {r[2]:>5} {r[3]:>4.0f}% {r[4]:>8.0f} {r[5]:>7.0f} {r[6]:>5.2f} {r[7]:>6.2f}")
        else:
            sell_results.append((zmin, 0, 0, 0, 0, 0, 0, 0))
    
    # ═══ GERAR GRAFICO ═══
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14))
    fig.suptitle('Recovery Factor vs Z-Score Entry\nWIN SL=560 TP=600 | 2021-2026', 
                 fontsize=16, fontweight='bold', y=0.98)
    
    # Dados para plot
    buy_z = [r[0] for r in buy_results]
    buy_rf = [r[7] for r in buy_results]
    buy_pnl = [r[4] for r in buy_results]
    buy_n = [r[2] for r in buy_results]
    
    sell_z = [r[0] for r in sell_results]
    sell_rf = [r[7] for r in sell_results]
    sell_pnl = [r[4] for r in sell_results]
    sell_n = [r[2] for r in sell_results]
    
    # ─── Plot 1: RF por Z-score ───
    ax1.fill_between(buy_z, buy_rf, alpha=0.3, color='#00c853', label='V2 Kalman BUY')
    ax1.plot(buy_z, buy_rf, 'o-', color='#00c853', linewidth=2.5, markersize=8)
    ax1.fill_between(sell_z, sell_rf, alpha=0.3, color='#ff5252', label='V1 OLS SELL')
    ax1.plot(sell_z, sell_rf, 's-', color='#ff5252', linewidth=2.5, markersize=8)
    
    # Anotar melhores
    best_buy_idx = np.argmax(buy_rf)
    best_sell_idx = np.argmax(sell_rf)
    ax1.annotate(f'RF={buy_rf[best_buy_idx]:.2f}\nz={buy_z[best_buy_idx]:.1f}', 
                 xy=(buy_z[best_buy_idx], buy_rf[best_buy_idx]),
                 xytext=(10, 15), textcoords='offset points',
                 fontsize=10, fontweight='bold', color='#00c853',
                 arrowprops=dict(arrowstyle='->', color='#00c853'))
    ax1.annotate(f'RF={sell_rf[best_sell_idx]:.2f}\nz={sell_z[best_sell_idx]:.1f}', 
                 xy=(sell_z[best_sell_idx], sell_rf[best_sell_idx]),
                 xytext=(10, 15), textcoords='offset points',
                 fontsize=10, fontweight='bold', color='#ff5252',
                 arrowprops=dict(arrowstyle='->', color='#ff5252'))
    
    ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax1.axhline(y=1, color='gold', linestyle='--', alpha=0.7, label='RF=1 (breakeven risk)')
    ax1.set_xlabel('Z-Score Entry Threshold', fontsize=12)
    ax1.set_ylabel('Recovery Factor (PnL / MaxDD)', fontsize=12)
    ax1.set_title('Recovery Factor por Z-Score', fontsize=14)
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(np.arange(1.5, 2.6, 0.1))
    
    # ─── Plot 2: PnL por Z-score ───
    ax2.bar([z-0.02 for z in buy_z], buy_pnl, width=0.04, color='#00c853', alpha=0.8, label='V2 Kalman BUY')
    ax2.bar([z+0.02 for z in sell_z], sell_pnl, width=0.04, color='#ff5252', alpha=0.8, label='V1 OLS SELL')
    ax2.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    ax2.set_xlabel('Z-Score Entry', fontsize=12)
    ax2.set_ylabel('PnL (R$)', fontsize=12)
    ax2.set_title('PnL Total por Z-Score', fontsize=14)
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(np.arange(1.5, 2.6, 0.1))
    
    # ─── Plot 3: Numero de trades por Z-score ───
    ax3.bar([z-0.02 for z in buy_z], buy_n, width=0.04, color='#00c853', alpha=0.8, label='V2 Kalman BUY')
    ax3.bar([z+0.02 for z in sell_z], sell_n, width=0.04, color='#ff5252', alpha=0.8, label='V1 OLS SELL')
    ax3.set_xlabel('Z-Score Entry', fontsize=12)
    ax3.set_ylabel('Numero de Trades (5 anos)', fontsize=12)
    ax3.set_title('Volume de Trades por Z-Score', fontsize=14)
    ax3.legend(fontsize=11)
    ax3.grid(True, alpha=0.3)
    ax3.set_xticks(np.arange(1.5, 2.6, 0.1))
    
    plt.tight_layout()
    plt.savefig('rf_distribution.png', dpi=150, bbox_inches='tight')
    print(f"\n[OK] Grafico salvo: rf_distribution.png")
    print(f"[OK] {(datetime.now()-start).total_seconds():.0f}s")


if __name__ == '__main__':
    main()
