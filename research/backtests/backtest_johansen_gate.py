# research/backtest_johansen_gate.py
"""
Johansen Gate Backtest — WIN x WDO
===================================
Compares 4 strategies using Kalman z-score as signal source:
  A) Kalman only (no gate) — baseline
  B) Kalman + Binary Johansen gate (on/off)
  C) Kalman + Conviction scaling (sizing by trace distance)
  D) Kalman + Dual check (Johansen gate + beta consistency)

Usage:
  python research/backtest_johansen_gate.py --pair wdo
  python research/backtest_johansen_gate.py --pair di
"""
import os, sys, warnings, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import MetaTrader5 as mt5

from core.config import MT5_PATH, SYMBOL_A, SYMBOL_B, BETA_INITIAL
from core.kalman_filter import KalmanBetaFilter

# --- Config ---
BARS_FETCH = 5000
Z_WINDOW = 40
Z_ENTRY = 1.8
Z_EXIT = 0.0
Z_ANOMALY = 4.0
JOH_WINDOW = 250       # Johansen rolling window
JOH_RECHECK = 12       # Recheck every N bars (~1h in M5)
BETA_TOLERANCE = 0.30  # 30% beta consistency threshold

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)
plt.style.use("dark_background")

PAIR_CONFIGS = {
    "wdo": {
        "sym_a": SYMBOL_A, "sym_b": SYMBOL_B, "label": "WIN x WDO",
        "col_a": "WIN", "col_b": "WDO",
        "kalman_beta": BETA_INITIAL, "kalman_tcov": 1e-4, "kalman_ocov": 1e4,
        "prefix": "wdo",
    },
    "di": {
        "sym_a": SYMBOL_A, "sym_b": "DI1$N", "label": "WIN x DI",
        "col_a": "WIN", "col_b": "DI",
        "kalman_beta": -10000.0, "kalman_tcov": 1e-4, "kalman_ocov": 1e6,
        "prefix": "di",
    },
}

PAIR = None


def fetch_data():
    kwargs = {"path": MT5_PATH} if MT5_PATH else {}
    if not mt5.initialize(**kwargs):
        print(f"[ERRO] MT5: {mt5.last_error()}")
        sys.exit(1)
    print(f"[MT5] Conectado -- {mt5.terminal_info().name}")

    rates_a = mt5.copy_rates_from_pos(PAIR["sym_a"], mt5.TIMEFRAME_M5, 0, BARS_FETCH)
    rates_b = mt5.copy_rates_from_pos(PAIR["sym_b"], mt5.TIMEFRAME_M5, 0, BARS_FETCH)
    mt5.shutdown()

    if rates_a is None or rates_b is None:
        print(f"[ERRO] Sem dados para {PAIR['sym_a']} / {PAIR['sym_b']}.")
        sys.exit(1)

    df_a = pd.DataFrame(rates_a)[["time", "close"]].rename(columns={"close": PAIR["col_a"]})
    df_b = pd.DataFrame(rates_b)[["time", "close"]].rename(columns={"close": PAIR["col_b"]})
    df = pd.merge(df_a, df_b, on="time", how="inner")
    df["dt"] = pd.to_datetime(df["time"], unit="s") + pd.Timedelta(hours=3)
    df.set_index("dt", inplace=True)
    df.drop(columns=["time"], inplace=True)

    print(f"[DATA] {len(df)} barras M5 | "
          f"{df.index[0].strftime('%Y-%m-%d')} -> {df.index[-1].strftime('%Y-%m-%d')}")
    return df


