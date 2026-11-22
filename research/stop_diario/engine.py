"""Motor de simulação, Sweep, Walk-Forward, Monte Carlo e análise por robô
para Stop Diário Máximo (Global, WIN, WDO e Combinado) baseado em barras M1 reais.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from research.stop_diario.data_loader import (
    DATE_END_2026,
    DATE_START_2026,
    DEFAULT_HTM_DIR,
    PORTFOLIO_PRESETS,
    ROBOT_METADATA,
    enrich_trades_with_m1_mae_mfe,
    load_m1_bars,
    load_portfolio_trades,
)

OOS_END = "2026-05-06"
IS_START = "2026-05-07"


# ═══════════════════════════════════════════════════════════════
# UTILIDADES ESTATÍSTICAS
# ═══════════════════════════════════════════════════════════════

def _percentile(arr: list[float], p: float) -> float:
    if not arr:
        return 0.0
    s = sorted(arr)
    idx = (p / 100.0) * (len(s) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return float(s[lo])
    return float(s[lo] + (s[hi] - s[lo]) * (idx - lo))


def _avg(arr: list[float]) -> float:
    return float(sum(arr) / len(arr)) if arr else 0.0


def _std(arr: list[float]) -> float:
    if len(arr) < 2:
        return 0.0
    m = _avg(arr)
    return float(math.sqrt(sum((v - m) ** 2 for v in arr) / (len(arr) - 1)))


def _round_step(val: float, step: int) -> int:
    if step <= 1:
        return max(1, int(round(val)))
    return max(step, int(round(val / step) * step))


# ═══════════════════════════════════════════════════════════════
# CONSTRUÇÃO DOS PREGÕES INTRADAY M1
# ═══════════════════════════════════════════════════════════════

def _eval_asset_minute_series(
    asset_trades: list[dict],
    asset_bars: dict | None,
    pt_val: float,
    mins_grid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Calcula séries por minuto de (worst, best, close, open_lots) para um ativo no pregão."""
    n_m = len(mins_grid)
    worst = np.zeros(n_m, dtype=np.float64)
    best = np.zeros(n_m, dtype=np.float64)
    close_s = np.zeros(n_m, dtype=np.float64)
    open_lots_s = np.zeros(n_m, dtype=np.float64)

    if not asset_trades:
        return worst, best, close_s, open_lots_s

    # Pré-indexar preços M1 na grade de minutos do dia
    has_bars = asset_bars is not None and len(asset_bars["mins"]) > 0
    if has_bars:
        bar_mins = asset_bars["mins"]
        # Para cada minuto da grade, encontra a barra M1 correspondente (ou última barra anterior)
        idx_map = asset_bars["min_to_idx"]
        lo_arr = np.empty(n_m, dtype=np.float64)
        hi_arr = np.empty(n_m, dtype=np.float64)
        cl_arr = np.empty(n_m, dtype=np.float64)
        last_cl = float(asset_bars["open"][0])
        for i, m in enumerate(mins_grid):
            bi = idx_map.get(int(m))
            if bi is not None:
                lo_arr[i] = asset_bars["low"][bi]
                hi_arr[i] = asset_bars["high"][bi]
                cl_arr[i] = asset_bars["close"][bi]
                last_cl = cl_arr[i]
            else:
                pos = int(np.searchsorted(bar_mins, m, side="right")) - 1
                px = float(asset_bars["close"][pos]) if pos >= 0 else last_cl
                lo_arr[i] = px
                hi_arr[i] = px
                cl_arr[i] = px
    else:
        lo_arr = hi_arr = cl_arr = None

    # Acumular realizados após o minuto de saída
    realized_by_idx = np.zeros(n_m, dtype=np.float64)
    min_to_grid = {int(m): i for i, m in enumerate(mins_grid)}

    # Soma de realizado no início de cada minuto m (trades com min_out < m)
    for tr in asset_trades:
        i_out = min_to_grid.get(tr["min_out"])
        if i_out is not None and i_out + 1 < n_m:
            realized_by_idx[i_out + 1 :] += tr["pnl"]

    # Para cada minuto m, avalia posições ativas (min_in <= m <= min_out)
    for i, m in enumerate(mins_grid):
        realized = realized_by_idx[i]
        fl_low = 0.0
        fl_high = 0.0
        fl_close = 0.0
        lots_open = 0.0

        for tr in asset_trades:
            if tr["min_in"] <= m <= tr["min_out"]:
                lots_open += tr["lots"]
                if has_bars:
                    lo_px = lo_arr[i]
                    hi_px = hi_arr[i]
                    cl_px = cl_arr[i]
                    v_lo = (lo_px - tr["px_in"]) * tr["side"] * pt_val * tr["lots"] - tr["cost_extra"]
                    v_hi = (hi_px - tr["px_in"]) * tr["side"] * pt_val * tr["lots"] - tr["cost_extra"]
                    if m == tr["min_out"]:
                        # Na barra exata da saída, limita excursão além do SL/TP real já executado
                        if tr["pnl"] < 0:
                            v_lo = max(v_lo, tr["pnl"])
                            v_hi = max(v_hi, tr["pnl"])
                        elif tr["pnl"] > 0:
                            v_lo = min(v_lo, tr["pnl"])
                            v_hi = min(v_hi, tr["pnl"])
                        if tr["min_in"] == tr["min_out"]:
                            v_lo = max(min(0.0, tr["pnl"]), v_lo)
                            v_hi = min(max(0.0, tr["pnl"]), v_hi)
                        v_cl = tr["pnl"]
                    else:
                        v_cl = (cl_px - tr["px_in"]) * tr["side"] * pt_val * tr["lots"] - tr["cost_extra"]
                else:
                    # Fallback sem barra M1
                    v_lo = min(0.0, tr["pnl"]) if m == tr["min_out"] else 0.0
                    v_hi = max(0.0, tr["pnl"]) if m == tr["min_out"] else 0.0
                    v_cl = tr["pnl"] if m == tr["min_out"] else 0.0

                fl_low += v_lo
                fl_high += v_hi
                fl_close += v_cl

        worst[i] = realized + min(fl_low, fl_high)
        best[i] = realized + max(fl_low, fl_high)
        close_s[i] = realized + fl_close
        open_lots_s[i] = lots_open

    return worst, best, close_s, open_lots_s


