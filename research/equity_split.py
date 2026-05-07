"""
RESEARCH EXPLORATÓRIO — NÃO USAR COMO VALIDAÇÃO DE PRODUÇÃO
============================================================
Este script diverge do motor live (core/config.py + core/trade_engine.py).
Ver docs/PARAM_PROFILE.md §2 (divergent hardcoded values).
Validação operacional: research/run_matador_v5_johansen.py (TASK-3 AC #15).

Equity Curve Split SL/TP
Simula o melhor cenario independente para BUY e SELL
BUY (Kalman z=2.0) e SELL (OLS z=2.1)
Otimiza SL e TP separadamente para cada perna e plota a equity curve combinada
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# Config
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40; BETA_INITIAL = -22.5; RHO_MIN = -0.40
BETA_REF_WINDOW = 80; BETA_DELTA_MAX = 25.0
CONTRACTS = 2; PV = 0.20
ENTRY_START = time(9, 15); ENTRY_END = time(16, 0); FC_TIME = time(17, 40)

BUY_ZMIN = 2.0; BUY_ZMAX = 3.0
SELL_ZMIN = 2.1; SELL_ZMAX = 3.0

SL_RANGE = list(range(200, 650, 50))
TP_RANGE = list(range(300, 1600, 100))


def load():
    cols = ['date','time','open','high','low','close','tickvol','vol','spread']
    wdo = pd.read_csv(WDO_CSV, sep='\t', names=cols, skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    wdo['dt'] = pd.to_datetime(wdo['date']+' '+wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date']+' '+win['time'], format='%Y.%m.%d %H:%M:%S')
    wdo.set_index('dt', inplace=True); win.set_index('dt', inplace=True)
    agg = {'open':'first','high':'max','low':'min','close':'last','vol':'sum'}
    wdo5=wdo.resample('5min').agg(agg).dropna()
    win5=win.resample('5min').agg(agg).dropna()
    return wdo5[['close']].rename(columns={'close':'wdo'}).join(
        win5.rename(columns={'open':'wo','high':'wh','low':'wl','close':'win'}), how='inner').dropna()

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

def sim(data, zs, ra, bs, zmin, zmax, direction, sl_pts, tp_pts):
    n=len(zs); ts=data.index; wh=data['wh'].values; wl=data['wl'].values; wc=data['win'].values
    pos=None; trades=[]
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            if direction=='buy':
                if wh[i]>=pos['px']+tp_pts: reason='TP'; ep=pos['px']+tp_pts
                elif wl[i]<=pos['px']-sl_pts: reason='SL'; ep=pos['px']-sl_pts
            else:
                if wl[i]<=pos['px']-tp_pts: reason='TP'; ep=pos['px']-tp_pts
                elif wh[i]>=pos['px']+sl_pts: reason='SL'; ep=pos['px']+sl_pts
            if reason is None and t>=FC_TIME: reason='FC'; ep=wc[i]
            if reason:
                d=1 if direction=='buy' else -1
                pnl=d*(ep-pos['px'])*CONTRACTS*PV
                trades.append({'time': ts[i], 'pnl': pnl})
                pos=None
        if pos is not None: continue
        if t<ENTRY_START or t>ENTRY_END: continue
        if not is_safe(bs,i,ra[i]): continue
        az=abs(z)
        if az<zmin or az>=zmax: continue
        if direction=='buy' and z<-zmin: pos={'px':wc[i]}
        elif direction=='sell' and z>zmin: pos={'px':wc[i]}
    return trades

def calc_metrics(trades):
    if not trades or len(trades)<5: return 0, 0, 0, 0, 0
    pnls = np.array([t['pnl'] for t in trades])
    pnl = pnls.sum()
    eq = np.cumsum(pnls); pk = np.maximum.accumulate(eq)
    dd = (pk-eq).max()
    rf = pnl/dd if dd>0 else 0
    wr = np.sum(pnls>0)/len(pnls)*100
    gp = pnls[pnls>0].sum(); gl = abs(pnls[pnls<=0].sum())+.001
    return len(trades), pnl, dd, rf, gp/gl


def main():
    start=datetime.now()
    data=load()
    wc=data['win'].values.astype(float); dc=data['wdo'].values.astype(float)
    b1,z1,r1 = calc_v1(wc,dc)
    b2,z2,r2 = calc_v2(wc,dc)
    
    # 1. Achar melhor SL/TP pra BUY
    print("Otimizando BUY...")
    best_buy = {'rf': -999}
    for sl in SL_RANGE:
        for tp in TP_RANGE:
            trd = sim(data, z2, r2, b2, BUY_ZMIN, BUY_ZMAX, 'buy', sl, tp)
            n, pnl, dd, rf, pf = calc_metrics(trd)
            if rf > best_buy['rf'] and pnl > 0:
                best_buy = {'sl': sl, 'tp': tp, 'trades': trd, 'n': n, 'pnl': pnl, 'dd': dd, 'rf': rf, 'pf': pf}
                
    # 2. Achar melhor SL/TP pra SELL
    print("Otimizando SELL...")
    best_sell = {'rf': -999}
    for sl in SL_RANGE:
        for tp in TP_RANGE:
            trd = sim(data, z1, r1, b1, SELL_ZMIN, SELL_ZMAX, 'sell', sl, tp)
            n, pnl, dd, rf, pf = calc_metrics(trd)
            if rf > best_sell['rf'] and pnl > 0:
                best_sell = {'sl': sl, 'tp': tp, 'trades': trd, 'n': n, 'pnl': pnl, 'dd': dd, 'rf': rf, 'pf': pf}

    print(f"\n--- MELHORES PARÂMETROS INDIVIDUAIS ---")
    print(f"  BUY  (Kalman): SL={best_buy['sl']}  TP={best_buy['tp']}  |  RF={best_buy['rf']:.2f}  |  PnL=R${best_buy['pnl']:.0f}")
    print(f"  SELL (OLS)   : SL={best_sell['sl']}  TP={best_sell['tp']}  |  RF={best_sell['rf']:.2f}  |  PnL=R${best_sell['pnl']:.0f}")
    
    # Combinar trades dos melhores cenarios
    all_trades = best_buy['trades'] + best_sell['trades']
    all_trades.sort(key=lambda x: x['time'])
    
    n_tot, pnl_tot, dd_tot, rf_tot, pf_tot = calc_metrics(all_trades)
    
    print(f"\n--- PERFORMANCE COMBINADA ---")
    print(f"  Trades: {n_tot}")
    print(f"  PnL   : R${pnl_tot:.0f}")
    print(f"  MaxDD : R${dd_tot:.0f}")
    print(f"  PF    : {pf_tot:.2f}")
    print(f"  RF    : {rf_tot:.2f} 👑")
    
    # PnL por ano
    yearly = {}
    for t in all_trades:
        y = t['time'].year
        if y not in yearly: yearly[y] = 0
        yearly[y] += t['pnl']
        
    print(f"\n  PnL por ano:")
    for y in sorted(yearly.keys()):
        print(f"    {y}: R${yearly[y]:>8,.0f}")
        
    # Grafico Equity
    all_times = [t['time'] for t in all_trades]
    all_eq = np.cumsum([t['pnl'] for t in all_trades])
    peak = np.maximum.accumulate(all_eq)
    
    fig, axes = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#0a0e17')
    
    # --- Equity Curve ---
    ax = axes[0]; ax.set_facecolor('#0a0e17')
    ax.fill_between(all_times, 0, all_eq, alpha=0.15, color='#00e87a')
    ax.plot(all_times, all_eq, color='#00e87a', linewidth=2.5, label=f'Combinado (R${pnl_tot:,.0f})')
    ax.fill_between(all_times, all_eq, peak, alpha=0.2, color='#ff5252')
    
    for y in range(2022, 2027): ax.axvline(x=pd.Timestamp(f'{y}-01-01'), color='gray', alpha=0.3, linestyle='--')
    ax.axhline(y=0, color='gray', alpha=0.5, linestyle='-')
    
    tit = (f'Equity Curve: V2 BUY (z=2.0 | SL={best_buy["sl"]} TP={best_buy["tp"]}) + '
           f'V1 SELL (z=2.1 | SL={best_sell["sl"]} TP={best_sell["tp"]})\n'
           f'{n_tot} trades | RF={rf_tot:.2f} | MaxDD=R${dd_tot:,.0f}')
    ax.set_title(tit, fontsize=14, fontweight='bold', color='white', pad=15)
    ax.set_ylabel('Capital Acumulado (R$)', fontsize=12, color='white')
    ax.tick_params(colors='white'); ax.grid(True, alpha=0.15, color='white')
    ax.spines['bottom'].set_color('#333'); ax.spines['left'].set_color('#333')
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    
    # --- PnL por ano ---
    ax2 = axes[1]; ax2.set_facecolor('#0a0e17')
    years = sorted(yearly.keys())
    vals = [yearly[y] for y in years]
    colors = ['#00e87a' if v > 0 else '#ff5252' for v in vals]
    bars = ax2.bar(years, vals, color=colors, alpha=0.8, edgecolor='white', linewidth=0.5)
    for bar, v in zip(bars, vals):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 100 if v>0 else bar.get_height() - 300,
                 f'R${v:,.0f}', ha='center', va='bottom' if v>0 else 'top', fontsize=10, fontweight='bold', color='white')
    
    ax2.axhline(y=0, color='gray', alpha=0.5)
    ax2.set_title('PnL por Ano', fontsize=12, fontweight='bold', color='white')
    ax2.set_ylabel('R$', fontsize=11, color='white')
    ax2.tick_params(colors='white'); ax2.grid(True, alpha=0.15, axis='y', color='white')
    ax2.spines['bottom'].set_color('#333'); ax2.spines['left'].set_color('#333')
    ax2.spines['top'].set_visible(False); ax2.spines['right'].set_visible(False)
    
    plt.tight_layout(); plt.savefig('equity_split.png', dpi=150, bbox_inches='tight', facecolor='#0a0e17')
    print(f"\n[OK] equity_split.png salvo")

if __name__ == '__main__':
    main()
