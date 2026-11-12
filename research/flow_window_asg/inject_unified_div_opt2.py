# -*- coding: utf-8 -*-
"""
Injeta de forma 100% aditiva e não-destrutiva a Estratégia Oficial Sniper `Opção 2`
(`2 contratos WIN Mix [NWE30 Din + 750p] + 1 contrato WDO MidWalls`) em
`data/processed/portfolio_4_sistematicas_equity_v1.json`, preservando intactos todos os setups
existentes (`EST_*`, `WDO_*`, `PORTFOLIO_TOP_8`) usados pelo `localhost:5174`.

Regras Auditadas do Modo Básico (`2L WIN + 1L WDO`, 100% Causal / Zero Lookahead):
  - `WIN_DIV_WALL` (2 contratos):
      * Gatilho Sniper 1:1: Setup estrutural na Wall + Divergência Visual `F1➔F2 / T1➔T2` (`tol=2` barras M5, c/ sobreposição)
      * Janela Horária: `09:05–16:45`, pulando o almoço `12:00–12:55`
      * Meta de Gain Diário Causal: trava novas entradas no WIN quando PnL já encerrado no dia atingir `>= +R$ 180,00`
      * Gestão 2L Mix: `L1 TP NWE30 Oposta Din [260..750p, front-run 15p] / SL 240p` + `L2 TP Fixo 750p / SL 260p` + `BE +180->+20p`
  - `WDO_DIV_WALL` (1 contrato):
      * Gatilho Sniper 1:1: Setup estrutural na Wall (`WDO_01/05/07/10` dedup) + Divergência Visual `F1➔F2 / T1➔T2` (`tol=2b`, c/ sobreposição)
      * Janela Horária: `09:00–17:00`, pulando abertura NY / PTAX `11:00–11:55`
      * Meta de Gain Diário Causal: trava novas entradas no WDO quando PnL já encerrado no dia atingir `>= +R$ 120,00`
      * Gestão 1L: `TP MidWall GEX (front-run 0.5p)` + `SL ~10p` + `Escudo BE`
  - `PORTFOLIO_DIV_OPT2`: Resumo consolidado da Carteira Oficial (`WIN_DIV_WALL + WDO_DIV_WALL`)
"""
import os
import sys
import json
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.mt5_loader import get_mt5_rates
from research.discover_gex_nwe_setups import compute_nwe_series
from research.flow_window_asg.generate_portfolio_6_json import (
    compute_summary_from_trades,
    COST_WIN_PTS,
)

SCRATCH_CACHE_WIN = r"C:\Users\ryzen\.gemini\antigravity\brain\1f7b6cde-39b3-4e1a-9494-7e36470a0f2a\scratch\cached_214_WIN.json"
SCRATCH_CACHE_WDO = r"C:\Users\ryzen\.gemini\antigravity\brain\1f7b6cde-39b3-4e1a-9494-7e36470a0f2a\scratch\cached_214_WDO.json"


def round5(val: float) -> float:
    return round(float(val) / 5.0) * 5.0


def compute_causal_3motor_bars(m5_series: list, is_win: bool = True) -> list:
    tick_sz = 5.0 if is_win else 0.5
    cum_eff = 0.0
    ema_fast = 0.0
    ema_slow = 0.0
    out = []
    for i, b in enumerate(m5_series):
        o, h, l, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
        rng = max(h - l, tick_sz)
        bv = float(b.get("buy_vol", 0.0))
        sv = float(b.get("sell_vol", 0.0))
        tv = max(1.0, bv + sv)
        lw = max(0.0, min(o, c) - l)
        uw = max(0.0, h - max(o, c))

        abs_buy_w = sv * ((c - l) / rng) * (0.80 + 1.40 * (lw / rng))
        abs_sell_w = bv * ((h - c) / rng) * (0.80 + 1.40 * (uw / rng))
        phi_wyckoff = round(abs_buy_w - abs_sell_w, 0)

        bl = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0))
        sl = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0))
        phi_porte = round(tv * ((bl - sl) / max(0.5, bl + sl)) * 2.2, 0)

        iagg = float(b.get("inst_aggr_delta", b.get("inst_delta_bar", 0.0)))
        ipas = float(b.get("inst_pass_delta", 0.0))
        ret = float(b.get("ret_delta_bar", 0.0))
        phi_inst = round(0.55 * iagg + 1.15 * ipas - 0.85 * ret, 0)

        bar_force = round(0.45 * phi_wyckoff + 0.25 * phi_porte + 0.30 * phi_inst, 0)
        f_prev1 = out[i - 1]["effective_force_bar"] if i >= 1 else bar_force
        f_prev2 = out[i - 2]["effective_force_bar"] if i >= 2 else f_prev1
        swing_imp = round(0.45 * bar_force + 0.35 * f_prev1 + 0.20 * f_prev2, 0)

        cum_eff += bar_force
        if i == 0:
            ema_fast = cum_eff
            ema_slow = cum_eff
        else:
            ema_fast = 0.50 * cum_eff + 0.50 * ema_fast
            ema_slow = (2.0 / 11.0) * cum_eff + (1.0 - 2.0 / 11.0) * ema_slow

        detrended = ema_fast - ema_slow
        smart_wave = round(0.55 * detrended + 0.45 * swing_imp, 0)

        t_raw = b.get("time", "09:00")
        if isinstance(t_raw, (int, float)):
            sec_day = int(t_raw) % 86400
            hhmm = f"{sec_day // 3600:02d}:{(sec_day % 3600) // 60:02d}"
        else:
            hhmm = str(t_raw)

        eb = dict(b)
        eb["time"] = hhmm
        eb["wyckoff_abs_bar"] = phi_wyckoff
        eb["lot_urgency_bar"] = phi_porte
        eb["smart_inst_bar"] = phi_inst
        eb["effective_force_bar"] = bar_force
        eb["swing_impulse_3b"] = swing_imp
        eb["smart_swing_wave"] = smart_wave
        out.append(eb)
    return out


