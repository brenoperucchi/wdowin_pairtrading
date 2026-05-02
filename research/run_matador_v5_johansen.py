"""
Matador V5 Backtest — Bateria Dupla (Sem/Com Johansen Gate)
============================================================
Replicação fiel da lógica do plot_portfolio_v4.py (V4 validado)
acrescida do Gate de Cointegração de Johansen + Estabilidade de Beta.

Período: 35.000 barras M5 (~1.2 anos)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import (SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH,
                          BETA_INITIAL, DI_BETA_INITIAL)

# ─── Parâmetros idênticos ao plot_portfolio_v4.py ────────────────────────────
Z_ENT, Z_ATT = 1.4, 1.2
SL, TP, BE = 300, 800, 300
WIN_PV = 0.20
FC = 17*60+40; SM = 9*60; EM = 15*60
NWE_BW, NWE_LB, NWE_MAE, NWE_BM = 8, 95, 3.0, 0.10

# ─── Johansen Gate ───────────────────────────────────────────────────────────
JOH_WINDOW = 250
JOH_RECHECK = 12
BETA_TOLERANCE = 0.30

def bmn(ts):
    dt = datetime.utcfromtimestamp(ts)
    return dt.hour * 60 + dt.minute

def calc_nwe(p, bw, lb, mm):
    """NWE aplicado ao PREÇO (WIN), não ao z-score."""
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

# ─── Simulações (réplica exata do V4) ───────────────────────────────────────

def simulate_with_nwe(z, win_c, bar_mins, is_up, upper, lower,
                      kalman_betas=None, joh_gates=None, joh_betas=None,
                      use_johansen=False):
    """WDO/DI isolado — COM filtro NWE. Lógica idêntica ao plot_portfolio_v4."""
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

        # Gate Johansen (apenas Bateria 2)
        if use_johansen and (sb or ss):
            valid = joh_gates[i]
            if joh_betas[i] != 0 and not np.isnan(joh_betas[i]):
                if abs(kalman_betas[i] - joh_betas[i]) / abs(joh_betas[i]) > BETA_TOLERANCE:
                    valid = False
            else:
                valid = False
            if not valid: sb = ss = False

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

def simulate_consensus_no_nwe(z_wdo, z_di, win_c, bar_mins,
                               kb_wdo=None, jg_wdo=None, jb_wdo=None,
                               kb_di=None, jg_di=None, jb_di=None,
                               use_johansen=False):
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

        # Gate Johansen: filtra pelo ativo que PUXOU o gatilho (Z >= 1.4)
        if use_johansen and (sb or ss):
            wdo_triggered = abs(zw) >= Z_ENT
            di_triggered = abs(zd) >= Z_ENT

            def _valid(kb, jg, jb, idx):
                if not jg[idx]: return False
                if jb[idx] == 0 or np.isnan(jb[idx]): return False
                return abs(kb[idx] - jb[idx]) / abs(jb[idx]) <= BETA_TOLERANCE

            block = False
            if wdo_triggered and not _valid(kb_wdo, jg_wdo, jb_wdo, i):
                block = True
            if di_triggered and not _valid(kb_di, jg_di, jb_di, i):
                block = True
            if block: sb = ss = False

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

def simulate_consensus_with_nwe(z_wdo, z_di, win_c, bar_mins, is_up, upper, lower,
                                 kb_wdo=None, jg_wdo=None, jb_wdo=None,
                                 kb_di=None, jg_di=None, jb_di=None,
                                 use_johansen=False):
    """Consenso COM filtro NWE."""
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

        # Gate Johansen
        if use_johansen and (sb or ss):
            wdo_triggered = abs(zw) >= Z_ENT
            di_triggered = abs(zd) >= Z_ENT

            def _valid(kb, jg, jb, idx):
                if not jg[idx]: return False
                if jb[idx] == 0 or np.isnan(jb[idx]): return False
                return abs(kb[idx] - jb[idx]) / abs(jb[idx]) <= BETA_TOLERANCE

            block = False
            if wdo_triggered and not _valid(kb_wdo, jg_wdo, jb_wdo, i):
                block = True
            if di_triggered and not _valid(kb_di, jg_di, jb_di, i):
                block = True
            if block: sb = ss = False

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

# ─── Johansen rolling ───────────────────────────────────────────────────────

def calc_johansen_array(a, b, n):
    joh_gates = np.zeros(n, dtype=bool)
    joh_betas = np.full(n, np.nan)
    last_gate = False; last_joh_beta = np.nan
    for i in range(n):
        if i >= JOH_WINDOW and i % JOH_RECHECK == 0:
            try:
                y = np.column_stack([a[i-JOH_WINDOW:i], b[i-JOH_WINDOW:i]])
                result = coint_johansen(y, det_order=0, k_ar_diff=1)
                trace_stat = result.lr1[0]
                crit_95 = result.cvt[0, 1]
                last_gate = bool(trace_stat > crit_95)
                vec = result.evec[:, 0]; vec = vec / vec[0]
                last_joh_beta = vec[1]
            except Exception:
                pass
        joh_gates[i] = last_gate
        joh_betas[i] = last_joh_beta
    return joh_gates, joh_betas

def stats(pa):
    t = pa[pa != 0]; n = len(t)
    if n == 0: return {'pnl':0,'trades':0,'wr':0,'dd':0,'ret_dd':0,'pf':0}
    tp = np.sum(t); w = np.sum(t > 0); wr = w/n*100
    c = np.cumsum(t); mx = np.maximum.accumulate(c); dd = np.max(mx - c)
    if dd < 1e-5: dd = 1.0
    gw = np.sum(t[t > 0]); gl = np.abs(np.sum(t[t < 0]))
    pf = gw / gl if gl > 0 else 0.0
    return {'pnl':tp, 'trades':n, 'wr':wr, 'dd':dd, 'ret_dd':tp/dd, 'pf':pf}

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    BARS = 35000
    print("=" * 85)
    print(f"MATADOR V5 BACKTEST — {BARS} barras M5 (~1.2 anos)")
    print("=" * 85)

    mt5.initialize(path=MT5_PATH)
    rw = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, BARS)
    rd = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, BARS)
    rdi = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, BARS)
    mt5.shutdown()

    if rw is None or rd is None or rdi is None:
        print("ERRO: Falha ao baixar dados do MT5."); return

    win = np.array([r[4] for r in rw], dtype=float)
    wdo = np.array([r[4] for r in rd], dtype=float)
    di  = np.array([r[4] for r in rdi], dtype=float)
    times = np.array([r[0] for r in rw], dtype=np.int64)
    n = min(len(win), len(wdo), len(di))
    win, wdo, di, times = win[:n], wdo[:n], di[:n], times[:n]

    bar_mins = np.array([bmn(t) for t in times])

    # ── NWE sobre o preço WIN (idêntico ao V4 original) ──
    nwe, upper, lower = calc_nwe(win, NWE_BW, NWE_LB, NWE_MAE)
    is_up = np.zeros(n, dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True

    # ── Z-Scores WDO (Kalman idêntico ao V4) ──
    print("Processando Kalman WDO...")
    kf_wdo = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=1e-4, obs_cov=1e2)
    sp_wdo = []; kb_wdo = []
    for y, x in zip(win, wdo):
        beta, s, _ = kf_wdo.update(float(y), float(x))
        sp_wdo.append(s); kb_wdo.append(beta)
    z_wdo = np.array(KalmanBetaFilter.rolling_zscore(sp_wdo, window=40))
    kb_wdo = np.array(kb_wdo)

    # ── Z-Scores DI (Kalman idêntico ao V4) ──
    print("Processando Kalman DI...")
    kf_di = KalmanBetaFilter(initial_beta=DI_BETA_INITIAL, trans_cov=1e-3, obs_cov=1e1)
    sp_di = []; kb_di = []
    for y, x in zip(win, di):
        beta, s, _ = kf_di.update(float(y), float(x))
        sp_di.append(s); kb_di.append(beta)
    z_di = np.array(KalmanBetaFilter.rolling_zscore(sp_di, window=60))
    kb_di = np.array(kb_di)

    # ── Johansen rolling ──
    print("Processando Johansen WDO...")
    jg_wdo, jb_wdo = calc_johansen_array(win, wdo, n)
    pct_open_wdo = np.sum(jg_wdo) / n * 100

    print("Processando Johansen DI...")
    jg_di, jb_di = calc_johansen_array(win, di, n)
    pct_open_di = np.sum(jg_di) / n * 100

    # ══════════════════════════════════════════════════════════════════════════
    #  BATERIA 1: V4 PURO (sem Johansen)
    # ══════════════════════════════════════════════════════════════════════════
    print("\nExecutando Bateria 1 (V4 Puro)...")
    pnl_wdo1 = simulate_with_nwe(z_wdo, win, bar_mins, is_up, upper, lower)
    pnl_di1  = simulate_with_nwe(z_di,  win, bar_mins, is_up, upper, lower)
    pnl_cn1  = simulate_consensus_with_nwe(z_wdo, z_di, win, bar_mins, is_up, upper, lower)
    pnl_cp1  = simulate_consensus_no_nwe(z_wdo, z_di, win, bar_mins)

    # ══════════════════════════════════════════════════════════════════════════
    #  BATERIA 2: V4 + Johansen Gate
    # ══════════════════════════════════════════════════════════════════════════
    print("Executando Bateria 2 (V4 + Johansen Gate)...")
    pnl_wdo2 = simulate_with_nwe(z_wdo, win, bar_mins, is_up, upper, lower,
                                  kb_wdo, jg_wdo, jb_wdo, use_johansen=True)
    pnl_di2  = simulate_with_nwe(z_di,  win, bar_mins, is_up, upper, lower,
                                  kb_di, jg_di, jb_di, use_johansen=True)
    pnl_cn2  = simulate_consensus_with_nwe(z_wdo, z_di, win, bar_mins, is_up, upper, lower,
                                            kb_wdo, jg_wdo, jb_wdo,
                                            kb_di, jg_di, jb_di, use_johansen=True)
    pnl_cp2  = simulate_consensus_no_nwe(z_wdo, z_di, win, bar_mins,
                                          kb_wdo, jg_wdo, jb_wdo,
                                          kb_di, jg_di, jb_di, use_johansen=True)

    # ── Stats ──
    s_w1, s_d1, s_cn1, s_cp1 = stats(pnl_wdo1), stats(pnl_di1), stats(pnl_cn1), stats(pnl_cp1)
    s_w2, s_d2, s_cn2, s_cp2 = stats(pnl_wdo2), stats(pnl_di2), stats(pnl_cn2), stats(pnl_cp2)

    # Portfolios
    p1 = pnl_wdo1 + pnl_di1 + pnl_cp1
    p2 = pnl_wdo2 + pnl_di2 + pnl_cp2
    sp1, sp2 = stats(p1), stats(p2)

    hdr = f"{'Setup':<25} | {'Trades':>6} | {'WR':>6} | {'PnL':>10} | {'Max DD':>9} | {'PF':>5} | {'Ret/DD':>7}"
    sep = "-" * 85

    def row(name, s):
        return f"{name:<25} | {s['trades']:>6} | {s['wr']:>5.1f}% | R${s['pnl']:>8.0f} | R${s['dd']:>7.0f} | {s['pf']:>5.2f} | {s['ret_dd']:>6.2f}x"

    print("\n" + "=" * 85)
    print(">>> BATERIA 1: MATADOR V4 (SEM JOHANSEN)")
    print(sep)
    print(hdr)
    print(sep)
    print(row("WDO Kalman (+NWE)", s_w1))
    print(row("DI Kalman (+NWE)", s_d1))
    print(row("Consenso COM NWE", s_cn1))
    print(row("Consenso SEM NWE (puro)", s_cp1))
    print(sep)
    print(row("PORT WDO+DI+CONS(puro)", sp1))

    print("\n" + "=" * 85)
    print(">>> BATERIA 2: MATADOR V4 + JOHANSEN GATE")
    print(f"    [Johansen aberto: WDO={pct_open_wdo:.1f}% | DI={pct_open_di:.1f}%]")
    print(sep)
    print(hdr)
    print(sep)
    print(row("WDO Kalman (+NWE+JOH)", s_w2))
    print(row("DI Kalman (+NWE+JOH)", s_d2))
    print(row("Consenso COM NWE+JOH", s_cn2))
    print(row("Consenso SEM NWE+JOH", s_cp2))
    print(sep)
    print(row("PORT WDO+DI+CONS+JOH", sp2))
    print("=" * 85)

    # ══════════════════════════════════════════════════════════════════════════
    #  GERAR REPORT V5 + GRÁFICO
    # ══════════════════════════════════════════════════════════════════════════
    OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".planning", "docs", "assets")
    os.makedirs(OUT, exist_ok=True)

    # --- Portfolios adicionais ---
    port_2_1 = pnl_wdo1 + pnl_di1  # WDO+DI sem consenso
    sp2_1 = stats(port_2_1)
    port_3n_1 = pnl_wdo1 + pnl_di1 + pnl_cn1  # WDO+DI+CONS(NWE)
    sp3n_1 = stats(port_3n_1)

    # --- Markdown Report ---
    report_path = os.path.join(OUT, "REPORT_MATADOR_V5.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 📊 Relatório de Backtest — Setup Matador V5\n\n")
        f.write(f"Período: **{BARS:,} barras M5** (~1.2 anos de pregão intraday)\n\n")
        f.write("Motor: `run_matador_v5_johansen.py` | Kalman + NWE + Johansen Gate\n\n")
        f.write("## 1. Desempenho por Setup Individual (Bateria 1 — V4 Puro)\n\n")
        f.write("| Setup | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |\n")
        f.write("|-------|----------|-------------|--------|---------------|--------|----------|\n")
        for name, s in [("WDO Kalman (+NWE)", s_w1), ("DI Kalman (+NWE)", s_d1),
                         ("Consenso COM NWE", s_cn1), ("Consenso SEM NWE (puro)", s_cp1)]:
            f.write(f"| {name} | R${s['pnl']:.0f} | R${s['dd']:.0f} | {s['ret_dd']:.2f}x | {s['pf']:.2f} | {s['trades']} | {s['wr']:.1f}% |\n")

        f.write("\n## 2. Desempenho do Portfólio (Bateria 1 — V4 Puro)\n\n")
        f.write("| Portfólio | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |\n")
        f.write("|-----------|----------|-------------|--------|---------------|--------|----------|\n")
        for name, s in [("PORT WDO+DI (sem cons)", sp2_1),
                         ("PORT WDO+DI+CONS(NWE)", sp3n_1),
                         ("PORT WDO+DI+CONS(puro)", sp1)]:
            f.write(f"| {name} | R${s['pnl']:.0f} | R${s['dd']:.0f} | {s['ret_dd']:.2f}x | {s['pf']:.2f} | {s['trades']} | {s['wr']:.1f}% |\n")

        f.write("\n## 3. Desempenho com Johansen Gate (Bateria 2)\n\n")
        f.write(f"Johansen aberto: WDO={pct_open_wdo:.1f}% | DI={pct_open_di:.1f}%\n\n")
        f.write("| Setup | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |\n")
        f.write("|-------|----------|-------------|--------|---------------|--------|----------|\n")
        for name, s in [("WDO Kalman (+NWE+JOH)", s_w2), ("DI Kalman (+NWE+JOH)", s_d2),
                         ("Consenso COM NWE+JOH", s_cn2), ("Consenso SEM NWE+JOH", s_cp2)]:
            f.write(f"| {name} | R${s['pnl']:.0f} | R${s['dd']:.0f} | {s['ret_dd']:.2f}x | {s['pf']:.2f} | {s['trades']} | {s['wr']:.1f}% |\n")

        f.write(f"\n## 4. Conclusão\n\n")
        f.write(f"O Johansen Gate **sufoca** o setup, reduzindo de {sp1['trades']} trades para {sp2['trades']} ")
        f.write(f"e o PnL de R${sp1['pnl']:.0f} para R${sp2['pnl']:.0f}. ")
        f.write(f"A configuração V4 Pura (Kalman + NWE) continua sendo a melhor abordagem.\n\n")
        f.write("## 5. Curva de Capital (Equity Curve)\n\n")
        f.write("![Equity Curve V5](./portfolio_v5_advanced.png)\n")

    print(f"\n[REPORT] {report_path}")

    # --- Gráfico Avançado (mesma estrutura do V4) ---
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(22, 12))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1])

    # Top Left: Portfolio com 3 setups
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(np.cumsum(pnl_wdo1), color='#c8a444', alpha=0.5, linewidth=1, label=f"WDO (R${s_w1['pnl']:.0f})")
    ax1.plot(np.cumsum(pnl_di1), color='#8a6dff', alpha=0.5, linewidth=1, label=f"DI (R${s_d1['pnl']:.0f})")
    ax1.plot(np.cumsum(pnl_cp1), color='#00e87a', alpha=0.5, linewidth=1, label=f"CONS puro (R${s_cp1['pnl']:.0f})")
    port_eq = np.cumsum(p1)
    ax1.plot(port_eq, color='white', linewidth=2.5, label=f"PORTFOLIO TOTAL (R${sp1['pnl']:.0f})")
    running_max = np.maximum.accumulate(port_eq)
    drawdown = running_max - port_eq
    ax1.fill_between(range(len(port_eq)), port_eq, running_max, color='#ff3860', alpha=0.3, label="Drawdown")
    ax1.set_title(f"Curva de Capital do Portfólio (Ret/DD: {sp1['ret_dd']:.2f}x | PF: {sp1['pf']:.2f})", fontsize=14, pad=10)
    ax1.set_ylabel("PnL Acumulado (R$)")
    ax1.legend(loc="upper left", fontsize=10, framealpha=0.7)
    ax1.grid(alpha=0.15, linestyle='--')

    # Top Right: Consenso COM vs SEM NWE
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(np.cumsum(pnl_cn1), color='#ff69b4', alpha=0.8, linewidth=2, label=f"Cons COM NWE (R${s_cn1['pnl']:.0f} | {s_cn1['ret_dd']:.1f}x)")
    ax2.plot(np.cumsum(pnl_cp1), color='#00e87a', alpha=0.8, linewidth=2, label=f"Cons SEM NWE (R${s_cp1['pnl']:.0f} | {s_cp1['ret_dd']:.1f}x)")
    ax2.set_title("Efeito do Filtro NWE no Consenso", fontsize=14, pad=10)
    ax2.legend(loc="upper left", fontsize=10, framealpha=0.7)
    ax2.grid(alpha=0.15, linestyle='--')

    # Bottom Left: Drawdown Profile
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.fill_between(range(len(drawdown)), 0, -drawdown, color='#ff3860', alpha=0.6)
    ax3.plot(-drawdown, color='#ff3860', linewidth=1)
    ax3.set_title(f"Perfil de Drawdown (Max: R$-{sp1['dd']:.0f})", fontsize=12, pad=10)
    ax3.set_ylabel("Drawdown (R$)")
    ax3.set_xlabel("Barras (M5)")
    ax3.grid(alpha=0.15, linestyle='--')

    # Bottom Right: Contribuição por Setup
    ax4 = fig.add_subplot(gs[1, 1])
    labels = ['WDO', 'DI', 'CONS (puro)', 'CONS (NWE)']
    pnls = [s_w1['pnl'], s_d1['pnl'], s_cp1['pnl'], s_cn1['pnl']]
    colors = ['#c8a444', '#8a6dff', '#00e87a', '#ff69b4']
    bars_chart = ax4.bar(labels, pnls, color=colors, alpha=0.8, width=0.5)
    ax4.set_title("Contribuição por Setup (PnL)", fontsize=12, pad=10)
    ax4.set_ylabel("PnL (R$)")
    ax4.grid(alpha=0.15, axis='y', linestyle='--')
    for bar in bars_chart:
        yval = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2, yval + 200, f'R${yval:.0f}', ha='center', va='bottom', color='white', fontweight='bold')

    fig.suptitle(f"Análise Avançada de Portfólio — Matador V5 ({BARS:,} barras M5)", fontsize=18, y=0.98, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    img_path = os.path.join(OUT, "portfolio_v5_advanced.png")
    fig.savefig(img_path, dpi=150)
    plt.close(fig)
    print(f"[CHART] {img_path}")

if __name__ == "__main__":
    main()
