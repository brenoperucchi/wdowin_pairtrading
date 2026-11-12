"""
Paridade dos setups registrados: motor AO VIVO × trades oficiais do BT.

  - Ao vivo: `GexLiveDealerEngine.analyze_asset` sobre o payload histórico do dia
    (`data/processed/gex_historical_sessions_v1/{data}.json`), com o atalho de trades em cache
    desligado (para o motor realmente avaliar os setups) e sem reconciliação com o terminal MT5.
  - BT: trades `in_flow` de `data/processed/portfolio_4_sistematicas_equity_v1.json`
    (gerados por `research/flow_window_asg/generate_portfolio_6_json.py` com os simuladores alinhados ao MT5).

Casamento por (data, estratégia, direção, horário de entrada). Saída: CSV trade a trade + resumo por estratégia.
Uso: python -m research.setup_parity.compare_live_vs_bt [n_dias|all] [runner|json]
  runner (padrão): BT = runner único no período inteiro; ao vivo = motor chamando o runner por dia.
  json: comparação original (JSON auditado × reimplementação antiga do motor).
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.gex_live_dealer_engine import GexLiveDealerEngine  # noqa: E402

HIST = os.path.join(ROOT, "data", "processed", "gex_historical_sessions_v1")
PORT = os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json")
OUT = os.path.join(ROOT, "research", "setup_parity", "results")
SKIP_SIDS = {"WIN_DIV_WALL", "WDO_DIV_WALL"}  # filtros por cima dos setups, fora desta etapa


def live_trades(engine, date):
    payload = json.load(open(os.path.join(HIST, f"{date}.json"), encoding="utf-8"))
    rows = []
    for asset in ("WIN", "WDO"):
        sym = payload.get(asset)
        if not sym or not sym.get("m5_cvd_series"):
            continue
        res = engine.analyze_asset(sym)
        for s in res.get("signals_log", []):
            sid = s.get("strategy_id")
            if not sid or sid in SKIP_SIDS:
                continue
            rows.append({"date": date, "asset": asset, "sid": sid, "dir": s.get("direction"), "time": s.get("time"),
                         "entry": s.get("entry_price"), "exit": s.get("exit_price"), "exit_time": s.get("exit_time"),
                         "reason": s.get("exit_reason"), "pts": s.get("realized_pts"),
                         "source": sym.get("source", "")[:20]})
    return rows


def bt_trades_runner(dates):
    """BT oficial novo: runner único sobre o período inteiro (uma execução, histórico completo)."""
    from core.setups_runner import run_setups
    res = run_setups(min(dates), max(dates))
    rows = []
    for sid, trs in res.items():
        for t in trs:
            if t["date"] in dates:
                rows.append({"date": t["date"], "asset": t["asset"], "sid": sid, "dir": t["direction"],
                             "time": t["time"], "entry": t["entry_price"], "exit": t.get("exit_price"),
                             "exit_time": t.get("exit_time"), "pts": t.get("pts")})
    return rows


def bt_trades(port, dates):
    rows = []
    for d in port["days"]:
        if d["date"] not in dates:
            continue
        for t in d.get("trades", []) or []:
            if not t.get("in_flow") or t.get("strategy_id") in SKIP_SIDS:
                continue
            rows.append({"date": d["date"], "asset": t["asset"], "sid": t["strategy_id"], "dir": t["direction"],
                         "time": t["time"], "entry": t["entry_price"], "exit": t.get("exit_price"),
                         "exit_time": t.get("exit_time"), "pts": t.get("pts_nocost", t.get("pts"))})
    return rows


def main(n="all", bt_source="runner"):
    os.makedirs(OUT, exist_ok=True)
    port = json.load(open(PORT, encoding="utf-8"))
    bt_dates = {d["date"] for d in port["days"]}
    dates = sorted(f[:-5] for f in os.listdir(HIST) if f.endswith(".json") and f[:-5] in bt_dates)
    if n != "all":
        k = int(n)
        dates = dates[:: max(1, len(dates) // k)][:k]
    eng = GexLiveDealerEngine()
    if bt_source == "json":   # modo antigo: força a reimplementação ao vivo antiga
        eng._get_portfolio_6_cached_trades = lambda *a, **k: []
        eng._get_setup_trades = lambda *a, **k: None
    eng._reconcile_mt5_terminal_live_deals = lambda **kw: kw["sim_signals"]
    live = []
    for i, d in enumerate(dates):
        try:
            live += live_trades(eng, d)
        except Exception as e:  # registra e segue
            print(f"{d}: erro no motor ao vivo: {e!r}")
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(dates)} dias")
    bt = bt_trades_runner(set(dates)) if bt_source == "runner" else bt_trades(port, set(dates))
    L = pd.DataFrame(live)
    B = pd.DataFrame(bt)
    key = ["date", "asset", "sid", "dir", "time"]
    M = B.merge(L, on=key, how="outer", suffixes=("_bt", "_live"), indicator=True)
    M["entry_eq"] = (M["entry_bt"] - M["entry_live"]).abs() < 1e-6
    M["exit_eq"] = (M["exit_bt"] - M["exit_live"]).abs() < 1e-6
    tag = "" if bt_source == "json" else "_runner"
    M.to_csv(os.path.join(OUT, f"trades_live_vs_bt{tag}.csv"), index=False)
    summ = []
    for (asset, sid), g in M.groupby(["asset", "sid"]):
        both = g[g["_merge"] == "both"]
        summ.append({"asset": asset, "sid": sid, "bt": int((g["_merge"] != "right_only").sum()),
                     "live": int((g["_merge"] != "left_only").sum()), "match": len(both),
                     "so_bt": int((g["_merge"] == "left_only").sum()), "so_live": int((g["_merge"] == "right_only").sum()),
                     "entrada_igual": int(both["entry_eq"].sum()), "saida_igual": int(both["exit_eq"].sum()),
                     "pts_bt": round(float(g["pts_bt"].fillna(0).sum()), 1),
                     "pts_live": round(float(g["pts_live"].fillna(0).sum()), 1)})
    S = pd.DataFrame(summ)
    S["match_pct"] = (100.0 * S["match"] / S[["bt", "live"]].max(axis=1).clip(lower=1)).round(1)
    S.to_csv(os.path.join(OUT, f"summary_live_vs_bt{tag}.csv"), index=False)
    print(f"{len(dates)} dias comparados")
    with pd.option_context("display.width", 200):
        print(S.to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all", sys.argv[2] if len(sys.argv) > 2 else "runner")