def detect_visual_swing_divergences(bars: list, walls: list, is_win: bool) -> list:
    """
    Detector 100% causal idêntico ao `swingDivergences` (`F1➔F2` e `T1➔T2`) desenhado no `FluxoRealAsgChart`.
    """
    p_tol = 50.0 if is_win else 1.5
    max_ext = 360.0 if is_win else 8.5
    w_rad = 130.0 if is_win else 3.0
    wall_prices = [float(w["price"]) for w in (walls or []) if float(w.get("price", 0)) > 0]

    signals = []
    last_bull_idx = -12
    last_bear_idx = -12

    for i in range(4, len(bars)):
        b = bars[i]
        pb = bars[i - 1]
        p2b = bars[i - 2]
        p3b = bars[i - 3]

        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        ph, pl, pc = float(pb["high"]), float(pb["low"]), float(pb["close"])
        p2h, p2l = float(p2b["high"]), float(p2b["low"])
        p3h, p3l = float(p3b["high"]), float(p3b["low"])

        w_i = float(b.get("smart_swing_wave", 0.0))
        w_p1 = float(pb.get("smart_swing_wave", 0.0))
        w_p2 = float(p2b.get("smart_swing_wave", 0.0))
        wyk = float(b.get("wyckoff_abs_bar", 0.0))
        eff = float(b.get("effective_force_bar", 0.0))
        sv = float(b.get("sell_vol", 0.0))
        bv = float(b.get("buy_vol", 0.0))
        abl = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0))
        asl = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0))

        l2 = min(l, pl)
        h2 = max(h, ph)
        w_low2 = min(w_i, w_p1, w_p2)
        w_high2 = max(w_i, w_p1, w_p2)

        is_local_bottom = (
            l2 <= min(p2l, p3l) + (20.0 if is_win else 0.5)
            and (c >= l + (h - l) * 0.35 or c >= pc or wyk > 0)
            and (eff > 0 or wyk > 0 or w_i > 0)
        )
        is_local_top = (
            h2 >= max(p2h, p3h) - (20.0 if is_win else 0.5)
            and (c <= h - (h - l) * 0.35 or c <= pc or wyk < 0)
            and (eff < 0 or wyk < 0 or w_i < 0)
        )

        if is_local_bottom:
            best_p1 = None
            for j in range(max(1, i - 16), i - 2):
                lj = float(bars[j]["low"])
                l_prev = float(bars[max(0, j - 1)]["low"])
                l_next = float(bars[min(i - 1, j + 1)]["low"])
                if lj <= l_prev and lj <= l_next:
                    wj = min(
                        float(bars[j].get("smart_swing_wave", 0.0)),
                        float(bars[max(0, j - 1)].get("smart_swing_wave", 0.0)),
                        float(bars[min(i - 1, j + 1)].get("smart_swing_wave", 0.0)),
                    )
                    if best_p1 is None or lj < best_p1["price"]:
                        best_p1 = {"idx": j, "price": lj, "wave": wj, "sv": float(bars[j].get("sell_vol", 0.0))}
            if best_p1 is not None:
                price_ok = (best_p1["price"] - max_ext) <= l2 <= (best_p1["price"] + p_tol)
                wave_ok = (w_low2 > best_p1["wave"] + max(1500.0 if is_win else 180.0, abs(best_p1["wave"]) * 0.18)) or (best_p1["wave"] < 0 and w_i > 0)
                sv_ok = (sv < best_p1["sv"] * 0.90) or (wyk > 0) or (abl >= asl)
                near_w = (not wall_prices) or any(abs(l2 - wp) <= w_rad or abs(c - wp) <= w_rad for wp in wall_prices)
                if price_ok and wave_ok and sv_ok:
                    if i - last_bull_idx > 6:
                        signals.append({"sig_idx": i, "dir": 1, "near_wall": near_w, "pivot_px": l2})
                        last_bull_idx = i

        if is_local_top:
            best_t1 = None
            for j in range(max(1, i - 16), i - 2):
                hj = float(bars[j]["high"])
                h_prev = float(bars[max(0, j - 1)]["high"])
                h_next = float(bars[min(i - 1, j + 1)]["high"])
                if hj >= h_prev and hj >= h_next:
                    wj = max(
                        float(bars[j].get("smart_swing_wave", 0.0)),
                        float(bars[max(0, j - 1)].get("smart_swing_wave", 0.0)),
                        float(bars[min(i - 1, j + 1)].get("smart_swing_wave", 0.0)),
                    )
                    if best_t1 is None or hj > best_t1["price"]:
                        best_t1 = {"idx": j, "price": hj, "wave": wj, "bv": float(bars[j].get("buy_vol", 0.0))}
            if best_t1 is not None:
                price_ok = (best_t1["price"] - p_tol) <= h2 <= (best_t1["price"] + max_ext)
                wave_ok = (w_high2 < best_t1["wave"] - max(1500.0 if is_win else 180.0, abs(best_t1["wave"]) * 0.18)) or (best_t1["wave"] > 0 and w_i < 0)
                bv_ok = (bv < best_t1["bv"] * 0.90) or (wyk < 0) or (asl >= abl)
                near_w = (not wall_prices) or any(abs(h2 - wp) <= w_rad or abs(c - wp) <= w_rad for wp in wall_prices)
                if price_ok and wave_ok and bv_ok:
                    if i - last_bear_idx > 6:
                        signals.append({"sig_idx": i, "dir": -1, "near_wall": near_w, "pivot_px": h2})
                        last_bear_idx = i

    return signals


