#!/usr/bin/env python3
"""
TASK-3 AC #16 — Paper trading × validated-backtest reconciliation tool.

Compares the SUM(pnl_brl) of CLOSED `matador_ops` trades over the last N
business days against the validation backtest summary written by
`research/run_matador_v5_johansen.py` (`portfolio_v5_summary.json`).

Two reconciliations are performed independently:
  1. **Net vs net**  — backtest is already net (slippage + B3 baked in by
     `_pnl_brl_close`). The matador_ops side is also adjusted by the same
     cost model so the comparison is apples-to-apples.
  2. **Gross vs gross** — backtest gross is recovered analytically from
     the JSON sidecar; matador_ops gross is `pnl_brl` as stored (live
     engine writes `pts_favor × WIN_CONTRACTS × WIN_PV` directly, no
     cost adjustment).

Verdict per AC #16: |relative error| < 10 % = PASS, ≥ 10 % = FAIL.

States:
  - `BLOCKED` — matador_ops has 0 closed trades in the period. Exit 0;
    AC #16 is gated by data accumulation, not by a code bug.
  - `MISSING_BACKTEST` — JSON sidecar absent. Exit 2; user must run
    `python research/run_matador_v5_johansen.py` first.
  - `PASS` / `FAIL` — both sides have data; verdict printed.

Usage:
    python scripts/reconcile_paper_vs_backtest.py [--db trades.db]
        [--days 30] [--summary .planning/docs/assets/portfolio_v5_summary.json]
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import config as cfg

DEFAULT_DB = os.path.join(REPO_ROOT, "trades.db")
DEFAULT_SUMMARY = os.path.join(
    REPO_ROOT, ".planning", "docs", "assets", "portfolio_v5_summary.json"
)
PARIDADE_THRESHOLD = 0.10  # AC #16 gate


def per_trade_cost_brl():
    """Match `_pnl_brl_close` in run_matador_v5_johansen.py."""
    return (
        2 * cfg.WIN_SLIPPAGE_PTS * cfg.WIN_PV * cfg.WIN_CONTRACTS
        + cfg.B3_COST_PER_CONTRACT_RT * cfg.WIN_CONTRACTS
    )


def load_paper_trades(db_path, days):
    """Return list of (timestamp_in, pnl_brl) for CLOSED trades in last N days.
    `pnl_brl` as stored is gross — live engine does no cost adjustment."""
    if not os.path.exists(db_path):
        return None  # signal missing DB
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT timestamp_in, pnl_brl FROM matador_ops "
            "WHERE status='CLOSED' AND pnl_brl IS NOT NULL "
            "AND timestamp_out >= ? "
            "ORDER BY timestamp_out",
            (cutoff,),
        )
        return c.fetchall()
    finally:
        conn.close()


def summarize_paper(rows):
    """Compute gross+net summaries from matador_ops rows.
    Net subtracts `per_trade_cost_brl` × n_trades."""
    n = len(rows)
    gross = sum(r[1] for r in rows)
    net = gross - n * per_trade_cost_brl()
    return {"trades": n, "pnl_brl_gross": gross, "pnl_brl_net": net}


def load_backtest_summary(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def relative_error(paper, backtest):
    """|paper - backtest| / |paper| — guard against /0."""
    denom = abs(paper) if abs(paper) > 1e-6 else 1.0
    return abs(paper - backtest) / denom


def render_verdict(paper, backtest, label):
    err = relative_error(paper, backtest)
    pass_ = err < PARIDADE_THRESHOLD
    tag = "PASS" if pass_ else "FAIL"
    return (
        f"  {label:<10} paper=R${paper:>10.2f}  backtest=R${backtest:>10.2f}  "
        f"|err|={err * 100:6.2f}%  [{tag}]"
    ), pass_


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--days", type=int, default=30,
                        help="Lookback window in calendar days (default 30)")
    parser.add_argument("--summary", default=DEFAULT_SUMMARY,
                        help="Path to portfolio_v5_summary.json")
    parser.add_argument("--portfolio-key", default="portfolio_wdo_di_cons_puro",
                        choices=["portfolio_wdo_di_cons_puro",
                                 "wdo_nwe", "di_nwe",
                                 "consenso_nwe", "consenso_puro"],
                        help="Which leg/portfolio to compare (default: full portfolio)")
    parser.add_argument("--bateria", default="bateria_1_v4_puro",
                        choices=["bateria_1_v4_puro", "bateria_2_johansen_gate"],
                        help="Which backtest battery (default: V4 Puro)")
    args = parser.parse_args()

    print(f"[reconcile] db={args.db}")
    print(f"[reconcile] window={args.days} days")
    print(f"[reconcile] backtest summary={args.summary}")
    print(f"[reconcile] portfolio={args.bateria}/{args.portfolio_key}")
    print()

    rows = load_paper_trades(args.db, args.days)
    if rows is None:
        print(f"[ERROR] DB not found at {args.db}")
        return 3
    paper = summarize_paper(rows)

    print(f"[paper] closed trades in last {args.days}d: {paper['trades']}")

    if paper["trades"] == 0:
        print()
        print("=" * 70)
        print("AC #16 BLOCKED: no paper history")
        print("=" * 70)
        print()
        print("matador_ops has zero CLOSED trades in the lookback window.")
        print("AC #16 paridade requires live paper-trading data to compare")
        print("against the backtest. This is gated by data accumulation,")
        print("not by a code bug.")
        print()
        print("Re-run this script after the paper-trading engine has")
        print("logged closed trades (typical: a few weeks of session uptime).")
        return 0

    backtest_full = load_backtest_summary(args.summary)
    if backtest_full is None:
        print(f"[reconcile] backtest summary not found at {args.summary}")
        print()
        print("=" * 70)
        print("AC #16 PARTIAL: paper data present, backtest summary missing")
        print("=" * 70)
        print(f"  paper trades:     {paper['trades']}")
        print(f"  paper gross P&L:  R${paper['pnl_brl_gross']:.2f}")
        print(f"  paper net P&L:    R${paper['pnl_brl_net']:.2f}")
        print()
        print("Run `python research/run_matador_v5_johansen.py` first to")
        print(f"generate {args.summary}, then re-run this script.")
        return 2

    bt = backtest_full[args.bateria][args.portfolio_key]

    print(f"[backtest] generated_at: {backtest_full['generated_at']}")
    print(f"[backtest] trades:        {bt['trades']}")
    print(f"[backtest] gross P&L:     R${bt['pnl_brl_gross']:.2f}")
    print(f"[backtest] net P&L:       R${bt['pnl_brl_net']:.2f}")
    print()
    print(f"[paper] gross P&L: R${paper['pnl_brl_gross']:.2f}")
    print(f"[paper] net P&L:   R${paper['pnl_brl_net']:.2f}  "
          f"(after subtracting {paper['trades']} × R${per_trade_cost_brl():.2f} costs)")
    print()
    print("=" * 70)
    print("AC #16 reconciliation")
    print("=" * 70)

    line_gross, ok_gross = render_verdict(
        paper["pnl_brl_gross"], bt["pnl_brl_gross"], "GROSS"
    )
    line_net, ok_net = render_verdict(
        paper["pnl_brl_net"], bt["pnl_brl_net"], "NET"
    )
    print(line_gross)
    print(line_net)
    print()
    print(f"AC #16 threshold: |relative error| < {PARIDADE_THRESHOLD * 100:.0f}%")
    if ok_gross and ok_net:
        print("VERDICT: PASS — paridade aceita")
        return 0
    print("VERDICT: FAIL — investigate divergence on either side")
    return 1


if __name__ == "__main__":
    sys.exit(main())
