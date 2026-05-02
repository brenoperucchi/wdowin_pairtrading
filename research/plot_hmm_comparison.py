import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter
import os

# ─── CONFIG ──────────────────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40; BETA_INITIAL = -22.5; RHO_MIN = -0.40
BETA_REF_WINDOW = 80; BETA_DELTA_MAX = 25.0
ENTRY_START = time(10, 0); ENTRY_END = time(16, 0); FC_TIME = time(17, 40)
CONTRACTS = 2; PV = 0.20 

# Otimization Parâmetros de Trava/Alvo da Sessão Anterior
BUY_SL = 350; BUY_TP = 500; BUY_BE_ACT = 400; BUY_BE_LOCK = 50
SELL_SL = 300; SELL_TP = 1400; SELL_BE_ACT = 800; SELL_BE_LOCK = 200

Z_TEST = 1.80

def load_data():
    cols = ['date','time','open','high','low','close','tickvol','vol','spread']
    wdo = pd.read_csv(WDO_CSV, sep='\t', names=cols, skiprows=1)
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    wdo['dt'] = pd.to_datetime(wdo['date']+' '+wdo['time'], format='%Y.%m.%d %H:%M:%S')
    win['dt'] = pd.to_datetime(win['date']+' '+win['time'], format='%Y.%m.%d %H:%M:%S')
    wdo.set_index('dt', inplace=True); win.set_index('dt', inplace=True)
    agg = {'open':'first','high':'max','low':'min','close':'last'}
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

