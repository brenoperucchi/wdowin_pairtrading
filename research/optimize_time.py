"""
RESEARCH EXPLORATÓRIO — NÃO USAR COMO VALIDAÇÃO DE PRODUÇÃO
============================================================
Este script diverge do motor live (core/config.py + core/trade_engine.py).
Ver docs/PARAM_PROFILE.md §2 (divergent hardcoded values).
Validação operacional: research/run_matador_v5_johansen.py (TASK-3 AC #15).

Otimizacao de Horarios de Operacao (Timeframes Intradiarios)
Gera simulacoes para diferentes horarios de inicio e fim de entradas.
V2 Kalman BUY (Z=2.0, SL=350, TP=500)
V1 OLS SELL (Z=2.1, SL=300, TP=1400)
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
CONTRACTS = 2; PV = 0.20
FC_TIME = time(17, 40)

BUY_ZMIN = 2.0; BUY_ZMAX = 3.0; BUY_SL = 350; BUY_TP = 500
SELL_ZMIN = 2.1; SELL_ZMAX = 3.0; SELL_SL = 300; SELL_TP = 1400

# Grades de tempo para testar
START_TIMES = [time(9, 15), time(9, 30), time(10, 0), time(10, 30)]
END_TIMES = [time(14, 0), time(15, 0), time(16, 0)]

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

def sim_leg(data, zs, ra, bs, zmin, zmax, direction, sl_pts, tp_pts, entry_start, entry_end):
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
        if t<entry_start or t>entry_end: continue
        if not is_safe(bs,i,ra[i]): continue
        az=abs(z)
        if az<zmin or az>=zmax: continue
        if direction=='buy' and z<-zmin: pos={'px':wc[i]}
        elif direction=='sell' and z>zmin: pos={'px':wc[i]}
    return trades

def calc_metrics(trades):
    if not trades or len(trades) < 5: return 0, 0, 0, 0, 0
    pnls = np.array([t['pnl'] for t in trades])
    pnl = pnls.sum()
    eq = np.cumsum(pnls); pk = np.maximum.accumulate(eq)
    dd = (pk - eq).max()
    rf = pnl / dd if dd > 0 else 0
    wr = np.sum(pnls > 0) / len(pnls) * 100
    gp = pnls[pnls > 0].sum(); gl = abs(pnls[pnls <= 0].sum()) + .001
    return len(trades), pnl, dd, rf, gp/gl

def main():
    start = datetime.now()
    data = load()
    wc = data['win'].values.astype(float); dc = data['wdo'].values.astype(float)
    print("  Calculando V1 OLS..."); b1, z1, r1 = calc_v1(wc, dc)
    print("  Calculando V2 Kalman..."); b2, z2, r2 = calc_v2(wc, dc)
    
    results = []
    print("\nSimulando combinações de horários de operação...")
    print(f"{'Início':>6} {'Fim':>6} | {'Trades':>6} {'PnL (R$)':>9} {'MaxDD':>9} {'RF':>5} {'PF':>5}")
    print("-" * 65)
    
    best_rf = -1
    best_combo = None
    
    for st in START_TIMES:
        for et in END_TIMES:
            # Simula as duas pernas independentemente para honrar a politica "Sem Limites" aprovada
            trd_buy = sim_leg(data, z2, r2, b2, BUY_ZMIN, BUY_ZMAX, 'buy', BUY_SL, BUY_TP, st, et)
            trd_sell = sim_leg(data, z1, r1, b1, SELL_ZMIN, SELL_ZMAX, 'sell', SELL_SL, SELL_TP, st, et)
            
            all_trades = trd_buy + trd_sell
            all_trades.sort(key=lambda x: x['time'])
            
            n, pnl, dd, rf, pf = calc_metrics(all_trades)
            
            st_str = st.strftime('%H:%M')
            et_str = et.strftime('%H:%M')
            
            results.append({
                'start': st_str, 'end': et_str,
                'trades': n, 'pnl': pnl, 'dd': dd, 'rf': rf, 'pf': pf
            })
            
            print(f"{st_str:>6} {et_str:>6} | {n:>6} {pnl:>9.0f} {dd:>9.0f} {rf:>5.2f} {pf:>5.2f}")
            
            if rf > best_rf:
                best_rf = rf
                best_combo = results[-1]

    print("\n" + "=" * 65)
    print(" MELHOR JANELA DE HORÁRIO (Por Recovery Factor)")
    print("=" * 65)
    print(f" Início               : {best_combo['start']}")
    print(f" Fim (Última Entrada) : {best_combo['end']} (Fechamento Geral às 17h40)")
    print("-" * 65)
    print(f" Trades Totais        : {best_combo['trades']}")
    print(f" PnL Acumulado        : R$ {best_combo['pnl']:,.0f}")
    print(f" Drawdown Máximo      : R$ {best_combo['dd']:,.0f}")
    print(f" Recovery Factor (RF) : {best_combo['rf']:.2f}")
    print(f" Profit Factor (PF)   : {best_combo['pf']:.2f}")
    print(f"[OK] Demorou {(datetime.now() - start).total_seconds():.0f}s")
    
if __name__ == '__main__':
    main()