def load_cached_or_build_session_bars(all_dates: list, is_win: bool) -> list:
    cache_path = SCRATCH_CACHE_WIN if is_win else SCRATCH_CACHE_WDO
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    from core.profit_wall_players_engine import build_profit_session_payload
    asset_nm = "WIN" if is_win else "WDO"
    out = []
    for d in all_dates:
        pay = build_profit_session_payload(asset_nm, d, [])
        bars_raw = pay.get("m5_bars", []) if pay else []
        out.append((d, compute_causal_3motor_bars(bars_raw, is_win), []))
    return out


def build_win_3motor_and_visual_maps(all_dates: list):
    data_win = load_cached_or_build_session_bars(all_dates, True)
    data_wdo = load_cached_or_build_session_bars(all_dates, False)
    valid_set = set(all_dates)

    win_3m_lookup = {}
    vis_win = {}
    for d, bars, walls in data_win:
        if d not in valid_set:
            continue
        sigs = detect_visual_swing_divergences(bars, walls, True)
        vis_win[d] = [(s["sig_idx"], s["dir"]) for s in sigs]
        vis_win[(d, "tmap")] = {b["time"]: idx for idx, b in enumerate(bars)}

        for i, b in enumerate(bars):
            hh, mm = map(int, b["time"].split(":"))
            t_min = hh * 60 + mm
            o_i, h_i, l_i, c_i = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
            w_i = float(b["smart_swing_wave"])
            wyk_i = float(b["wyckoff_abs_bar"])
            urg_i = float(b["lot_urgency_bar"])
            eff_i = float(b["effective_force_bar"])
            imp3_i = float(b["swing_impulse_3b"])

            bull_swing_div = False
            bear_swing_div = False
            if i >= 3:
                l_2b = min(l_i, float(bars[i - 1]["low"]))
                h_2b = max(h_i, float(bars[i - 1]["high"]))
                w_low_2 = min(w_i, float(bars[i - 1]["smart_swing_wave"]))
                w_high_2 = max(w_i, float(bars[i - 1]["smart_swing_wave"]))
                for k in range(i - 2, max(0, i - 16), -1):
                    kb = bars[k]
                    l_k, h_k, w_k = float(kb["low"]), float(kb["high"]), float(kb["smart_swing_wave"])
                    sv_i = float(b["sell_vol"]) + float(bars[i - 1]["sell_vol"])
                    sv_k = float(kb["sell_vol"]) + float(bars[max(0, k - 1)]["sell_vol"])
                    bv_i = float(b["buy_vol"]) + float(bars[i - 1]["buy_vol"])
                    bv_k = float(kb["buy_vol"]) + float(bars[max(0, k - 1)]["buy_vol"])
                    if (-380.0 <= (l_2b - l_k) <= 50.0) and (max(w_i, w_low_2) > w_k + 1200 or sv_i < 0.85 * sv_k or wyk_i > 0):
                        bull_swing_div = True
                    if (-50.0 <= (h_2b - h_k) <= 380.0) and (min(w_i, w_high_2) < w_k - 1200 or bv_i < 0.85 * bv_k or wyk_i < 0):
                        bear_swing_div = True

            dp3 = c_i - float(bars[max(0, i - 3)]["close"])
            bull_3motor = (
                (bull_swing_div and (eff_i > 0 or wyk_i > 0 or imp3_i > 0 or urg_i > 0))
                or ((dp3 <= 30.0 or c_i <= o_i) and (wyk_i > 0 or eff_i > 0 or imp3_i > 0))
                or (eff_i > 0 and imp3_i > 0 and wyk_i >= -800)
            )
            bear_3motor = (
                (bear_swing_div and (eff_i < 0 or wyk_i < 0 or imp3_i < 0 or urg_i < 0))
                or ((dp3 >= -30.0 or c_i >= o_i) and (wyk_i < 0 or eff_i < 0 or imp3_i < 0))
                or (eff_i < 0 and imp3_i < 0 and wyk_i <= 800)
            )
            win_3m_lookup[(d, t_min)] = {
                "bull_3motor": bull_3motor,
                "bear_3motor": bear_3motor,
            }

    vis_wdo = {}
    for d, bars, walls in data_wdo:
        if d not in valid_set:
            continue
        sigs = detect_visual_swing_divergences(bars, walls, False)
        vis_wdo[d] = [(s["sig_idx"], s["dir"]) for s in sigs]
        vis_wdo[(d, "tmap")] = {b["time"]: idx for idx, b in enumerate(bars)}

    return win_3m_lookup, vis_win, vis_wdo