def run_simulation():
    data = load_data()
    wc = data['win'].values.astype(float); dc = data['wdo'].values.astype(float)
    
    print("Recalculando V1 e V2 com Z=1.8 ...")
    b1, z1, r1 = calc_v1(wc, dc)
    b2, z2, r2 = calc_v2(wc, dc)
    data['z_buy'] = z2; data['b_buy'] = b2; data['r_buy'] = r2
    data['z_sell'] = z1; data['b_sell'] = b1; data['r_sell'] = r1
    
    print("Regimes mapping...")
    regimes = pd.read_csv("win_m30_regimes.csv")
    regimes['dt'] = pd.to_datetime(regimes['dt'])
    regime_map = dict(zip(regimes['dt'], regimes['regime_name']))
    data['regime_dt'] = data.index.floor('30min')
    data['regime_name'] = data['regime_dt'].map(regime_map)
    data.dropna(subset=['regime_name'], inplace=True)
    
    ts = data.index
    wh = data['wh'].values; wl = data['wl'].values; wc = data['win'].values
    z_b = data['z_buy'].values; r_b = data['r_buy'].values; b_b = data['b_buy'].values
    z_s = data['z_sell'].values; r_s = data['r_sell'].values; b_s = data['b_sell'].values
    reg_names = data['regime_name'].values
    n = len(wc)
    
    def simulate_curve(use_filter):
        pos_buy = None
        pos_sell = None
        
        dates_out = []
        eq_out = []
        cum_pnl = 0
        eq_out.append(0)
        dates_out.append(ts[WINDOW])
        
        for i in range(WINDOW, n):
            t = ts[i].time()
            z_b_val = z_b[i]; z_s_val = z_s[i]
            regime = reg_names[i]
            trade_closed = False
            
            # Update pos_buy
            if pos_buy is not None:
                reason = None; ep = 0
                was_be = pos_buy['be']
                
                if not pos_buy['be'] and wh[i] >= pos_buy['px'] + BUY_BE_ACT:
                    pos_buy['be'] = True; pos_buy['sl_level'] = pos_buy['px'] + BUY_BE_LOCK
                    
                if wh[i] >= pos_buy['px'] + BUY_TP: reason='TP'; ep = pos_buy['px'] + BUY_TP
                elif was_be and wl[i] <= pos_buy['sl_level']: reason='SL/BE'; ep = pos_buy['sl_level']
                elif not was_be and wl[i] <= pos_buy['px'] - BUY_SL: reason='SL'; ep = pos_buy['px'] - BUY_SL
                
                if reason is None and t>=FC_TIME: reason='FC'; ep=wc[i]
                
                if reason:
                    pnl = (ep - pos_buy['px']) * CONTRACTS * PV
                    cum_pnl += pnl
                    trade_closed = True
                    pos_buy = None
            
            # Update pos_sell
            if pos_sell is not None:
                reason = None; ep = 0
                was_be = pos_sell['be']
                
                if not pos_sell['be'] and wl[i] <= pos_sell['px'] - SELL_BE_ACT:
                    pos_sell['be'] = True; pos_sell['sl_level'] = pos_sell['px'] - SELL_BE_LOCK
                    
                if wl[i] <= pos_sell['px'] - SELL_TP: reason='TP'; ep = pos_sell['px'] - SELL_TP
                elif was_be and wh[i] >= pos_sell['sl_level']: reason='SL/BE'; ep = pos_sell['sl_level']
                elif not was_be and wh[i] >= pos_sell['px'] + SELL_SL: reason='SL'; ep = pos_sell['px'] + SELL_SL
                
                if reason is None and t>=FC_TIME: reason='FC'; ep=wc[i]
                
                if reason:
                    pnl = -1 * (ep - pos_sell['px']) * CONTRACTS * PV
                    cum_pnl += pnl
                    trade_closed = True
                    pos_sell = None
            
            # Append curve only on closes to save memory, or maybe just end of loop
            if trade_closed:
                dates_out.append(ts[i])
                eq_out.append(cum_pnl)
            
            # Check Entries
            if t >= ENTRY_START and t <= ENTRY_END:
                # Filter Logic (Estatístico = Cortar em todo BULL)
                buy_blocked = use_filter and (regime == 'BULL')
                sell_blocked = use_filter and (regime == 'BULL')
                
                if pos_buy is None and not buy_blocked:
                    if is_safe(b_b, i, r_b[i]) and z_b_val <= -Z_TEST:
                        pos_buy = {'px': wc[i], 'sl_level': wc[i] - BUY_SL, 'be': False}
                        
                if pos_sell is None and not sell_blocked:
                    if is_safe(b_s, i, r_s[i]) and z_s_val >= Z_TEST:
                        pos_sell = {'px': wc[i], 'sl_level': wc[i] + SELL_SL, 'be': False}
        
        # Closing point
        dates_out.append(ts[n-1])
        eq_out.append(cum_pnl)
        
        eq_arr = np.array(eq_out)
        pk = np.maximum.accumulate(eq_arr)
        dd = (pk - eq_arr).max()
        
        return dates_out, eq_out, cum_pnl, dd

    print("Simulando Baseline (Sem Filtro) Z=1.8 ...")
    d1, eq1, p1, dd1 = simulate_curve(use_filter=False)
    rf1 = p1/dd1 if dd1 > 0 else 0
    
    print("Simulando Filtrado HMM (Bloqueia BULL) Z=1.8 ...")
    d2, eq2, p2, dd2 = simulate_curve(use_filter=True)
    rf2 = p2/dd2 if dd2 > 0 else 0

    print("Plotando gráfico iterativo...")
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(d1, eq1, color='#ff3860', alpha=0.8, linewidth=1.5, label=f"Baseline Z={Z_TEST} Cego (MaxDD R${dd1:,.0f} | PnL R${p1:,.0f} | RF {rf1:.2f})")
    ax.plot(d2, eq2, color='#00e87a', linewidth=2.5, label=f"HMM Filtrado Z={Z_TEST} S/BULL (MaxDD R${dd2:,.0f} | PnL R${p2:,.0f} | RF {rf2:.2f})")
    
    ax.set_title("Comparativo Curva de Capital (Agressividade Z=1.80) — Cego vs. HMM Filtrado M30", fontsize=15, fontweight='bold', pad=20)
    ax.set_ylabel("PnL (R$)", fontsize=12)
    ax.grid(color='#333333', linestyle='--', linewidth=0.5)
    ax.legend(loc="upper left", fontsize=11, facecolor='black')
    
    ax.fill_between(d1, eq1, color='#ff3860', alpha=0.05)
    ax.fill_between(d2, eq2, color='#00e87a', alpha=0.1)
    
    save_path = "C:/Users/ryzen/.gemini/antigravity/brain/ef5aebe9-595c-4cef-ba9a-979de966c203/hmm_comparison.png"
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    print(f"Gráfico salvo em: {save_path}")

if __name__ == '__main__':
    run_simulation()
