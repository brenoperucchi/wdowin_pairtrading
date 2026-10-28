"""
Equity Curve: V2 Kalman BUY z=2.0 + V1 OLS SELL z=2.1
WIN SL=560 TP=600 | 2 contratos
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# Config
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40; BETA_INITIAL = -22.5; RHO_MIN = -0.40
BETA_REF_WINDOW = 80; BETA_DELTA_MAX = 25.0
SL = 560.0; TP = 600.0; CONTRACTS = 2; PV = 0.20
ENTRY_START = time(9, 15); ENTRY_END = time(16, 0); FC_TIME = time(17, 40)

# Params otimizados
BUY_ZMIN = 2.0; BUY_ZMAX = 3.0   # V2 Kalman
SELL_ZMIN = 2.1; SELL_ZMAX = 3.0  # V1 OLS

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

def simulate(data, zs, ra, bs, zmin, zmax, direction):
    n=len(zs); ts=data.index; wh=data['wh'].values; wl=data['wl'].values; wc=data['win'].values
    pos=None; trades=[]
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            if direction=='buy':
                if wh[i]>=pos['px']+TP: reason='TP'; ep=pos['px']+TP
                elif wl[i]<=pos['px']-SL: reason='SL'; ep=pos['px']-SL
            else:
                if wl[i]<=pos['px']-TP: reason='TP'; ep=pos['px']-TP
                elif wh[i]>=pos['px']+SL: reason='SL'; ep=pos['px']+SL
            if reason is None and t>=FC_TIME: reason='FC'; ep=wc[i]
            if reason:
                d=1 if direction=='buy' else -1
                pnl=d*(ep-pos['px'])*CONTRACTS*PV
                trades.append({'time': ts[i], 'pnl': pnl, 'reason': reason, 'leg': direction})
                pos=None
        if pos is not None: continue
        if t<ENTRY_START or t>ENTRY_END: continue
        if not is_safe(bs,i,ra[i]): continue
        az=abs(z)
        if az<zmin or az>=zmax: continue
        if direction=='buy' and z<-zmin: pos={'px':wc[i]}
        elif direction=='sell' and z>zmin: pos={'px':wc[i]}
    return trades

def main():
    print("Carregando...")
    data=load()
    wc=data['win'].values.astype(float); dc=data['wdo'].values.astype(float)
    print("  V1 OLS..."); b1,z1,r1=calc_v1(wc,dc)
    print("  V2 Kalman..."); b2,z2,r2=calc_v2(wc,dc)
    
    print("Simulando...")
    buy_trades = simulate(data, z2, r2, b2, BUY_ZMIN, BUY_ZMAX, 'buy')
    sell_trades = simulate(data, z1, r1, b1, SELL_ZMIN, SELL_ZMAX, 'sell')
    
    # Combinar e ordenar por tempo
    all_trades = buy_trades + sell_trades
    all_trades.sort(key=lambda x: x['time'])
    
    # Equity curves
    buy_times = [t['time'] for t in buy_trades]
    buy_eq = np.cumsum([t['pnl'] for t in buy_trades])
    sell_times = [t['time'] for t in sell_trades]
    sell_eq = np.cumsum([t['pnl'] for t in sell_trades])
    all_times = [t['time'] for t in all_trades]
    all_eq = np.cumsum([t['pnl'] for t in all_trades])
    
    # Stats
    buy_pnl = sum(t['pnl'] for t in buy_trades)
    sell_pnl = sum(t['pnl'] for t in sell_trades)
    total_pnl = sum(t['pnl'] for t in all_trades)
    
    # Drawdown da curva combinada
    peak = np.maximum.accumulate(all_eq)
    dd = peak - all_eq
    max_dd = dd.max()
    rf = total_pnl / max_dd if max_dd > 0 else 0
    
    # Win rate
    wins = sum(1 for t in all_trades if t['pnl'] > 0)
    wr = wins / len(all_trades) * 100
    
    # PnL por ano
    yearly = {}
    for t in all_trades:
        y = t['time'].year
        if y not in yearly: yearly[y] = 0
        yearly[y] += t['pnl']
    
    # Imprimir resultados
    print(f"\n{'='*60}")
    print(f"  BUY z=2.0 (Kalman) + SELL z=2.1 (OLS)")
    print(f"  WIN | SL=560 TP=600 | 2 contratos")
    print(f"{'='*60}")
    print(f"  BUY:     {len(buy_trades)} trades | PnL=R${buy_pnl:.0f}")
    print(f"  SELL:    {len(sell_trades)} trades | PnL=R${sell_pnl:.0f}")
    print(f"  TOTAL:   {len(all_trades)} trades | PnL=R${total_pnl:.0f}")
    print(f"  WR:      {wr:.1f}%")
    print(f"  MaxDD:   R${max_dd:.0f}")
    print(f"  RF:      {rf:.2f}")
    print(f"\n  PnL por ano:")
    for y in sorted(yearly.keys()):
        print(f"    {y}: R${yearly[y]:>8,.0f}")
    
    # ═══ GRAFICO ═══
    fig, axes = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#0a0e17')
    
    # --- Equity Curve ---
    ax = axes[0]
    ax.set_facecolor('#0a0e17')
    
    # Curvas individuais
    ax.plot(buy_times, buy_eq, color='#00e87a', alpha=0.4, linewidth=1, label=f'Kalman BUY z=2.0 (R${buy_pnl:,.0f})')
    ax.plot(sell_times, sell_eq, color='#ff5252', alpha=0.4, linewidth=1, label=f'OLS SELL z=2.1 (R${sell_pnl:,.0f})')
    
    # Curva combinada
    ax.fill_between(all_times, 0, all_eq, alpha=0.15, color='#00bfff')
    ax.plot(all_times, all_eq, color='#00bfff', linewidth=2.5, label=f'COMBINADO (R${total_pnl:,.0f})')
    
    # Drawdown shading
    ax.fill_between(all_times, all_eq, peak, alpha=0.2, color='#ff5252')
    
    # Linhas anuais
    for y in range(2022, 2027):
        ax.axvline(x=pd.Timestamp(f'{y}-01-01'), color='gray', alpha=0.3, linestyle='--')
    
    ax.axhline(y=0, color='gray', alpha=0.5, linestyle='-')
    ax.set_title(f'Equity Curve — V2 Kalman BUY (z=2.0) + V1 OLS SELL (z=2.1)\n'
                 f'WIN SL=560 TP=600 | {len(all_trades)} trades | RF={rf:.2f} | MaxDD=R${max_dd:,.0f}',
                 fontsize=14, fontweight='bold', color='white', pad=15)
    ax.set_ylabel('Capital Acumulado (R$)', fontsize=12, color='white')
    ax.legend(fontsize=11, loc='upper left', facecolor='#1a1f2e', edgecolor='#333', labelcolor='white')
    ax.tick_params(colors='white')
    ax.grid(True, alpha=0.15, color='white')
    ax.spines['bottom'].set_color('#333'); ax.spines['left'].set_color('#333')
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    
    # --- PnL por ano (barras) ---
    ax2 = axes[1]
    ax2.set_facecolor('#0a0e17')
    years = sorted(yearly.keys())
    vals = [yearly[y] for y in years]
    colors = ['#00e87a' if v > 0 else '#ff5252' for v in vals]
    bars = ax2.bar(years, vals, color=colors, alpha=0.8, edgecolor='white', linewidth=0.5)
    
    for bar, v in zip(bars, vals):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 100,
                 f'R${v:,.0f}', ha='center', va='bottom', fontsize=10, 
                 fontweight='bold', color='white')
    
    ax2.axhline(y=0, color='gray', alpha=0.5)
    ax2.set_title('PnL por Ano', fontsize=12, fontweight='bold', color='white')
    ax2.set_ylabel('R$', fontsize=11, color='white')
    ax2.tick_params(colors='white')
    ax2.grid(True, alpha=0.15, color='white', axis='y')
    ax2.spines['bottom'].set_color('#333'); ax2.spines['left'].set_color('#333')
    ax2.spines['top'].set_visible(False); ax2.spines['right'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig('equity_curve.png', dpi=150, bbox_inches='tight', facecolor='#0a0e17')
    print(f"\n[OK] equity_curve.png salvo")
    print(f"[OK] {(datetime.now()-datetime.now()).total_seconds():.0f}s")

if __name__ == '__main__':
    main()
