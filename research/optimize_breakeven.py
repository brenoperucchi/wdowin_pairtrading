"""
Otimizacao de BE/Trailing Stop para WIN
Janela: 10h as 16h
V2 Kalman BUY (SL=350, TP=500)
V1 OLS SELL (SL=300, TP=1400)
Testa diferentes niveis de ativacao e trava do Breakeven.
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
CONTRACTS = 2; PV = 0.20 

BUY_ZMIN = 2.0; BUY_ZMAX = 3.0; BUY_SL = 350; BUY_TP = 500
SELL_ZMIN = 2.1; SELL_ZMAX = 3.0; SELL_SL = 300; SELL_TP = 1400

# Parametros para o Grid de Breakeven
BUY_BE_ACT_RANGE = [200, 250, 300, 350, 400, 450, 500]
SELL_BE_ACT_RANGE = [200, 400, 600, 800, 1000, 1200, 1400]
BE_LOCK_RANGE = [0, 50, 100, 150, 200]

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

def run_leg_be(data, zs, ra, bs, zmin, zmax, direction, sl_pts, tp_pts, be_act, be_lock):
    n=len(zs); ts=data.index; wh=data['wh'].values; wl=data['wl'].values; wc=data['win'].values
    wo=data['wo'].values
    pos=None; trades=[]
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            was_be = pos['be'] # Registra se o BE já estava ativo no começo dessa barra
            
            # Atualiza BE Max
            if direction == 'buy':
                if not pos['be'] and wh[i] >= pos['px'] + be_act:
                    pos['be'] = True
                    pos['sl_level'] = pos['px'] + be_lock
            else:
                if not pos['be'] and wl[i] <= pos['px'] - be_act:
                    pos['be'] = True
                    pos['sl_level'] = pos['px'] - be_lock
                    
            # Verifica Saídas da Barra
            if direction=='buy':
                if wh[i] >= pos['px'] + tp_pts: reason='TP'; ep = pos['px'] + tp_pts
                # Se BE já estava ativo na barra anterior, ou se o SL basico foi hit (nós priorizamos sair se dropou)
                elif was_be and wl[i] <= pos['sl_level']: reason='SL/BE'; ep = pos['sl_level']
                elif not was_be and wl[i] <= pos['px'] - sl_pts: reason='SL'; ep = pos['px'] - sl_pts
            else:
                if wl[i] <= pos['px'] - tp_pts: reason='TP'; ep = pos['px'] - tp_pts
                elif was_be and wh[i] >= pos['sl_level']: reason='SL/BE'; ep = pos['sl_level']
                elif not was_be and wh[i] >= pos['px'] + sl_pts: reason='SL'; ep = pos['px'] + sl_pts
                
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
        
        if direction=='buy' and z<-zmin: 
            pos={'px':wc[i], 'sl_level': wc[i] - sl_pts, 'be': False}
        elif direction=='sell' and z>zmin: 
            pos={'px':wc[i], 'sl_level': wc[i] + sl_pts, 'be': False}
            
    return trades

def calc_rf(trades):
    if not trades or len(trades)<5: return 0, 0, 0, 0, 0
    a = np.array(trades)
    pnl = a.sum()
    eq = np.cumsum(a); pk = np.maximum.accumulate(eq)
    dd = (pk-eq).max()
    rf = pnl/dd if dd>0 else 0
    return len(trades), pnl, dd, rf, (a[a>0].sum() / (abs(a[a<=0].sum())+.001))

def main():
    start = datetime.now()
    data = load()
    wc = data['win'].values.astype(float); dc = data['wdo'].values.astype(float)
    print("  Calculando V1 OLS e V2 Kalman...")
    b1, z1, r1 = calc_v1(wc, dc)
    b2, z2, r2 = calc_v2(wc, dc)
    
    print("\n" + "="*70)
    print(" BASELINE (Sem Breakeven)")
    trd_buy_base = run_leg_be(data, z2, r2, b2, BUY_ZMIN, BUY_ZMAX, 'buy', BUY_SL, BUY_TP, 9999, 0)
    trd_sell_base = run_leg_be(data, z1, r1, b1, SELL_ZMIN, SELL_ZMAX, 'sell', SELL_SL, SELL_TP, 9999, 0)
    nb, pb, db, rb, pfb = calc_rf(trd_buy_base)
    ns, ps, ds, rs, pfs = calc_rf(trd_sell_base)
    print(f" BUY  | Trades: {nb:>4} | PnL: R${pb:>6.0f} | MaxDD: R${db:>5.0f} | RF: {rb:.2f}")
    print(f" SELL | Trades: {ns:>4} | PnL: R${ps:>6.0f} | MaxDD: R${ds:>5.0f} | RF: {rs:.2f}")
    
    rf_buy = np.zeros((len(BUY_BE_ACT_RANGE), len(BE_LOCK_RANGE)))
    rf_sell = np.zeros((len(SELL_BE_ACT_RANGE), len(BE_LOCK_RANGE)))
    
    print("\n--- Otimização Breakeven BUY (Kalman) ---")
    best_buy = {'rf': rb, 'desc': 'Nenhum (Baseline)'}
    for i, act in enumerate(BUY_BE_ACT_RANGE):
        for j, lock in enumerate(BE_LOCK_RANGE):
            if lock >= act: continue
            trd = run_leg_be(data, z2, r2, b2, BUY_ZMIN, BUY_ZMAX, 'buy', BUY_SL, BUY_TP, act, lock)
            n, p, d, r, pf = calc_rf(trd)
            rf_buy[i, j] = r if p>0 else 0
            if r > best_buy['rf']:
                best_buy = {'rf': r, 'desc': f"Ativa em +{act} pts, Trava +{lock} pts"}
                
    print(f" > Melhor BE BUY: {best_buy['desc']} -> RF = {best_buy['rf']:.2f}")
    
    print("\n--- Otimização Breakeven SELL (OLS) ---")
    best_sell = {'rf': rs, 'desc': 'Nenhum (Baseline)'}
    for i, act in enumerate(SELL_BE_ACT_RANGE):
        for j, lock in enumerate(BE_LOCK_RANGE):
            if lock >= act: continue
            trd = run_leg_be(data, z1, r1, b1, SELL_ZMIN, SELL_ZMAX, 'sell', SELL_SL, SELL_TP, act, lock)
            n, p, d, r, pf = calc_rf(trd)
            rf_sell[i, j] = r if p>0 else 0
            if r > best_sell['rf']:
                best_sell = {'rf': r, 'desc': f"Ativa em +{act} pts, Trava +{lock} pts", 'pnl': p, 'dd': d}
                
    print(f" > Melhor BE SELL: {best_sell['desc']} -> RF = {best_sell['rf']:.2f} (PnL R${best_sell.get('pnl', ps):.0f} / DD R${best_sell.get('dd', ds):.0f})")

    # Heatmaps 
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    fig.patch.set_facecolor('#0a0e17')
    for ax in axes: ax.set_facecolor('#0a0e17')
    
    def draw_hm(ax, matrix, act_range, title):
        im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(np.arange(len(BE_LOCK_RANGE)))
        ax.set_yticks(np.arange(len(act_range)))
        ax.set_xticklabels(BE_LOCK_RANGE)
        ax.set_yticklabels(act_range)
        ax.set_title(title, color='white', fontsize=12)
        ax.set_xlabel("Trava (Lock em Pts)", color='white')
        ax.set_ylabel("Gatilho de Ativação (+Pts)", color='white')
        ax.tick_params(colors='white')
        for i in range(len(act_range)):
            for j in range(len(BE_LOCK_RANGE)):
                val = matrix[i, j]
                vls = matrix[matrix>0]
                color = 'white' if len(vls) > 0 and abs(val - np.mean(vls)) > np.std(vls) else 'black'
                if val > 0: ax.text(j, i, f"{val:.2f}", ha='center', va='center', color=color, fontweight='bold')
                
    draw_hm(axes[0], rf_buy, BUY_BE_ACT_RANGE, f"BUY BE RF vs Baseline ({rb:.2f})")
    draw_hm(axes[1], rf_sell, SELL_BE_ACT_RANGE, f"SELL BE RF vs Baseline ({rs:.2f})")
    
    plt.tight_layout()
    plt.savefig('be_heatmap.png', dpi=150, facecolor='#0a0e17')
    print(f"\n[OK] be_heatmap.png salvo")
    print(f"[OK] Demorou {(datetime.now() - start).total_seconds():.0f}s")
    
if __name__ == '__main__':
    main()