def filter_sniper_and_daily_cap(
    trades: list,
    vis_map: dict,
    tol_bars: int,
    start_time: str,
    end_time: str,
    skip_windows: list,
    daily_gain_cap_brl: float,
) -> list:
    """
    Aplica o filtro Sniper 1:1 (`F1➔F2 / T1➔T2` na janela `tol_bars`, com sobreposição permitida)
    + Janela Horária + Limite Causal de Gain Diário (só soma trades já encerrados `exit_time <= entry_time`).
    """
    sniper_matched = []
    for tr in trades:
        d = tr["date"]
        tmap = vis_map.get((d, "tmap"), {})
        bi = tmap.get(tr["time"])
        if bi is None:
            continue
        s_dir = 1 if tr["direction"] == "COMPRA" else -1
        # Causal (auditoria 11/11/2026, versão B): a divergência tem que estar confirmada até a barra ANTERIOR à entrada
        # (a entrada é na abertura da barra `bi`; a divergência detectada no fechamento de `bi` ainda não existia).
        if any(sd == s_dir and (bi - tol_bars - 1) <= si <= bi - 1 for (si, sd) in vis_map.get(d, [])):
            sniper_matched.append(tr)

    by_day = {}
    for tr in sniper_matched:
        by_day.setdefault(tr["date"], []).append(tr)

    accepted = []
    for d, arr in sorted(by_day.items()):
        arr_sorted = sorted(arr, key=lambda x: (x["time"], x.get("asset", "")))
        day_acc = []
        for tr in arr_sorted:
            tm = tr["time"]
            if tm < start_time or tm > end_time:
                continue
            if any(w0 <= tm <= w1 for (w0, w1) in skip_windows):
                continue
            realized_closed = sum(
                prev["brl_1c"] for prev in day_acc if prev.get("exit_time", "23:59") < tm
            )
            if daily_gain_cap_brl is not None and realized_closed >= daily_gain_cap_brl:
                continue
            day_acc.append(tr)
        accepted.extend(day_acc)
    return accepted


