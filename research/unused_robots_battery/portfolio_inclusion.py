"""Teste de inclusão incremental e seleção stepwise dos robôs validados no portfólio atual (top_8 da 2004051),
usando o motor M1 intraday real de `research/stop_diario/engine.py` (Sem Stop + Stop Atual G850/W400/D550 + W400/D550).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from research.stop_diario.data_loader import load_portfolio_trades
from research.stop_diario.engine import build_intraday_days, simulate_combined_stops
from research.unused_robots_battery.catalog import ACTIVE_8_ROBOTS, IS_END, OOS_START


def _slice_curve_metrics(days: list[dict], curve: list[dict], lo: str, hi: str) -> dict[str, Any]:
    sub = [c for c in curve if lo <= c["date"] <= hi]
    if not sub:
        return {"days": 0, "ret": 0.0, "max_dd": 0.0, "ret_dd": 0.0, "sharpe": 0.0, "worst_day": 0.0}
    pnls = [float(c["day_pnl"]) for c in sub]
    eq = np.concatenate([[0.0], np.cumsum(pnls)])
    pk = np.maximum.accumulate(eq)
    dd = float((pk - eq).max())
    ret = float(sum(pnls))
    std = float(np.std(pnls, ddof=1)) if len(pnls) > 1 else 0.0
    sharpe = (float(np.mean(pnls)) / std * math.sqrt(252.0)) if std > 1e-9 else 0.0
    return {
        "days": len(pnls),
        "ret": round(ret, 2),
        "max_dd": round(dd, 2),
        "ret_dd": round(ret / dd, 2) if dd > 1e-6 else (99.0 if ret > 0 else 0.0),
        "sharpe": round(sharpe, 2),
        "worst_day": round(min(pnls), 2),
    }


def evaluate_portfolio_modes(
    trades: list[dict],
    win_m1: dict[str, dict],
    wdo_m1: dict[str, dict],
    all_dates: list[str],
) -> dict[str, Any]:
    """Avalia o portfólio com motor M1 intraday em 3 regimes: Sem Stop, G850+W400+D550 (atual 2004051) e W400+D550."""
    days = build_intraday_days(trades, win_m1, wdo_m1, all_dates=all_dates)

    def _run(sg: float, sw: float, sd: float) -> dict[str, Any]:
        r = simulate_combined_stops(days, stop_global=sg, stop_win=sw, stop_wdo=sd)
        # Split cronológico primário: IS (Jan–Jul) vs OOS Cego (Ago–Nov)
        is_c = _slice_curve_metrics(days, r["curve"], "2026-01-02", IS_END)
        oos_c = _slice_curve_metrics(days, r["curve"], OOS_START, "2026-11-06")
        return {
            "ret": r["ret"],
            "max_dd": r["max_dd"],
            "max_dd_intraday": r["max_dd_intraday"],
            "ret_dd": r["ret_dd"],
            "sharpe": r["sharpe"],
            "win_rate": r["win_rate"],
            "worst_day": r["worst_day"],
            "stopped": r["stopped"],
            "pos_months": r["pos_months"],
            "total_months": r["total_months"],
            "is_chron": is_c,
            "oos_chron": oos_c,
            "oos_h1": r["oos"],
            "is_h2": r["is"],
            "curve": [{"date": c["date"], "pnl": c["day_pnl"], "equity": c["equity"]} for c in r["curve"]],
        }

    return {
        "no_stop": _run(0.0, 0.0, 0.0),
        "stop_live_850": _run(850.0, 400.0, 550.0),
        "stop_indep_0": _run(0.0, 400.0, 550.0),
    }


def _daily_series(trades: list[dict], all_dates: list[str], asset: str | None = None) -> np.ndarray:
    m: dict[str, float] = {}
    for t in trades:
        if asset is not None and t["asset"] != asset:
            continue
        m[t["date"]] = m.get(t["date"], 0.0) + float(t["pnl"])
    return np.array([m.get(d, 0.0) for d in all_dates], dtype=np.float64)


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return round(float(np.corrcoef(a, b)[0, 1]), 3)


def run_portfolio_inclusion_study(
    battery_results: list[dict[str, Any]],
    win_m1: dict[str, dict],
    wdo_m1: dict[str, dict],
    all_dates: list[str],
) -> dict[str, Any]:
    """Testa inclusão 1-a-1 e seleção forward stepwise dos candidatos APROVADOS/RESERVA sobre o Top 8 (2004051)."""
    base_trades = load_portfolio_trades(ACTIVE_8_ROBOTS, cost_mode="net", win_mult=1.0, wdo_mult=1.0)
    base_eval = evaluate_portfolio_modes(base_trades, win_m1, wdo_m1, all_dates)

    base_daily_all = _daily_series(base_trades, all_dates)
    base_daily_win = _daily_series(base_trades, all_dates, asset="WIN")
    base_daily_wdo = _daily_series(base_trades, all_dates, asset="WDO")

    # Piores 15 pregões do Top 8 atual (para ver se o candidato ajuda ou afunda junto)
    worst15_idx = np.argsort(base_daily_all)[:15]
    worst15_dates = {all_dates[i] for i in worst15_idx}

    # Monta pool de candidatos elegíveis (APROVADO e RESERVA), sempre usando a versão escolhida no IS
    # e também a versão ORIGINAL se ela própria era APROVADO e distinta do ajustado.
    pool: list[dict[str, Any]] = []
    for r in battery_results:
        best_v = r["best_is"]["verdict"]
        base_v = r["baseline"]["verdict"]
        if best_v in ("APROVADO", "RESERVA"):
            pool.append({
                "key": r["code"],
                "code": r["code"],
                "variant": "AJUSTADO" if r["best_is"]["n_changed"] > 0 else "ORIGINAL",
                "label": r["best_is"]["label"],
                "asset": r["asset"],
                "tf": r["tf"],
                "verdict": best_v,
                "gates_passed": r["best_is"]["gates_passed"],
                "in_proposta_b": r["in_proposta_b"],
                "standalone_full": r["best_is"]["full"],
                "standalone_oos": r["best_is"]["oos"],
                "trades": r["best_trades"],
            })
        elif base_v in ("APROVADO", "RESERVA"):
            # Se o ajuste no IS piorou no OOS, mas o original passava nos critérios, testa o original!
            pool.append({
                "key": f"{r['code']} (ORIG)",
                "code": r["code"],
                "variant": "ORIGINAL",
                "label": "ORIGINAL (sem ajuste)",
                "asset": r["asset"],
                "tf": r["tf"],
                "verdict": base_v,
                "gates_passed": r["baseline"]["gates_passed"],
                "in_proposta_b": r["in_proposta_b"],
                "standalone_full": r["baseline"]["full"],
                "standalone_oos": r["baseline"]["oos"],
                "trades": r["baseline_trades"],
            })

    # 1. Teste de inclusão 1-a-1 (Top 8 + 1 candidato)
    marginal_rows: list[dict[str, Any]] = []
    for item in pool:
        c_daily = _daily_series(item["trades"], all_dates)
        corr_all = _safe_corr(base_daily_all, c_daily)
        corr_asset = _safe_corr(base_daily_win if item["asset"] == "WIN" else base_daily_wdo, c_daily)
        pnl_worst15 = round(sum(float(t["pnl"]) for t in item["trades"] if t["date"] in worst15_dates), 2)

        comb_trades = sorted(base_trades + item["trades"], key=lambda t: (t["date"], t["sec_in"], t["sec_out"], t["strat"]))
        comb_eval = evaluate_portfolio_modes(comb_trades, win_m1, wdo_m1, all_dates)

        def _delta(mode: str) -> dict[str, Any]:
            b = base_eval[mode]
            c = comb_eval[mode]
            return {
                "ret": c["ret"],
                "d_ret": round(c["ret"] - b["ret"], 2),
                "max_dd": c["max_dd"],
                "d_dd": round(c["max_dd"] - b["max_dd"], 2),
                "ret_dd": c["ret_dd"],
                "d_ret_dd": round(c["ret_dd"] - b["ret_dd"], 2),
                "sharpe": c["sharpe"],
                "d_sharpe": round(c["sharpe"] - b["sharpe"], 2),
                "is_ret_dd": c["is_chron"]["ret_dd"],
                "d_is_ret_dd": round(c["is_chron"]["ret_dd"] - b["is_chron"]["ret_dd"], 2),
                "oos_ret": c["oos_chron"]["ret"],
                "d_oos_ret": round(c["oos_chron"]["ret"] - b["oos_chron"]["ret"], 2),
                "oos_ret_dd": c["oos_chron"]["ret_dd"],
                "d_oos_ret_dd": round(c["oos_chron"]["ret_dd"] - b["oos_chron"]["ret_dd"], 2),
                "stopped": c["stopped"],
            }

        marginal_rows.append({
            "key": item["key"],
            "code": item["code"],
            "asset": item["asset"],
            "tf": item["tf"],
            "variant": item["variant"],
            "label": item["label"],
            "verdict": item["verdict"],
            "gates_passed": item["gates_passed"],
            "in_proposta_b": item["in_proposta_b"],
            "corr_all": corr_all,
            "corr_asset": corr_asset,
            "pnl_on_top8_worst15": pnl_worst15,
            "standalone_net": item["standalone_full"]["net"],
            "standalone_ret_dd": item["standalone_full"]["ret_dd"],
            "standalone_oos_net": item["standalone_oos"]["net"],
            "no_stop": _delta("no_stop"),
            "stop_live_850": _delta("stop_live_850"),
            "stop_indep_0": _delta("stop_indep_0"),
        })

    # Ordena por ganho de Ret/DD no stop_live_850 (G 850 + W 400 + D 550)
    marginal_rows.sort(key=lambda r: (r["verdict"] == "APROVADO", r["stop_live_850"]["d_ret_dd"]), reverse=True)

    # 2. Seleção Forward Stepwise guiada EXCLUSIVAMENTE pelo IS (Jan–Jul) com validação cega no OOS (Ago–Nov)
    def _run_greedy(guide_mode: str, only_approved: bool = True) -> list[dict[str, Any]]:
        eligible = [p for p in pool if (p["verdict"] == "APROVADO" if only_approved else True)]
        cur_trades = list(base_trades)
        cur_robots = list(ACTIVE_8_ROBOTS)
        cur_eval = base_eval

        steps: list[dict[str, Any]] = [{
            "step": 0,
            "n_robots": len(cur_robots),
            "added": "BASE Top 8 (2004051)",
            "added_label": "EST-04,07,13,14,15 + WDO-01,05,07",
            "robots": list(cur_robots),
            "no_stop": {k: v for k, v in cur_eval["no_stop"].items() if k != "curve"},
            "stop_live_850": {k: v for k, v in cur_eval["stop_live_850"].items() if k != "curve"},
            "stop_indep_0": {k: v for k, v in cur_eval["stop_indep_0"].items() if k != "curve"},
            "curve_stop_live_850": cur_eval["stop_live_850"]["curve"],
            "curve_no_stop": cur_eval["no_stop"]["curve"],
        }]

        remaining = list(eligible)
        for st in range(1, min(8, len(eligible)) + 1):
            best_cand = None
            best_is_score = -999.0
            best_eval = None
            best_trades = None

            for cand in remaining:
                trial_trades = sorted(cur_trades + cand["trades"], key=lambda t: (t["date"], t["sec_in"], t["sec_out"], t["strat"]))
                ev = evaluate_portfolio_modes(trial_trades, win_m1, wdo_m1, all_dates)
                # Critério 100% IS (Jan–Jul): maximiza Ret/DD no IS (com tie-break por Sharpe IS)
                is_m = ev[guide_mode]["is_chron"]
                sc = is_m["ret_dd"] + 0.05 * is_m["sharpe"]
                if sc > best_is_score:
                    best_is_score = sc
                    best_cand = cand
                    best_eval = ev
                    best_trades = trial_trades

            if best_cand is None or best_eval is None or best_trades is None:
                break

            cur_trades = best_trades
            cur_robots.append(best_cand["code"])
            cur_eval = best_eval
            remaining = [c for c in remaining if c["code"] != best_cand["code"]]

            steps.append({
                "step": st,
                "n_robots": len(cur_robots),
                "added": best_cand["key"],
                "added_asset": best_cand["asset"],
                "added_label": best_cand["label"],
                "added_verdict": best_cand["verdict"],
                "robots": list(cur_robots),
                "no_stop": {k: v for k, v in cur_eval["no_stop"].items() if k != "curve"},
                "stop_live_850": {k: v for k, v in cur_eval["stop_live_850"].items() if k != "curve"},
                "stop_indep_0": {k: v for k, v in cur_eval["stop_indep_0"].items() if k != "curve"},
                "curve_stop_live_850": cur_eval["stop_live_850"]["curve"],
                "curve_no_stop": cur_eval["no_stop"]["curve"],
            })

        return steps

    greedy_approved_stop = _run_greedy("stop_live_850", only_approved=True)
    greedy_approved_nostop = _run_greedy("no_stop", only_approved=True)
    greedy_all_stop = _run_greedy("stop_live_850", only_approved=False)

    return {
        "base_robots": ACTIVE_8_ROBOTS,
        "base_eval": {
            m: {k: v for k, v in base_eval[m].items() if k != "curve"}
            for m in ("no_stop", "stop_live_850", "stop_indep_0")
        },
        "base_curve_stop_live_850": base_eval["stop_live_850"]["curve"],
        "base_curve_no_stop": base_eval["no_stop"]["curve"],
        "pool_size": len(pool),
        "marginal": marginal_rows,
        "greedy_approved_stop": greedy_approved_stop,
        "greedy_approved_nostop": greedy_approved_nostop,
        "greedy_all_stop": greedy_all_stop,
    }