def precompute(df):
    """Pre-compute Kalman z-scores and Johansen gate signals."""
    a = df[PAIR["col_a"]].values
    b = df[PAIR["col_b"]].values
    n = len(a)

    # --- Kalman z-scores ---
    kf = KalmanBetaFilter(
        initial_beta=PAIR["kalman_beta"],
        trans_cov=PAIR["kalman_tcov"],
        obs_cov=PAIR["kalman_ocov"],
    )
    kalman_spreads = np.zeros(n)
    kalman_betas = np.zeros(n)
    for i in range(n):
        beta, spread, _ = kf.update(float(a[i]), float(b[i]))
        kalman_spreads[i] = spread
        kalman_betas[i] = beta

    kalman_z = np.array(KalmanBetaFilter.rolling_zscore(
        kalman_spreads.tolist(), window=Z_WINDOW
    ))

    # --- Johansen gate (recomputed every JOH_RECHECK bars) ---
    joh_gate = np.zeros(n, dtype=bool)       # True = cointegrated
    joh_trace_ratio = np.zeros(n)            # trace_stat / critical_value
    joh_betas = np.full(n, np.nan)           # Johansen beta

    last_gate = False
    last_ratio = 0.0
    last_joh_beta = np.nan

    for i in range(n):
        if i >= JOH_WINDOW and i % JOH_RECHECK == 0:
            try:
                y = np.column_stack([a[i-JOH_WINDOW:i], b[i-JOH_WINDOW:i]])
                result = coint_johansen(y, det_order=0, k_ar_diff=1)
                trace_stat = result.lr1[0]        # r=0 trace statistic
                crit_95 = result.cvt[0, 1]         # 95% critical value
                last_gate = bool(trace_stat > crit_95)
                last_ratio = trace_stat / crit_95 if crit_95 > 0 else 0.0
                vec = result.evec[:, 0]
                vec = vec / vec[0]
                last_joh_beta = vec[1]
            except Exception:
                pass

        joh_gate[i] = last_gate
        joh_trace_ratio[i] = last_ratio
        joh_betas[i] = last_joh_beta

    return kalman_z, kalman_betas, joh_gate, joh_trace_ratio, joh_betas


def run_backtest(z_scores, gate_fn, label):
    """Run mean-reversion backtest with optional gate function.

    gate_fn(i) -> (allow_trade: bool, size_mult: float)
    """
    n = len(z_scores)
    position = 0       # +1 long, -1 short, 0 flat
    size_mult = 1.0
    trades = []
    equity = [0.0]
    current_pnl = 0.0
    entry_z = 0.0
    entry_idx = 0

    for i in range(1, n):
        z = z_scores[i]

        # --- Exit logic ---
        if position != 0:
            dz = z - z_scores[i-1]
            bar_pnl = -position * dz * size_mult
            current_pnl += bar_pnl

            # Exit conditions
            closed = False
            if position == 1 and z >= Z_EXIT and z_scores[i-1] < Z_EXIT:
                closed = True
            elif position == -1 and z <= -Z_EXIT and z_scores[i-1] > -Z_EXIT:
                closed = True
            elif abs(z) >= Z_ANOMALY:
                closed = True

            if closed:
                trades.append({
                    "entry_i": entry_idx, "exit_i": i,
                    "direction": "LONG" if position == 1 else "SHORT",
                    "entry_z": entry_z, "exit_z": z,
                    "pnl": current_pnl, "size": size_mult,
                    "bars_held": i - entry_idx,
                })
                position = 0
                current_pnl = 0.0

        # --- Entry logic ---
        if position == 0:
            allow, sm = gate_fn(i)
            if allow and abs(z) < Z_ANOMALY:
                if z <= -Z_ENTRY:
                    position = 1
                    size_mult = sm
                    entry_z = z
                    entry_idx = i
                    current_pnl = 0.0
                elif z >= Z_ENTRY:
                    position = -1
                    size_mult = sm
                    entry_z = z
                    entry_idx = i
                    current_pnl = 0.0

        # Track equity
        if position != 0:
            dz = z - z_scores[i-1]
            eq_change = -position * dz * size_mult
        else:
            eq_change = 0.0
        equity.append(equity[-1] + eq_change)

    return trades, equity