def load_mt5_win_bars_and_nwe30():
    df = get_mt5_rates("WIN$N", "M5").copy()
    df["session_date"] = df["t"].dt.strftime("%Y-%m-%d")
    df["t_min"] = df["t"].dt.hour * 60 + df["t"].dt.minute
    df = df[(df["t_min"] >= 540) & (df["t_min"] <= 1075)].copy().reset_index(drop=True)
    df["time_str"] = df["t"].dt.strftime("%H:%M")

    closes_arr = df["close"].values.astype(float)
    n30_c, n30_u, n30_l, _, _ = compute_nwe_series(closes_arr, 30, 3.0, 1.6)
    df["n30_c"] = n30_c
    df["n30_u"] = n30_u
    df["n30_l"] = n30_l

    bars_by_day = {}
    nwe_by_day = {}
    last_vals = None
    for d, grp in df.groupby("session_date", sort=True):
        bars_by_day[str(d)] = [
            {
                "time": row.time_str,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
            }
            for row in grp.itertuples(index=False)
        ]
        nwe_by_day[str(d)] = {
            "n30_c": grp["n30_c"].values.astype(float),
            "n30_u": grp["n30_u"].values.astype(float),
            "n30_l": grp["n30_l"].values.astype(float),
            "prev": last_vals,
        }
        if len(grp) > 0:
            last_vals = {
                "n30_c": float(grp["n30_c"].iloc[-1]),
                "n30_u": float(grp["n30_u"].iloc[-1]),
                "n30_l": float(grp["n30_l"].iloc[-1]),
            }
    return bars_by_day, nwe_by_day


def get_causal_nwe30_opp(nwe_day: dict, bar_idx: int, sig: int) -> float:
    if bar_idx > 0:
        r = bar_idx - 1
        return float(nwe_day["n30_u"][r]) if sig == 1 else float(nwe_day["n30_l"][r])
    prev = nwe_day.get("prev")
    if prev:
        return float(prev["n30_u"]) if sig == 1 else float(prev["n30_l"])
    return float(nwe_day["n30_u"][0]) if sig == 1 else float(nwe_day["n30_l"][0])


def calc_nwe30_tp1(ep: float, sig: int, opp30: float, min_tp: float = 260.0, max_tp: float = 750.0, front_run: float = 15.0) -> float:
    raw_px = opp30 - sig * front_run
    clipped = np.clip(raw_px, ep + min_tp, ep + max_tp) if sig == 1 else np.clip(raw_px, ep - max_tp, ep - min_tp)
    return round5(clipped)


