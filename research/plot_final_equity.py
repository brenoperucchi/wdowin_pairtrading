"""
RESEARCH EXPLORATÓRIO — NÃO USAR COMO VALIDAÇÃO DE PRODUÇÃO
============================================================
Este script diverge do motor live (core/config.py + core/trade_engine.py).
Ver docs/PARAM_PROFILE.md §2 (divergent hardcoded values).
Validação operacional: research/run_matador_v5_johansen.py (TASK-3 AC #15).

Otimizacao de BE/Trailing Stop para WIN
Gera o grafico de Patrimonio final.
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

BUY_ZMIN = 2.0; BUY_ZMAX = 4.0; BUY_SL = 350; BUY_TP = 500; BUY_BE_ACT = 400; BUY_BE_LOCK = 50
SELL_ZMIN = 2.1; SELL_ZMAX = 4.0; SELL_SL = 300; SELL_TP = 1400; SELL_BE_ACT = 800; SELL_BE_LOCK = 200

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
    
    dates_out = []
    
    for i in range(WINDOW,n):
        t=ts[i].time(); z=zs[i]
        if pos is not None:
            reason=None; ep=0
            was_be = pos['be']
            
            if direction == 'buy':
                if not pos['be'] and wh[i] >= pos['px'] + be_act:
                    pos['be'] = True; pos['sl_level'] = pos['px'] + be_lock
            else:
                if not pos['be'] and wl[i] <= pos['px'] - be_act:
                    pos['be'] = True; pos['sl_level'] = pos['px'] - be_lock
                    
            if direction=='buy':
                if wh[i] >= pos['px'] + tp_pts: reason='TP'; ep = pos['px'] + tp_pts
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
                dates_out.append(ts[i])
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
            
    return trades, dates_out

def main():
    start = datetime.now()
    data = load()
    wc = data['win'].values.astype(float); dc = data['wdo'].values.astype(float)
    print("  Calculando V1 OLS e V2 Kalman...")
    b1, z1, r1 = calc_v1(wc, dc)
    b2, z2, r2 = calc_v2(wc, dc)
    
    print("\nExecutando Setup Matador...")
    trd_buy, dts_buy = run_leg_be(data, z2, r2, b2, BUY_ZMIN, BUY_ZMAX, 'buy', BUY_SL, BUY_TP, BUY_BE_ACT, BUY_BE_LOCK)
    trd_sell, dts_sell = run_leg_be(data, z1, r1, b1, SELL_ZMIN, SELL_ZMAX, 'sell', SELL_SL, SELL_TP, SELL_BE_ACT, SELL_BE_LOCK)
    
    # Combined equity
    combined_trades = []
    for d, p in zip(dts_buy, trd_buy):
        combined_trades.append((d, 'BUY', p))
    for d, p in zip(dts_sell, trd_sell):
        combined_trades.append((d, 'SELL', p))
        
    combined_trades.sort(key=lambda x: x[0])
    
    dates_comb = [combined_trades[0][0]] if combined_trades else []
    eq_comb = [0]
    eq_buy = [0]
    eq_sell = [0]
    
    dts_b_plot = [combined_trades[0][0]] if combined_trades else []
    dts_s_plot = [combined_trades[0][0]] if combined_trades else []
    
    cum_b = 0
    cum_s = 0
    cum_c = 0
    for d, type_, pnl in combined_trades:
        cum_c += pnl
        eq_comb.append(cum_c)
        dates_comb.append(d)
        
        if type_ == 'BUY':
            cum_b += pnl
            eq_buy.append(cum_b)
            dts_b_plot.append(d)
        else:
            cum_s += pnl
            eq_sell.append(cum_s)
            dts_s_plot.append(d)
            
    print(f" BUY  | Trades: {len(trd_buy):>4} | PnL: R${sum(trd_buy):>6.0f}")
    print(f" SELL | Trades: {len(trd_sell):>4} | PnL: R${sum(trd_sell):>6.0f}")
    print(f" TOTAL COMBINADO: R${cum_c:>6.0f}")
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(dates_comb, eq_comb, color='#00e87a', linewidth=2, label="Capital Total Combinado (V1 + V2)")
    ax.plot(dts_b_plot, eq_buy, color='#00d4ff', alpha=0.6, linewidth=1, label="Apenas BUY (Kalman)")
    ax.plot(dts_s_plot, eq_sell, color='#ff3860', alpha=0.6, linewidth=1, label="Apenas SELL (OLS)")
    
    ax.set_title("Curva de Capital - Setup Matador Definitivo (2020-2025)", fontsize=16, fontweight='bold', pad=20)
    ax.set_ylabel("PnL Liquido Constante (R$)", fontsize=12)
    ax.grid(color='#333333', linestyle='--', linewidth=0.5)
    ax.legend(loc="upper left")
    
    total_trades = len(combined_trades)
    wins = sum(1 for _, _, p in combined_trades if p > 0)
    win_rate = (wins/total_trades*100) if total_trades > 0 else 0
    ax.text(0.02, 0.70, f"Trades: {total_trades}\nWin Rate: {win_rate:.1f}%\nTarget Final: R$ {cum_c:.2f}", 
            transform=ax.transAxes, fontsize=11, bbox=dict(facecolor='black', alpha=0.7, edgecolor='white'))
            
    # Criar e salvar dataframe pros trades
    df_trades = pd.DataFrame(combined_trades, columns=['entry_time', 'dir', 'pnl'])
    df_trades.to_csv("backtest_win_trades.csv", index=False)
            
    save_path = "C:/Users/ryzen/.gemini/antigravity/brain/ef5aebe9-595c-4cef-ba9a-979de966c203/final_equity.png"
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    print(f"Gráfico salvo em: {save_path}")

if __name__ == '__main__':
    main()