def build_intraday_days(
    trades: list[dict],
    win_m1: dict[str, dict],
    wdo_m1: dict[str, dict],
    all_dates: list[str] | None = None,
) -> list[dict]:
    """Constrói estrutura diária completa com séries M1 de WIN, WDO e Global."""
    if all_dates is None:
        all_dates = sorted(
            d for d in (set(win_m1.keys()) | set(wdo_m1.keys()))
            if DATE_START_2026 <= d <= DATE_END_2026
        )
        if not all_dates and trades:
            all_dates = sorted({t["date"] for t in trades})

    trades_by_day: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        trades_by_day[t["date"]].append(t)

    days: list[dict] = []
    for d in all_dates:
        dt = sorted(trades_by_day.get(d, []), key=lambda x: (x["sec_out"], x["sec_in"], x["strat"]))
        win_tr = [t for t in dt if t["asset"] == "WIN"]
        wdo_tr = [t for t in dt if t["asset"] == "WDO"]

        final_win = sum(t["pnl"] for t in win_tr)
        final_wdo = sum(t["pnl"] for t in wdo_tr)
        final_pnl = final_win + final_wdo

        # Curva fechada (trade-a-trade em ordem de fechamento)
        run_c = 0.0
        min_c = 0.0
        max_c = 0.0
        pnls_closed = []
        for t in dt:
            run_c += t["pnl"]
            min_c = min(min_c, run_c)
            max_c = max(max_c, run_c)
            pnls_closed.append(t["pnl"])

        wb = win_m1.get(d)
        db = wdo_m1.get(d)

        # Grade unificada de minutos do pregão apenas para dias com trades
        if dt:
            m_set = set()
            if wb is not None:
                m_set.update(int(x) for x in wb["mins"] if 540 <= x <= 1050)
            if db is not None:
                m_set.update(int(x) for x in db["mins"] if 540 <= x <= 1050)
            for t in dt:
                m_set.add(t["min_in"])
                m_set.add(t["min_out"])
            mins_grid = np.array(sorted(m_set), dtype=np.int32)
            w_worst, w_best, w_close, w_lots = _eval_asset_minute_series(win_tr, wb, 0.20, mins_grid)
            d_worst, d_best, d_close, d_lots = _eval_asset_minute_series(wdo_tr, db, 10.0, mins_grid)
            g_worst = w_worst + d_worst
            g_best = w_best + d_best

            mae_win = abs(min(0.0, float(np.min(w_worst)))) if len(w_worst) else 0.0
            mfe_win = max(0.0, float(np.max(w_best))) if len(w_best) else 0.0
            mae_wdo = abs(min(0.0, float(np.min(d_worst)))) if len(d_worst) else 0.0
            mfe_wdo = max(0.0, float(np.max(d_best))) if len(d_best) else 0.0
            mae_intra = abs(min(0.0, float(np.min(g_worst)))) if len(g_worst) else 0.0
            mfe_intra = max(0.0, float(np.max(g_best))) if len(g_best) else 0.0
        else:
            mins_grid = np.array([], dtype=np.int32)
            w_worst = w_best = w_close = w_lots = np.array([], dtype=np.float64)
            d_worst = d_best = d_close = d_lots = np.array([], dtype=np.float64)
            g_worst = g_best = np.array([], dtype=np.float64)
            mae_win = mfe_win = mae_wdo = mfe_wdo = mae_intra = mfe_intra = 0.0

        days.append({
            "date": d,
            "period": "OOS" if d <= OOS_END else "IS",
            "num_trades": len(dt),
            "final_pnl": round(final_pnl, 2),
            "final_win": round(final_win, 2),
            "final_wdo": round(final_wdo, 2),
            "mae_intraday": round(mae_intra, 2),
            "mfe_intraday": round(mfe_intra, 2),
            "mae_closed": round(abs(min_c), 2),
            "mfe_closed": round(max_c, 2),
            "mae_win": round(mae_win, 2),
            "mfe_win": round(mfe_win, 2),
            "mae_wdo": round(mae_wdo, 2),
            "mfe_wdo": round(mfe_wdo, 2),
            "pnls_closed": pnls_closed,
            "pnls_win_closed": [t["pnl"] for t in win_tr],
            "pnls_wdo_closed": [t["pnl"] for t in wdo_tr],
            # Séries numpy compactas para replay ultrarrápido
            "_mins": mins_grid,
            "_w_worst": w_worst,
            "_w_close": w_close,
            "_w_lots": w_lots,
            "_d_worst": d_worst,
            "_d_close": d_close,
            "_d_lots": d_lots,
            "_g_worst": g_worst,
        })

    return days


# ═══════════════════════════════════════════════════════════════
# MÉTRICAS & SIMULAÇÃO
# ═══════════════════════════════════════════════════════════════