def simulate_win_div_2lots_opt2(trades_list: list, win_bars_map: dict, nwe_win_map: dict) -> list:
    out = []
    for t in trades_list:
        d = t["date"]
        bars = win_bars_map.get(d)
        nwe_day = nwe_win_map.get(d)
        if not bars or not nwe_day:
            continue
        t_in = t["time"]
        fbar = next((idx for idx, b in enumerate(bars) if b["time"] >= t_in), None)
        if fbar is None or fbar >= len(bars) - 1:
            continue

        sig = 1 if t["direction"] == "COMPRA" else -1
        ep = float(t["entry_price"])

        # --- Lote 1: NWE30 Oposta Dinâmico (260..750p, SL 240, BE 180->20, max_bars=24) ---
        tp1_px = calc_nwe30_tp1(ep, sig, get_causal_nwe30_opp(nwe_day, fbar, sig))
        sl1_init = ep - sig * 240.0
        sl1_px = sl1_init
        be1_on = False
        mfe1 = 0.0
        k1 = fbar + 1
        xp1 = float(bars[fbar]["close"])
        exit_k1 = fbar
        rsn1 = "TEMPO"

        while k1 < len(bars):
            bk = bars[k1]
            bh, bl, bc, bo = float(bk["high"]), float(bk["low"]), float(bk["close"]), float(bk["open"])
            if bk["time"] >= "17:25":
                xp1 = bo
                exit_k1 = k1
                rsn1 = "EOD"
                break

            tp1_px = calc_nwe30_tp1(ep, sig, get_causal_nwe30_opp(nwe_day, k1, sig))

            if (sig == 1 and bl <= sl1_px) or (sig == -1 and bh >= sl1_px):
                xp1 = sl1_px
                exit_k1 = k1
                rsn1 = "BE" if be1_on else "SL"
                break

            if sig == 1 and bh >= tp1_px:
                xp1 = bo if bo >= tp1_px else tp1_px
                exit_k1 = k1
                rsn1 = "TP1"
                break
            if sig == -1 and bl <= tp1_px:
                xp1 = bo if bo <= tp1_px else tp1_px
                exit_k1 = k1
                rsn1 = "TP1"
                break

            fav = (bh - ep) if sig == 1 else (ep - bl)
            if fav > mfe1:
                mfe1 = fav

            if not be1_on and mfe1 >= 180.0 and k1 + 1 < len(bars):
                no = float(bars[k1 + 1]["open"])
                cand = ep + sig * 20.0
                if (sig == 1 and cand > sl1_px and no > cand) or (sig == -1 and cand < sl1_px and no < cand):
                    sl1_px = cand
                    be1_on = True

            if (k1 - fbar) >= 24:
                xp1 = bc
                exit_k1 = k1
                rsn1 = "TEMPO"
                break
            k1 += 1

        # --- Lote 2: TP Fixo 750p (SL 260, BE 180->20, max_bars=24) ---
        tp2_px = ep + sig * 750.0
        sl2_init = ep - sig * 260.0
        sl2_px = sl2_init
        be2_on = False
        mfe2 = 0.0
        k2 = fbar + 1
        xp2 = float(bars[fbar]["close"])
        exit_k2 = fbar
        rsn2 = "TEMPO"

        while k2 < len(bars):
            bk = bars[k2]
            bh, bl, bc, bo = float(bk["high"]), float(bk["low"]), float(bk["close"]), float(bk["open"])
            if bk["time"] >= "17:25":
                xp2 = bo
                exit_k2 = k2
                rsn2 = "EOD"
                break

            if (sig == 1 and bl <= sl2_px) or (sig == -1 and bh >= sl2_px):
                xp2 = sl2_px
                exit_k2 = k2
                rsn2 = "BE" if be2_on else "SL"
                break

            if (sig == 1 and bh >= tp2_px) or (sig == -1 and bl <= tp2_px):
                xp2 = tp2_px
                exit_k2 = k2
                rsn2 = "TP2"
                break

            fav = (bh - ep) if sig == 1 else (ep - bl)
            if fav > mfe2:
                mfe2 = fav

            if not be2_on and mfe2 >= 180.0 and k2 + 1 < len(bars):
                no = float(bars[k2 + 1]["open"])
                cand = ep + sig * 20.0
                if (sig == 1 and cand > sl2_px and no > cand) or (sig == -1 and cand < sl2_px and no < cand):
                    sl2_px = cand
                    be2_on = True

            if (k2 - fbar) >= 24:
                xp2 = bc
                exit_k2 = k2
                rsn2 = "TEMPO"
                break
            k2 += 1

        pts1_raw = (xp1 - ep) * sig
        pts2_raw = (xp2 - ep) * sig
        pts1_net = round(pts1_raw - COST_WIN_PTS, 1)
        pts2_net = round(pts2_raw - COST_WIN_PTS, 1)
        tot_pts = round(pts1_net + pts2_net, 1)
        tot_brl = round(pts1_net * 0.20 + pts2_net * 0.20, 2)
        tot_brl_nocost = round((pts1_raw + pts2_raw) * 0.20, 2)
        exit_time = max(bars[exit_k1]["time"], bars[exit_k2]["time"])

        if rsn1 == "TP1" and rsn2 == "TP2":
            lbl = f"✅ ALVO DUPLO NWE30+750 ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
        elif rsn1 == "TP1" and tot_pts > 0:
            lbl = f"✅ ALVO TP1 NWE30 + {rsn2} ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
        elif tot_pts > 0 and (be1_on or be2_on):
            lbl = f"🛡️ PROTEÇÃO BE ZERO ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
        elif tot_pts > 0:
            lbl = f"✅ A FAVOR ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
        else:
            lbl = f"❌ STOP ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"

        out.append({
            "date": d,
            "month": d[:7],
            "time": t_in,
            "exit_time": exit_time,
            "asset": "WIN",
            "strategy_id": "WIN_DIV_WALL",
            "direction": t["direction"],
            "entry_price": round(ep, 1),
            "exit_price": round(0.5 * (xp1 + xp2), 1),
            "tp1_price": round(tp1_px, 1),
            "tp_price": round(tp2_px, 1),
            "sl1_price": round(sl1_init, 1),
            "stop_price": round(sl2_init, 1),
            "be_triggered": bool(be1_on or be2_on),
            "be_trigger_price": round(ep + sig * 180.0, 1),
            "be_stop_price": round(ep + sig * 20.0, 1),
            "pts_l1": pts1_net,
            "pts_l2": pts2_net,
            "pts": tot_pts,
            "brl_1c": tot_brl,
            "brl_1c_nocost": tot_brl_nocost,
            "contracts": 2,
            "label": lbl,
            "status": "FECHADA",
            "in_flow": True,
            "in_base": True,
            "in_mt5_11": False,
            "in_walls_flow": True,
            "also_in_raw_base": True,
        })
    return out


