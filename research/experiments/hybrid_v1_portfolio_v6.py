"""
Portfolio V6 Advanced Chart - 3 Setups: Consenso + WDO_NWE + DI_NWE
Valores em R$ (1 pt WIN = R$0.20 por mini contrato)
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import time as dtime

from research.test_supreme_longterm import fetch_local_history
from core.signals import calc_nwe_with_bands

PT_TO_BRL = 0.20  # 1 ponto WIN = R$0.20 por mini contrato

class KalmanFilter:
    def __init__(self, delta=1e-4, vt=1e-3):
        self.delta, self.vt = delta, vt
        self.beta = np.zeros(2)
        self.P = np.zeros((2, 2))
    def step(self, x, y):
        F = np.array([x, 1.0])
        R = self.P + np.eye(2) * self.delta
        e = y - np.dot(F, self.beta)
        Q = np.dot(F, np.dot(R, F.T)) + self.vt
        K = np.dot(R, F.T) / Q
        self.beta = self.beta + K * e
        self.P = R - np.outer(K, np.dot(F, R))
        return self.beta[0], e

def rolling_ols_z(y, x, window):
    s_y, s_x = pd.Series(y), pd.Series(x)
    cov = s_y.rolling(window=window).cov(s_x)
    var = s_x.rolling(window=window).var()
    beta = (cov / var).bfill().fillna(1.0).values
    spread = y - (beta * x)
    s = pd.Series(spread)
    mu = s.rolling(window=window).mean().bfill().fillna(0).values.copy()
    sd = s.rolling(window=window).std().bfill().fillna(1).values.copy()
    sd = np.where(sd == 0, 1.0, sd)
    return (spread - mu) / sd

def kalman_z(win, di, window=40):
    kf = KalmanFilter(1e-4, 1e-3)
    errs = [kf.step(di[i], win[i])[1] for i in range(len(win))]
    e = np.array(errs)
    s = pd.Series(e)
    mu = s.rolling(window).mean().bfill().fillna(0).values
    sd = s.rolling(window).std().bfill().fillna(1).values
    sd = np.where(sd == 0, 1.0, sd)
    return (e - mu) / sd

def run_backtest(df, signals, sl, tp, sh, eh, wb):
    trades = []
    open_trade = None
    cooldown_until = None
    win_high = df['win_high'].values
    win_low = df['win_low'].values
    win_close = df['win'].values
    times = df.index
    eod = dtime(17, 30)
    t_start, t_end = dtime(sh, 0), dtime(eh, 0)
    
    for i in range(len(df)):
        dt = times[i]
        t = dt.time()
        if open_trade is not None:
            entry_price = open_trade['entry_price']
            d = open_trade['direction']
            hit, ep = False, None
            if d == 1:
                if win_high[i] >= entry_price + tp: hit, ep = True, entry_price + tp
                elif win_low[i] <= entry_price - sl: hit, ep = True, entry_price - sl
            else:
                if win_low[i] <= entry_price - tp: hit, ep = True, entry_price - tp
                elif win_high[i] >= entry_price + sl: hit, ep = True, entry_price + sl
            if not hit and t >= eod: hit, ep = True, win_close[i]
            if hit:
                open_trade['pnl'] = (ep - entry_price) * d
                open_trade['exit_time'] = dt
                trades.append(open_trade)
                open_trade = None
                cooldown_until = i + wb
                continue
        if open_trade is None and signals[i] != 0:
            if cooldown_until is not None and i <= cooldown_until: continue
            if t >= t_start and t < t_end:
                open_trade = {'direction': signals[i], 'entry_price': win_close[i],
                              'entry_time': dt, 'bars_held': 0}
    return trades

def main():
    print("=" * 70)
    print("  PORTFOLIO V6 COMPLETO (3 SETUPS) - em R$")
    print("=" * 70)
    
    df = fetch_local_history()
    win = df['win'].values
    wdo = df['wdo'].values
    di = df['di'].values
    
    # Z-Scores
    z_wdo = rolling_ols_z(win, wdo, 40)
    z_di = kalman_z(win, di, 40)
    
    # NWE unificado (BW=1, LB=100, MAE=2.0, Prox=15%, is_up=False)
    nwe, up_nwe, _, _ = calc_nwe_with_bands(win, bandwidth=1, lookback=100, mult_mae=1.0)
    mae_raw = up_nwe - nwe
    upper = nwe + mae_raw * 2.0
    lower = nwe - mae_raw * 2.0
    bw_w = upper - lower
    vb_nwe = (win <= lower + bw_w * 0.15)
    vs_nwe = (win >= upper - bw_w * 0.15)
    
    # --- CONSENSO: WDO(OLS) + DI(Kalman), sem NWE ---
    z_entry, z_att = 2.2, 1.6
    sig_wdo_s = np.where(z_wdo <= -z_entry, 1, np.where(z_wdo >= z_entry, -1, 0))
    sig_di_s = np.where(z_di <= -z_entry, 1, np.where(z_di >= z_entry, -1, 0))
    sig_wdo_a = np.where(z_wdo <= -z_att, 1, np.where(z_wdo >= z_att, -1, 0))
    sig_di_a = np.where(z_di <= -z_att, 1, np.where(z_di >= z_att, -1, 0))
    cons_buy = ((sig_wdo_s == 1) & (sig_di_a == 1)) | ((sig_wdo_a == 1) & (sig_di_s == 1))
    cons_sell = ((sig_wdo_s == -1) & (sig_di_a == -1)) | ((sig_wdo_a == -1) & (sig_di_s == -1))
    sig_cons = np.zeros(len(df))
    sig_cons[cons_buy] = 1
    sig_cons[cons_sell] = -1
    
    # --- WDO_NWE: OLS Z=2.2 + NWE ---
    sig_wdo_nwe = np.zeros(len(df))
    sig_wdo_nwe[(z_wdo <= -2.2) & vb_nwe] = 1
    sig_wdo_nwe[(z_wdo >= 2.2) & vs_nwe] = -1
    
    # --- DI_NWE: Kalman Z=1.8 + NWE ---
    sig_di_nwe = np.zeros(len(df))
    sig_di_nwe[(z_di <= -1.8) & vb_nwe] = 1
    sig_di_nwe[(z_di >= 1.8) & vs_nwe] = -1
    
    # Run backtests
    print("Running Consenso...")
    trades_cons = run_backtest(df, sig_cons, 300, 500, 9, 16, 2)
    print("Running WDO_NWE...")
    trades_wdo = run_backtest(df, sig_wdo_nwe, 300, 600, 10, 16, 3)
    print("Running DI_NWE...")
    trades_di = run_backtest(df, sig_di_nwe, 300, 400, 9, 15, 2)
    
    def summary(trades, label):
        pnls = [t['pnl'] for t in trades]
        cum = np.cumsum(pnls)
        total = cum[-1] if len(cum) else 0
        total_brl = total * PT_TO_BRL
        peak = np.maximum.accumulate(cum)
        dd = np.max(peak - cum) if len(cum) else 0
        dd_brl = dd * PT_TO_BRL
        ret_dd = total / dd if dd > 0 else 0
        tc = len(trades)
        wr = len([t for t in trades if t['pnl'] > 0]) / tc * 100 if tc else 0
        print(f"  {label}: {tc} trades | WR={wr:.1f}% | PnL=R${total_brl:+,.0f} | DD=R${dd_brl:,.0f} | Ret/DD={ret_dd:.2f}")
        return total_brl, dd_brl, ret_dd
    
    pnl_cons, dd_cons, rd_cons = summary(trades_cons, "CONSENSO")
    pnl_wdo, dd_wdo, rd_wdo = summary(trades_wdo, "WDO_NWE")
    pnl_di, dd_di, rd_di = summary(trades_di, "DI_NWE")
    
    # Portfolio: merge all trades by exit time
    all_trades = []
    for t in trades_cons:
        all_trades.append({'time': t['exit_time'], 'pnl': t['pnl'] * PT_TO_BRL, 'setup': 'CONS'})
    for t in trades_wdo:
        all_trades.append({'time': t['exit_time'], 'pnl': t['pnl'] * PT_TO_BRL, 'setup': 'WDO'})
    for t in trades_di:
        all_trades.append({'time': t['exit_time'], 'pnl': t['pnl'] * PT_TO_BRL, 'setup': 'DI'})
    
    df_port = pd.DataFrame(all_trades).sort_values('time').reset_index(drop=True)
    df_port['cum_pnl'] = df_port['pnl'].cumsum()
    df_port['peak'] = df_port['cum_pnl'].cummax()
    df_port['drawdown'] = df_port['peak'] - df_port['cum_pnl']
    
    port_pnl = df_port['cum_pnl'].iloc[-1]
    port_dd = df_port['drawdown'].max()
    port_ret_dd = port_pnl / port_dd if port_dd > 0 else 0
    port_tc = len(df_port)
    gp = df_port[df_port['pnl'] > 0]['pnl'].sum()
    gl = abs(df_port[df_port['pnl'] < 0]['pnl'].sum())
    pf = gp / gl if gl > 0 else 0
    print(f"\n  PORTFOLIO: {port_tc} trades | PnL=R${port_pnl:+,.0f} | DD=R${port_dd:,.0f} | Ret/DD={port_ret_dd:.2f} | PF={pf:.2f}")
    
    # Build per-setup equity curves (in R$)
    def eq_curve(trades):
        pnls_brl = [t['pnl'] * PT_TO_BRL for t in trades]
        times = [t['exit_time'] for t in trades]
        return times, np.cumsum(pnls_brl)
    
    t_cons, eq_cons = eq_curve(trades_cons)
    t_wdo, eq_wdo = eq_curve(trades_wdo)
    t_di, eq_di = eq_curve(trades_di)
    
    # ---- PLOT ----
    fig, axes = plt.subplots(2, 2, figsize=(20, 12))
    fig.suptitle('Analise Avancada de Portfolio - Matador V6 (126,770 barras M5 / ~5 anos)',
                 fontsize=16, fontweight='bold', color='white')
    fig.patch.set_facecolor('#0a0a0a')
    
    colors = {'cons': '#ff6699', 'wdo': '#00ff88', 'di': '#8888ff',
              'port': '#ffffff', 'dd': '#ff4444', 'bg': '#0a0a0a', 'grid': '#222222'}
    
    for ax in axes.flat:
        ax.set_facecolor(colors['bg'])
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')
        ax.title.set_color('white')
        for spine in ax.spines.values():
            spine.set_color(colors['grid'])
    
    # Panel 1: Equity curves
    ax1 = axes[0, 0]
    ax1.plot(t_cons, eq_cons, color=colors['cons'], linewidth=1, alpha=0.8,
             label=f'CONSENSO (R${pnl_cons:+,.0f})')
    ax1.plot(t_wdo, eq_wdo, color=colors['wdo'], linewidth=1, alpha=0.8,
             label=f'WDO_NWE (R${pnl_wdo:+,.0f})')
    ax1.plot(t_di, eq_di, color=colors['di'], linewidth=1, alpha=0.8,
             label=f'DI_NWE (R${pnl_di:+,.0f})')
    ax1.plot(df_port['time'], df_port['cum_pnl'], color=colors['port'], linewidth=2,
             label=f'PORTFOLIO (R${port_pnl:+,.0f})')
    ax1.fill_between(df_port['time'], df_port['cum_pnl'],
                     df_port['cum_pnl'] - df_port['drawdown'],
                     color=colors['dd'], alpha=0.3, label='Drawdown')
    ax1.set_title(f'Curva de Capital (Ret/DD: {port_ret_dd:.2f}x | PF: {pf:.2f})', color='white')
    ax1.set_ylabel('PnL Acumulado (R$)', color='white')
    ax1.legend(loc='upper left', fontsize=9, facecolor='#1a1a1a', edgecolor='#333', labelcolor='white')
    ax1.grid(True, alpha=0.15, color=colors['grid'])
    
    # Panel 2: Yearly PnL stacked bars
    ax2 = axes[0, 1]
    df_c = pd.DataFrame({'time': [t['exit_time'] for t in trades_cons], 'pnl': [t['pnl']*PT_TO_BRL for t in trades_cons]})
    df_w = pd.DataFrame({'time': [t['exit_time'] for t in trades_wdo], 'pnl': [t['pnl']*PT_TO_BRL for t in trades_wdo]})
    df_d = pd.DataFrame({'time': [t['exit_time'] for t in trades_di], 'pnl': [t['pnl']*PT_TO_BRL for t in trades_di]})
    for d in [df_c, df_w, df_d]: d['year'] = pd.to_datetime(d['time']).dt.year
    years = sorted(set(df_c['year'].tolist() + df_w['year'].tolist() + df_d['year'].tolist()))
    
    c_y = [df_c[df_c['year']==y]['pnl'].sum() for y in years]
    w_y = [df_w[df_w['year']==y]['pnl'].sum() for y in years]
    d_y = [df_d[df_d['year']==y]['pnl'].sum() for y in years]
    
    x = np.arange(len(years))
    width = 0.25
    ax2.bar(x - width, c_y, width, label='CONSENSO', color=colors['cons'], alpha=0.85)
    ax2.bar(x, w_y, width, label='WDO_NWE', color=colors['wdo'], alpha=0.85)
    ax2.bar(x + width, d_y, width, label='DI_NWE', color=colors['di'], alpha=0.85)
    ax2.set_xticks(x)
    ax2.set_xticklabels(years, color='white')
    ax2.set_title('PnL Anual por Setup (R$)', color='white')
    ax2.set_ylabel('PnL (R$)', color='white')
    ax2.legend(facecolor='#1a1a1a', edgecolor='#333', labelcolor='white', fontsize=8)
    ax2.grid(True, alpha=0.15, color=colors['grid'], axis='y')
    ax2.axhline(y=0, color='white', linewidth=0.5, alpha=0.3)
    
    # Panel 3: Underwater drawdown
    ax3 = axes[1, 0]
    ax3.fill_between(df_port['time'], 0, -df_port['drawdown'], color=colors['dd'], alpha=0.6)
    ax3.set_title(f'Perfil de Drawdown (Max: -R${port_dd:,.0f})', color='white')
    ax3.set_ylabel('Drawdown (R$)', color='white')
    ax3.set_xlabel('Data', color='white')
    ax3.grid(True, alpha=0.15, color=colors['grid'])
    
    # Panel 4: Contribution bars
    ax4 = axes[1, 1]
    setups = ['CONSENSO', 'WDO_NWE', 'DI_NWE', 'PORTFOLIO']
    pnls = [pnl_cons, pnl_wdo, pnl_di, port_pnl]
    bar_c = [colors['cons'], colors['wdo'], colors['di'], colors['port']]
    bars = ax4.bar(setups, pnls, color=bar_c, alpha=0.85, edgecolor='#333')
    ax4.set_title('Contribuicao por Setup (R$)', color='white')
    ax4.set_ylabel('PnL (R$)', color='white')
    ax4.grid(True, alpha=0.15, color=colors['grid'], axis='y')
    for bar, val in zip(bars, pnls):
        ax4.text(bar.get_x() + bar.get_width()/2., val + 200,
                f'R${val:+,.0f}', ha='center', va='bottom', fontsize=10,
                fontweight='bold', color='white')
    
    plt.tight_layout()
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".planning", "docs", "assets", "portfolio_v6_advanced.png")
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"\nChart saved: {out}")
    plt.close()

if __name__ == "__main__":
    main()
