"""
Matador v4 — Consenso SEM filtro NWE (só z-scores WDO+DI alinhados)
====================================================================
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from datetime import datetime
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

Z_ENT, Z_ATT = 1.4, 1.2
SL, TP, BE = 300, 800, 300
WIN_PV = 0.20
FC = 17*60+40; SM = 9*60; EM = 15*60
NWE_BW, NWE_LB, NWE_MAE, NWE_BM = 8, 95, 3.0, 0.10

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".planning", "docs", "assets")

def bmn(ts):
    dt = datetime.utcfromtimestamp(ts)
    return dt.hour * 60 + dt.minute

def calc_nwe(p, bw, lb, mm):
    n = len(p); nw = np.zeros(n); mae = np.zeros(n)
    for t in range(n):
        l = min(t, lb)
        if l == 0: nw[t] = p[t]; continue
        i = np.arange(l+1); w = np.exp(-(i*i)/(2*bw*bw))
        nw[t] = np.sum(p[t-l:t+1][::-1]*w) / np.sum(w)
    for t in range(n):
        l = min(t, lb)
        if l == 0: continue
        mae[t] = np.mean(np.abs(p[t-l:t+1] - nw[t-l:t+1])) * mm
    return nw, nw+mae, nw-mae

def simulate_with_nwe(z, win_c, bar_mins, is_up, upper, lower):
    """WDO/DI isolado — COM filtro NWE."""
    n = len(win_c); pnl = np.zeros(n)
    pos = 0; ep = 0.0; bh = False
    for i in range(1000, n):
        p = win_c[i]; tm = bar_mins[i]
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p)
            pnl[i] = d * WIN_PV; pos = 0; continue
        sb = (z[i] <= -Z_ENT); ss = (z[i] >= Z_ENT)
        bww = upper[i] - lower[i]
        if bww < 1e-10: bww = 1.0
        u = is_up[i]
        if sb:
            if u: sb = False
            elif p > lower[i] + bww * NWE_BM: sb = False
        if ss:
            if not u: ss = False
            elif p < upper[i] - bww * NWE_BM: ss = False
        if pos == 0:
            if tm < SM or tm > EM: sb = ss = False
            if sb: pos, ep, bh = 1, p, False
            elif ss: pos, ep, bh = -1, p, False
        else:
            d = (p-ep) if pos == 1 else (ep-p)
            if not bh and d >= BE: bh = True
            if d >= TP: pnl[i] = TP * WIN_PV; pos = 0
            elif bh and d <= 0: pnl[i] = 0; pos = 0
            elif not bh and d <= -SL: pnl[i] = -SL * WIN_PV; pos = 0
    return pnl

def simulate_consensus_no_nwe(z_wdo, z_di, win_c, bar_mins):
    """Consenso PURO — SEM filtro NWE, só z-scores alinhados."""
    n = len(win_c); pnl = np.zeros(n)
    pos = 0; ep = 0.0; bh = False
    for i in range(1000, n):
        p = win_c[i]; tm = bar_mins[i]
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p)
            pnl[i] = d * WIN_PV; pos = 0; continue

        zw, zd = z_wdo[i], z_di[i]
        sb = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
        ss = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)

        # NO NWE filter — only time window
        if pos == 0:
            if tm < SM or tm > EM: sb = ss = False
            if sb: pos, ep, bh = 1, p, False
            elif ss: pos, ep, bh = -1, p, False
        else:
            d = (p-ep) if pos == 1 else (ep-p)
            if not bh and d >= BE: bh = True
            if d >= TP: pnl[i] = TP * WIN_PV; pos = 0
            elif bh and d <= 0: pnl[i] = 0; pos = 0
            elif not bh and d <= -SL: pnl[i] = -SL * WIN_PV; pos = 0
    return pnl

def simulate_consensus_with_nwe(z_wdo, z_di, win_c, bar_mins, is_up, upper, lower):
    """Consenso COM filtro NWE (para comparação)."""
    n = len(win_c); pnl = np.zeros(n)
    pos = 0; ep = 0.0; bh = False
    for i in range(1000, n):
        p = win_c[i]; tm = bar_mins[i]
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p)
            pnl[i] = d * WIN_PV; pos = 0; continue

        zw, zd = z_wdo[i], z_di[i]
        sb = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
        ss = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)

        bww = upper[i] - lower[i]
        if bww < 1e-10: bww = 1.0
        u = is_up[i]
        if sb:
            if u: sb = False
            elif p > lower[i] + bww * NWE_BM: sb = False
        if ss:
            if not u: ss = False
            elif p < upper[i] - bww * NWE_BM: ss = False

        if pos == 0:
            if tm < SM or tm > EM: sb = ss = False
            if sb: pos, ep, bh = 1, p, False
            elif ss: pos, ep, bh = -1, p, False
        else:
            d = (p-ep) if pos == 1 else (ep-p)
            if not bh and d >= BE: bh = True
            if d >= TP: pnl[i] = TP * WIN_PV; pos = 0
            elif bh and d <= 0: pnl[i] = 0; pos = 0
            elif not bh and d <= -SL: pnl[i] = -SL * WIN_PV; pos = 0
    return pnl

def stats(pa):
    t = pa[pa != 0]; n = len(t)
    if n == 0: return {'pnl':0,'trades':0,'wr':0,'dd':0,'ret_dd':0}
    tp = np.sum(t); w = np.sum(t > 0); wr = w/n*100
    c = np.cumsum(t); mx = np.maximum.accumulate(c); dd = np.max(mx - c)
    if dd < 1e-5: dd = 1.0
    gw = np.sum(t[t > 0])
    gl = np.abs(np.sum(t[t < 0]))
    pf = gw / gl if gl > 0 else 0.0
    return {'pnl':tp, 'trades':n, 'wr':wr, 'dd':dd, 'ret_dd':tp/dd, 'pf':pf}

def main():
    print("=" * 85)
    print("MATADOR v4 — CONSENSO SEM NWE vs COM NWE")
    print("=" * 85)

    mt5.initialize(path=MT5_PATH)
    rw = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 15000)
    rd = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, 15000)
    rdi = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, 15000)
    mt5.shutdown()

    win = np.array([r[4] for r in rw], dtype=float)
    wdo = np.array([r[4] for r in rd], dtype=float)
    di = np.array([r[4] for r in rdi], dtype=float)
    times = np.array([r[0] for r in rw], dtype=np.int64)
    n = min(len(win), len(wdo), len(di))
    win, wdo, di, times = win[:n], wdo[:n], di[:n], times[:n]

    nwe, upper, lower = calc_nwe(win, NWE_BW, NWE_LB, NWE_MAE)
    is_up = np.zeros(n, dtype=bool); is_up[1:] = nwe[1:] >= nwe[:-1]; is_up[0] = True
    bar_mins = np.array([bmn(t) for t in times])

    # Z-scores
    kf_wdo = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=1e-4, obs_cov=1e2)
    sp_wdo = []
    for y, x in zip(win, wdo):
        _, s, _ = kf_wdo.update(float(y), float(x)); sp_wdo.append(s)
    z_wdo = np.array(KalmanBetaFilter.rolling_zscore(sp_wdo, window=40))

    kf_di = KalmanBetaFilter(initial_beta=-10000.0, trans_cov=1e-3, obs_cov=1e1)
    sp_di = []
    for y, x in zip(win, di):
        _, s, _ = kf_di.update(float(y), float(x)); sp_di.append(s)
    z_di = np.array(KalmanBetaFilter.rolling_zscore(sp_di, window=60))

    # Simulate
    pnl_wdo = simulate_with_nwe(z_wdo, win, bar_mins, is_up, upper, lower)
    pnl_di = simulate_with_nwe(z_di, win, bar_mins, is_up, upper, lower)
    pnl_cons_nwe = simulate_consensus_with_nwe(z_wdo, z_di, win, bar_mins, is_up, upper, lower)
    pnl_cons_pure = simulate_consensus_no_nwe(z_wdo, z_di, win, bar_mins)

    # Portfolios
    port_2 = pnl_wdo + pnl_di
    port_3_nwe = pnl_wdo + pnl_di + pnl_cons_nwe
    port_3_pure = pnl_wdo + pnl_di + pnl_cons_pure

    s_wdo = stats(pnl_wdo)
    s_di = stats(pnl_di)
    s_cn = stats(pnl_cons_nwe)
    s_cp = stats(pnl_cons_pure)
    s_2 = stats(port_2)
    s_3n = stats(port_3_nwe)
    s_3p = stats(port_3_pure)

    # Prepare data for report
    setups = [
        ("WDO Kalman (+NWE)", s_wdo),
        ("DI Kalman (+NWE)", s_di),
        ("Consenso COM NWE", s_cn),
        ("Consenso SEM NWE (puro)", s_cp),
    ]
    ports = [
        ("PORT WDO+DI (sem cons)", s_2),
        ("PORT WDO+DI+CONS(NWE)", s_3n),
        ("PORT WDO+DI+CONS(puro)", s_3p),
    ]

    # Generate Markdown Report
    report_path = os.path.join(OUT, "REPORT_MATADOR_V4.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 📊 Relatório de Backtest — Setup Matador V4\n\n")
        f.write("Este relatório contém os resultados validados do backtest atual.\n\n")
        f.write("## 1. Desempenho por Setup Individual\n\n")
        f.write("| Setup | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |\n")
        f.write("|-------|----------|-------------|--------|---------------|--------|----------|\n")
        for name, s in setups:
            f.write(f"| {name} | R${s['pnl']:.0f} | R${s['dd']:.0f} | {s['ret_dd']:.2f}x | {s['pf']:.2f} | {s['trades']} | {s['wr']:.1f}% |\n")
        
        f.write("\n## 2. Desempenho do Portfólio (Combinações)\n\n")
        f.write("| Portfólio | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |\n")
        f.write("|-----------|----------|-------------|--------|---------------|--------|----------|\n")
        for name, s in ports:
            f.write(f"| {name} | R${s['pnl']:.0f} | R${s['dd']:.0f} | {s['ret_dd']:.2f}x | {s['pf']:.2f} | {s['trades']} | {s['wr']:.1f}% |\n")
        
        f.write("\n## 3. Curva de Capital (Equity Curve)\n\n")
        f.write("![Equity Curve](./portfolio_v4_advanced.png)\n")

    print(f"\nRelatório gerado: {report_path}")

    # Plot Advanced Chart
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(22, 12))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1])

    # Top Left: Portfolio 3 strats com consenso puro (Main Equity Curve)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(np.cumsum(pnl_wdo), color='#c8a444', alpha=0.5, linewidth=1, label=f"WDO (R${s_wdo['pnl']:.0f})")
    ax1.plot(np.cumsum(pnl_di), color='#8a6dff', alpha=0.5, linewidth=1, label=f"DI (R${s_di['pnl']:.0f})")
    ax1.plot(np.cumsum(pnl_cons_pure), color='#00e87a', alpha=0.5, linewidth=1, label=f"CONS puro (R${s_cp['pnl']:.0f})")
    
    port_eq = np.cumsum(port_3_pure)
    ax1.plot(port_eq, color='white', linewidth=2.5, label=f"PORTFOLIO TOTAL (R${s_3p['pnl']:.0f})")
    
    # Fill drawdown area for portfolio
    running_max = np.maximum.accumulate(port_eq)
    drawdown = running_max - port_eq
    ax1.fill_between(range(len(port_eq)), port_eq, running_max, color='#ff3860', alpha=0.3, label="Drawdown")

    ax1.set_title(f"Curva de Capital do Portfólio (Ret/DD: {s_3p['ret_dd']:.2f}x | PF: {s_3p['pf']:.2f})", fontsize=14, pad=10)
    ax1.set_ylabel("PnL Acumulado (R$)")
    ax1.legend(loc="upper left", fontsize=10, framealpha=0.7)
    ax1.grid(alpha=0.15, linestyle='--')

    # Top Right: Consenso COM vs SEM NWE
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(np.cumsum(pnl_cons_nwe), color='#ff69b4', alpha=0.8, linewidth=2, label=f"Cons COM NWE (R${s_cn['pnl']:.0f} | {s_cn['ret_dd']:.1f}x)")
    ax2.plot(np.cumsum(pnl_cons_pure), color='#00e87a', alpha=0.8, linewidth=2, label=f"Cons SEM NWE (R${s_cp['pnl']:.0f} | {s_cp['ret_dd']:.1f}x)")
    ax2.set_title("Efeito do Filtro NWE no Consenso", fontsize=14, pad=10)
    ax2.legend(loc="upper left", fontsize=10, framealpha=0.7)
    ax2.grid(alpha=0.15, linestyle='--')

    # Bottom Left: Drawdown Profile (Underwater Chart)
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.fill_between(range(len(drawdown)), 0, -drawdown, color='#ff3860', alpha=0.6)
    ax3.plot(-drawdown, color='#ff3860', linewidth=1)
    ax3.set_title(f"Perfil de Drawdown (Max: R$-{s_3p['dd']:.0f})", fontsize=12, pad=10)
    ax3.set_ylabel("Drawdown (R$)")
    ax3.set_xlabel("Barras (M5)")
    ax3.grid(alpha=0.15, linestyle='--')

    # Bottom Right: Individual Setups Performance Bar Chart
    ax4 = fig.add_subplot(gs[1, 1])
    labels = ['WDO', 'DI', 'CONS (puro)']
    pnls = [s_wdo['pnl'], s_di['pnl'], s_cp['pnl']]
    colors = ['#c8a444', '#8a6dff', '#00e87a']
    bars = ax4.bar(labels, pnls, color=colors, alpha=0.8, width=0.5)
    ax4.set_title("Contribuição por Setup (PnL)", fontsize=12, pad=10)
    ax4.set_ylabel("PnL (R$)")
    ax4.grid(alpha=0.15, axis='y', linestyle='--')
    for bar in bars:
        yval = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2, yval + 1000, f'R${yval:.0f}', ha='center', va='bottom', color='white', fontweight='bold')

    fig.suptitle("Análise Avançada de Portfólio — Matador V4", fontsize=18, y=0.98, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    
    img_path = os.path.join(OUT, "portfolio_v4_advanced.png")
    fig.savefig(img_path, dpi=150)
    plt.close(fig)
    print(f"Gráfico salvo: {img_path}")

if __name__ == "__main__":
    main()
