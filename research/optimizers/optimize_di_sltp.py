"""
DI Reoptimization — Phase 3: SL/TP/BE Grid for Kalman DI
=========================================================
Winner from Phase 2: KQ=1e-3, KR=1e1, KW=60
Now optimize SL/TP/BE independently for DI.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, DI_SYMBOL, TIMEFRAME, MT5_PATH

# ── Fixed: Best Kalman DI params from Phase 2 ──
DI_KQ, DI_KR, DI_KW = 1e-3, 1e1, 60
DI_BETA_INIT = -10000.0
Z_ENT = 1.4
WIN_PV = 0.20
FC = 17*60+40; SM = 9*60; EM = 15*60
NWE_BW, NWE_LB, NWE_MAE, NWE_BM = 8, 95, 3.0, 0.10

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

def simulate_di(z_di, win_c, bar_mins, is_up, upper, lower, sl, tp, be_act):
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
            if not bh and d >= be_act: bh = True
            if d >= tp: pnl[i] = tp * WIN_PV; pos = 0
            elif bh and d <= 0: pnl[i] = 0; pos = 0
            elif not bh and d <= -sl: pnl[i] = -sl * WIN_PV; pos = 0
    return pnl

def stats(pa):
    t = pa[pa != 0]; n = len(t)
    if n == 0: return {'pnl':0,'trades':0,'wr':0,'dd':0,'ret_dd':0}
    tp = np.sum(t); w = np.sum(t > 0); wr = w/n*100
    c = np.cumsum(t); mx = np.maximum.accumulate(c); dd = np.max(mx - c)
    if dd < 1e-5: dd = 1.0
    return {'pnl':tp, 'trades':n, 'wr':wr, 'dd':dd, 'ret_dd':tp/dd}

def main():
    print("=" * 80)
    print("FASE 3 — GRID SL/TP/BE para DI Kalman (KQ=1e-3, KR=1e1, KW=60)")
    print("=" * 80)

    mt5.initialize(path=MT5_PATH)
    rw = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 100000)
    rdi = mt5.copy_rates_from_pos(DI_SYMBOL, TIMEFRAME, 0, 100000)
    mt5.shutdown()

    win = np.array([r[4] for r in rw], dtype=float)
    di = np.array([r[4] for r in rdi], dtype=float)
    times = np.array([r[0] for r in rw], dtype=np.int64)
    n = min(len(win), len(di))
    win, di, times = win[:n], di[:n], times[:n]

    # Build Kalman z-score for DI
    kf = KalmanBetaFilter(initial_beta=DI_BETA_INIT, trans_cov=DI_KQ, obs_cov=DI_KR)
    spreads = []
    for y, x in zip(win, di):
        _, s, _ = kf.update(float(y), float(x)); spreads.append(s)
    z_di = np.array(KalmanBetaFilter.rolling_zscore(spreads, window=DI_KW))

    # NWE
    nwe, upper, lower = calc_nwe(win, NWE_BW, NWE_LB, NWE_MAE)
    is_up = np.zeros(n, dtype=bool); is_up[1:] = nwe[1:] >= nwe[:-1]; is_up[0] = True
    bar_mins = np.array([bmn(t) for t in times])

    # Grid
    sl_list = [150, 200, 250, 300, 400, 500]
    tp_list = [400, 600, 800, 1000, 1200]
    be_list = [150, 200, 250, 300, 400]

    total = len(sl_list) * len(tp_list) * len(be_list)
    print(f"\nGrid: {len(sl_list)} SL x {len(tp_list)} TP x {len(be_list)} BE = {total} combinacoes\n")

    header = f"{'SL':>4} | {'TP':>5} | {'BE':>4} | {'PNL':>10} | {'DD':>8} | {'RET/DD':>7} | {'TR':>5} | {'WR':>5}"
    print(header)
    print("-" * len(header))

    results = []
    for sl in sl_list:
        for tp in tp_list:
            for be in be_list:
                if be > tp:
                    continue  # BE can't exceed TP
                pnl = simulate_di(z_di, win, bar_mins, is_up, upper, lower, sl, tp, be)
                s = stats(pnl)
                results.append({'sl':sl, 'tp':tp, 'be':be, **s})
                print(f"{sl:>4} | {tp:>5} | {be:>4} | R${s['pnl']:>8.0f} | R${s['dd']:>5.0f} | {s['ret_dd']:>7.2f} | {s['trades']:>5} | {s['wr']:>4.1f}%")

    # Top 10 by Ret/DD
    results.sort(key=lambda r: r['ret_dd'], reverse=True)
    print("\n" + "=" * 80)
    print("TOP 10 POR RET/DD (min 300 trades)")
    print("=" * 80)
    top = [r for r in results if r['trades'] >= 300]
    for i, r in enumerate(top[:10]):
        print(f"  {i+1:2d}. SL={r['sl']:>3} TP={r['tp']:>4} BE={r['be']:>3} | PnL R${r['pnl']:.0f} | DD R${r['dd']:.0f} | Ret/DD {r['ret_dd']:.2f} | {r['trades']} trades | WR {r['wr']:.1f}%")

    # Top 10 by PnL
    results.sort(key=lambda r: r['pnl'], reverse=True)
    print("\n" + "=" * 80)
    print("TOP 10 POR PNL (min 300 trades)")
    print("=" * 80)
    top_pnl = [r for r in results if r['trades'] >= 300]
    for i, r in enumerate(top_pnl[:10]):
        print(f"  {i+1:2d}. SL={r['sl']:>3} TP={r['tp']:>4} BE={r['be']:>3} | PnL R${r['pnl']:.0f} | DD R${r['dd']:.0f} | Ret/DD {r['ret_dd']:.2f} | {r['trades']} trades | WR {r['wr']:.1f}%")

    # Overall winner
    best = [r for r in results if r['trades'] >= 300]
    best.sort(key=lambda r: r['ret_dd'], reverse=True)
    if best:
        w = best[0]
        print(f"\n>>> VENCEDOR: SL={w['sl']} TP={w['tp']} BE={w['be']} | Ret/DD {w['ret_dd']:.2f}x <<<")

if __name__ == "__main__":
    main()
