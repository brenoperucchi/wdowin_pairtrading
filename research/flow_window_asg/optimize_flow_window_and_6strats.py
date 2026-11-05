# -*- coding: utf-8 -*-
import os
import sys
import glob
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT_DIR = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

SCRATCH_DIR = r"C:\Users\ryzen\.gemini\antigravity\brain\c2b74f00-91a2-46d9-a669-fdd6bd3e1379\scratch"
if SCRATCH_DIR not in sys.path:
    sys.path.insert(0, SCRATCH_DIR)

# 1. Load all 123 historical sessions from data/processed/gex_historical_sessions_v1
files = sorted(glob.glob(os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1", "*.json")))
print(f"Carregando {len(files)} sessoes historicas...")

raw_sessions = {"WIN": {}, "WDO": {}}
for f in files:
    s_date = os.path.basename(f).replace(".json", "")
    if s_date < "2026-05-07":
        continue
    with open(f, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    for sym in ("WIN", "WDO"):
        bars = [b for b in data.get(sym, {}).get("m5_cvd_series", []) if not b.get("is_prev_day", False)]
        if bars:
            # Pre-extract numpy arrays for ultra-fast grid search
            n = len(bars)
            t_mins = np.zeros(n, dtype=np.int32)
            opens = np.zeros(n, dtype=np.float64)
            highs = np.zeros(n, dtype=np.float64)
            lows = np.zeros(n, dtype=np.float64)
            closes = np.zeros(n, dtype=np.float64)
            cvds = np.zeros(n, dtype=np.float64)
            inst_5m = np.zeros(n, dtype=np.float64)
            delta_5m = np.zeros(n, dtype=np.float64)
            for i, b in enumerate(bars):
                ts_raw = int(b.get("time", 0))
                dt = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                t_mins[i] = dt.hour * 60 + dt.minute
                opens[i] = float(b.get("open", b.get("close", 0.0)))
                highs[i] = float(b.get("high", opens[i]))
                lows[i] = float(b.get("low", opens[i]))
                closes[i] = float(b.get("close", opens[i]))
                cvds[i] = round(float(b.get("cvd_inst", 0.0)), 0)
                inst_5m[i] = float(b.get("inst_delta_bar", 0.0))
                delta_5m[i] = float(b.get("delta_bar", 0.0))
            raw_sessions[sym][s_date] = {
                "t_mins": t_mins,
                "opens": opens,
                "highs": highs,
                "lows": lows,
                "closes": closes,
                "cvds": cvds,
                "inst_5m": inst_5m,
                "delta_5m": delta_5m,
            }

all_dates = sorted(raw_sessions["WIN"].keys())
print(f"Datas validas: {len(all_dates)} ({all_dates[0]} a {all_dates[-1]})")


def simulate_flow_window_for_params(
    sym: str,
    fast_p: float,
    slow_p: float,
    w_cvd: float,
    smooth_alpha: float,
    flip_thr: float,
    trade_start_min: int = 555,  # 09:15
    trade_end_min: int = 1020,   # 17:00
):
    """
    Calcula o histograma e a janela A.S.G para cada sessao com os parametros dados,
    e simula operar PURAMENTE a virada da janela (Stop & Reverse na barra fechada de virada,
    encerrando as 17:00).
    Retorna metricas de trade puro da janela + dicionario de features por (data, t_min).
    """
    is_win = (sym == "WIN")
    alpha_fast = 2.0 / (fast_p + 1.0)
    alpha_slow = 2.0 / (slow_p + 1.0)
    alpha_band = 2.0 / (7.0 + 1.0)
    w_price = 1.0 - w_cvd
    mult_brl = 0.20 if is_win else 10.0
    cost_pts = 15.0 if is_win else 0.5  # Custo/slippage realista por trade

    daily_pnl_brl = []
    daily_months = []
    total_trades = 0
    wins = 0
    gross_win_brl = 0.0
    gross_loss_brl = 0.0
    total_flips = 0

    sess_map = raw_sessions[sym]

    for d_str in all_dates:
        s = sess_map.get(d_str)
        if not s:
            continue
        t_mins = s["t_mins"]
        opens = s["opens"]
        highs = s["highs"]
        lows = s["lows"]
        closes = s["closes"]
        cvds = s["cvds"]
        inst_5m = s["inst_5m"]
        n = len(closes)

        first_h = highs[0]
        first_l = lows[0]
        first_cvd = cvds[0]

        ema_p_high = first_h
        ema_p_low = first_l
        ema_atr = max(first_h - first_l, 40.0 if is_win else 1.5)
        ema_cvd_f = first_cvd
        ema_cvd_s = first_cvd
        ema_cvd_step = max(abs(inst_5m[0]), 2500.0 if is_win else 500.0)
        ema_hist = 0.0
        active_win_dir = 0
        prev_cvd = first_cvd - inst_5m[0]

        pos_dir = 0
        entry_px = 0.0
        day_brl = 0.0

        for i in range(n):
            h = highs[i]
            l = lows[i]
            c = closes[i]
            o = opens[i]
            cvd = cvds[i]
            tm = t_mins[i]

            rng_bar = max(h - l, 15.0 if is_win else 0.5)
            ema_atr = alpha_band * rng_bar + (1.0 - alpha_band) * ema_atr
            ema_p_high = alpha_band * h + (1.0 - alpha_band) * ema_p_high
            ema_p_low = alpha_band * l + (1.0 - alpha_band) * ema_p_low

            p_mid_trava = 0.5 * ((ema_p_high + 0.35 * ema_atr) + (ema_p_low - 0.35 * ema_atr))

            ema_cvd_f = alpha_fast * cvd + (1.0 - alpha_fast) * ema_cvd_f
            ema_cvd_s = alpha_slow * cvd + (1.0 - alpha_slow) * ema_cvd_s
            ema_cvd_step = alpha_band * max(abs(cvd - prev_cvd), 500.0 if is_win else 100.0) + (1.0 - alpha_band) * ema_cvd_step

            raw_cvd_osc = (ema_cvd_f - ema_cvd_s) / max(1.0, ema_cvd_step * 1.4)
            raw_price_osc = (c - p_mid_trava) / max(1.0, ema_atr * 0.9)
            raw_score = np.clip((w_cvd * raw_cvd_osc + w_price * raw_price_osc) * 55.0, -100.0, 100.0)
            ema_hist = smooth_alpha * raw_score + (1.0 - smooth_alpha) * ema_hist
            hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

            prev_win_dir = active_win_dir
            if active_win_dir == 0:
                if hist_val >= 4.0 or (cvd >= prev_cvd and c >= o):
                    active_win_dir = 1
                else:
                    active_win_dir = -1
            else:
                if active_win_dir == 1 and hist_val <= -flip_thr:
                    active_win_dir = -1
                    total_flips += 1
                elif active_win_dir == -1 and hist_val >= flip_thr:
                    active_win_dir = 1
                    total_flips += 1

            prev_cvd = cvd

            # Simula operacao pura da Janela (Stop & Reverse na virada dentro do horario operacional)
            if tm < trade_start_min:
                continue

            if tm >= trade_end_min or i == n - 1:
                if pos_dir != 0:
                    pts = pos_dir * (c - entry_px) - cost_pts
                    brl = pts * mult_brl
                    day_brl += brl
                    total_trades += 1
                    if brl > 0:
                        wins += 1
                        gross_win_brl += brl
                    else:
                        gross_loss_brl += abs(brl)
                    pos_dir = 0
                continue

            # Se ainda nao abriu posicao hoje ou se a janela virou:
            if pos_dir == 0:
                # Entra apenas no momento em que ocorre uma virada real (ou na abertura da janela as 09:15)
                if prev_win_dir != active_win_dir or tm == trade_start_min:
                    pos_dir = active_win_dir
                    entry_px = c
            elif pos_dir != active_win_dir:
                # Fecha posicao atual e reverte
                pts = pos_dir * (c - entry_px) - cost_pts
                brl = pts * mult_brl
                day_brl += brl
                total_trades += 1
                if brl > 0:
                    wins += 1
                    gross_win_brl += brl
                else:
                    gross_loss_brl += abs(brl)
                pos_dir = active_win_dir
                entry_px = c

        daily_pnl_brl.append(day_brl)
        daily_months.append(d_str[:7])

    arr_pnl = np.array(daily_pnl_brl, dtype=np.float64)
    net_brl = float(np.sum(arr_pnl))
    cum = np.cumsum(arr_pnl)
    peak = np.maximum.accumulate(np.maximum(0.0, cum))
    mdd = float(np.max(peak - cum)) if len(cum) > 0 else 0.0
    ret_dd = net_brl / max(1.0, mdd)
    pf = gross_win_brl / max(1.0, gross_loss_brl)
    wr = (wins / max(1, total_trades)) * 100.0

    # Months positive
    m_dict = {}
    for m_str, val in zip(daily_months, arr_pnl):
        m_dict[m_str] = m_dict.get(m_str, 0.0) + val
    pos_m = sum(1 for v in m_dict.values() if v > 0)

    return {
        "fast": fast_p,
        "slow": slow_p,
        "w_cvd": w_cvd,
        "smooth": smooth_alpha,
        "flip_thr": flip_thr,
        "trades": total_trades,
        "flips_per_day": round(total_flips / max(1, len(all_dates)), 1),
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "net_brl": round(net_brl, 0),
        "mdd_brl": round(mdd, 0),
        "ret_dd": round(ret_dd, 2),
        "pos_months": pos_m,
        "total_months": len(m_dict),
    }


print("\n======================================================================")
print("ETAPA 1: GRID SEARCH - OPERANDO PURAMENTE A VIRADA DA JANELA (09:15-17:00)")
print("======================================================================")

for sym in ("WIN", "WDO"):
    # Baseline atual: fast=4, slow=11, w_cvd=0.68, smooth=0.45, flip_thr=6.5
    base_res = simulate_flow_window_for_params(sym, 4, 11, 0.68, 0.45, 6.5)
    print(f"\n>>> ATIVO: {sym} | BASELINE ATUAL (Fast=4, Slow=11, wCVD=0.68, Smooth=0.45, Flip=6.5):")
    print(f"    Trades={base_res['trades']} ({base_res['flips_per_day']} viradas/dia) | WR={base_res['wr']}% | PF={base_res['pf']} | Net=R$ {base_res['net_brl']:.0f} | MDD=R$ {base_res['mdd_brl']:.0f} | Ret/DD={base_res['ret_dd']}x | Meses={base_res['pos_months']}/{base_res['total_months']}")

    results = []
    for fast_p in [2, 3, 4, 5, 6, 8, 10]:
        for slow_p in [8, 11, 14, 18, 22, 28, 36]:
            if fast_p >= slow_p - 2:
                continue
            for w_cvd in [0.50, 0.68, 0.85, 1.00]:
                for smooth_a in [0.30, 0.45, 0.65]:
                    for flip_t in [4.0, 6.5, 10.0, 14.0, 18.0, 22.0]:
                        r = simulate_flow_window_for_params(sym, fast_p, slow_p, w_cvd, smooth_a, flip_t)
                        results.append(r)

    # Sort by Ret/DD and Net BRL (filtering minimum 80 trades)
    valid_res = [r for r in results if r["trades"] >= 80 and r["net_brl"] > 0]
    valid_res.sort(key=lambda x: (x["pos_months"], x["ret_dd"], x["pf"]), reverse=True)
    print(f"--- TOP 10 COMBINACOES PURAS DE JANELA ({sym}) ---")
    for idx_r, r in enumerate(valid_res[:10], 1):
        print(
            f"  #{idx_r:02d} Fast={r['fast']:2d} Slow={r['slow']:2d} wCVD={r['w_cvd']:.2f} Sm={r['smooth']:.2f} Flip={r['flip_thr']:4.1f} | "
            f"Tr={r['trades']:4d} ({r['flips_per_day']:3.1f}/d) | WR={r['wr']:4.1f}% | PF={r['pf']:4.2f} | "
            f"Net=R$ {r['net_brl']:6.0f} | MDD=R$ {r['mdd_brl']:5.0f} | Ret/DD={r['ret_dd']:5.2f}x | Meses={r['pos_months']}/{r['total_months']}"
        )
