"""
Matador V5 Backtest — VALIDATION CANDIDATE (TASK-3 AC #15)
============================================================
Production-validation backtest reconciliado com core/config.py + o motor
em core/trade_engine.py. Hardened em slice 6b (TASK-3) com:

  - Slippage WIN: cfg.WIN_SLIPPAGE_PTS por lado (entrada + saída).
  - Custos B3: cfg.B3_COST_PER_CONTRACT_RT × cfg.WIN_CONTRACTS por trade.
  - Rollover gap: trades que cruzam barra com retorno > 5σ recente são
    descartados (heurística — runbook docs/RUNBOOK_ROLLOVER.md cobre
    detecção manual via calendário B3).

Diferente dos demais scripts em research/ (todos carimbados como
"research exploratório" — ver docs/PARAM_PROFILE.md §2), este consome
core/config.py como fonte única de verdade. Qualquer constante de
trade aqui vem de cfg; nada é hardcoded.

Período: 35.000 barras M5 (~1.2 anos)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core import config as cfg

# ─── Parâmetros canônicos (todos vindos de core/config.py) ───────────────────
SYMBOL_A, SYMBOL_B, DI_SYMBOL = cfg.SYMBOL_A, cfg.SYMBOL_B, cfg.DI_SYMBOL
TIMEFRAME, MT5_PATH = cfg.TIMEFRAME, cfg.MT5_PATH
BETA_INITIAL, DI_BETA_INITIAL = cfg.BETA_INITIAL, cfg.DI_BETA_INITIAL

Z_ENT, Z_ATT = cfg.Z_ENTRY, cfg.Z_ATTENTION
# Live engine has separate BUY/SELL sides; this backtest uses BUY values
# symmetrically (matches the actual cfg.BUY_* == cfg.SELL_* equality today).
SL, TP, BE = cfg.BUY_SL, cfg.BUY_TP, cfg.BUY_BE_ACT
FC = cfg.FORCE_CLOSE_H * 60 + cfg.FORCE_CLOSE_M
SM = cfg.ENTRY_START_H * 60 + cfg.ENTRY_START_M
EM = cfg.ENTRY_END_H * 60 + cfg.ENTRY_END_M
NWE_BW, NWE_LB = cfg.NWE_BANDWIDTH, cfg.NWE_LOOKBACK
NWE_MAE, NWE_BM = cfg.NWE_MULT_MAE, cfg.NWE_BAND_MULT

JOH_WINDOW = cfg.JOH_WINDOW
JOH_RECHECK = cfg.JOH_RECHECK_BARS
BETA_TOLERANCE = cfg.JOH_BETA_TOLERANCE

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

# ─── Cost model + rollover gap detection (TASK-3 AC #15) ────────────────────
#
# Exit-fill convention: simulators close at the *actual* `pts_favor` of the
# triggering bar (i.e. `d` at the bar that breached TP / -SL / BE_LOCK), not
# at the threshold itself. This matches `core.trade_engine._handle_open` which
# realizes `pnl = pts_favor * WIN_CONTRACTS * WIN_PV` once `pts_favor >= tp`
# (or `<= -sl`, etc.). Pre-slice-6c the backtest hardcoded TP/-SL/0 — that
# overstated winners (overshoot) and understated losers (undershoot below SL),
# breaking AC #16 paridade.

def _pnl_brl_close(pts_gross):
    """Convert gross point P&L of a closed trade to realized BRL.

    `pts_gross` is the actual `pts_favor` at the bar that triggered the exit
    (positive for favorable, negative for stop). Applies cfg.WIN_SLIPPAGE_PTS
    on each side (2× total) and round-trip cfg.B3_COST_PER_CONTRACT_RT ×
    cfg.WIN_CONTRACTS. Slippage is subtracted regardless of sign — the
    operator pays it on both entries and exits.
    """
    pts_net = pts_gross - 2 * cfg.WIN_SLIPPAGE_PTS
    gross_brl = pts_net * cfg.WIN_PV * cfg.WIN_CONTRACTS
    cost_brl = cfg.B3_COST_PER_CONTRACT_RT * cfg.WIN_CONTRACTS
    return gross_brl - cost_brl

def _detect_rollover_bars(prices, sigma_window=500, sigma_mult=5.0):
    """Heuristic rollover detector for continuous symbols (WIN$N/WDO$N/DI1$N).

    On a continuous symbol, MT5 stitches the new front-month onto the old
    series at expiry. The resulting bar shows a synthetic gap that does not
    correspond to a fill in the account. We flag any bar whose absolute
    return exceeds `sigma_mult` × the rolling stdev of returns over the
    prior `sigma_window` bars. The simulator discards trades crossing
    these bars (returns 0 P&L for that trade — see AC #15).

    Limitations: this is a price heuristic, not a calendar lookup. It
    will catch most rollover gaps and very large news moves alike. The
    runbook (docs/RUNBOOK_ROLLOVER.md) documents the manual calendar
    process; a calendar-aware detector is future work.
    """
    n = len(prices)
    rollover = np.zeros(n, dtype=bool)
    if n < 2:
        return rollover
    rets = np.zeros(n)
    rets[1:] = np.abs(np.diff(prices)) / np.maximum(np.abs(prices[:-1]), 1e-9)
    for i in range(sigma_window, n):
        sigma = np.std(rets[i - sigma_window:i]) + 1e-12
        if rets[i] > sigma_mult * sigma:
            rollover[i] = True
    return rollover

# ─── Simulações (réplica exata do V4) ───────────────────────────────────────

def simulate_with_nwe(z, win_c, bar_mins, is_up, upper, lower,
                      rollover_mask,
                      kalman_betas=None, joh_gates=None, joh_betas=None,
                      use_johansen=False):
    """WDO/DI isolado — COM filtro NWE. Lógica do plot_portfolio_v4 +
    custos (slippage + B3) e descarte de trades cruzando rollover.

    Returns (pnl, n_discarded). n_discarded counts open trades that were
    closed flat by a rollover bar (AC #15 transparency)."""
    n = len(win_c); pnl = np.zeros(n)
    pos = 0; ep = 0.0; bh = False; n_discarded = 0
    for i in range(1000, n):
        p = win_c[i]; tm = bar_mins[i]
        if pos != 0 and rollover_mask[i]:
            pos = 0; n_discarded += 1; continue  # AC #15: discard trade crossing rollover
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p)
            pnl[i] = _pnl_brl_close(d); pos = 0; continue
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
            if d >= TP: pnl[i] = _pnl_brl_close(d); pos = 0
            elif bh and d <= 0: pnl[i] = _pnl_brl_close(d); pos = 0
            elif not bh and d <= -SL: pnl[i] = _pnl_brl_close(d); pos = 0
    return pnl, n_discarded

def simulate_consensus_no_nwe(z_wdo, z_di, win_c, bar_mins, rollover_mask,
                               kb_wdo=None, jg_wdo=None, jb_wdo=None,
                               kb_di=None, jg_di=None, jb_di=None,
                               use_johansen=False):
    """Consenso PURO — SEM filtro NWE, só z-scores alinhados.
    Inclui custos + descarte por rollover (AC #15).

    Returns (pnl, n_discarded)."""
    n = len(win_c); pnl = np.zeros(n)
    pos = 0; ep = 0.0; bh = False; n_discarded = 0
    for i in range(1000, n):
        p = win_c[i]; tm = bar_mins[i]
        if pos != 0 and rollover_mask[i]:
            pos = 0; n_discarded += 1; continue
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p)
            pnl[i] = _pnl_brl_close(d); pos = 0; continue

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
            if d >= TP: pnl[i] = _pnl_brl_close(d); pos = 0
            elif bh and d <= 0: pnl[i] = _pnl_brl_close(d); pos = 0
            elif not bh and d <= -SL: pnl[i] = _pnl_brl_close(d); pos = 0
    return pnl, n_discarded