def analyze_results(trades, equity, label):
    """Compute performance metrics from trades."""
    if not trades:
        return {
            "Label": label, "Trades": 0, "Win Rate": 0, "Sharpe": 0,
            "Avg PnL": 0, "Max DD": 0, "Avg Bars": 0, "Total PnL": 0,
        }

    pnls = [t["pnl"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = dd.max()

    returns = np.diff(eq)
    sharpe = 0.0
    if len(returns) > 0 and returns.std() > 1e-10:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(108 * 252)

    return {
        "Label": label,
        "Trades": len(trades),
        "Win Rate": round(wins / len(trades) * 100, 1),
        "Sharpe": round(sharpe, 2),
        "Avg PnL": round(np.mean(pnls), 3),
        "Total PnL": round(sum(pnls), 2),
        "Max DD": round(max_dd, 2),
        "Avg Bars": round(np.mean([t["bars_held"] for t in trades]), 1),
    }


def run():
    print("=" * 65)
    print(f"  JOHANSEN GATE BACKTEST -- {PAIR['label']}")
    print("=" * 65)

    df = fetch_data()
    print("\n[CALC] Pre-computando sinais...")
    kalman_z, kalman_betas, joh_gate, joh_ratio, joh_betas = precompute(df)

    # --- Strategy A: Kalman only (no gate) ---
    def gate_none(i):
        return True, 1.0

    # --- Strategy B: Binary Johansen gate ---
    def gate_binary(i):
        return bool(joh_gate[i]), 1.0

    # --- Strategy C: Conviction scaling ---
    def gate_conviction(i):
        if not joh_gate[i]:
            return False, 0.0
        ratio = joh_ratio[i]
        # Scale: ratio=1.0 -> size=0.5, ratio=2.0 -> size=1.0, ratio=3.0+ -> size=1.5
        size = min(1.5, max(0.5, (ratio - 1.0) * 0.5 + 0.5))
        return True, size

    # --- Strategy D: Dual check (gate + beta consistency) ---
    def gate_dual(i):
        if not joh_gate[i]:
            return False, 0.0
        kb = kalman_betas[i]
        jb = joh_betas[i]
        if np.isnan(jb) or kb == 0:
            return True, 1.0  # Can't check, allow
        # Beta consistency: are they within tolerance of each other?
        diff_pct = abs(kb - jb) / abs(kb)
        if diff_pct > BETA_TOLERANCE:
            return False, 0.0  # Betas diverged, block
        return True, 1.0

    strategies = [
        ("A) Kalman Only", gate_none),
        ("B) Binary Gate", gate_binary),
        ("C) Conviction", gate_conviction),
        ("D) Dual Check", gate_dual),
    ]

    print("\n[CALC] Rodando 4 estrategias...\n")
    all_results = []
    all_equity = {}

    for label, gate_fn in strategies:
        trades, equity = run_backtest(kalman_z, gate_fn, label)
        metrics = analyze_results(trades, equity, label)
        all_results.append(metrics)
        all_equity[label] = equity
        print(f"  {label}: {metrics['Trades']} trades | "
              f"WR={metrics['Win Rate']}% | Sharpe={metrics['Sharpe']} | "
              f"PnL={metrics['Total PnL']}")

    # --- Results table ---
    print("\n" + "=" * 80)
    print("  RESULTADOS")
    print("=" * 80)
    df_r = pd.DataFrame(all_results)
    print(df_r.to_string(index=False))

    best = max(all_results, key=lambda r: r["Sharpe"])
    print(f"\n  >> Melhor Sharpe: {best['Label']} ({best['Sharpe']})")

    # --- Gate status over time ---
    n = len(kalman_z)
    gate_pct = sum(joh_gate) / n * 100
    print(f"\n  [INFO] Johansen gate ABERTO em {gate_pct:.1f}% do tempo")

    # --- Charts ---
    print("\n[PLOT] Gerando graficos...")
    _plot_results(df.index, kalman_z, joh_gate, joh_ratio, all_equity, all_results)
    print(f"\n  [OK] Graficos salvos em: {REPORT_DIR}")


def _plot_results(idx, kalman_z, joh_gate, joh_ratio, equities, results):
    p = PAIR["prefix"]
    n = len(kalman_z)
    eq_idx = idx[:max(len(e) for e in equities.values())]

    fig, axes = plt.subplots(4, 1, figsize=(18, 16), gridspec_kw={"height_ratios": [2, 1, 1, 2]})
    fig.suptitle(f"Johansen Gate Backtest -- {PAIR['label']}", fontsize=16, color="white", y=0.98)

    # Panel 1: Kalman Z-score + gate overlay
    ax = axes[0]
    ax.plot(idx, kalman_z, color="#4fc3f7", linewidth=0.6, alpha=0.9, label="Kalman Z")
    ax.axhline(Z_ENTRY, color="#ff3860", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axhline(-Z_ENTRY, color="#00e87a", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axhline(0, color="gray", linewidth=0.3, alpha=0.4)
    # Shade gate closed regions
    gate_closed = ~joh_gate
    ax.fill_between(idx, -5, 5, where=gate_closed, color="#ff3860", alpha=0.08, label="Gate CLOSED")
    ax.set_ylabel("Kalman Z-Score", fontsize=10)
    ax.set_ylim(-5, 5)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title("Kalman Z-Score com Johansen Gate (vermelho = bloqueado)", fontsize=10, color="gray")
    ax.grid(True, alpha=0.1)

    # Panel 2: Johansen gate status
    ax = axes[1]
    gate_int = joh_gate.astype(float)
    ax.fill_between(idx, 0, gate_int, color="#00e87a", alpha=0.4, label="Gate OPEN")
    ax.fill_between(idx, 0, 1 - gate_int, color="#ff3860", alpha=0.2, label="Gate CLOSED")
    ax.set_ylabel("Gate", fontsize=10)
    ax.set_ylim(-0.1, 1.1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["CLOSED", "OPEN"])
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.1)

    # Panel 3: Johansen trace ratio
    ax = axes[2]
    ax.plot(idx, joh_ratio, color="#e040fb", linewidth=0.8, alpha=0.8)
    ax.axhline(1.0, color="#ff3860", linewidth=1, linestyle="--", label="Critical (1.0)")
    ax.set_ylabel("Trace / Critical", fontsize=10)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title("Johansen Trace Ratio (> 1.0 = cointegrado)", fontsize=10, color="gray")
    ax.grid(True, alpha=0.1)

    # Panel 4: Equity curves
    ax = axes[3]
    colors = {"A) Kalman Only": "#4fc3f7", "B) Binary Gate": "#00e87a",
              "C) Conviction": "#ff9800", "D) Dual Check": "#e040fb"}
    for label, eq in equities.items():
        eq_i = idx[:len(eq)]
        ax.plot(eq_i, eq, color=colors.get(label, "white"), linewidth=1.2, alpha=0.9, label=label)
    ax.set_ylabel("Equity (z-units)", fontsize=10)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title("Equity Curves", fontsize=10, color="gray")
    ax.grid(True, alpha=0.1)

    plt.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{p}_johansen_gate_backtest.png"),
                dpi=150, bbox_inches="tight")
    plt.close(fig)

    # --- Bar chart ---
    fig, axes = plt.subplots(1, 4, figsize=(18, 5))
    fig.suptitle(f"Gate Strategy Comparison -- {PAIR['label']}", fontsize=14, color="white")
    labels = [r["Label"] for r in results]
    c = ["#4fc3f7", "#00e87a", "#ff9800", "#e040fb"]

    for ax, metric, title in zip(axes, ["Sharpe", "Win Rate", "Trades", "Total PnL"],
                                       ["Sharpe Ratio", "Win Rate (%)", "# Trades", "Total PnL"]):
        vals = [r[metric] for r in results]
        bars = ax.barh(labels, vals, color=c, alpha=0.8)
        if metric == "Sharpe":
            ax.axvline(0, color="gray", linewidth=0.5)
        ax.set_title(title, fontsize=10)
        ax.grid(True, alpha=0.1)

    plt.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{p}_johansen_gate_metrics.png"),
                dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"  - {p}_johansen_gate_backtest.png")
    print(f"  - {p}_johansen_gate_metrics.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", choices=["wdo", "di"], default="wdo")
    args = parser.parse_args()
    PAIR = PAIR_CONFIGS[args.pair]
    run()