def _summarize_daily_pnls(
    days: list[dict],
    applied_pnls: list[float],
    intraday_maes: list[float],
    stopped_flags: list[bool],
    saved_total: float,
    missed_total: float,
    recovered_count: int,
    extra_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    n = len(days)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    max_dd_intra = 0.0
    wins = 0
    monthly: dict[str, float] = defaultdict(float)
    curve: list[dict] = []

    for d, pnl, mae_i, is_stp in zip(days, applied_pnls, intraday_maes, stopped_flags):
        # DD intraday pico-a-vale a partir do equity de abertura do dia
        intra_trough = equity - mae_i
        if peak - intra_trough > max_dd_intra:
            max_dd_intra = peak - intra_trough

        equity += pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        if dd > max_dd_intra:
            max_dd_intra = dd
        if pnl > 0:
            wins += 1
        monthly[d["date"][:7]] += pnl
        curve.append({
            "date": d["date"],
            "equity": round(equity, 2),
            "dd": round(dd, 2),
            "day_pnl": round(pnl, 2),
            "stopped": is_stp,
        })

    ret = equity
    std_d = _std(applied_pnls)
    sharpe = (_avg(applied_pnls) / std_d * math.sqrt(252.0)) if std_d > 1e-9 else 0.0
    stopped = sum(1 for f in stopped_flags if f)
    pos_months = sum(1 for v in monthly.values() if v > 0)

    def _slice_stats(mask: list[bool]) -> dict:
        sub_p = [p for p, m in zip(applied_pnls, mask) if m]
        sub_s = sum(1 for f, m in zip(stopped_flags, mask) if m and f)
        eq = pk = dd_s = 0.0
        for p in sub_p:
            eq += p
            if eq > pk:
                pk = eq
            dd_s = max(dd_s, pk - eq)
        sd = _std(sub_p)
        return {
            "days": len(sub_p),
            "ret": round(eq, 2),
            "max_dd": round(dd_s, 2),
            "ret_dd": round(eq / dd_s, 2) if dd_s > 1e-6 else 0.0,
            "sharpe": round((_avg(sub_p) / sd * math.sqrt(252.0)) if sd > 1e-9 else 0.0, 2),
            "stopped": sub_s,
            "worst_day": round(min(sub_p), 2) if sub_p else 0.0,
            "best_day": round(max(sub_p), 2) if sub_p else 0.0,
        }

    oos_mask = [d["period"] == "OOS" for d in days]
    is_mask = [d["period"] == "IS" for d in days]

    out: dict[str, Any] = {
        "ret": round(ret, 2),
        "max_dd": round(max_dd, 2),
        "max_dd_intraday": round(max_dd_intra, 2),
        "ret_dd": round(ret / max_dd, 2) if max_dd > 1e-6 else (99.9 if ret > 0 else 0.0),
        "ret_dd_intraday": round(ret / max_dd_intra, 2) if max_dd_intra > 1e-6 else 0.0,
        "sharpe": round(sharpe, 2),
        "win_rate": round(wins / n * 100.0, 1) if n > 0 else 0.0,
        "stopped": stopped,
        "stopped_pct": round(stopped / n * 100.0, 1) if n > 0 else 0.0,
        "recovered": recovered_count,
        "recovery_rate": round(recovered_count / stopped * 100.0, 1) if stopped > 0 else 0.0,
        "saved": round(saved_total, 2),
        "missed": round(missed_total, 2),
        "net": round(saved_total - missed_total, 2),
        "worst_day": round(min(applied_pnls), 2) if applied_pnls else 0.0,
        "best_day": round(max(applied_pnls), 2) if applied_pnls else 0.0,
        "pos_months": pos_months,
        "total_months": len(monthly),
        "monthly": {k: round(v, 2) for k, v in sorted(monthly.items())},
        "oos": _slice_stats(oos_mask),
        "is": _slice_stats(is_mask),
        "curve": curve,
    }
    if extra_counts:
        out.update(extra_counts)
    return out


def simulate_single_scope(
    days: list[dict],
    stop_value: float,
    scope: str = "global",
    mode: str = "intraday_m1",
    slippage_per_lot: float = 0.0,
    isolated_asset: bool = False,
) -> dict[str, Any]:
    """Simula um stop diário único para `scope` in ('global', 'win', 'wdo').

    Se `isolated_asset=True` e `scope in ('win','wdo')`, mede o impacto na curva
    apenas daquele ativo; se `False`, mede o impacto no portfólio total (WIN+WDO).
    """
    if scope not in ("global", "win", "wdo"):
        raise ValueError(f"scope inválido: {scope}")
    if mode not in ("intraday_m1", "closed_only"):
        raise ValueError(f"mode inválido: {mode}")

    applied: list[float] = []
    intra_maes: list[float] = []
    stopped_flags: list[bool] = []
    saved = 0.0
    missed = 0.0
    recovered = 0

    for d in days:
        if scope == "global":
            mae_val = d["mae_intraday"] if mode == "intraday_m1" else d["mae_closed"]
            base_pnl = d["final_pnl"]
            other_pnl = 0.0
            g_arr = d["_g_worst"]
            lots_arr = (d["_w_lots"] + d["_d_lots"]) if len(d["_w_lots"]) else np.array([])
        elif scope == "win":
            if mode == "intraday_m1":
                mae_val = d["mae_win"]
            else:
                r = m = 0.0
                for p in d["pnls_win_closed"]:
                    r += p
                    m = min(m, r)
                mae_val = abs(m)
            base_pnl = d["final_win"]
            other_pnl = 0.0 if isolated_asset else d["final_wdo"]
            g_arr = d["_w_worst"]
            lots_arr = d["_w_lots"]
        else:  # scope == "wdo"
            if mode == "intraday_m1":
                mae_val = d["mae_wdo"]
            else:
                r = m = 0.0
                for p in d["pnls_wdo_closed"]:
                    r += p
                    m = min(m, r)
                mae_val = abs(m)
            base_pnl = d["final_wdo"]
            other_pnl = 0.0 if isolated_asset else d["final_win"]
            g_arr = d["_d_worst"]
            lots_arr = d["_d_lots"]

        if stop_value > 0 and mae_val >= stop_value:
            slip = 0.0
            if slippage_per_lot > 0 and len(g_arr):
                hits = np.flatnonzero(g_arr <= -stop_value)
                if len(hits) > 0:
                    slip = float(lots_arr[hits[0]]) * slippage_per_lot
            stopped_scope_pnl = -stop_value - slip
            day_pnl = stopped_scope_pnl + other_pnl
            stopped_flags.append(True)
            if base_pnl < stopped_scope_pnl:
                saved += stopped_scope_pnl - base_pnl
            else:
                missed += base_pnl - stopped_scope_pnl
                if base_pnl >= 0:
                    recovered += 1
            intra_maes.append(min(mae_val, abs(stopped_scope_pnl)) if scope == "global" else d["mae_intraday"])
        else:
            day_pnl = base_pnl + other_pnl
            stopped_flags.append(False)
            if scope == "global":
                intra_maes.append(mae_val)
            else:
                intra_maes.append(mae_val if isolated_asset else d["mae_intraday"])

        applied.append(round(day_pnl, 2))

    return _summarize_daily_pnls(
        days, applied, intra_maes, stopped_flags, saved, missed, recovered
    )


def simulate_combined_stops(
    days: list[dict],
    stop_global: float = 0.0,
    stop_win: float = 0.0,
    stop_wdo: float = 0.0,
    slippage_per_lot: float = 0.0,
) -> dict[str, Any]:
    """Replay cronológico M1 exato com limites simultâneos Global + WIN + WDO."""
    applied: list[float] = []
    intra_maes: list[float] = []
    stopped_flags: list[bool] = []
    saved = 0.0
    missed = 0.0
    recovered = 0
    cnt_global = 0
    cnt_win = 0
    cnt_wdo = 0

    for d in days:
        need_win = stop_win > 0 and d["mae_win"] >= stop_win
        need_wdo = stop_wdo > 0 and d["mae_wdo"] >= stop_wdo
        need_glob = stop_global > 0 and d["mae_intraday"] >= stop_global

        # Fast-path O(1): nenhum limite tocado hoje
        if not need_win and not need_wdo and not need_glob:
            applied.append(d["final_pnl"])
            intra_maes.append(d["mae_intraday"])
            stopped_flags.append(False)
            continue

        mins = d["_mins"]
        if len(mins) == 0:
            applied.append(d["final_pnl"])
            intra_maes.append(d["mae_intraday"])
            stopped_flags.append(False)
            continue

        w_worst = d["_w_worst"]
        w_close = d["_w_close"]
        w_lots = d["_w_lots"]
        d_worst = d["_d_worst"]
        d_close = d["_d_close"]
        d_lots = d["_d_lots"]

        win_halted = False
        wdo_halted = False
        glob_halted = False
        win_locked_pnl = 0.0
        wdo_locked_pnl = 0.0
        day_locked_pnl = 0.0
        day_min = 0.0

        for i in range(len(mins)):
            cur_w_worst = win_locked_pnl if win_halted else float(w_worst[i])
            cur_d_worst = wdo_locked_pnl if wdo_halted else float(d_worst[i])
            cur_g_worst = cur_w_worst + cur_d_worst
            day_min = min(day_min, cur_g_worst)

            # 1) Global tem prioridade se ambos baterem simultaneamente no mesmo minuto
            if stop_global > 0 and cur_g_worst <= -stop_global:
                open_l = (0.0 if win_halted else float(w_lots[i])) + (0.0 if wdo_halted else float(d_lots[i]))
                day_locked_pnl = -stop_global - open_l * slippage_per_lot
                day_min = min(day_min, day_locked_pnl)
                glob_halted = True
                break

            # 2) Sub-limite WIN
            if stop_win > 0 and not win_halted and cur_w_worst <= -stop_win:
                win_halted = True
                win_locked_pnl = -stop_win - float(w_lots[i]) * slippage_per_lot
                cnt_win += 1
                # Re-checar Global imediatamente com WIN travado
                recheck_g = win_locked_pnl + cur_d_worst
                day_min = min(day_min, recheck_g)
                if stop_global > 0 and recheck_g <= -stop_global:
                    open_l = 0.0 if wdo_halted else float(d_lots[i])
                    day_locked_pnl = -stop_global - open_l * slippage_per_lot
                    day_min = min(day_min, day_locked_pnl)
                    glob_halted = True
                    break

            # 3) Sub-limite WDO
            if stop_wdo > 0 and not wdo_halted and cur_d_worst <= -stop_wdo:
                wdo_halted = True
                wdo_locked_pnl = -stop_wdo - float(d_lots[i]) * slippage_per_lot
                cnt_wdo += 1
                cur_w_now = win_locked_pnl if win_halted else float(w_close[i])
                recheck_g = cur_w_now + wdo_locked_pnl
                day_min = min(day_min, recheck_g)
                if stop_global > 0 and recheck_g <= -stop_global:
                    open_l = 0.0 if win_halted else float(w_lots[i])
                    day_locked_pnl = -stop_global - open_l * slippage_per_lot
                    day_min = min(day_min, day_locked_pnl)
                    glob_halted = True
                    break

        if glob_halted:
            day_pnl = day_locked_pnl
            cnt_global += 1
        else:
            fin_w = win_locked_pnl if win_halted else d["final_win"]
            fin_d = wdo_locked_pnl if wdo_halted else d["final_wdo"]
            day_pnl = fin_w + fin_d

        any_stop = glob_halted or win_halted or wdo_halted
        stopped_flags.append(any_stop)
        intra_maes.append(abs(min(0.0, day_min)))
        applied.append(round(day_pnl, 2))

        if any_stop:
            base = d["final_pnl"]
            if base < day_pnl:
                saved += day_pnl - base
            else:
                missed += base - day_pnl
                if base >= 0:
                    recovered += 1

    return _summarize_daily_pnls(
        days,
        applied,
        intra_maes,
        stopped_flags,
        saved,
        missed,
        recovered,
        extra_counts={
            "stopped_global": cnt_global,
            "stopped_win": cnt_win,
            "stopped_wdo": cnt_wdo,
        },
    )


# ═══════════════════════════════════════════════════════════════
# SWEEP, COMBO GRID, RECOVERY, WFA, MONTE CARLO, ROBÔS
# ═══════════════════════════════════════════════════════════════

def run_param_sweep(
    days: list[dict],
    scope: str = "global",
    mode: str = "intraday_m1",
    slippage_per_lot: float = 0.0,
    isolated_asset: bool = False,
) -> dict[str, Any]:
    """Executa sweep de stops para o escopo escolhido e seleciona stops ótimos."""
    if scope == "global":
        key = "mae_intraday" if mode == "intraday_m1" else "mae_closed"
    elif scope == "win":
        key = "mae_win"
    else:
        key = "mae_wdo"

    maes = [d[key] for d in days if d[key] > 0]
    avg_mae = _avg(maes) if maes else 200.0
    max_mae = max(maes) if maes else 2000.0

    step = 25 if max_mae <= 1200 else 50
    start_stop = max(step, _round_step(max(50.0, avg_mae * 0.25), step))
    end_stop = max(start_stop + step * 5, _round_step(max_mae * 1.10, step))

    base = simulate_single_scope(days, 0.0, scope=scope, mode=mode, isolated_asset=isolated_asset)
    base_ret = base["ret"]
    base_rdd = base["ret_dd"]

    rows: list[dict] = []
    for s in range(start_stop, end_stop + step, step):
        sim = simulate_single_scope(
            days,
            float(s),
            scope=scope,
            mode=mode,
            slippage_per_lot=slippage_per_lot,
            isolated_asset=isolated_asset,
        )
        rows.append({
            "stop": s,
            "ret": sim["ret"],
            "max_dd": sim["max_dd"],
            "max_dd_intraday": sim["max_dd_intraday"],
            "ret_dd": sim["ret_dd"],
            "sharpe": sim["sharpe"],
            "win_rate": sim["win_rate"],
            "recovery_rate": sim["recovery_rate"],
            "recovered": sim["recovered"],
            "stopped": sim["stopped"],
            "stopped_pct": sim["stopped_pct"],
            "saved": sim["saved"],
            "missed": sim["missed"],
            "net": sim["net"],
            "worst_day": sim["worst_day"],
            "oos_ret": sim["oos"]["ret"],
            "oos_ret_dd": sim["oos"]["ret_dd"],
            "is_ret": sim["is"]["ret"],
            "is_ret_dd": sim["is"]["ret_dd"],
        })

    min_floor = avg_mae * 0.80
    cand_conserv = [
        r for r in rows
        if r["stop"] >= min_floor and r["ret_dd"] > base_rdd and r["ret"] >= base_ret * 0.85
    ]
    cand_profit = [
        r for r in rows
        if r["stop"] >= min_floor and r["ret_dd"] > base_rdd
    ]

    stop_recommended = bool(cand_conserv or cand_profit)
    if cand_conserv:
        stop_conserv = max(cand_conserv, key=lambda r: (r["ret_dd"], r["ret"]))["stop"]
    elif cand_profit:
        stop_conserv = max(cand_profit, key=lambda r: (r["ret_dd"], r["ret"]))["stop"]
    else:
        stop_conserv = 0

    if cand_profit:
        stop_profit = max(cand_profit, key=lambda r: (r["ret"], r["ret_dd"]))["stop"]
    else:
        stop_profit = stop_conserv

    # Melhor ponto de proteção de cauda informativo (pior dia limitado mantendo >=92% do lucro)
    tail_cands = [r for r in rows if r["stop"] >= min_floor and r["ret"] >= base_ret * 0.92]
    if tail_cands:
        best_tail = max(tail_cands, key=lambda r: (r["ret_dd"], -r["max_dd"]))
        tail_stop = best_tail["stop"]
    else:
        tail_stop = _round_step(_percentile(maes, 95), step) if maes else 0

    return {
        "scope": scope,
        "mode": mode,
        "avg_mae": round(avg_mae, 2),
        "max_mae": round(max_mae, 2),
        "min_stop_floor": round(min_floor, 2),
        "baseline": base,
        "stop_recommended": stop_recommended,
        "stop_conserv": stop_conserv,
        "stop_profit": stop_profit,
        "tail_guard_stop": tail_stop,
        "rows": rows,
    }


def run_combined_grid(
    days: list[dict],
    win_sweep: dict,
    wdo_sweep: dict,
    global_sweep: dict,
    slippage_per_lot: float = 0.0,
) -> dict[str, Any]:
    """Grid 3D combinado `(Stop Global, Stop WIN, Stop WDO)` + Matriz 2D `WIN × WDO`."""
    def _pick_candidates(sw: dict, n_pick: int = 8) -> list[int]:
        rows = sw["rows"]
        if not rows:
            return [0]
        lo = max(rows[0]["stop"], int(sw["min_stop_floor"]))
        hi = rows[-1]["stop"]
        elig = [r["stop"] for r in rows if lo <= r["stop"] <= hi]
        if not elig:
            elig = [r["stop"] for r in rows]
        if len(elig) <= n_pick:
            picked = list(elig)
        else:
            idxs = np.linspace(0, len(elig) - 1, n_pick, dtype=int)
            picked = [elig[i] for i in idxs]
        for special in (sw["stop_conserv"], sw["stop_profit"], sw["tail_guard_stop"]):
            if special and special > 0:
                picked.append(special)
        return sorted(set([0] + picked))

    win_cands = _pick_candidates(win_sweep, 8)
    wdo_cands = _pick_candidates(wdo_sweep, 8)
    glob_cands = _pick_candidates(global_sweep, 6)

    # Matriz 2D WIN x WDO (com stop_global=0)
    win_no_zero = [x for x in win_cands if x > 0]
    wdo_no_zero = [x for x in wdo_cands if x > 0]
    matrix_rows: list[dict] = []
    for sw_val in [0] + win_no_zero:
        for sd_val in [0] + wdo_no_zero:
            sim = simulate_combined_stops(
                days, stop_global=0.0, stop_win=float(sw_val), stop_wdo=float(sd_val), slippage_per_lot=slippage_per_lot
            )
            matrix_rows.append({
                "stop_win": sw_val,
                "stop_wdo": sd_val,
                "ret": sim["ret"],
                "max_dd": sim["max_dd"],
                "ret_dd": sim["ret_dd"],
                "sharpe": sim["sharpe"],
                "stopped": sim["stopped"],
                "worst_day": sim["worst_day"],
            })

    # Grid 3D completo
    combos: list[dict] = []
    for sg in glob_cands:
        for sw_val in win_cands:
            for sd_val in wdo_cands:
                if sg == 0 and sw_val == 0 and sd_val == 0:
                    continue
                if sg > 0 and sw_val > 0 and sd_val > 0 and sg > sw_val + sd_val:
                    # Global maior que a soma WIN+WDO nunca pode disparar antes dos dois isolados
                    continue
                sim = simulate_combined_stops(
                    days,
                    stop_global=float(sg),
                    stop_win=float(sw_val),
                    stop_wdo=float(sd_val),
                    slippage_per_lot=slippage_per_lot,
                )
                combos.append({
                    "stop_global": sg,
                    "stop_win": sw_val,
                    "stop_wdo": sd_val,
                    "ret": sim["ret"],
                    "max_dd": sim["max_dd"],
                    "max_dd_intraday": sim["max_dd_intraday"],
                    "ret_dd": sim["ret_dd"],
                    "sharpe": sim["sharpe"],
                    "stopped": sim["stopped"],
                    "stopped_global": sim["stopped_global"],
                    "stopped_win": sim["stopped_win"],
                    "stopped_wdo": sim["stopped_wdo"],
                    "worst_day": sim["worst_day"],
                    "oos_ret": sim["oos"]["ret"],
                    "oos_ret_dd": sim["oos"]["ret_dd"],
                    "is_ret": sim["is"]["ret"],
                    "is_ret_dd": sim["is"]["ret_dd"],
                })

    base_ret = global_sweep["baseline"]["ret"]
    valid_conserv = [c for c in combos if c["ret"] >= base_ret * 0.85]
    best_ret_dd = max(valid_conserv or combos, key=lambda c: (c["ret_dd"], c["ret"])) if combos else None
    valid_profit = [c for c in combos if c["ret_dd"] >= global_sweep["baseline"]["ret_dd"]]
    best_profit = max(valid_profit or combos, key=lambda c: (c["ret"], c["ret_dd"])) if combos else None

    top_by_rdd = sorted(combos, key=lambda c: (c["ret_dd"], c["ret"]), reverse=True)[:15]
    top_by_ret = sorted(combos, key=lambda c: (c["ret"], c["ret_dd"]), reverse=True)[:15]

    return {
        "win_candidates": win_cands,
        "wdo_candidates": wdo_cands,
        "global_candidates": glob_cands,
        "matrix_2d": matrix_rows,
        "all_combos": combos,
        "top_by_ret_dd": top_by_rdd,
        "top_by_ret": top_by_ret,
        "best_combo_ret_dd": best_ret_dd,
        "best_combo_profit": best_profit,
    }


def compute_recovery_bands(days: list[dict], scope: str = "global") -> list[dict]:
    """Calcula probabilidade de recuperação por faixa de MAE diário intraday."""
    if scope == "global":
        mae_k, pnl_k, step = "mae_intraday", "final_pnl", 100
    elif scope == "win":
        mae_k, pnl_k, step = "mae_win", "final_win", 50
    else:
        mae_k, pnl_k, step = "mae_wdo", "final_wdo", 50

    maes = [d[mae_k] for d in days if d[mae_k] > 0]
    max_m = int(max(maes) * 1.05) if maes else 1000
    if max_m > 2500 and step < 100:
        step = 100

    out = []
    for lo in range(0, max_m + step, step):
        hi = lo + step
        in_band = [d for d in days if lo <= d[mae_k] < hi]
        if not in_band:
            continue
        rec = [d for d in in_band if d[pnl_k] >= 0]
        not_rec = [d for d in in_band if d[pnl_k] < 0]
        out.append({
            "lo": lo,
            "hi": hi,
            "days": len(in_band),
            "recov_pct": round(len(rec) / len(in_band) * 100.0, 1),
            "avg_recov": round(_avg([d[pnl_k] for d in rec]), 2) if rec else 0.0,
            "avg_not": round(_avg([d[pnl_k] for d in not_rec]), 2) if not_rec else 0.0,
            "expected": round(_avg([d[pnl_k] for d in in_band]), 2),
        })
    return out


def _optimize_stop_on_train(train_days: list[dict], min_floor: float) -> tuple[float, float, float]:
    """Encontra melhor stop por Ret/DD e por Profit em uma janela de treino."""
    maes = [d["mae_intraday"] for d in train_days if d["mae_intraday"] > 0]
    if not maes:
        return 0.0, 0.0, 0.0
    local_avg = _avg(maes)
    local_std = _std(maes)
    local_floor = max(min_floor, local_avg * 0.80)

    base = simulate_single_scope(train_days, 0.0, scope="global", mode="intraday_m1")
    base_rd = base["ret_dd"]

    cands = {_percentile(maes, p) for p in range(55, 100)}
    for mult in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
        cands.add(local_avg + local_std * mult * 0.5)

    best_rd = base_rd
    best_stop_rd = 0.0
    best_prof = base["ret"]
    best_stop_prof = 0.0

    for sv in sorted(cands):
        if sv < local_floor:
            continue
        sim = simulate_single_scope(train_days, sv, scope="global", mode="intraday_m1")
        if sim["ret_dd"] > best_rd:
            best_rd = sim["ret_dd"]
            best_stop_rd = sv
        if sim["ret_dd"] >= base_rd and sim["ret"] > best_prof:
            best_prof = sim["ret"]
            best_stop_prof = sv

    if best_stop_prof == 0.0:
        best_stop_prof = best_stop_rd
    return best_stop_rd, best_stop_prof, best_rd


def run_walk_forward(
    days: list[dict],
    min_stop_floor: float,
    train_window: int = 60,
    test_window: int = 20,
    step: int = 20,
) -> dict[str, Any]:
    """Walk-Forward Rolling (`60d treino -> 20d teste`) + Validação Cruzada IS<->OOS."""
    folds: list[dict] = []
    i = 0
    while i + train_window + test_window <= len(days):
        train = days[i : i + train_window]
        test = days[i + train_window : i + train_window + test_window]

        stop_rd, stop_prof, train_rd = _optimize_stop_on_train(train, min_stop_floor)
        base_oos = simulate_single_scope(test, 0.0, scope="global", mode="intraday_m1")
        sim_oos = simulate_single_scope(test, stop_rd, scope="global", mode="intraday_m1")
        imp = (sim_oos["ret_dd"] / base_oos["ret_dd"] - 1.0) if base_oos["ret_dd"] > 0 else 0.0

        folds.append({
            "fold": len(folds) + 1,
            "train_period": f"{train[0]['date']} -> {train[-1]['date']}",
            "test_period": f"{test[0]['date']} -> {test[-1]['date']}",
            "optimal_stop_ret_dd": _round_step(stop_rd, 25) if stop_rd > 0 else 0,
            "optimal_stop_profit": _round_step(stop_prof, 25) if stop_prof > 0 else 0,
            "train_ret_dd": round(train_rd, 2),
            "oos_ret_dd": sim_oos["ret_dd"],
            "base_ret_dd": base_oos["ret_dd"],
            "oos_ret": sim_oos["ret"],
            "base_ret": base_oos["ret"],
            "improvement": round(imp, 4),
            "oos_stopped": sim_oos["stopped"],
        })
        i += step

    valid_rd = [f["optimal_stop_ret_dd"] for f in folds if f["optimal_stop_ret_dd"] > 0]
    valid_pf = [f["optimal_stop_profit"] for f in folds if f["optimal_stop_profit"] > 0]
    med_rd = _round_step(_percentile(valid_rd, 50), 25) if valid_rd else 0
    med_pf = _round_step(_percentile(valid_pf, 50), 25) if valid_pf else 0

    # Validação Cruzada Canônica IS <-> OOS
    oos_days = [d for d in days if d["period"] == "OOS"]
    is_days = [d for d in days if d["period"] == "IS"]
    split_checks = []
    for label, tr_set, te_set in [
        ("Treino IS (Mai-Nov) -> Teste OOS Cego (Jan-Mai)", is_days, oos_days),
        ("Treino OOS (Jan-Mai) -> Teste IS (Mai-Nov)", oos_days, is_days),
    ]:
        if tr_set and te_set:
            s_rd, s_pf, _ = _optimize_stop_on_train(tr_set, min_stop_floor)
            s_rd_r = _round_step(s_rd, 25) if s_rd > 0 else 0
            b_te = simulate_single_scope(te_set, 0.0, scope="global", mode="intraday_m1")
            r_te = simulate_single_scope(te_set, float(s_rd_r), scope="global", mode="intraday_m1")
            split_checks.append({
                "label": label,
                "stop_calibrated": s_rd_r,
                "base_ret": b_te["ret"],
                "base_dd": b_te["max_dd"],
                "base_ret_dd": b_te["ret_dd"],
                "stop_ret": r_te["ret"],
                "stop_dd": r_te["max_dd"],
                "stop_ret_dd": r_te["ret_dd"],
                "stopped": r_te["stopped"],
            })

    return {
        "train_window": train_window,
        "test_window": test_window,
        "step": step,
        "folds": folds,
        "robust_stop_ret_dd": med_rd,
        "robust_stop_profit": med_pf,
        "canonical_splits": split_checks,
    }


def run_monte_carlo(
    days: list[dict],
    stop_value: float,
    n_sims: int = 2000,
    seed: int = 42,
    block_size: int = 1,
) -> dict[str, Any]:
    """Bootstrap Monte Carlo (IID quando `block_size=1`, ou em blocos de dias)."""
    rng = random.Random(seed)
    n = len(days)
    if n == 0 or stop_value <= 0:
        return {
            "n": n_sims,
            "block_size": block_size,
            "stop_value": stop_value,
            "wins_rdd": 0,
            "wins_dd": 0,
            "wins_ret": 0,
            "avg_rdd_stop": 0.0,
            "avg_rdd_no": 0.0,
            "avg_dd_stop": 0.0,
            "avg_dd_no": 0.0,
            "p95_dd_stop": 0.0,
            "p95_dd_no": 0.0,
        }

    # Pré-extrai arrays por dia para velocidade máxima
    base_pnls = [d["final_pnl"] for d in days]
    stop_pnls = [
        (-float(stop_value) if d["mae_intraday"] >= stop_value else d["final_pnl"])
        for d in days
    ]

    wins_rdd = wins_dd = wins_ret = 0
    s_rdds: list[float] = []
    n_rdds: list[float] = []
    s_dds: list[float] = []
    n_dds: list[float] = []

    def _fast_metrics(seq_idx: list[int], arr: list[float]) -> tuple[float, float, float]:
        eq = pk = dd = 0.0
        for idx in seq_idx:
            eq += arr[idx]
            if eq > pk:
                pk = eq
            d_val = pk - eq
            if d_val > dd:
                dd = d_val
        rdd = (eq / dd) if dd > 1e-6 else (99.9 if eq > 0 else 0.0)
        return eq, dd, rdd

    n_blocks = max(1, (n + block_size - 1) // block_size)
    for _ in range(n_sims):
        if block_size <= 1:
            idxs = [rng.randrange(n) for _ in range(n)]
        else:
            idxs = []
            for _b in range(n_blocks):
                start = rng.randrange(n)
                for off in range(block_size):
                    idxs.append((start + off) % n)
                    if len(idxs) >= n:
                        break
        sr, sdd, srdd = _fast_metrics(idxs, stop_pnls)
        nr, ndd, nrdd = _fast_metrics(idxs, base_pnls)
        s_rdds.append(srdd)
        n_rdds.append(nrdd)
        s_dds.append(sdd)
        n_dds.append(ndd)
        if srdd > nrdd:
            wins_rdd += 1
        if sdd < ndd:
            wins_dd += 1
        if sr > nr:
            wins_ret += 1

    return {
        "n": n_sims,
        "block_size": block_size,
        "stop_value": stop_value,
        "wins_rdd": wins_rdd,
        "wins_dd": wins_dd,
        "wins_ret": wins_ret,
        "avg_rdd_stop": round(_avg(s_rdds), 2),
        "avg_rdd_no": round(_avg(n_rdds), 2),
        "avg_dd_stop": round(_avg(s_dds), 2),
        "avg_dd_no": round(_avg(n_dds), 2),
        "p95_dd_stop": round(_percentile(s_dds, 95), 2),
        "p95_dd_no": round(_percentile(n_dds, 95), 2),
    }


def analyze_robots(trades: list[dict], days: list[dict]) -> list[dict]:
    """Estatísticas individuais por robô + contribuição nos 15 piores dias da carteira."""
    worst_15_dates = {d["date"] for d in sorted(days, key=lambda x: x["final_pnl"])[:15]}
    total_worst_loss = sum(abs(min(0.0, d["final_pnl"])) for d in days if d["date"] in worst_15_dates)

    by_robot: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_robot[t["strat"]].append(t)

    robots: list[dict] = []
    for rid, rt in by_robot.items():
        spec = ROBOT_METADATA[rid]
        profits = [t["pnl"] for t in rt]
        maes = [t.get("mae_brl", 0.0) for t in rt]
        mfes = [t.get("mfe_brl", 0.0) for t in rt]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]

        gw = sum(wins)
        gl = abs(sum(losses))
        avg_win = _avg(wins)
        avg_loss = abs(_avg(losses))
        payoff = (avg_win / avg_loss) if avg_loss > 0 else 0.0
        pf = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)

        mfe_effs = [(t["pnl"] / t["mfe_brl"]) * 100.0 for t in rt if t.get("mfe_brl", 0.0) > 1.0]
        mfe_eff = _avg([e for e in mfe_effs if abs(e) < 500.0])

        daily_map: dict[str, float] = defaultdict(float)
        for t in rt:
            daily_map[t["date"]] += t["pnl"]
        dv = list(daily_map.values())
        worst_15_pnl = sum(daily_map.get(dt_s, 0.0) for dt_s in worst_15_dates)
        worst_15_share = (abs(min(0.0, worst_15_pnl)) / total_worst_loss * 100.0) if total_worst_loss > 0 else 0.0

        mae_std = _std(maes)
        robots.append({
            "id": rid,
            "magic": spec.magic,
            "asset": spec.asset,
            "tf": spec.tf,
            "desc": spec.desc,
            "total_trades": len(rt),
            "total_lots": int(round(sum(t["lots"] for t in rt))),
            "total_profit": round(sum(profits), 2),
            "win_rate": round(len(wins) / len(profits) * 100.0, 1) if profits else 0.0,
            "pf": round(pf, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "payoff": round(payoff, 2),
            "expectancy": round(_avg(profits), 2),
            "mae": {
                "mean": round(_avg(maes), 2),
                "std": round(mae_std, 2),
                "p50": round(_percentile(maes, 50), 2),
                "p75": round(_percentile(maes, 75), 2),
                "p90": round(_percentile(maes, 90), 2),
                "p95": round(_percentile(maes, 95), 2),
                "p99": round(_percentile(maes, 99), 2),
                "max": round(max(maes) if maes else 0.0, 2),
            },
            "mfe": {
                "mean": round(_avg(mfes), 2),
                "p50": round(_percentile(mfes, 50), 2),
                "p75": round(_percentile(mfes, 75), 2),
                "p90": round(_percentile(mfes, 90), 2),
            },
            "mfe_eff": round(mfe_eff, 1),
            "optimal_trade_stop": round(_percentile(maes, 90) + mae_std * 0.5, 2),
            "daily": {
                "mean": round(_avg(dv), 2),
                "std": round(_std(dv), 2),
                "worst": round(min(dv), 2) if dv else 0.0,
                "best": round(max(dv), 2) if dv else 0.0,
                "days": len(dv),
            },
            "suggested_daily_stop": round(abs(_avg(dv) - 2.0 * _std(dv)), 2) if len(dv) >= 2 else 0.0,
            "worst_15_pnl": round(worst_15_pnl, 2),
            "worst_15_share_pct": round(worst_15_share, 1),
        })

    robots.sort(key=lambda r: r["total_profit"], reverse=True)
    return robots


# ═══════════════════════════════════════════════════════════════
# ORQUESTRADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════

def run_full_analysis(
    portfolio_id: str = "proposta_b_11",
    win_mult: float = 1.0,
    wdo_mult: float = 1.0,
    cost_mode: str = "net",
    slippage_per_lot: float = 0.0,
    htm_dir: str | Path = DEFAULT_HTM_DIR,
    m1_cache: tuple[dict[str, dict], dict[str, dict]] | None = None,
) -> dict[str, Any]:
    """Executa análise completa de stop diário máximo para o portfólio especificado."""
    if portfolio_id not in PORTFOLIO_PRESETS:
        raise ValueError(f"Preset desconhecido: {portfolio_id}. Opções: {list(PORTFOLIO_PRESETS)}")

    preset = PORTFOLIO_PRESETS[portfolio_id]
    robot_codes = preset["robots"]

    win_m1, wdo_m1 = m1_cache if m1_cache is not None else load_m1_bars()
    trades = load_portfolio_trades(
        robot_codes, htm_dir=htm_dir, cost_mode=cost_mode, win_mult=win_mult, wdo_mult=wdo_mult
    )
    enrich_trades_with_m1_mae_mfe(trades, win_m1, wdo_m1)
    days = build_intraday_days(trades, win_m1, wdo_m1)

    # Sweeps em 4 eixos: Global M1, Global Fechado, WIN (M1 no portfólio + isolado), WDO
    sw_global_m1 = run_param_sweep(days, scope="global", mode="intraday_m1", slippage_per_lot=slippage_per_lot)
    sw_global_closed = run_param_sweep(days, scope="global", mode="closed_only", slippage_per_lot=slippage_per_lot)
    sw_win_port = run_param_sweep(days, scope="win", mode="intraday_m1", slippage_per_lot=slippage_per_lot, isolated_asset=False)
    sw_win_iso = run_param_sweep(days, scope="win", mode="intraday_m1", slippage_per_lot=slippage_per_lot, isolated_asset=True)
    sw_wdo_port = run_param_sweep(days, scope="wdo", mode="intraday_m1", slippage_per_lot=slippage_per_lot, isolated_asset=False)
    sw_wdo_iso = run_param_sweep(days, scope="wdo", mode="intraday_m1", slippage_per_lot=slippage_per_lot, isolated_asset=True)

    # Grid 3D combinado Global + WIN + WDO
    combined = run_combined_grid(days, sw_win_iso, sw_wdo_iso, sw_global_m1, slippage_per_lot=slippage_per_lot)

    # Determinar stops principais (ou fallback de proteção de cauda / melhor combo)
    primary_stop_rdd = sw_global_m1["stop_conserv"] or sw_global_m1["tail_guard_stop"]
    primary_stop_prof = sw_global_m1["stop_profit"] or primary_stop_rdd

    baseline = sw_global_m1["baseline"]
    sim_rdd = simulate_single_scope(days, float(primary_stop_rdd), scope="global", mode="intraday_m1", slippage_per_lot=slippage_per_lot)
    sim_prof = simulate_single_scope(days, float(primary_stop_prof), scope="global", mode="intraday_m1", slippage_per_lot=slippage_per_lot)

    best_c = combined["best_combo_ret_dd"]
    if best_c:
        sim_combo = simulate_combined_stops(
            days,
            stop_global=float(best_c["stop_global"]),
            stop_win=float(best_c["stop_win"]),
            stop_wdo=float(best_c["stop_wdo"]),
            slippage_per_lot=slippage_per_lot,
        )
    else:
        sim_combo = baseline

    # Recovery, WFA, Monte Carlo, Robôs
    rec_global = compute_recovery_bands(days, "global")
    rec_win = compute_recovery_bands(days, "win")
    rec_wdo = compute_recovery_bands(days, "wdo")

    wfa = run_walk_forward(days, min_stop_floor=sw_global_m1["min_stop_floor"], train_window=60, test_window=20, step=20)
    mc_iid = run_monte_carlo(days, primary_stop_rdd, n_sims=2000, seed=42, block_size=1)
    mc_block = run_monte_carlo(days, primary_stop_rdd, n_sims=2000, seed=42, block_size=5)
    robots = analyze_robots(trades, days)

    d_maes_g = [d["mae_intraday"] for d in days if d["mae_intraday"] > 0]
    d_maes_c = [d["mae_closed"] for d in days if d["mae_closed"] > 0]
    d_maes_w = [d["mae_win"] for d in days if d["mae_win"] > 0]
    d_maes_d = [d["mae_wdo"] for d in days if d["mae_wdo"] > 0]
    d_pnls = [d["final_pnl"] for d in days]

    win_count = sum(1 for r in robot_codes if ROBOT_METADATA[r].asset == "WIN")
    wdo_count = sum(1 for r in robot_codes if ROBOT_METADATA[r].asset == "WDO")

    # Resumo por ativo
    asset_summary = []
    for asset_name, iso_sw in [("WIN", sw_win_iso), ("WDO", sw_wdo_iso)]:
        sub_tr = [t for t in trades if t["asset"] == asset_name]
        asset_summary.append({
            "asset": asset_name,
            "robots": win_count if asset_name == "WIN" else wdo_count,
            "trades": len(sub_tr),
            "lots": int(round(sum(t["lots"] for t in sub_tr))),
            "profit": iso_sw["baseline"]["ret"],
            "max_dd": iso_sw["baseline"]["max_dd"],
            "ret_dd": iso_sw["baseline"]["ret_dd"],
            "mae_avg": iso_sw["avg_mae"],
            "mae_max": iso_sw["max_mae"],
            "stop_conserv": iso_sw["stop_conserv"],
            "stop_profit": iso_sw["stop_profit"],
            "tail_guard_stop": iso_sw["tail_guard_stop"],
            "stop_recommended": iso_sw["stop_recommended"],
        })

    # Compactar dias sem arrays numpy privados para export JSON limpo
    worst_days = [
        {
            "date": d["date"],
            "period": d["period"],
            "final_pnl": d["final_pnl"],
            "final_win": d["final_win"],
            "final_wdo": d["final_wdo"],
            "mae_intraday": d["mae_intraday"],
            "mae_closed": d["mae_closed"],
            "mae_win": d["mae_win"],
            "mae_wdo": d["mae_wdo"],
            "num_trades": d["num_trades"],
        }
        for d in sorted(days, key=lambda x: x["final_pnl"])[:20]
    ]

    return {
        "portfolio_id": portfolio_id,
        "label": preset["label"],
        "subtitle": preset["subtitle"],
        "robots_list": robot_codes,
        "cost_mode": cost_mode,
        "win_mult": win_mult,
        "wdo_mult": wdo_mult,
        "slippage_per_lot": slippage_per_lot,
        "period_start": days[0]["date"] if days else "",
        "period_end": days[-1]["date"] if days else "",
        "total_days": len(days),
        "oos_days": sum(1 for d in days if d["period"] == "OOS"),
        "is_days": sum(1 for d in days if d["period"] == "IS"),
        "portfolio": {
            "total_robots": len(robot_codes),
            "win_robots": win_count,
            "wdo_robots": wdo_count,
            "total_trades": len(trades),
            "total_lots": int(round(sum(t["lots"] for t in trades))),
            "total_profit": round(sum(t["pnl"] for t in trades), 2),
            "total_profit_mt5_raw": round(sum(t["pnl_mt5_raw"] for t in trades), 2),
            "total_profit_gross": round(sum(t["pnl_gross"] for t in trades), 2),
            "daily_stats": {
                "mean": round(_avg(d_pnls), 2),
                "std": round(_std(d_pnls), 2),
                "worst": round(min(d_pnls), 2) if d_pnls else 0.0,
                "best": round(max(d_pnls), 2) if d_pnls else 0.0,
                "days": len(d_pnls),
            },
            "mae_daily_m1": {
                "mean": round(_avg(d_maes_g), 2),
                "std": round(_std(d_maes_g), 2),
                "p50": round(_percentile(d_maes_g, 50), 2),
                "p75": round(_percentile(d_maes_g, 75), 2),
                "p90": round(_percentile(d_maes_g, 90), 2),
                "p95": round(_percentile(d_maes_g, 95), 2),
                "p99": round(_percentile(d_maes_g, 99), 2),
                "max": round(max(d_maes_g), 2) if d_maes_g else 0.0,
            },
            "mae_daily_closed": {
                "mean": round(_avg(d_maes_c), 2),
                "p75": round(_percentile(d_maes_c, 75), 2),
                "p90": round(_percentile(d_maes_c, 90), 2),
                "max": round(max(d_maes_c), 2) if d_maes_c else 0.0,
            },
            "mae_win_m1": {
                "mean": round(_avg(d_maes_w), 2),
                "p75": round(_percentile(d_maes_w, 75), 2),
                "p90": round(_percentile(d_maes_w, 90), 2),
                "max": round(max(d_maes_w), 2) if d_maes_w else 0.0,
            },
            "mae_wdo_m1": {
                "mean": round(_avg(d_maes_d), 2),
                "p75": round(_percentile(d_maes_d, 75), 2),
                "p90": round(_percentile(d_maes_d, 90), 2),
                "max": round(max(d_maes_d), 2) if d_maes_d else 0.0,
            },
        },
        "stop_recommended": sw_global_m1["stop_recommended"],
        "robust_stops": {
            "global_ret_dd": sw_global_m1["stop_conserv"],
            "global_profit": sw_global_m1["stop_profit"],
            "global_tail_guard": sw_global_m1["tail_guard_stop"],
            "global_closed_ret_dd": sw_global_closed["stop_conserv"],
            "win_isolated_ret_dd": sw_win_iso["stop_conserv"],
            "win_isolated_tail": sw_win_iso["tail_guard_stop"],
            "wdo_isolated_ret_dd": sw_wdo_iso["stop_conserv"],
            "wdo_isolated_tail": sw_wdo_iso["tail_guard_stop"],
            "primary_used": primary_stop_rdd,
            "combo_best_ret_dd": best_c,
            "combo_best_profit": combined["best_combo_profit"],
        },
        "baseline": baseline,
        "final_ret_dd": sim_rdd,
        "final_profit": sim_prof,
        "final_combo": sim_combo,
        "sweeps": {
            "global_m1": sw_global_m1["rows"],
            "global_closed": sw_global_closed["rows"],
            "win_portfolio": sw_win_port["rows"],
            "win_isolated": sw_win_iso["rows"],
            "wdo_portfolio": sw_wdo_port["rows"],
            "wdo_isolated": sw_wdo_iso["rows"],
        },
        "combined": combined,
        "recovery": {
            "global": rec_global,
            "win": rec_win,
            "wdo": rec_wdo,
        },
        "walk_forward": wfa,
        "monte_carlo": {
            "iid": mc_iid,
            "block_5d": mc_block,
        },
        "robots": robots,
        "asset_summary": asset_summary,
        "worst_days": worst_days,
    }
