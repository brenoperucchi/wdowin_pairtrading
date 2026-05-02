"""
Otimização Fina de SL e TP para WDO (Dólar Mini)
Horário: 10:00 às 16:00
V2 Kalman BUY (Z < -3.00)
V1 OLS SELL (Z > +2.75)
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# ─── CONFIG ──────────────────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40; BETA_INITIAL = -22.5; RHO_MIN = -0.40
BETA_REF_WINDOW = 80; BETA_DELTA_MAX = 25.0
ENTRY_START = time(10, 0); ENTRY_END = time(16, 0); FC_TIME = time(17, 40)
CONTRACTS = 1; PV = 10.00 

BUY_ZMIN = 3.00
SELL_ZMIN = 2.75

SL_RANGE = np.arange(5, 36, 5)   # 5, 10, 15, 20, 25, 30, 35
TP_RANGE = np.arange(10, 61, 5)  # 10, 15, 20 ... 60

def load():
    print("Carregando bases...")
    cols = ['date','time','open','high','low','close','tickvol','vol','spread']
    wdo = pd.read_csv(WDO_CSV, sep='\t', names=cols, skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    wdo['dt'] = pd.to_datetime(wdo['date']+' '+wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date']+' '+win['time'], format='%Y.%m.%d %H:%M:%S')
    wdo.set_index('dt', inplace=True); win.set_index('dt', inplace=True)
    agg = {'open':'first','high':'max','low':'min','close':'last','vol':'sum'}
    wdo5 = wdo.resample('5min').agg(agg).dropna()
    win5 = win.resample('5min').agg(agg).dropna()
    return wdo5[['open','high','low','close']].rename(columns={'open':'wo','high':'wh','low':'wl','close':'wdo'}).join(
        win5[['close']].rename(columns={'close':'win'}), how='inner').dropna()

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
    n=len(wc); kf=KalmanBetaFilter(initial_beta=BETA_INITIAL); sp=[]; bt=[]
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

def run_wdo(data, zs, ra, bs, zmin, direction, sl_pts, tp_pts):
    n = len(zs); ts=data.index; wh=data['wh'].values; wl=data['wl'].values; wc=data['wdo'].values
    pos=None; trades=[]
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            if direction=='buy':
                if wh[i] >= pos['px'] + tp_pts: reason='TP'; ep = pos['px'] + tp_pts
                elif wl[i] <= pos['px'] - sl_pts: reason='SL'; ep = pos['px'] - sl_pts
            else:
                if wl[i] <= pos['px'] - tp_pts: reason='TP'; ep = pos['px'] - tp_pts
                elif wh[i] >= pos['px'] + sl_pts: reason='SL'; ep = pos['px'] + sl_pts
            if reason is None and t>=FC_TIME: reason='FC'; ep=wc[i]
            if reason:
                d=1 if direction=='buy' else -1
                pnl=d*(ep-pos['px'])*CONTRACTS*PV
                trades.append(pnl)
                pos=None
        if pos is not None: continue
        if t<ENTRY_START or t>ENTRY_END: continue
        if not is_safe(bs,i,ra[i]): continue
        az=abs(z)
        if direction=='buy' and z < -zmin: pos={'px':wc[i]}
        elif direction=='sell' and z > zmin: pos={'px':wc[i]}
    return trades

def calc_rf(trades):
    if not trades or len(trades)<5: return 0, 0, 0, 0, 0
    a = np.array(trades)
    pnl = a.sum()
    eq = np.cumsum(a); pk = np.maximum.accumulate(eq)
    dd = (pk-eq).max()
    rf = pnl/dd if dd>0 else 0
    return pnl, dd, rf

def main():
    start = datetime.now()
    data = load()
    wc = data['win'].values.astype(float); dc = data['wdo'].values.astype(float)
    print("  Calculando V1 OLS e V2 Kalman...")
    b1, z1, r1 = calc_v1(wc, dc)
    b2, z2, r2 = calc_v2(wc, dc)
    
    print("\nSimulando Otimizacao Fina de SL/TP WDO ...")
    
    rf_buy = np.zeros((len(SL_RANGE), len(TP_RANGE)))
    rf_sell = np.zeros((len(SL_RANGE), len(TP_RANGE)))
    
    # Grid de BUY (V2)
    for i, sl in enumerate(SL_RANGE):
        for j, tp in enumerate(TP_RANGE):
            trd = run_wdo(data, z2, r2, b2, BUY_ZMIN, 'buy', sl, tp)
            p, d, r = calc_rf(trd)
            rf_buy[i, j] = r if p>0 else 0
            
    # Grid de SELL (V1)
    for i, sl in enumerate(SL_RANGE):
        for j, tp in enumerate(TP_RANGE):
            trd = run_wdo(data, z1, r1, b1, SELL_ZMIN, 'sell', sl, tp)
            p, d, r = calc_rf(trd)
            rf_sell[i, j] = r if p>0 else 0
            
    # Graficos
    fig, axes = plt.subplots(1, 2, figsize=(20, 8))
    fig.patch.set_facecolor('#0a0e17')
    for ax in axes: ax.set_facecolor('#0a0e17')
    
    def draw_heatmap(ax, matrix, title):
        im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(np.arange(len(TP_RANGE)))
        ax.set_yticks(np.arange(len(SL_RANGE)))
        ax.set_xticklabels(TP_RANGE)
        ax.set_yticklabels(SL_RANGE)
        ax.set_title(title, color='white', fontsize=14)
        ax.set_xlabel("Take Profit (Pts WDO)", color='white')
        ax.set_ylabel("Stop Loss (Pts WDO)", color='white')
        ax.tick_params(colors='white')
        for i in range(len(SL_RANGE)):
            for j in range(len(TP_RANGE)):
                val = matrix[i, j]
                color = 'white' if abs(val - np.mean(matrix[matrix>0])) > np.std(matrix[matrix>0]) else 'black'
                if val > 0: ax.text(j, i, f"{val:.1f}", ha='center', va='center', color=color, fontweight='bold')
    
    draw_heatmap(axes[0], rf_buy, f"V2 Kalman WDO BUY (Z=<-{BUY_ZMIN}) - RF")
    draw_heatmap(axes[1], rf_sell, f"V1 OLS WDO SELL (Z=>{SELL_ZMIN}) - RF")
    
    plt.tight_layout()
    plt.savefig('wdo_sltp_heatmap.png', dpi=150, facecolor='#0a0e17')
    print(f"\n[OK] wdo_sltp_heatmap.png salvo")
    print(f"[OK] Demorou {(datetime.now() - start).total_seconds():.0f}s")
    
if __name__ == '__main__':
    main()
