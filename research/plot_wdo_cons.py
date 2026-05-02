"""WDO + Consensus (sem DI) — LB=95, BandMult=0.10"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from core.kalman_filter import KalmanBetaFilter
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, BETA_INITIAL

K_Q, K_R, K_W = 1e-4, 1e2, 40
J_JW, J_ZW = 150, 60
Z_ENT, Z_ATT = 1.4, 1.2
TP, SL, BE = 800, 300, 300
WIN_PV = 0.20
FC = 17*60+40; SM = 9*60; EM = 15*60
BW, LB, MAE_M, BM = 8, 95, 3.0, 0.10

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".planning", "docs", "assets")

def bmn(ts):
    return datetime.utcfromtimestamp(ts).hour * 60 + datetime.utcfromtimestamp(ts).minute

def nwe_calc(p, bw, lb, mm):
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

def sim(k_z, j_z, wc, bms, mode, iu, up, lo, bm_):
    n = len(wc); pnl = np.zeros(n); pos = 0; ep = 0; bh = False
    for i in range(1000, n):
        p = wc[i]; tm = bms[i]
        if pos != 0 and tm >= FC:
            d = (p-ep) if pos == 1 else (ep-p); pnl[i] = d*WIN_PV; pos = 0; continue
        zw, zd = k_z[i], j_z[i]
        if mode == 'wdo':
            sb, ss = (zw <= -Z_ENT), (zw >= Z_ENT)
        elif mode == 'cons':
            sb = (zw <= -Z_ENT and zd <= -Z_ATT) or (zw <= -Z_ATT and zd <= -Z_ENT)
            ss = (zw >= Z_ENT and zd >= Z_ATT) or (zw >= Z_ATT and zd >= Z_ENT)
        else:
            sb = ss = False
        bww = up[i] - lo[i]
        if bww < 1e-10: bww = 1.0
        u = iu[i]
        if sb:
            if u: sb = False
            elif p > lo[i] + bww * bm_: sb = False
        if ss:
            if not u: ss = False
            elif p < up[i] - bww * bm_: ss = False
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

def main():
    print("Carregando MT5...")
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

    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=K_Q, obs_cov=K_R)
    sp = []
    for y, x in zip(win, wdo):
        _, s, _ = kf.update(float(y), float(x)); sp.append(s)
    k_z = np.array(KalmanBetaFilter.rolling_zscore(sp, window=K_W))

    betas = np.zeros(n)
    for i in range(J_JW, n, 12):
        yd = np.column_stack([win[i-J_JW:i], di[i-J_JW:i]])
        try:
            res = coint_johansen(yd, det_order=0, k_ar_diff=1)
            vec = res.evec[:, 0]; betas[i] = float(vec[1]/vec[0])
        except:
            betas[i] = betas[i-1] if i > 0 else 0
    for i in range(J_JW, n):
        if betas[i] == 0: betas[i] = betas[i-1]
    sdi = win + betas * di
    j_z = np.zeros(n)
    for i in range(J_JW + J_ZW, n):
        ws = sdi[i-J_ZW:i]; mu, sd = np.mean(ws), np.std(ws)
        j_z[i] = (sdi[i] - mu) / (sd if sd > 1e-10 else 1.0)

    nwe, upper, lower = nwe_calc(win, BW, LB, MAE_M)
    is_up = np.zeros(n, dtype=bool); is_up[1:] = nwe[1:] >= nwe[:-1]; is_up[0] = True
    bmins = np.array([bmn(t) for t in times])

    pw = sim(k_z, j_z, win, bmins, 'wdo', is_up, upper, lower, BM)
    pc = sim(k_z, j_z, win, bmins, 'cons', is_up, upper, lower, BM)
    pp = pw + pc

    sw = stats(pw); sc = stats(pc); sp_ = stats(pp)

    print("=" * 75)
    print("PORTFOLIO WDO + CONSENSO (sem DI) -- LB=95, BM=0.10")
    print("=" * 75)
    for name, s in [("WDO Kalman", sw), ("Consenso", sc), ("PORT WDO+CONS", sp_)]:
        print(f"{name:25s} | PnL: R${s['pnl']:>8.0f} | DD: R${s['dd']:>5.0f} | Ret/DD: {s['ret_dd']:>7.2f} | Trades: {s['trades']:>5} | WR: {s['wr']:.1f}%")
    print("=" * 75)

    # Plot
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(np.cumsum(pw), color='#c8a444', alpha=0.7,
            label=f"WDO (R${sw['pnl']:.0f} | DD R${sw['dd']:.0f} | {sw['ret_dd']:.1f}x)")
    ax.plot(np.cumsum(pc), color='#ff69b4', alpha=0.7,
            label=f"CONS (R${sc['pnl']:.0f} | DD R${sc['dd']:.0f} | {sc['ret_dd']:.1f}x)")
    ax.plot(np.cumsum(pp), color='white', linewidth=2.5,
            label=f"PORT WDO+CONS (R${sp_['pnl']:.0f} | DD R${sp_['dd']:.0f} | {sp_['ret_dd']:.1f}x)")
    ax.set_title("WDO + Consenso (sem DI) -- LB=95, BandMult=0.10", fontsize=14, pad=15)
    ax.set_ylabel("PnL (R$)"); ax.set_xlabel("Barras (M5)")
    ax.legend(fontsize=9, framealpha=0.7); ax.grid(alpha=0.12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "equity_wdo_cons.png"), dpi=130)
    plt.close(fig)
    print("Grafico salvo!")

if __name__ == "__main__":
    main()
