"""
DI Reoptimization — Phase 1 (Diagnostic) + Phase 2 (Kalman vs Johansen Grid)
=============================================================================
Phase 1: Quick diagnostic stats
Phase 2: Grid search for best DI model
  Model A: Kalman (45 combos)
  Model B: Johansen (126 combos)
  Model C: Hybrid Kalman+Johansen (top5 × top3)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

# ── Fixed params ──
Z_ENT = 1.4
TP, SL, BE = 800, 300, 300
WIN_PV = 0.20
FC = 17*60+40; SM = 9*60; EM = 15*60
NWE_BW, NWE_LB, NWE_MAE = 8, 95, 3.0
NWE_BM = 0.10

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

def simulate_di(z_di, win_c, bar_mins, is_up, upper, lower):
    """Simulate DI strategy with fixed SL/TP/BE and NWE filter."""
    n = len(win_c); pnl = np.zeros(n)
    pos = 0; ep = 0.0; bh = False

    for i in range(1000, n):
        p = win_c[i]; tm = bar_mins[i]
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p)
            pnl[i] = d * WIN_PV; pos = 0; continue

        sb = (z_di[i] <= -Z_ENT)
        ss = (z_di[i] >= Z_ENT)

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
            if d >= TP: pnl[i] = TP*WIN_PV; pos = 0
            elif bh and d <= 0: pnl[i] = 0; pos = 0
            elif not bh and d <= -SL: pnl[i] = -SL*WIN_PV; pos = 0
    return pnl

def stats(pa):
    t = pa[pa != 0]; n = len(t)
    if n == 0: return {'pnl':0,'trades':0,'wr':0,'dd':0,'ret_dd':0}
    tp = np.sum(t); w = np.sum(t > 0); wr = w/n*100
    c = np.cumsum(t); mx = np.maximum.accumulate(c); dd = np.max(mx - c)
    if dd < 1e-5: dd = 1.0
    return {'pnl':tp, 'trades':n, 'wr':wr, 'dd':dd, 'ret_dd':tp/dd}

# ── Z-score builders ──
def build_kalman_zscore(win, di, kq, kr, kw, beta_init=-10000.0):
    """Build z-score for WIN×DI using Kalman filter."""
    kf = KalmanBetaFilter(initial_beta=beta_init, trans_cov=kq, obs_cov=kr)
    spreads = []
    for y, x in zip(win, di):
        _, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
    return np.array(KalmanBetaFilter.rolling_zscore(spreads, window=kw))

def build_johansen_zscore(win, di, jw, jzw, recheck):
    """Build z-score for WIN×DI using Johansen cointegration."""
    n = len(win)
    betas = np.zeros(n)
    for i in range(jw, n, recheck):
        yd = np.column_stack([win[i-jw:i], di[i-jw:i]])
        try:
            res = coint_johansen(yd, det_order=0, k_ar_diff=1)
            vec = res.evec[:, 0]
            betas[i] = float(vec[1] / vec[0])
        except:
            betas[i] = betas[i-1] if i > 0 else 0
    for i in range(jw, n):
        if betas[i] == 0: betas[i] = betas[i-1]
    spread = win + betas * di
    z = np.zeros(n)
    for i in range(jw + jzw, n):
        ws = spread[i-jzw:i]; mu, sd = np.mean(ws), np.std(ws)
        z[i] = (spread[i] - mu) / (sd if sd > 1e-10 else 1.0)
    return z, betas

def main():
    print("=" * 80)
    print("DI REOPTIMIZATION — Phase 1 + 2")
    print("=" * 80)

    # Load data
    print("\nCarregando MT5 (100k barras)...")
    mt5.initialize(path=MT5_PATH)
    rw = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 100000)
    rd = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, 100000)
    rdi = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, 100000)
    mt5.shutdown()

    win = np.array([r[4] for r in rw], dtype=float)
    wdo = np.array([r[4] for r in rd], dtype=float)
    di = np.array([r[4] for r in rdi], dtype=float)
    times = np.array([r[0] for r in rw], dtype=np.int64)
    n = min(len(win), len(wdo), len(di))
    win, wdo, di, times = win[:n], wdo[:n], di[:n], times[:n]
    print(f"Barras alinhadas: {n}")

    # Pre-compute NWE (fixed)
    print(f"NWE fixo: LB={NWE_LB}, BM={NWE_BM}")
    nwe, upper, lower = calc_nwe(win, NWE_BW, NWE_LB, NWE_MAE)
    is_up = np.zeros(n, dtype=bool); is_up[1:] = nwe[1:] >= nwe[:-1]; is_up[0] = True
    bar_mins = np.array([bmn(t) for t in times])

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 1: Quick diagnostic
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE 1 — DIAGNOSTICO")
    print("=" * 80)

    # Current Johansen baseline
    z_joh_base, betas_base = build_johansen_zscore(win, di, 150, 60, 12)
    s_base = stats(simulate_di(z_joh_base, win, bar_mins, is_up, upper, lower))
    print(f"\nBaseline Johansen (JW=150, ZW=60, RC=12):")
    print(f"  PnL: R${s_base['pnl']:.0f} | DD: R${s_base['dd']:.0f} | Ret/DD: {s_base['ret_dd']:.2f} | Trades: {s_base['trades']} | WR: {s_base['wr']:.1f}%")

    # Beta stability
    valid_betas = betas_base[betas_base != 0]
    print(f"\nBeta Johansen: mean={np.mean(valid_betas):.2f}, std={np.std(valid_betas):.2f}, "
          f"min={np.min(valid_betas):.2f}, max={np.max(valid_betas):.2f}")

    # Z-score distribution
    z_valid = z_joh_base[z_joh_base != 0]
    print(f"Z-Score DI: mean={np.mean(z_valid):.3f}, std={np.std(z_valid):.3f}, "
          f"pct_below_-1.4={np.mean(z_valid < -1.4)*100:.1f}%, pct_above_1.4={np.mean(z_valid > 1.4)*100:.1f}%")

    # WDO Kalman baseline for comparison
    z_wdo = build_kalman_zscore(win, wdo, 1e-4, 1e2, 40, BETA_INITIAL)
    z_wdo_valid = z_wdo[z_wdo != 0]
    print(f"Z-Score WDO: mean={np.mean(z_wdo_valid):.3f}, std={np.std(z_wdo_valid):.3f}, "
          f"pct_below_-1.4={np.mean(z_wdo_valid < -1.4)*100:.1f}%, pct_above_1.4={np.mean(z_wdo_valid > 1.4)*100:.1f}%")

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 2A: Kalman Grid (45 combos)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE 2A — GRID KALMAN DI (45 combinacoes)")
    print("=" * 80)

    kq_list = [1e-5, 1e-4, 1e-3]
    kr_list = [1e1, 1e2, 1e3]
    kw_list = [20, 30, 40, 60, 80]

    header = f"{'KQ':>8} | {'KR':>6} | {'KW':>4} | {'PNL':>10} | {'DD':>8} | {'RET/DD':>7} | {'TR':>5} | {'WR':>5}"
    print(header)
    print("-" * len(header))

    kalman_results = []
    for kq in kq_list:
        for kr in kr_list:
            for kw in kw_list:
                z = build_kalman_zscore(win, di, kq, kr, kw, -10000.0)
                pnl = simulate_di(z, win, bar_mins, is_up, upper, lower)
                s = stats(pnl)
                kalman_results.append({'kq':kq, 'kr':kr, 'kw':kw, **s})
                print(f"{kq:>8.0e} | {kr:>6.0e} | {kw:>4} | R${s['pnl']:>8.0f} | R${s['dd']:>5.0f} | {s['ret_dd']:>7.2f} | {s['trades']:>5} | {s['wr']:>4.1f}%")

    kalman_results.sort(key=lambda r: r['ret_dd'], reverse=True)
    print("\nTOP 5 KALMAN (por Ret/DD, min 100 trades):")
    top_kalman = [r for r in kalman_results if r['trades'] >= 100][:5]
    for i, r in enumerate(top_kalman):
        print(f"  {i+1}. KQ={r['kq']:.0e} KR={r['kr']:.0e} KW={r['kw']} | PnL R${r['pnl']:.0f} | DD R${r['dd']:.0f} | Ret/DD {r['ret_dd']:.2f} | {r['trades']} trades | WR {r['wr']:.1f}%")

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 2B: Johansen Grid (126 combos)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE 2B — GRID JOHANSEN DI (126 combinacoes)")
    print("=" * 80)

    jw_list = [80, 100, 120, 150, 200, 250, 300]
    jzw_list = [30, 40, 50, 60, 80, 100]
    rc_list = [6, 12, 24]

    header = f"{'JW':>4} | {'ZW':>4} | {'RC':>3} | {'PNL':>10} | {'DD':>8} | {'RET/DD':>7} | {'TR':>5} | {'WR':>5}"
    print(header)
    print("-" * len(header))

    joh_results = []
    for jw in jw_list:
        for jzw in jzw_list:
            for rc in rc_list:
                z, _ = build_johansen_zscore(win, di, jw, jzw, rc)
                pnl = simulate_di(z, win, bar_mins, is_up, upper, lower)
                s = stats(pnl)
                joh_results.append({'jw':jw, 'jzw':jzw, 'rc':rc, **s})
                print(f"{jw:>4} | {jzw:>4} | {rc:>3} | R${s['pnl']:>8.0f} | R${s['dd']:>5.0f} | {s['ret_dd']:>7.2f} | {s['trades']:>5} | {s['wr']:>4.1f}%")

    joh_results.sort(key=lambda r: r['ret_dd'], reverse=True)
    print("\nTOP 5 JOHANSEN (por Ret/DD, min 100 trades):")
    top_joh = [r for r in joh_results if r['trades'] >= 100][:5]
    for i, r in enumerate(top_joh):
        print(f"  {i+1}. JW={r['jw']} ZW={r['jzw']} RC={r['rc']} | PnL R${r['pnl']:.0f} | DD R${r['dd']:.0f} | Ret/DD {r['ret_dd']:.2f} | {r['trades']} trades | WR {r['wr']:.1f}%")

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 2C: Hybrid — Kalman signal + Johansen gate
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("FASE 2C — HIBRIDO KALMAN+JOHANSEN")
    print("=" * 80)

    # Use top 5 Kalman configs × top 3 Johansen windows as coint gate
    joh_gates = [80, 150, 250]  # small, medium, large

    header = f"{'KQ':>8} | {'KR':>6} | {'KW':>4} | {'JG':>4} | {'PNL':>10} | {'DD':>8} | {'RET/DD':>7} | {'TR':>5} | {'WR':>5}"
    print(header)
    print("-" * len(header))

    hybrid_results = []
    for tk in top_kalman[:5]:
        z_kalman = build_kalman_zscore(win, di, tk['kq'], tk['kr'], tk['kw'], -10000.0)
        for jg in joh_gates:
            # Check cointegration at each recheck point
            coint_valid = np.ones(n, dtype=bool)
            for i in range(jg, n, 12):
                yd = np.column_stack([win[i-jg:i], di[i-jg:i]])
                try:
                    res = coint_johansen(yd, det_order=0, k_ar_diff=1)
                    # Trace stat > critical value at 95%
                    coint_valid[i] = res.lr1[0] > res.cvt[0, 1]
                except:
                    coint_valid[i] = False
            # Forward fill
            for i in range(jg+1, n):
                if i % 12 != 0:
                    coint_valid[i] = coint_valid[i - (i % 12)]

            # Gate: zero out z when not cointegrated
            z_gated = z_kalman.copy()
            z_gated[~coint_valid] = 0

            pnl = simulate_di(z_gated, win, bar_mins, is_up, upper, lower)
            s = stats(pnl)
            hybrid_results.append({'kq':tk['kq'], 'kr':tk['kr'], 'kw':tk['kw'], 'jg':jg, **s})
            print(f"{tk['kq']:>8.0e} | {tk['kr']:>6.0e} | {tk['kw']:>4} | {jg:>4} | R${s['pnl']:>8.0f} | R${s['dd']:>5.0f} | {s['ret_dd']:>7.2f} | {s['trades']:>5} | {s['wr']:>4.1f}%")

    hybrid_results.sort(key=lambda r: r['ret_dd'], reverse=True)

    # ═══════════════════════════════════════════════════════════════════════
    # FINAL COMPARISON
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("RESULTADO FINAL — MELHOR DE CADA MODELO")
    print("=" * 80)

    best_k = top_kalman[0] if top_kalman else None
    best_j = top_joh[0] if top_joh else None
    best_h = ([r for r in hybrid_results if r['trades'] >= 100] or [None])[0]

    if best_k:
        print(f"\nKALMAN:   KQ={best_k['kq']:.0e} KR={best_k['kr']:.0e} KW={best_k['kw']} | PnL R${best_k['pnl']:.0f} | DD R${best_k['dd']:.0f} | Ret/DD {best_k['ret_dd']:.2f} | {best_k['trades']} trades | WR {best_k['wr']:.1f}%")
    if best_j:
        print(f"JOHANSEN: JW={best_j['jw']} ZW={best_j['jzw']} RC={best_j['rc']} | PnL R${best_j['pnl']:.0f} | DD R${best_j['dd']:.0f} | Ret/DD {best_j['ret_dd']:.2f} | {best_j['trades']} trades | WR {best_j['wr']:.1f}%")
    if best_h:
        print(f"HIBRIDO:  KQ={best_h['kq']:.0e} KR={best_h['kr']:.0e} KW={best_h['kw']} JG={best_h['jg']} | PnL R${best_h['pnl']:.0f} | DD R${best_h['dd']:.0f} | Ret/DD {best_h['ret_dd']:.2f} | {best_h['trades']} trades | WR {best_h['wr']:.1f}%")

    # Identify absolute winner
    all_best = []
    if best_k: all_best.append(('KALMAN', best_k))
    if best_j: all_best.append(('JOHANSEN', best_j))
    if best_h: all_best.append(('HIBRIDO', best_h))
    all_best.sort(key=lambda x: x[1]['ret_dd'], reverse=True)

    if all_best:
        winner_name, winner = all_best[0]
        print(f"\n>>> VENCEDOR: {winner_name} com Ret/DD {winner['ret_dd']:.2f}x <<<")

if __name__ == "__main__":
    main()