def simulate_consensus_with_nwe(z_wdo, z_di, win_c, bar_mins, is_up, upper, lower,
                                 rollover_mask,
                                 kb_wdo=None, jg_wdo=None, jb_wdo=None,
                                 kb_di=None, jg_di=None, jb_di=None,
                                 use_johansen=False):
    """Consenso COM filtro NWE. Inclui custos + descarte por rollover.

    Returns (pnl, n_discarded)."""
    n = len(win_c); pnl = np.zeros(n)
    pos = 0; ep = 0.0; bh = False; n_discarded = 0
    for i in range(1000, n):
        p = win_c[i]; tm = bar_mins[i]
        if pos != 0 and rollover_mask[i]:
            pos = 0; n_discarded += 1; continue
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p)
            pnl[i] = _pnl_brl_close(d); pos = 0; continue

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
            if d >= TP: pnl[i] = _pnl_brl_close(d); pos = 0
            elif bh and d <= 0: pnl[i] = _pnl_brl_close(d); pos = 0
            elif not bh and d <= -SL: pnl[i] = _pnl_brl_close(d); pos = 0
    return pnl, n_discarded

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

    # ── Z-Scores WDO (Kalman ← cfg.WDO_KALMAN_*) ──
    print("Processando Kalman WDO...")
    kf_wdo = KalmanBetaFilter(initial_beta=BETA_INITIAL,
                              trans_cov=cfg.WDO_KALMAN_Q,
                              obs_cov=cfg.WDO_KALMAN_R)
    sp_wdo = []; kb_wdo = []
    for y, x in zip(win, wdo):
        beta, s, _ = kf_wdo.update(float(y), float(x))
        sp_wdo.append(s); kb_wdo.append(beta)
    z_wdo = np.array(KalmanBetaFilter.rolling_zscore(sp_wdo, window=cfg.WDO_KALMAN_W))
    kb_wdo = np.array(kb_wdo)

    # ── Z-Scores DI (Kalman ← cfg.DI_KALMAN_*) ──
    print("Processando Kalman DI...")
    kf_di = KalmanBetaFilter(initial_beta=DI_BETA_INITIAL,
                             trans_cov=cfg.DI_KALMAN_Q,
                             obs_cov=cfg.DI_KALMAN_R)
    sp_di = []; kb_di = []
    for y, x in zip(win, di):
        beta, s, _ = kf_di.update(float(y), float(x))
        sp_di.append(s); kb_di.append(beta)
    z_di = np.array(KalmanBetaFilter.rolling_zscore(sp_di, window=cfg.DI_KALMAN_W))
    kb_di = np.array(kb_di)

    # ── Rollover gap detection (TASK-3 AC #15) ──
    # Mark bars where any of the three continuous symbols shows a return
    # > 5σ vs the rolling stdev. Trades crossing such bars are discarded.
    rollover_mask = (
        _detect_rollover_bars(win)
        | _detect_rollover_bars(wdo)
        | _detect_rollover_bars(di)
    )
    n_rollover = int(rollover_mask.sum())
    print(f"Rollover bars flagged: {n_rollover} ({100.0 * n_rollover / n:.2f}% of {n})")

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
    pnl_wdo1, dq_wdo1 = simulate_with_nwe(z_wdo, win, bar_mins, is_up, upper, lower, rollover_mask)
    pnl_di1,  dq_di1  = simulate_with_nwe(z_di,  win, bar_mins, is_up, upper, lower, rollover_mask)
    pnl_cn1,  dq_cn1  = simulate_consensus_with_nwe(z_wdo, z_di, win, bar_mins, is_up, upper, lower, rollover_mask)
    pnl_cp1,  dq_cp1  = simulate_consensus_no_nwe(z_wdo, z_di, win, bar_mins, rollover_mask)

    # ══════════════════════════════════════════════════════════════════════════
    #  BATERIA 2: V4 + Johansen Gate
    # ══════════════════════════════════════════════════════════════════════════
    print("Executando Bateria 2 (V4 + Johansen Gate)...")
    pnl_wdo2, dq_wdo2 = simulate_with_nwe(z_wdo, win, bar_mins, is_up, upper, lower, rollover_mask,
                                          kb_wdo, jg_wdo, jb_wdo, use_johansen=True)
    pnl_di2,  dq_di2  = simulate_with_nwe(z_di,  win, bar_mins, is_up, upper, lower, rollover_mask,
                                          kb_di, jg_di, jb_di, use_johansen=True)
    pnl_cn2,  dq_cn2  = simulate_consensus_with_nwe(z_wdo, z_di, win, bar_mins, is_up, upper, lower, rollover_mask,
                                                    kb_wdo, jg_wdo, jb_wdo,
                                                    kb_di, jg_di, jb_di, use_johansen=True)
    pnl_cp2,  dq_cp2  = simulate_consensus_no_nwe(z_wdo, z_di, win, bar_mins, rollover_mask,
                                                  kb_wdo, jg_wdo, jb_wdo,
                                                  kb_di, jg_di, jb_di, use_johansen=True)

    discarded_b1 = dq_wdo1 + dq_di1 + dq_cn1 + dq_cp1
    discarded_b2 = dq_wdo2 + dq_di2 + dq_cn2 + dq_cp2
    print(f"Trades discarded by rollover — Bateria 1: {discarded_b1} | Bateria 2: {discarded_b2}")

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

        f.write(f"\n## 4. Comparativo Bateria 1 × Bateria 2\n\n")
        f.write(f"O Johansen Gate reduz de {sp1['trades']} para {sp2['trades']} trades ")
        f.write(f"e o PnL realizado de R${sp1['pnl']:.0f} para R${sp2['pnl']:.0f}. ")
        f.write(f"P&L está líquido de slippage ({cfg.WIN_SLIPPAGE_PTS} pts/lado) e ")
        f.write(f"custos B3 (R${cfg.B3_COST_PER_CONTRACT_RT:.2f}/contrato/RT). ")
        f.write(f"Rollover: {n_rollover} barras sinalizadas ({100.0 * n_rollover / n:.2f}%); ")
        f.write(f"trades descartados por cruzamento — Bateria 1: {discarded_b1}, Bateria 2: {discarded_b2}.\n\n")
        f.write("## 5. Curva de Capital (Equity Curve)\n\n")
        f.write("![Equity Curve V5](./portfolio_v5_advanced.png)\n")

    print(f"\n[REPORT] {report_path}")

    # --- JSON sidecar for AC #16 reconciliation (slice 6c) ---
    # `pnl` in `stats` is already net (cost-adjusted by _pnl_brl_close).
    # Gross is recovered analytically: gross = net + trades × per-trade cost,
    # where per-trade cost = 2·WIN_SLIPPAGE_PTS·WIN_PV·WIN_CONTRACTS +
    # B3_COST_PER_CONTRACT_RT·WIN_CONTRACTS. Keeps the simulator hot-path
    # cheap (no second pnl array) while still exposing both numbers.
    per_trade_cost_brl = (
        2 * cfg.WIN_SLIPPAGE_PTS * cfg.WIN_PV * cfg.WIN_CONTRACTS
        + cfg.B3_COST_PER_CONTRACT_RT * cfg.WIN_CONTRACTS
    )

    # Per-bar dates so the reconciler can filter both sides by the same
    # window (codex round-10 finding: prior sidecar was a 1.2-year aggregate
    # that couldn't be sliced). Skip the warmup tail (i < 1000 in simulators).
    bar_dates = [datetime.fromtimestamp(int(t)).date().isoformat()
                 for t in times]

    def _daily_aggregate(pnl):
        """Bucket non-zero pnl entries by close-bar date.
        Returns sorted list of {date, trades, pnl_brl_net, pnl_brl_gross}."""
        buckets = {}
        for i in range(1000, len(pnl)):
            v = pnl[i]
            if v == 0:
                continue
            d = bar_dates[i]
            b = buckets.setdefault(d, [0, 0.0])
            b[0] += 1
            b[1] += float(v)
        out = []
        for d in sorted(buckets):
            t, net = buckets[d]
            out.append({
                "date": d,
                "trades": t,
                "pnl_brl_net": net,
                "pnl_brl_gross": net + t * per_trade_cost_brl,
            })
        return out

    def _summary_pair(s, discarded, pnl_array):
        return {
            "trades": int(s["trades"]),
            "pnl_brl_net": float(s["pnl"]),
            "pnl_brl_gross": float(s["pnl"] + s["trades"] * per_trade_cost_brl),
            "win_rate_pct": float(s["wr"]),
            "max_dd_brl": float(s["dd"]),
            "rollover_discarded": int(discarded),
            "daily": _daily_aggregate(pnl_array),
        }

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "bars_total": int(n),
        "bars_used": int(BARS),
        "first_bar_date": bar_dates[0] if bar_dates else None,
        "last_bar_date": bar_dates[-1] if bar_dates else None,
        "rollover_bars_flagged": int(n_rollover),
        "cost_model": {
            "slippage_pts_per_side": cfg.WIN_SLIPPAGE_PTS,
            "b3_cost_per_contract_rt_brl": cfg.B3_COST_PER_CONTRACT_RT,
            "win_contracts": cfg.WIN_CONTRACTS,
            "win_pv_brl_per_pt": cfg.WIN_PV,
            "per_trade_cost_brl": per_trade_cost_brl,
        },
        "bateria_1_v4_puro": {
            "wdo_nwe": _summary_pair(s_w1, dq_wdo1, pnl_wdo1),
            "di_nwe": _summary_pair(s_d1, dq_di1, pnl_di1),
            "consenso_nwe": _summary_pair(s_cn1, dq_cn1, pnl_cn1),
            "consenso_puro": _summary_pair(s_cp1, dq_cp1, pnl_cp1),
            "portfolio_wdo_di_cons_puro": _summary_pair(sp1, discarded_b1, p1),
        },
        "bateria_2_johansen_gate": {
            "wdo_nwe": _summary_pair(s_w2, dq_wdo2, pnl_wdo2),
            "di_nwe": _summary_pair(s_d2, dq_di2, pnl_di2),
            "consenso_nwe": _summary_pair(s_cn2, dq_cn2, pnl_cn2),
            "consenso_puro": _summary_pair(s_cp2, dq_cp2, pnl_cp2),
            "portfolio_wdo_di_cons_puro": _summary_pair(sp2, discarded_b2, p2),
        },
    }
    summary_path = os.path.join(OUT, "portfolio_v5_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[SUMMARY] {summary_path}")

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