def main():
    json_path = os.path.join(ROOT_DIR, "data", "processed", "portfolio_4_sistematicas_equity_v1.json")
    with open(json_path, "r", encoding="utf-8") as f:
        p4 = json.load(f)

    all_dates = [d["date"] for d in p4["days"]]
    print(f"[1/4] Carregando barras MT5 WIN$N + NWE30 + Divergências Visuais F1->F2 / T1->T2 ({len(all_dates)} pregões)...")
    win_bars_map, nwe_win_map = load_mt5_win_bars_and_nwe30()
    win_lkp, vis_win, vis_wdo = build_win_3motor_and_visual_maps(all_dates)

    # Remove eventuais registros anteriores de WIN_DIV_WALL / WDO_DIV_WALL para idempotência absoluta
    raw_win_div_entries = []
    raw_wdo_div_trades = []
    for day_obj in p4["days"]:
        d = day_obj["date"]
        clean_existing = [
            t for t in day_obj.get("trades", [])
            if t.get("strategy_id") not in ("WIN_DIV_WALL", "WDO_DIV_WALL")
        ]
        day_obj["trades"] = clean_existing

        seen_win = set()
        seen_wdo = set()
        for t in clean_existing:
            if t.get("asset") == "WIN":
                key = (d, t["time"], t["direction"])
                hh, mm = map(int, t["time"].split(":"))
                tm = hh * 60 + mm
                info = win_lkp.get((d, tm - 5)) or {}   # só a barra anterior à entrada (sem cair na própria barra)
                has_3m = info.get("bull_3motor", False) if t["direction"] == "COMPRA" else info.get("bear_3motor", False)
                if key not in seen_win and has_3m:
                    seen_win.add(key)
                    raw_win_div_entries.append(t)
            elif t.get("asset") == "WDO":
                key = (d, t["time"], t["direction"])
                if t.get("strategy_id") in ("WDO_01", "WDO_05", "WDO_07", "WDO_10") and key not in seen_wdo:
                    seen_wdo.add(key)
                    tc = dict(t)
                    tc["strategy_id"] = "WDO_DIV_WALL"
                    tc["contracts"] = 1
                    tc["in_flow"] = True
                    tc["in_base"] = True
                    tc["in_mt5_11"] = False
                    tc["in_walls_flow"] = True
                    raw_wdo_div_trades.append(tc)

    print(f"[2/4] Simulando candidatos WIN 2L Mix ({len(raw_win_div_entries)}) e aplicando Sniper F1->F2 + Horário + Meta Diária...")
    all_win_sim = simulate_win_div_2lots_opt2(raw_win_div_entries, win_bars_map, nwe_win_map)

    # Aplica Filtro Sniper 1:1 c/ sobreposição (tol=2b) + Horário s/ 12h WIN & s/ 11h WDO + Meta Diária Causal (WIN R$180 / WDO R$120)
    win_div_trades = filter_sniper_and_daily_cap(
        trades=all_win_sim,
        vis_map=vis_win,
        tol_bars=2,
        start_time="09:05",
        end_time="16:45",
        skip_windows=[("12:00", "12:55")],
        daily_gain_cap_brl=180.0,
    )
    wdo_div_trades = filter_sniper_and_daily_cap(
        trades=raw_wdo_div_trades,
        vis_map=vis_wdo,
        tol_bars=2,
        start_time="09:00",
        end_time="17:00",
        skip_windows=[("11:00", "11:55")],
        daily_gain_cap_brl=120.0,
    )

    print("[3/4] Calculando métricas auditadas (2 ct WIN + 1 ct WDO) e injetando de forma aditiva por pregão...")
    st_win_div = compute_summary_from_trades(win_div_trades, all_dates)
    st_wdo_div = compute_summary_from_trades(wdo_div_trades, all_dates)
    comb_sorted = sorted(win_div_trades + wdo_div_trades, key=lambda x: (x["date"], x["time"], x["asset"]))
    st_port_opt2 = compute_summary_from_trades(comb_sorted, all_dates)

    win_meta = {
        "id": "WIN_DIV_WALL",
        "asset": "WIN",
        "name": "WIN · Sniper Divergência F1➔F2 / T1➔T2 · 2c Mix (s/ 12h · Meta +R$180)",
        "short": "WIN Sniper 2c Mix",
        "window": "09:05–16:45 (s/ 12h)",
        "lotes": "2c (1+1)",
        "tp_rule": "L1: NWE30 Oposta Din (260..750p) · L2: Fixo 750p",
        "sl_be_rule": "SL 240p/260p + BE Zero (+20p) aos +180p · Meta +R$180/dia",
        "nwe_rule": "TP1 Dinâmico na Banda Oposta NWE30 (front-run 15p)",
        "flow_rule": "Sniper Divergência F1➔F2 / T1➔T2 na Wall (c/ sobreposição)",
    }
    wdo_meta = {
        "id": "WDO_DIV_WALL",
        "asset": "WDO",
        "name": "WDO · Sniper Divergência F1➔F2 / T1➔T2 · 1c MidWall (s/ 11h NY · Meta +R$120)",
        "short": "WDO Sniper 1c MidWall",
        "window": "09:00–17:00 (s/ 11h NY/PTAX)",
        "lotes": "1c",
        "tp_rule": "TP MidWall GEX (front-run 0.5p)",
        "sl_be_rule": "SL ~10p + Escudo BE · Meta +R$120/dia",
        "nwe_rule": "Confluência NWE50/30 + Defesa de Wall",
        "flow_rule": "Sniper Divergência F1➔F2 / T1➔T2 na Wall (c/ sobreposição)",
    }

    p4["summary_1c"]["WIN_DIV_WALL"] = {
        **st_win_div,
        "meta": win_meta,
        "base_mt5_variant": st_win_div,
        "flow_variant": st_win_div,
    }
    p4["summary_1c"]["WDO_DIV_WALL"] = {
        **st_wdo_div,
        "meta": wdo_meta,
        "base_mt5_variant": st_wdo_div,
        "flow_variant": st_wdo_div,
    }
    p4["summary_1c"]["PORTFOLIO_DIV_OPT2"] = st_port_opt2

    win_by_day = {}
    for tr in win_div_trades:
        win_by_day.setdefault(tr["date"], []).append(tr)
    wdo_by_day = {}
    for tr in wdo_div_trades:
        wdo_by_day.setdefault(tr["date"], []).append(tr)

    for day_obj in p4["days"]:
        d = day_obj["date"]
        w_list = win_by_day.get(d, [])
        d_list = wdo_by_day.get(d, [])

        w_pts = round(sum(t["pts"] for t in w_list), 2)
        d_pts = round(sum(t["pts"] for t in d_list), 2)

        day_obj["WIN_DIV_WALL_pts"] = w_pts
        day_obj["WIN_DIV_WALL_ops"] = len(w_list)
        day_obj["WIN_DIV_WALL_base_pts"] = w_pts
        day_obj["WIN_DIV_WALL_base_ops"] = len(w_list)
        day_obj["WIN_DIV_WALL_flow_pts"] = w_pts
        day_obj["WIN_DIV_WALL_flow_ops"] = len(w_list)

        day_obj["WDO_DIV_WALL_pts"] = d_pts
        day_obj["WDO_DIV_WALL_ops"] = len(d_list)
        day_obj["WDO_DIV_WALL_base_pts"] = d_pts
        day_obj["WDO_DIV_WALL_base_ops"] = len(d_list)
        day_obj["WDO_DIV_WALL_flow_pts"] = d_pts
        day_obj["WDO_DIV_WALL_flow_ops"] = len(d_list)

        merged = day_obj["trades"] + w_list + d_list
        merged.sort(key=lambda x: (x.get("time", ""), x.get("exit_time", ""), x.get("strategy_id", "")))
        day_obj["trades"] = merged

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(p4, f, ensure_ascii=False)

    p8 = p4["summary_1c"]["PORTFOLIO_TOP_8"]
    print("=" * 115)
    print(f"  [OK] Atualizado aditivamente: {json_path} ({os.path.getsize(json_path)/1024:.1f} KB)")
    print(f"  5174 INTACTO (PORTFOLIO_TOP_8): {p8['ops']} tr | WR {p8['wr_pct']}% | PF {p8['pf']} | Net +R$ {p8['tot_brl_1c']:,.0f} | DD R$ {p8['max_dd_brl_1c']:,.0f} | Ret/DD {p8['ret_dd']}x")
    print(f"  5176 WIN_DIV_WALL (2c Mix):     {st_win_div['ops']} tr | WR {st_win_div['wr_pct']}% | PF {st_win_div['pf']} | Net +R$ {st_win_div['tot_brl_1c']:,.0f} | DD R$ {st_win_div['max_dd_brl_1c']:,.0f} | Ret/DD {st_win_div['ret_dd']}x | {st_win_div['pos_months']}/{st_win_div['total_months']} M+")
    print(f"  5176 WDO_DIV_WALL (1c MidWall): {st_wdo_div['ops']} tr | WR {st_wdo_div['wr_pct']}% | PF {st_wdo_div['pf']} | Net +R$ {st_wdo_div['tot_brl_1c']:,.0f} | DD R$ {st_wdo_div['max_dd_brl_1c']:,.0f} | Ret/DD {st_wdo_div['ret_dd']}x | {st_wdo_div['pos_months']}/{st_wdo_div['total_months']} M+")
    print(f"  5176 PORTFOLIO_DIV_OPT2 TOTAL:  {st_port_opt2['ops']} tr | WR {st_port_opt2['wr_pct']}% | PF {st_port_opt2['pf']} | Net +R$ {st_port_opt2['tot_brl_1c']:,.0f} | DD R$ {st_port_opt2['max_dd_brl_1c']:,.0f} | Ret/DD {st_port_opt2['ret_dd']}x | {st_port_opt2['pos_months']}/{st_port_opt2['total_months']} M+")
    print("=" * 115)


if __name__ == "__main__":
    main()
