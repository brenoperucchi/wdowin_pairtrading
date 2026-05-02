"""
Otimização para WDO (Dólar Mini)
Fase 1: Otimiza Z-Score para BUY (V2) e SELL (V1)
Horário: 10:00 às 16:00
Baseline WDO: SL = 15 pts, TP = 15 pts | 1 contrato, PV=10
"""

import numpy as np
import pandas as pd
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# ─── CONFIG ──────────────────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40; BETA_INITIAL = -22.5; RHO_MIN = -0.40
BETA_REF_WINDOW = 80; BETA_DELTA_MAX = 25.0

# Horario Novo Otimizado!
ENTRY_START = time(10, 0); ENTRY_END = time(16, 0); FC_TIME = time(17, 40)

# Configuracoes do Ativo WDO
CONTRACTS = 1; PV = 10.00 
SL_PTS = 15.0  # Baseline inicial (15 pontos ~ R$150/ctto)
TP_PTS = 15.0

Z_MIN_RANGE = np.arange(1.5, 3.51, 0.25)
Z_MAX_RANGE = np.arange(3.0, 6.5, 0.5)

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

def run_wdo(data, zs, ra, bs, zmin, zmax, direction):
    # ATENÇÃO: Spread = WIN - beta * WDO. Como beta é negativo (~ -22), Spread sobe se WIN ou WDO sobem muito.
    # Spread baixo (Z < -ZMIN): WIN baixo, WDO baixo. Compramos ambos (BUY WDO).
    # Spread alto (Z > ZMIN): WIN alto, WDO alto. Vendemos ambos (SELL WDO).
    n = len(zs); ts=data.index; wh=data['wh'].values; wl=data['wl'].values; wc=data['wdo'].values
    pos=None; trades=[]
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            if direction=='buy':
                if wh[i] >= pos['px'] + TP_PTS: reason='TP'; ep = pos['px'] + TP_PTS
                elif wl[i] <= pos['px'] - SL_PTS: reason='SL'; ep = pos['px'] - SL_PTS
            else:
                if wl[i] <= pos['px'] - TP_PTS: reason='TP'; ep = pos['px'] - TP_PTS
                elif wh[i] >= pos['px'] + SL_PTS: reason='SL'; ep = pos['px'] + SL_PTS
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
        if az<zmin or az>=zmax: continue
        if direction=='buy' and z<-zmin: pos={'px':wc[i]}
        elif direction=='sell' and z>zmin: pos={'px':wc[i]}
    return trades

def calc_rf(trades):
    if not trades or len(trades)<5: return 0, 0, 0, 0, 0
    a = np.array(trades)
    pnl = a.sum()
    eq = np.cumsum(a); pk = np.maximum.accumulate(eq)
    dd = (pk-eq).max()
    rf = pnl/dd if dd>0 else 0
    wr = np.sum(a>0)/len(a)*100
    gp = a[a>0].sum(); gl = abs(a[a<=0].sum())+.001
    return len(trades), pnl, dd, rf, gp/gl

def main():
    start = datetime.now()
    data = load()
    wc = data['win'].values.astype(float); dc = data['wdo'].values.astype(float)
    print("  Calculando V1 OLS e V2 Kalman...")
    b1, z1, r1 = calc_v1(wc, dc)
    b2, z2, r2 = calc_v2(wc, dc)
    
    # BUY Kalman WDO
    print(f"\n--- V2 KALMAN WDO BUY (Z < -x) | SL={SL_PTS} TP={TP_PTS} ---")
    print(f"{'z_min':>5} {'z_max':>5} | {'Trades':>6} {'WR':>4} {'PnL (R$)':>9} {'MaxDD':>9} {'RF':>6} {'PF':>5}")
    best_buy = {'rf': -999}
    for zmin in Z_MIN_RANGE:
        for zmax in Z_MAX_RANGE:
            if zmax <= zmin: continue
            trades = run_wdo(data, z2, r2, b2, zmin, zmax, 'buy')
            n, pnl, dd, rf, pf = calc_rf(trades)
            if rf > best_buy['rf'] and pnl > 0:
                best_buy = {'zmin': zmin, 'zmax': zmax, 'n': n, 'wr': (sum(x>0 for x in trades)/n*100 if n>0 else 0), 'pnl': pnl, 'dd': dd, 'rf': rf, 'pf': pf}
    
    print(f"{best_buy['zmin']:>5.2f} {best_buy['zmax']:>5.2f} | {best_buy['n']:>6} {best_buy['wr']:>3.0f}% {best_buy['pnl']:>9.0f} {best_buy['dd']:>9.0f} {best_buy['rf']:>6.2f} {best_buy['pf']:>5.2f}")
    
    # SELL OLS WDO
    print(f"\n--- V1 OLS WDO SELL (Z > +x) | SL={SL_PTS} TP={TP_PTS} ---")
    print(f"{'z_min':>5} {'z_max':>5} | {'Trades':>6} {'WR':>4} {'PnL (R$)':>9} {'MaxDD':>9} {'RF':>6} {'PF':>5}")
    best_sell = {'rf': -999}
    for zmin in Z_MIN_RANGE:
        for zmax in Z_MAX_RANGE:
            if zmax <= zmin: continue
            trades = run_wdo(data, z1, r1, b1, zmin, zmax, 'sell')
            n, pnl, dd, rf, pf = calc_rf(trades)
            if rf > best_sell['rf'] and pnl > 0:
                best_sell = {'zmin': zmin, 'zmax': zmax, 'n': n, 'wr': (sum(x>0 for x in trades)/n*100 if n>0 else 0), 'pnl': pnl, 'dd': dd, 'rf': rf, 'pf': pf}
    
    print(f"{best_sell['zmin']:>5.2f} {best_sell['zmax']:>5.2f} | {best_sell['n']:>6} {best_sell['wr']:>3.0f}% {best_sell['pnl']:>9.0f} {best_sell['dd']:>9.0f} {best_sell['rf']:>6.2f} {best_sell['pf']:>5.2f}")
    
    print(f"\n[OK] Demorou {(datetime.now() - start).total_seconds():.0f}s")
    print("Agora crie o script de heatmaps para WDO se o baseline acima for positivo =)")

if __name__ == '__main__':
    main()
