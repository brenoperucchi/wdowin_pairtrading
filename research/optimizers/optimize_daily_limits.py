"""
Otimização de Limites Diários: Max Trades e Max Loss
V2 Kalman BUY (Z=2.0, SL=350, TP=500)
V1 OLS SELL (Z=2.1, SL=300, TP=1400)
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, time
from kalman_filter import KalmanBetaFilter

# ─── CONFIGURAÇÕES BASE ───────────────────────────────────────────────────────
WDO_CSV = r"base de dados\WDO$N_M1_202103100900_202603261829.csv"
WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"
WINDOW = 40; BETA_INITIAL = -22.5; RHO_MIN = -0.40
BETA_REF_WINDOW = 80; BETA_DELTA_MAX = 25.0
CONTRACTS = 2; PV = 0.20
ENTRY_START = time(9, 15); ENTRY_END = time(16, 0); FC_TIME = time(17, 40)

# Parâmetros Otimizados
BUY_ZMIN = 2.0; BUY_ZMAX = 3.0; BUY_SL = 350; BUY_TP = 500
SELL_ZMIN = 2.1; SELL_ZMAX = 3.0; SELL_SL = 300; SELL_TP = 1400

# Ranges de Limites Diários
# Max trades: 1, 2, 3, 4, 5, 999 (sem limite)
MAX_TRADES_RANGE = [1, 2, 3, 4, 5, 999]
# Max loss financeiro (R$): -100, -200, -300, -400, -500, -99999 (sem limite)
MAX_LOSS_RANGE = [-150, -250, -350, -450, -550, -99999]

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

def run_simulation(data, z1, r1, b1, z2, r2, b2, max_trades, max_loss):
    n = len(data)
    ts = data.index
    wh = data['wh'].values
    wl = data['wl'].values
    wc = data['win'].values
    
    pos = None  # None ou dict {'px': open_px, 'dir': 'buy'/'sell', 'sl': pts, 'tp': pts}
    trades = []
    
    current_day = None
    daily_trades = 0
    daily_pnl = 0.0
    daily_blocked = False
    
    for i in range(WINDOW, n):
        t_time = ts[i].time()
        t_date = ts[i].date()
        
        # Reset de dia
        if t_date != current_day:
            current_day = t_date
            daily_trades = 0
            daily_pnl = 0.0
            daily_blocked = False
            
        # Verifica fechamento da posicao
        if pos is not None:
            reason = None; ep = 0
            
            if pos['dir'] == 'buy':
                if wh[i] >= pos['px'] + pos['tp']: reason = 'TP'; ep = pos['px'] + pos['tp']
                elif wl[i] <= pos['px'] - pos['sl']: reason = 'SL'; ep = pos['px'] - pos['sl']
            else:
                if wl[i] <= pos['px'] - pos['tp']: reason = 'TP'; ep = pos['px'] - pos['tp']
                elif wh[i] >= pos['px'] + pos['sl']: reason = 'SL'; ep = pos['px'] + pos['sl']
                
            if reason is None and t_time >= FC_TIME: reason = 'FC'; ep = wc[i]
            
            if reason:
                d = 1 if pos['dir'] == 'buy' else -1
                pnl = d * (ep - pos['px']) * CONTRACTS * PV
                trades.append({'time': ts[i], 'pnl': pnl, 'dir': pos['dir']})
                daily_pnl += pnl
                pos = None
                
                # Check se bateu loss diario
                if daily_pnl <= max_loss:
                    daily_blocked = True
        
        # Verifica abertura de posicao se nao tem nenhuma
        if pos is None and not daily_blocked:
            if t_time < ENTRY_START or t_time > ENTRY_END: continue
            if daily_trades >= max_trades: continue
            
            z_buy = z2[i]; r_buy = r2[i]; b_buy = b2[i]
            z_sell = z1[i]; r_sell = r1[i]; b_sell = b1[i]
            
            # Prioridade de entrada: se os 2 derem sinal, entra no de maior desvio absoluto
            signal_buy = (z_buy < -BUY_ZMIN and z_buy >= -BUY_ZMAX and is_safe(b2, i, r_buy))
            signal_sell = (z_sell > SELL_ZMIN and z_sell <= SELL_ZMAX and is_safe(b1, i, r_sell))
            
            if signal_buy and signal_sell:
                if abs(z_buy) > abs(z_sell): signal_sell = False
                else: signal_buy = False
                
            if signal_buy:
                pos = {'px': wc[i], 'dir': 'buy', 'sl': BUY_SL, 'tp': BUY_TP}
                daily_trades += 1
            elif signal_sell:
                pos = {'px': wc[i], 'dir': 'sell', 'sl': SELL_SL, 'tp': SELL_TP}
                daily_trades += 1

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
    print("\nSimulando combinações de limites...")
    print(f"{'Max Trds':>8} {'Max Loss':>9} | {'Trades':>6} {'PnL (R$)':>9} {'MaxDD (R$)':>10} {'RF':>6} {'PF':>5}")
    print("-" * 75)
    
    best_rf = -1
    best_combo = None
    best_trades = None
    
    for max_t in MAX_TRADES_RANGE:
        for max_l in MAX_LOSS_RANGE:
            trades = run_simulation(data, z1, r1, b1, z2, r2, b2, max_t, max_l)
            n, pnl, dd, rf, pf = calc_metrics(trades)
            
            max_t_str = "Sem Lim" if max_t == 999 else str(max_t)
            max_l_str = "Sem Lim" if max_l == -99999 else str(max_l)
            
            results.append({
                'max_t': max_t_str, 'max_l': max_l_str,
                'trades': n, 'pnl': pnl, 'dd': dd, 'rf': rf, 'pf': pf
            })
            
            print(f"{max_t_str:>8} {max_l_str:>9} | {n:>6} {pnl:>9.0f} {dd:>10.0f} {rf:>6.2f} {pf:>5.2f}")
            
            if rf > best_rf:
                best_rf = rf
                best_combo = results[-1]
                best_trades = trades

    print("\n" + "=" * 60)
    print(" MELHOR COMBINAÇÃO DE LIMITES DIÁRIOS (Por Recovery Factor)")
    print("=" * 60)
    print(f" Máximo de Trades/Dia : {best_combo['max_t']}")
    print(f" Loss Máximo/Dia (R$) : {best_combo['max_l']}")
    print("-" * 60)
    print(f" Trades Totais        : {best_combo['trades']}")
    print(f" PnL Acumulado        : R$ {best_combo['pnl']:,.0f}")
    print(f" Drawdown Máximo      : R$ {best_combo['dd']:,.0f}")
    print(f" Recovery Factor (RF) : {best_combo['rf']:.2f} 👑")
    print(f" Profit Factor (PF)   : {best_combo['pf']:.2f}")
    
    # Heatmap RF
    res_df = pd.DataFrame(results)
    pivot_rf = res_df.pivot(index='max_l', columns='max_t', values='rf')
    
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(pivot_rf.values, cmap='RdYlGn', aspect='auto')
    
    # Config ticks
    ax.set_xticks(np.arange(len(pivot_rf.columns)))
    ax.set_yticks(np.arange(len(pivot_rf.index)))
    ax.set_xticklabels(pivot_rf.columns)
    ax.set_yticklabels(pivot_rf.index)
    
    ax.set_title("Heatmap: Recovery Factor por Limites Diários", fontsize=14, pad=15)
    ax.set_xlabel("Máximo de Trades por Dia")
    ax.set_ylabel("Loss Diário Máximo (R$)")
    
    # Anotar valores no heatmap
    for i in range(len(pivot_rf.index)):
        for j in range(len(pivot_rf.columns)):
            val = pivot_rf.values[i, j]
            color = 'white' if abs(val - pivot_rf.values.mean()) > pivot_rf.values.std() else 'black'
            ax.text(j, i, f"{val:.2f}", ha='center', va='center', color=color, fontweight='bold')
    
    plt.colorbar(im, ax=ax, label="Recovery Factor")
    plt.tight_layout()
    plt.savefig('daily_limits_heatmap.png', dpi=150)
    print(f"\n[OK] Heatmap salvo em daily_limits_heatmap.png")
    print(f"[OK] Demorou {(datetime.now() - start).total_seconds():.0f}s")
    
if __name__ == '__main__':
    main()
