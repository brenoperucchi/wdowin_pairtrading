"""Bateria de testes anti-overfitting (IS-only -> Validação Cega OOS -> 5 Gates) para os 24 robôs não utilizados."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import math
from typing import Any

import numpy as np
import pandas as pd

from research.unused_robots_battery.catalog import (
    CandidateSpec,
    FULL_END,
    FULL_START,
    H1_END,
    H2_START,
    IS_END,
    OOS_START,
    SPEC_BY_CODE,
    UNUSED_24_SPECS,
    count_changed_knobs,
    format_cfg_label,
    load_shared_market_data,
    simulate_candidate,
)

# Worker process global cache
_WORKER_MARKET: dict[str, Any] = {}


def _init_worker(load_win: bool = True, load_wdo: bool = True):
    global _WORKER_MARKET
    _WORKER_MARKET = load_shared_market_data(load_win=load_win, load_wdo=load_wdo)


def compute_trade_metrics(
    trades: list[dict[str, Any]],
    all_days: list[str] | None = None,
    date_lo: str | None = None,
    date_hi: str | None = None,
) -> dict[str, Any]:
    """Calcula métricas padronizadas (trades, WR, PF, payoff, líquido, DD diário/trade, Ret/DD, Sharpe, meses+)."""
    sub = trades
    if date_lo is not None:
        sub = [t for t in sub if t["date"] >= date_lo]
    if date_hi is not None:
        sub = [t for t in sub if t["date"] <= date_hi]

    if not sub:
        return {
            "trades": 0, "lots": 0, "wr": 0.0, "pf": 0.0, "payoff": 0.0,
            "net": 0.0, "dd_day": 0.0, "dd_trade": 0.0, "ret_dd": 0.0,
            "ret_dd_trade": 0.0, "sharpe": 0.0, "worst_day": 0.0, "best_day": 0.0,
            "max_streak": 0, "pos_months": 0, "total_months": 0, "pos_days_pct": 0.0,
            "active_days": 0,
        }

    pnls = np.array([float(t["pnl"]) for t in sub], dtype=np.float64)
    lots = int(sum(float(t["lots"]) for t in sub))
    n = len(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    wr = 100.0 * len(wins) / n
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = gw / gl if gl > 1e-6 else (99.0 if gw > 0 else 0.0)
    avg_w = float(wins.mean()) if len(wins) else 0.0
    avg_l = float(-losses.mean()) if len(losses) else 0.0
    payoff = avg_w / avg_l if avg_l > 1e-6 else (99.0 if avg_w > 0 else 0.0)
    net = float(pnls.sum())

    # Max DD trade-a-trade
    eq_tr = np.concatenate([[0.0], np.cumsum(pnls)])
    pk_tr = np.maximum.accumulate(eq_tr)
    dd_trade = float((pk_tr - eq_tr).max())
    ret_dd_trade = net / dd_trade if dd_trade > 1e-6 else (99.0 if net > 0 else 0.0)

    # Série diária
    day_map: dict[str, float] = {}
    month_map: dict[str, float] = {}
    for t in sub:
        d = t["date"]
        day_map[d] = day_map.get(d, 0.0) + float(t["pnl"])
        m = d[:7]
        month_map[m] = month_map.get(m, 0.0) + float(t["pnl"])

    if all_days is not None:
        days_seq = [d for d in all_days if (date_lo is None or d >= date_lo) and (date_hi is None or d <= date_hi)]
    else:
        days_seq = sorted(day_map.keys())

    daily_vals = np.array([day_map.get(d, 0.0) for d in days_seq], dtype=np.float64)
    eq_d = np.concatenate([[0.0], np.cumsum(daily_vals)])
    pk_d = np.maximum.accumulate(eq_d)
    dd_day = float((pk_d - eq_d).max()) if len(daily_vals) else 0.0
    ret_dd = net / dd_day if dd_day > 1e-6 else (99.0 if net > 0 else 0.0)

    std_d = float(daily_vals.std(ddof=1)) if len(daily_vals) > 1 else 0.0
    sharpe = (float(daily_vals.mean()) / std_d * math.sqrt(252.0)) if std_d > 1e-9 else 0.0

    # Max loss streak
    streak = max_s = 0
    for x in pnls:
        if x < 0:
            streak += 1
            if streak > max_s:
                max_s = streak
        elif x > 0:
            streak = 0

    active_days = len(day_map)
    pos_days = sum(1 for v in day_map.values() if v > 0)
    pos_months = sum(1 for v in month_map.values() if v > 0)
    total_months = len(month_map)

    return {
        "trades": n,
        "lots": lots,
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "payoff": round(payoff, 2),
        "net": round(net, 2),
        "dd_day": round(dd_day, 2),
        "dd_trade": round(dd_trade, 2),
        "ret_dd": round(ret_dd, 2),
        "ret_dd_trade": round(ret_dd_trade, 2),
        "sharpe": round(sharpe, 2),
        "worst_day": round(float(daily_vals.min()), 2) if len(daily_vals) else 0.0,
        "best_day": round(float(daily_vals.max()), 2) if len(daily_vals) else 0.0,
        "max_streak": int(max_s),
        "pos_months": int(pos_months),
        "total_months": int(total_months),
        "pos_days_pct": round(100.0 * pos_days / active_days, 1) if active_days else 0.0,
        "active_days": int(active_days),
    }


def _dedup_cfgs(cfgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for c in cfgs:
        key = (
            c["order_type"], c["be_mode"], round(float(c["wall_buf"]), 2),
            c["tp_mode"], int(c["max_trades_day"]), int(c["max_losses_day"]), c["window"],
        )
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def build_stage_a_grid(spec: CandidateSpec) -> list[dict[str, Any]]:
    """Etapa A: Tipo de Ordem x Proteção na Wall (BE) x Alvo Estrutural (TP)."""
    base = dict(spec.baseline_cfg)
    cfgs: list[dict[str, Any]] = [base]

    if spec.engine == "win_o16":
        orders = ["CURRENT", "LIMIT_B1_MID", "LIMIT_B1_EXT", "STOP_B1_EXT"]
        be_opts = [
            ("BE_ZERO", 20.0),
            ("BE_WALL_SHIELD", 15.0),
            ("BE_WALL_SHIELD", 25.0),
            ("BE_WALL_2STAGE", 15.0),
        ]
        tps = ["TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL"]
        for o in orders:
            for bm, wb in be_opts:
                for tp in tps:
                    c = dict(base)
                    c.update(order_type=o, be_mode=bm, wall_buf=wb, tp_mode=tp)
                    cfgs.append(c)

    elif spec.engine == "win_m15":
        orders = ["MARKET", "LIMIT_WALL", "LIMIT_50PCT"]
        be_opts = [
            ("BE_ZERO", base["wall_buf"]),
            ("BE_WALL_SHIELD", 25.0),
            ("BE_WALL_SHIELD", 35.0),
        ]
        tps = ["TP_MIDWALL", "TP_MAIN_WALL"]
        for o in orders:
            for bm, wb in be_opts:
                for tp in tps:
                    c = dict(base)
                    c.update(order_type=o, be_mode=bm, wall_buf=wb, tp_mode=tp)
                    cfgs.append(c)

    elif spec.engine == "win_sg":
        orders = ["CURRENT", "LIMIT_B1_35", "LIMIT_B1_EXT"]
        be_opts = [
            ("BE_WALL_SHIELD", 20.0),
            ("BE_ZERO", 20.0),
        ]
        for o in orders:
            for bm, wb in be_opts:
                c = dict(base)
                c.update(order_type=o, be_mode=bm, wall_buf=wb)
                cfgs.append(c)

    elif spec.engine == "wdo_core":
        orders = ["CURRENT", "LIMIT_B1_MID", "LIMIT_B1_EXT", "STOP_B1_EXT", "MARKET"]
        be_opts = [
            ("CURRENT", -1.0),
            ("BE_ZERO", 0.0),
            ("BE_WALL_SHIELD", 1.0),
            ("BE_WALL_SHIELD", 1.5),
            ("BE_WALL_2STAGE", 1.0),
        ]
        tps = ["CURRENT", "TP_MIDWALL", "TP_MAIN_WALL"]
        for o in orders:
            for bm, wb in be_opts:
                for tp in tps:
                    c = dict(base)
                    c.update(order_type=o, be_mode=bm, wall_buf=wb, tp_mode=tp)
                    cfgs.append(c)

    return _dedup_cfgs(cfgs)


def build_stage_b_grid(seed_cfgs: list[dict[str, Any]], compact: bool = False) -> list[dict[str, Any]]:
    """Etapa B: Disciplina Diária (Max Trades/Dia, Max Losses/Dia) x Janela Horária nos top seeds da Etapa A."""
    cfgs: list[dict[str, Any]] = []
    use_seeds = seed_cfgs[:2] if compact else seed_cfgs
    mt_opts = (0, 1, 2) if compact else (0, 1, 2, 3)
    ml_opts = (0, 1) if compact else (0, 1, 2)
    win_opts = ("NO_LUNCH", "NY_1000_1630") if compact else ("NO_LUNCH", "NY_1000_1630", "MORNING_09_12")
    for seed in use_seeds:
        cfgs.append(dict(seed))
        for mt in mt_opts:
            for ml in ml_opts:
                if mt == 0 and ml == 0:
                    continue
                if mt > 0 and ml > mt:
                    continue
                c = dict(seed)
                c.update(max_trades_day=mt, max_losses_day=ml)
                cfgs.append(c)
        for w in win_opts:
            for ml in ((0,) if compact else (0, 1, 2)):
                c = dict(seed)
                c.update(window=w, max_losses_day=ml)
                cfgs.append(c)
            if not compact:
                for mt in (1, 2):
                    c = dict(seed)
                    c.update(window=w, max_trades_day=mt)
                    cfgs.append(c)
    return _dedup_cfgs(cfgs)


def compute_is_selection_score(spec: CandidateSpec, cfg: dict[str, Any], m_is: dict[str, Any]) -> float:
    """
    Score regularizado calculado EXCLUSIVAMENTE no IS (02/01–31/07/2026).
    Penaliza amostras pequenas (<60 trades no IS), PF fraco e excesso de alavancas alteradas.
    """
    if m_is["trades"] < 25 or m_is["net"] <= 0 or m_is["pf"] < 1.05:
        return -999.0
    sample_factor = min(1.0, math.sqrt(m_is["trades"] / 60.0))
    months_ratio = (m_is["pos_months"] / m_is["total_months"]) if m_is["total_months"] > 0 else 0.0
    eff_ret_dd = min(m_is["ret_dd"], 15.0)
    n_changed = count_changed_knobs(spec, cfg)
    # Parsimônia: cada alavanca modificada exige ganho real de Ret/DD no IS
    complexity_pen = 0.08 * n_changed
    return round(eff_ret_dd * sample_factor * (0.65 + 0.35 * months_ratio) - complexity_pen, 4)


def evaluate_5_gates(
    m_is: dict[str, Any],
    m_oos: dict[str, Any],
    m_h1: dict[str, Any],
    m_h2: dict[str, Any],
    m_full: dict[str, Any],
    m_stress: dict[str, Any],
) -> dict[str, Any]:
    """Bateria de 5 critérios rígidos anti-overfitting."""
    g1_is = (m_is["trades"] >= 40) and (m_is["net"] > 0) and (m_is["pf"] >= 1.15) and (m_is["ret_dd"] >= 1.50)
    g2_oos = (m_oos["trades"] >= 15) and (m_oos["net"] > 0) and (m_oos["pf"] >= 1.10) and (m_oos["ret_dd"] >= 0.80)
    g3_halves = (m_h1["net"] > 0) and (m_h2["net"] > 0)
    g4_months = (m_full["total_months"] > 0) and (m_full["pos_months"] >= 7)
    g5_stress = (m_stress["net"] > 0) and (m_stress["pf"] >= 1.05)

    gates = {
        "G1_IS": bool(g1_is),
        "G2_OOS_BLIND": bool(g2_oos),
        "G3_BOTH_HALVES": bool(g3_halves),
        "G4_MONTHLY": bool(g4_months),
        "G5_COST_STRESS": bool(g5_stress),
    }
    passed = sum(1 for v in gates.values() if v)

    if passed == 5:
        verdict = "APROVADO"
    elif g2_oos and g5_stress and passed >= 3 and m_full["net"] > 0 and m_is["net"] > 0:
        verdict = "RESERVA"
    else:
        verdict = "REPROVADO"

    return {"gates": gates, "gates_passed": passed, "verdict": verdict}


def evaluate_single_robot(code: str, all_days: list[str]) -> dict[str, Any]:
    """Executa toda a bateria (Baseline + Etapa A + Etapa B no IS + Validação Cega OOS + Stress +50%) para 1 robô."""
    spec = SPEC_BY_CODE[code]
    market = _WORKER_MARKET

    # 1. Baseline exato do EA atual
    base_trades = simulate_candidate(spec, spec.baseline_cfg, market, cost_mult=1.0)
    base_stress_trades = simulate_candidate(spec, spec.baseline_cfg, market, cost_mult=1.5)

    b_full = compute_trade_metrics(base_trades, all_days)
    b_is = compute_trade_metrics(base_trades, all_days, date_lo=FULL_START, date_hi=IS_END)
    b_oos = compute_trade_metrics(base_trades, all_days, date_lo=OOS_START, date_hi=FULL_END)
    b_h1 = compute_trade_metrics(base_trades, all_days, date_lo=FULL_START, date_hi=H1_END)
    b_h2 = compute_trade_metrics(base_trades, all_days, date_lo=H2_START, date_hi=FULL_END)
    b_stress = compute_trade_metrics(base_stress_trades, all_days)
    b_eval = evaluate_5_gates(b_is, b_oos, b_h1, b_h2, b_full, b_stress)
    b_score = compute_is_selection_score(spec, spec.baseline_cfg, b_is)

    # 2. Etapa A (IS-only ranking)
    stage_a_cfgs = build_stage_a_grid(spec)
    stage_a_scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    grid_records: list[dict[str, Any]] = []

    for cfg in stage_a_cfgs:
        tr = base_trades if cfg == spec.baseline_cfg else simulate_candidate(spec, cfg, market, cost_mult=1.0)
        m_is = compute_trade_metrics(tr, all_days, date_lo=FULL_START, date_hi=IS_END)
        sc = compute_is_selection_score(spec, cfg, m_is)
        stage_a_scored.append((sc, cfg, m_is))
        grid_records.append({
            "robot": code,
            "stage": "A",
            "label": format_cfg_label(spec, cfg),
            "is_score": sc,
            "is_trades": m_is["trades"],
            "is_pf": m_is["pf"],
            "is_net": m_is["net"],
            "is_dd": m_is["dd_day"],
            "is_ret_dd": m_is["ret_dd"],
            "cfg": cfg,
        })

    stage_a_scored.sort(key=lambda x: x[0], reverse=True)
    # Seeds para Etapa B: sempre inclui o baseline + até 3 melhores distintos da Etapa A
    seeds: list[dict[str, Any]] = [dict(spec.baseline_cfg)]
    for sc, cfg, _ in stage_a_scored:
        if len(seeds) >= 4:
            break
        if cfg not in seeds:
            seeds.append(cfg)

    # 3. Etapa B (Disciplina Diária + Janela nos top seeds, IS-only ranking)
    stage_b_cfgs = build_stage_b_grid(seeds, compact=(spec.engine == "win_sg"))
    best_sc = b_score
    best_cfg = dict(spec.baseline_cfg)
    best_trades = base_trades

    # Primeiro considera o melhor da Etapa A
    if stage_a_scored and stage_a_scored[0][0] > best_sc:
        best_sc = stage_a_scored[0][0]
        best_cfg = dict(stage_a_scored[0][1])
        best_trades = simulate_candidate(spec, best_cfg, market, cost_mult=1.0)

    for cfg in stage_b_cfgs:
        tr = base_trades if cfg == spec.baseline_cfg else simulate_candidate(spec, cfg, market, cost_mult=1.0)
        m_is = compute_trade_metrics(tr, all_days, date_lo=FULL_START, date_hi=IS_END)
        sc = compute_is_selection_score(spec, cfg, m_is)
        grid_records.append({
            "robot": code,
            "stage": "B",
            "label": format_cfg_label(spec, cfg),
            "is_score": sc,
            "is_trades": m_is["trades"],
            "is_pf": m_is["pf"],
            "is_net": m_is["net"],
            "is_dd": m_is["dd_day"],
            "is_ret_dd": m_is["ret_dd"],
            "cfg": cfg,
        })
        if sc > best_sc:
            best_sc = sc
            best_cfg = dict(cfg)
            best_trades = tr

    # 4. Avaliação Cega (OOS + H1/H2 + Stress +50%) do Vencedor escolhido 100% no IS
    best_stress_trades = (
        base_stress_trades
        if best_cfg == spec.baseline_cfg
        else simulate_candidate(spec, best_cfg, market, cost_mult=1.5)
    )
    o_full = compute_trade_metrics(best_trades, all_days)
    o_is = compute_trade_metrics(best_trades, all_days, date_lo=FULL_START, date_hi=IS_END)
    o_oos = compute_trade_metrics(best_trades, all_days, date_lo=OOS_START, date_hi=FULL_END)
    o_h1 = compute_trade_metrics(best_trades, all_days, date_lo=FULL_START, date_hi=H1_END)
    o_h2 = compute_trade_metrics(best_trades, all_days, date_lo=H2_START, date_hi=FULL_END)
    o_stress = compute_trade_metrics(best_stress_trades, all_days)
    o_eval = evaluate_5_gates(o_is, o_oos, o_h1, o_h2, o_full, o_stress)

    # Top 5 configs no IS (para diagnóstico de estabilidade / platô)
    grid_records.sort(key=lambda r: r["is_score"], reverse=True)
    top5_is = [
        {k: v for k, v in r.items() if k != "cfg"}
        for r in grid_records[:5]
    ]
    n_tested = len(grid_records)
    n_is_positive = sum(1 for r in grid_records if r["is_net"] > 0 and r["is_pf"] >= 1.10)

    # Se o baseline já era APROVADO e o ajustado perdeu no OOS ou não trouxe ganho real, reportamos ambos claramente
    return {
        "code": code,
        "asset": spec.asset,
        "tf": spec.tf,
        "engine": spec.engine,
        "name": spec.name,
        "in_proposta_b": spec.in_proposta_b,
        "configs_tested": n_tested,
        "configs_is_positive": n_is_positive,
        "plateau_pct": round(100.0 * n_is_positive / max(1, n_tested), 1),
        "baseline": {
            "cfg": spec.baseline_cfg,
            "label": "ORIGINAL",
            "is_score": b_score,
            "full": b_full,
            "is": b_is,
            "oos": b_oos,
            "h1": b_h1,
            "h2": b_h2,
            "stress": b_stress,
            **b_eval,
        },
        "best_is": {
            "cfg": best_cfg,
            "label": format_cfg_label(spec, best_cfg),
            "n_changed": count_changed_knobs(spec, best_cfg),
            "is_score": best_sc,
            "full": o_full,
            "is": o_is,
            "oos": o_oos,
            "h1": o_h1,
            "h2": o_h2,
            "stress": o_stress,
            **o_eval,
        },
        "top5_is": top5_is,
        "baseline_trades": base_trades,
        "best_trades": best_trades,
    }


def run_all_24_battery(all_days: list[str], max_workers: int = 8) -> list[dict[str, Any]]:
    """Roda a bateria completa em paralelo para os 24 robôs não utilizados."""
    win_codes = [s.code for s in UNUSED_24_SPECS if s.asset == "WIN"]
    wdo_codes = [s.code for s in UNUSED_24_SPECS if s.asset == "WDO"]

    results_by_code: dict[str, dict[str, Any]] = {}

    # Executa WIN (11 robôs) com pool dedicado carregando só WIN
    n_win_w = min(max_workers, len(win_codes))
    with ProcessPoolExecutor(max_workers=n_win_w, initializer=_init_worker, initargs=(True, False)) as ex:
        futs = {ex.submit(evaluate_single_robot, c, all_days): c for c in win_codes}
        for fut, c in futs.items():
            res = fut.result()
            results_by_code[c] = res
            b = res["baseline"]
            o = res["best_is"]
            print(
                f"  [{c}] Base: {b['verdict']:9s} ({b['gates_passed']}/5) Ret/DD={b['full']['ret_dd']:5.2f} OOS={b['oos']['net']:+7.0f} | "
                f"Ajustado ({o['label']}): {o['verdict']:9s} ({o['gates_passed']}/5) Ret/DD={o['full']['ret_dd']:5.2f} OOS={o['oos']['net']:+7.0f}",
                flush=True,
            )

    # Executa WDO (13 robôs) com pool dedicado carregando só WDO
    n_wdo_w = min(max_workers, len(wdo_codes))
    with ProcessPoolExecutor(max_workers=n_wdo_w, initializer=_init_worker, initargs=(False, True)) as ex:
        futs = {ex.submit(evaluate_single_robot, c, all_days): c for c in wdo_codes}
        for fut, c in futs.items():
            res = fut.result()
            results_by_code[c] = res
            b = res["baseline"]
            o = res["best_is"]
            print(
                f"  [{c}] Base: {b['verdict']:9s} ({b['gates_passed']}/5) Ret/DD={b['full']['ret_dd']:5.2f} OOS={b['oos']['net']:+7.0f} | "
                f"Ajustado ({o['label']}): {o['verdict']:9s} ({o['gates_passed']}/5) Ret/DD={o['full']['ret_dd']:5.2f} OOS={o['oos']['net']:+7.0f}",
                flush=True,
            )

    return [results_by_code[s.code] for s in UNUSED_24_SPECS]
