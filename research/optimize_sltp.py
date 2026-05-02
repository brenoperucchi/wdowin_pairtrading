"""
Otimizacao SL x TP — Heatmap de Recovery Factor
Z fixos: BUY z=2.0 (Kalman) + SELL z=2.1 (OLS)
SL: 200-600 step 50 | TP: 300-1500 step 100
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

SL_RANGE = list(range(200, 650, 50))   # 200,250,...,600
TP_RANGE = list(range(300, 1600, 100)) # 300,400,...,1500


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
    """Retorna lista de PnLs"""
    n=len(zs); ts=data.index; wh=data['wh'].values; wl=data['wl'].values; wc=data['win'].values
    pos=None; pnls=[]
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            if direction=='buy':
                if wh[i]>=pos+tp_pts: reason='TP'; ep=pos+tp_pts
                elif wl[i]<=pos-sl_pts: reason='SL'; ep=pos-sl_pts
            else:
                if wl[i]<=pos-tp_pts: reason='TP'; ep=pos-tp_pts
                elif wh[i]>=pos+sl_pts: reason='SL'; ep=pos+sl_pts
            if reason is None and t>=FC_TIME: reason='FC'; ep=wc[i]
            if reason:
                d=1 if direction=='buy' else -1
                pnls.append(d*(ep-pos)*CONTRACTS*PV)
                pos=None
        if pos is not None: continue
        if t<ENTRY_START or t>ENTRY_END: continue
        if not is_safe(bs,i,ra[i]): continue
        az=abs(z)
        if az<zmin or az>=zmax: continue
        if direction=='buy' and z<-zmin: pos=wc[i]
        elif direction=='sell' and z>zmin: pos=wc[i]
    return pnls


def calc_metrics(pnls):
    if not pnls or len(pnls)<5: return 0, 0, 0, 0, 0
    a = np.array(pnls)
    pnl = a.sum()
    eq = np.cumsum(a); pk = np.maximum.accumulate(eq)
    dd = (pk-eq).max()
    rf = pnl/dd if dd>0 else 0
    wr = np.sum(a>0)/len(a)*100
    gp = a[a>0].sum(); gl = abs(a[a<=0].sum())+.001
    return len(pnls), pnl, dd, rf, gp/gl


def main():
    start = datetime.now()
    print("Carregando...")
    data = load()
    wc = data['win'].values.astype(float); dc = data['wdo'].values.astype(float)
    print("  V1 OLS..."); b1,z1,r1 = calc_v1(wc,dc)
    print("  V2 Kalman..."); b2,z2,r2 = calc_v2(wc,dc)
    
    total = len(SL_RANGE) * len(TP_RANGE)
    print(f"\nGrid: SL {SL_RANGE[0]}-{SL_RANGE[-1]} x TP {TP_RANGE[0]}-{TP_RANGE[-1]} = {total} combos")
    
    # Matrizes para heatmaps
    rf_buy = np.zeros((len(SL_RANGE), len(TP_RANGE)))
    rf_sell = np.zeros((len(SL_RANGE), len(TP_RANGE)))
    rf_comb = np.zeros((len(SL_RANGE), len(TP_RANGE)))
    pnl_comb = np.zeros((len(SL_RANGE), len(TP_RANGE)))
    n_comb = np.zeros((len(SL_RANGE), len(TP_RANGE)))
    
    best = {'rf': -999}
    count = 0
    
    for si, sl in enumerate(SL_RANGE):
        for ti, tp in enumerate(TP_RANGE):
            count += 1
            # BUY (Kalman z=2.0)
            buy_pnls = sim(data, z2, r2, b2, BUY_ZMIN, BUY_ZMAX, 'buy', sl, tp)
            # SELL (OLS z=2.1)
            sell_pnls = sim(data, z1, r1, b1, SELL_ZMIN, SELL_ZMAX, 'sell', sl, tp)
            
            nb, pb, db, rfb, pfb = calc_metrics(buy_pnls)
            ns, ps, ds, rfs, pfs = calc_metrics(sell_pnls)
            
            # Combinado
            all_pnls = []
            # Merge by order (approximation: just concatenate)
            combined = buy_pnls + sell_pnls
            nc, pc, dc_m, rfc, pfc = calc_metrics(combined)
            
            rf_buy[si, ti] = rfb
            rf_sell[si, ti] = rfs
            rf_comb[si, ti] = rfc
            pnl_comb[si, ti] = pc
            n_comb[si, ti] = nc
            
            if rfc > best['rf'] and pc > 0:
                best = {'sl': sl, 'tp': tp, 'n': nc, 'pnl': pc, 'dd': dc_m, 'rf': rfc, 'pf': pfc,
                        'nb': nb, 'pb': pb, 'rfb': rfb, 'ns': ns, 'ps': ps, 'rfs': rfs}
        
        pct = count / total * 100
        print(f"  SL={sl} done ({pct:.0f}%)")
    
    # Print best
    b = best
    print(f"\n{'='*70}")
    print(f"  MELHOR COMBINACAO (max RF)")
    print(f"{'='*70}")
    print(f"  SL={b['sl']} | TP={b['tp']}")
    print(f"  BUY:  {b['nb']} trades, PnL=R${b['pb']:.0f}, RF={b['rfb']:.2f}")
    print(f"  SELL: {b['ns']} trades, PnL=R${b['ps']:.0f}, RF={b['rfs']:.2f}")
    print(f"  TOTAL: {b['n']} trades, PnL=R${b['pnl']:.0f}, RF={b['rf']:.2f}, PF={b['pf']:.2f}, DD=R${b['dd']:.0f}")
    
    # Print top 10
    print(f"\n  TOP 10 por RF (combinado):")
    flat = []
    for si, sl in enumerate(SL_RANGE):
        for ti, tp in enumerate(TP_RANGE):
            if pnl_comb[si,ti] > 0:
                flat.append((rf_comb[si,ti], sl, tp, pnl_comb[si,ti], n_comb[si,ti]))
    flat.sort(reverse=True)
    print(f"  {'SL':>5} {'TP':>5} {'trades':>7} {'PnL':>8} {'RF':>6}")
    for rf_v, sl, tp, pnl, n in flat[:10]:
        print(f"  {sl:>5} {tp:>5} {n:>7.0f} {pnl:>8.0f} {rf_v:>6.2f}")
    
    # ═══ HEATMAP ═══
    fig, axes = plt.subplots(1, 3, figsize=(22, 8))
    fig.suptitle('Otimizacao SL x TP — Recovery Factor\n'
                 'V2 Kalman BUY z=2.0 + V1 OLS SELL z=2.1 | WIN 2 contratos',
                 fontsize=14, fontweight='bold')
    
    titles = ['V2 Kalman BUY', 'V1 OLS SELL', 'COMBINADO']
    matrices = [rf_buy, rf_sell, rf_comb]
    
    for ax, title, matrix in zip(axes, titles, matrices):
        # Clip for visual
        vmin = -1; vmax = max(4, matrix.max())
        im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn', vmin=vmin, vmax=vmax,
                       origin='lower', interpolation='nearest')
        
        ax.set_xticks(range(len(TP_RANGE)))
        ax.set_xticklabels(TP_RANGE, rotation=45, fontsize=8)
        ax.set_yticks(range(len(SL_RANGE)))
        ax.set_yticklabels(SL_RANGE, fontsize=9)
        ax.set_xlabel('TP (pontos)', fontsize=11)
        ax.set_ylabel('SL (pontos)', fontsize=11)
        ax.set_title(title, fontsize=13, fontweight='bold')
        
        # Anotar valores
        for si in range(len(SL_RANGE)):
            for ti in range(len(TP_RANGE)):
                v = matrix[si, ti]
                color = 'white' if abs(v) > 2 else 'black'
                ax.text(ti, si, f'{v:.1f}', ha='center', va='center', fontsize=7, color=color)
        
        plt.colorbar(im, ax=ax, label='RF', shrink=0.8)
        
        # Marcar melhor
        if title == 'COMBINADO':
            bi = SL_RANGE.index(best['sl'])
            bj = TP_RANGE.index(best['tp'])
            ax.plot(bj, bi, 'r*', markersize=20, markeredgecolor='white', markeredgewidth=1.5)
    
    plt.tight_layout()
    plt.savefig('sl_tp_heatmap.png', dpi=150, bbox_inches='tight')
    print(f"\n[OK] sl_tp_heatmap.png salvo")
    print(f"[OK] {(datetime.now()-start).total_seconds():.0f}s")


if __name__ == '__main__':
    main()
