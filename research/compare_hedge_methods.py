# research/compare_hedge_methods.py
"""
Hedge Ratio Methods Comparison: WIN×DI Pair Trading
====================================================
Compares 4 methods for calculating the spread/z-score:
  1. OLS (baseline)
  2. Kalman raw
  3. Kalman log-prices
  4. Johansen cointegration vector

Metrics: Half-Life, Hurst Exponent, ADF p-value, Sharpe Ratio
Output: Comparative charts saved to data/reports/

Usage:
  python research/compare_hedge_methods.py --pair wdo   (WIN x WDO)
  python research/compare_hedge_methods.py --pair di    (WIN x DI)
"""
import os, sys, warnings, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime
from statsmodels.tsa.stattools import adfuller, coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import MetaTrader5 as mt5

from core.config import MT5_PATH, SYMBOL_A, SYMBOL_B, WINDOW, BETA_INITIAL
from core.kalman_filter import KalmanBetaFilter

# ─── Config ──────────────────────────────────────────────────────────────────
BARS_FETCH = 5000
Z_WINDOW = 40
Z_ENTRY = 1.8
Z_EXIT = 0.0
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

plt.style.use("dark_background")
COLORS = {"OLS": "#00e87a", "Kalman": "#4fc3f7", "Kalman Log": "#ff9800", "Johansen": "#e040fb"}

# Pair-specific configs
PAIR_CONFIGS = {
    "wdo": {
        "sym_a": SYMBOL_A, "sym_b": SYMBOL_B, "label": "WIN x WDO",
        "col_a": "WIN", "col_b": "WDO",
        "kalman_beta": BETA_INITIAL,       # -22.5
        "kalman_tcov": 1e-4, "kalman_ocov": 1e4,
        "klog_beta": -1.0, "klog_tcov": 1e-5, "klog_ocov": 1e-2,
        "prefix": "wdo",
    },
    "di": {
        "sym_a": SYMBOL_A, "sym_b": "DI1$N", "label": "WIN x DI",
        "col_a": "WIN", "col_b": "DI",
        "kalman_beta": -10000.0,
        "kalman_tcov": 1e-4, "kalman_ocov": 1e6,
        "klog_beta": -1.0, "klog_tcov": 1e-5, "klog_ocov": 1e-2,
        "prefix": "di",
    },
}

PAIR = None  # set at runtime


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_data():
    """Fetch pair data from MT5."""
    kwargs = {"path": MT5_PATH} if MT5_PATH else {}
    if not mt5.initialize(**kwargs):
        print(f"[ERRO] MT5 nao conectou: {mt5.last_error()}")
        sys.exit(1)

    print(f"[MT5] Conectado -- {mt5.terminal_info().name}")

    sym_a, sym_b = PAIR["sym_a"], PAIR["sym_b"]
    col_a, col_b = PAIR["col_a"], PAIR["col_b"]

    rates_a = mt5.copy_rates_from_pos(sym_a, mt5.TIMEFRAME_M5, 0, BARS_FETCH)
    rates_b = mt5.copy_rates_from_pos(sym_b, mt5.TIMEFRAME_M5, 0, BARS_FETCH)
    mt5.shutdown()

    if rates_a is None or rates_b is None:
        print(f"[ERRO] Sem dados para {sym_a} / {sym_b}.")
        sys.exit(1)

    df_a = pd.DataFrame(rates_a)[["time", "close"]].rename(columns={"close": col_a})
    df_b = pd.DataFrame(rates_b)[["time", "close"]].rename(columns={"close": col_b})
    df = pd.merge(df_a, df_b, on="time", how="inner")
    df["dt"] = pd.to_datetime(df["time"], unit="s") + pd.Timedelta(hours=3)
    df.set_index("dt", inplace=True)
    df.drop(columns=["time"], inplace=True)

    print(f"[DATA] {len(df)} barras M5 | "
          f"{df.index[0].strftime('%Y-%m-%d')} -> {df.index[-1].strftime('%Y-%m-%d')}")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: HEDGE RATIO METHODS
# ═══════════════════════════════════════════════════════════════════════════════

def method_ols(win, di, window=Z_WINDOW):
    """Method 1: Rolling OLS beta."""
    n = len(win)
    betas = np.full(n, np.nan)
    spreads = np.full(n, np.nan)

    for i in range(window, n):
        y = win[i-window:i]
        x = di[i-window:i]
        X = np.column_stack([np.ones(window), x])
        coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
        b = coefs[1]
        betas[i] = b
        spreads[i] = win[i] - b * di[i]

    return betas, spreads


def method_kalman_raw(win, di, initial_beta=None):
    """Method 2: Kalman filter on raw prices."""
    ib = initial_beta or PAIR["kalman_beta"]
    kf = KalmanBetaFilter(initial_beta=ib, trans_cov=PAIR["kalman_tcov"], obs_cov=PAIR["kalman_ocov"])
    n = len(win)
    betas = np.zeros(n)
    spreads = np.zeros(n)

    for i in range(n):
        beta, spread, _ = kf.update(float(win[i]), float(di[i]))
        betas[i] = beta
        spreads[i] = spread

    return betas, spreads


def method_kalman_log(win, di, initial_beta=None):
    """Method 3: Kalman filter on log-prices (scale normalized)."""
    log_win = np.log(win)
    log_di = np.log(di)
    ib = initial_beta or PAIR["klog_beta"]
    kf = KalmanBetaFilter(initial_beta=ib, trans_cov=PAIR["klog_tcov"], obs_cov=PAIR["klog_ocov"])
    n = len(win)
    betas = np.zeros(n)
    spreads = np.zeros(n)

    for i in range(n):
        beta, spread, _ = kf.update(float(log_win[i]), float(log_di[i]))
        betas[i] = beta
        spreads[i] = spread

    return betas, spreads


def method_johansen(win, di, window=250):
    """Method 4: Rolling Johansen cointegration vector."""
    n = len(win)
    betas = np.full(n, np.nan)
    spreads = np.full(n, np.nan)

    for i in range(window, n):
        y = np.column_stack([win[i-window:i], di[i-window:i]])
        try:
            result = coint_johansen(y, det_order=0, k_ar_diff=1)
            vec = result.evec[:, 0]
            # Normalize so coefficient of WIN = 1
            vec = vec / vec[0]
            b = vec[1]
            betas[i] = b
            spreads[i] = win[i] + b * di[i]  # vec = [1, b] → spread = WIN + b*DI
        except Exception:
            if i > window:
                betas[i] = betas[i-1]
                spreads[i] = win[i] + betas[i] * di[i]

    return betas, spreads


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def rolling_zscore(spread, window=Z_WINDOW):
    """Compute rolling z-score from spread array."""
    n = len(spread)
    z = np.zeros(n)
    for i in range(window, n):
        w = spread[max(0, i-window):i]
        valid = w[~np.isnan(w)]
        if len(valid) < 5:
            continue
        mu, sd = valid.mean(), valid.std()
        if sd > 1e-10 and not np.isnan(spread[i]):
            z[i] = (spread[i] - mu) / sd
    return z


def calc_half_life(spread):
    """Half-life of mean reversion via AR(1)."""
    s = spread[~np.isnan(spread)]
    if len(s) < 10:
        return np.inf
    lag = s[:-1]
    curr = s[1:]
    X = np.column_stack([np.ones(len(lag)), lag])
    coefs, *_ = np.linalg.lstsq(X, curr, rcond=None)
    lam = coefs[1]
    if lam >= 1.0 or lam <= 0.0:
        return np.inf
    return -np.log(2) / np.log(lam)


def calc_hurst(spread, max_lags=100):
    """Hurst exponent via R/S analysis. H < 0.5 = mean-reverting."""
    s = spread[~np.isnan(spread)]
    if len(s) < max_lags * 2:
        max_lags = len(s) // 3

    lags = range(2, max_lags)
    rs_list = []
    for lag in lags:
        chunks = [s[i:i+lag] for i in range(0, len(s) - lag, lag)]
        rs_vals = []
        for chunk in chunks:
            if len(chunk) < 2:
                continue
            mean_c = chunk.mean()
            cumdev = np.cumsum(chunk - mean_c)
            R = cumdev.max() - cumdev.min()
            S = chunk.std()
            if S > 1e-10:
                rs_vals.append(R / S)
        if rs_vals:
            rs_list.append((np.log(lag), np.log(np.mean(rs_vals))))

    if len(rs_list) < 5:
        return 0.5

    x = np.array([r[0] for r in rs_list])
    y = np.array([r[1] for r in rs_list])
    coefs = np.polyfit(x, y, 1)
    return coefs[0]


def calc_adf_pvalue(spread):
    """ADF test p-value. Lower = more stationary."""
    s = spread[~np.isnan(spread)]
    if len(s) < 20:
        return 1.0
    try:
        result = adfuller(s, maxlag=20, autolag="AIC")
        return result[1]
    except Exception:
        return 1.0


def backtest_sharpe(z_scores, z_entry=Z_ENTRY, z_exit=Z_EXIT):
    """Simple mean-reversion backtest Sharpe ratio.
    Long when z < -entry, short when z > +entry, exit at z_exit crossing.
    Returns per bar."""
    n = len(z_scores)
    position = 0  # +1 long, -1 short, 0 flat
    returns = []

    for i in range(1, n):
        z = z_scores[i]
        z_prev = z_scores[i-1]

        # Entry
        if position == 0:
            if z <= -z_entry:
                position = 1
            elif z >= z_entry:
                position = -1

        # Exit
        if position == 1 and z_prev < z_exit and z >= z_exit:
            position = 0
        elif position == -1 and z_prev > -z_exit and z <= -z_exit:
            position = 0

        # PnL is position * delta_z (mean reversion = z moving toward 0)
        dz = z_scores[i] - z_scores[i-1]
        returns.append(-position * dz)  # Negative because we want z to revert

    returns = np.array(returns)
    if returns.std() < 1e-10:
        return 0.0
    # Annualize: ~108 bars/day * 252 days
    return (returns.mean() / returns.std()) * np.sqrt(108 * 252)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def run_analysis():
    label = PAIR["label"]
    print("=" * 65)
    print(f"  HEDGE RATIO METHODS COMPARISON -- {label}")
    print("=" * 65)
    print()

    # 1. Fetch data
    df = fetch_data()
    win = df[PAIR["col_a"]].values
    di = df[PAIR["col_b"]].values

    # 2. Run all methods
    print("\n[CALC] Rodando 4 métodos...")

    print("  1/4 OLS rolling...")
    betas_ols, spreads_ols = method_ols(win, di)

    print("  2/4 Kalman raw...")
    betas_kalman, spreads_kalman = method_kalman_raw(win, di)

    print("  3/4 Kalman log-prices...")
    betas_klog, spreads_klog = method_kalman_log(win, di)

    print("  4/4 Johansen rolling...")
    betas_joh, spreads_joh = method_johansen(win, di)

    # 3. Z-scores
    print("\n[CALC] Calculando z-scores rolling...")
    methods = {
        "OLS":        {"betas": betas_ols,    "spreads": spreads_ols},
        "Kalman":     {"betas": betas_kalman, "spreads": spreads_kalman},
        "Kalman Log": {"betas": betas_klog,   "spreads": spreads_klog},
        "Johansen":   {"betas": betas_joh,    "spreads": spreads_joh},
    }

    for name, data in methods.items():
        data["z"] = rolling_zscore(data["spreads"])

    # 4. Metrics
    print("\n[CALC] Calculando métricas...")
    results = []
    for name, data in methods.items():
        s = data["spreads"]
        z = data["z"]
        # Use only valid (non-NaN) portion
        valid_mask = ~np.isnan(s)
        s_valid = s[valid_mask]

        hl = calc_half_life(s_valid)
        hurst = calc_hurst(s_valid)
        adf_p = calc_adf_pvalue(s_valid)
        sharpe = backtest_sharpe(z)

        row = {
            "Method": name,
            "Half-Life (bars)": round(hl, 1) if hl < 1e6 else "∞",
            "Hurst": round(hurst, 3),
            "ADF p-value": round(adf_p, 4),
            "Sharpe (ann.)": round(sharpe, 2),
            "Mean-Reverting?": "YES" if hurst < 0.5 and adf_p < 0.05 else "MAYBE" if adf_p < 0.10 else "NO",
        }
        results.append(row)
        data["metrics"] = row

    # 5. Print results table
    print("\n" + "=" * 80)
    print("  RESULTADOS COMPARATIVOS")
    print("=" * 80)
    df_results = pd.DataFrame(results)
    print(df_results.to_string(index=False))
    print()

    # Recommendation
    best_sharpe = max(results, key=lambda r: r["Sharpe (ann.)"])
    best_hurst = min(results, key=lambda r: r["Hurst"] if isinstance(r["Hurst"], float) else 999)
    print(f"  >> Melhor Sharpe:        {best_sharpe['Method']} ({best_sharpe['Sharpe (ann.)']})")
    print(f"  >> Mais Mean-Reverting:  {best_hurst['Method']} (Hurst={best_hurst['Hurst']})")

    # 6. Charts
    print("\n[PLOT] Gerando gráficos comparativos...")
    _plot_all(df.index, methods, results)

    print(f"\n  [OK] Graficos salvos em: {REPORT_DIR}")
    print("  Concluído!")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def _plot_all(idx, methods, results):
    """Generate all comparison charts."""
    # --- Chart 1: Z-Scores side by side ---
    fig, axes = plt.subplots(4, 1, figsize=(18, 14), sharex=True)
    fig.suptitle(f"Z-Score Comparison -- {PAIR['label']} (4 Methods)", fontsize=16, color="white", y=0.98)

    for ax, (name, data) in zip(axes, methods.items()):
        z = data["z"]
        color = COLORS[name]
        ax.plot(idx, z, color=color, linewidth=0.6, alpha=0.9)
        ax.axhline(Z_ENTRY, color="#ff3860", linewidth=0.5, linestyle="--", alpha=0.5)
        ax.axhline(-Z_ENTRY, color="#00e87a", linewidth=0.5, linestyle="--", alpha=0.5)
        ax.axhline(0, color="gray", linewidth=0.3, alpha=0.4)
        ax.fill_between(idx, z, 0, where=(z > Z_ENTRY), color="#ff3860", alpha=0.15)
        ax.fill_between(idx, z, 0, where=(z < -Z_ENTRY), color="#00e87a", alpha=0.15)
        m = data["metrics"]
        ax.set_ylabel(name, fontsize=11, color=color, fontweight="bold")
        ax.set_title(f"HL={m['Half-Life (bars)']}  |  Hurst={m['Hurst']}  |  "
                     f"ADF p={m['ADF p-value']}  |  Sharpe={m['Sharpe (ann.)']}",
                     fontsize=9, color="gray", loc="right")
        ax.set_ylim(-5, 5)
        ax.grid(True, alpha=0.1)

    plt.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{PAIR['prefix']}_hedge_compare_zscores.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    # --- Chart 2: Beta evolution ---
    fig, ax = plt.subplots(figsize=(18, 5))
    fig.suptitle(f"Beta (Hedge Ratio) Evolution -- {PAIR['label']}", fontsize=14, color="white")

    for name, data in methods.items():
        b = data["betas"].copy()
        # Normalize for visual comparison (different scales)
        valid = b[~np.isnan(b)]
        if len(valid) > 0:
            b_norm = (b - np.nanmean(b)) / (np.nanstd(b) + 1e-10)
            ax.plot(idx, b_norm, color=COLORS[name], linewidth=0.8, alpha=0.8, label=name)

    ax.set_ylabel("Beta (z-normalized)", fontsize=10)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.1)
    plt.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{PAIR['prefix']}_hedge_compare_betas.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    # --- Chart 3: Spread stationarity ---
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(f"Spread Distribution & Stationarity -- {PAIR['label']}", fontsize=14, color="white", y=1.01)

    for ax, (name, data) in zip(axes.flat, methods.items()):
        s = data["spreads"]
        valid = s[~np.isnan(s)]
        ax.hist(valid, bins=80, color=COLORS[name], alpha=0.7, edgecolor="none")
        ax.axvline(np.mean(valid), color="white", linewidth=1, linestyle="--", label=f"μ={np.mean(valid):.1f}")
        ax.set_title(f"{name} — ADF p={data['metrics']['ADF p-value']}", fontsize=11, color=COLORS[name])
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.1)

    plt.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{PAIR['prefix']}_hedge_compare_distributions.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    # --- Chart 4: Metrics radar/bar ---
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle(f"Metrics Comparison -- {PAIR['label']}", fontsize=14, color="white")
    names = list(methods.keys())
    colors_list = [COLORS[n] for n in names]

    # Hurst
    vals = [methods[n]["metrics"]["Hurst"] for n in names]
    axes[0].barh(names, vals, color=colors_list, alpha=0.8)
    axes[0].axvline(0.5, color="#ff3860", linewidth=1, linestyle="--", label="H=0.5 (random walk)")
    axes[0].set_title("Hurst Exponent (< 0.5 = mean-reverting)", fontsize=10)
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.1)

    # ADF p-value
    vals = [methods[n]["metrics"]["ADF p-value"] for n in names]
    axes[1].barh(names, vals, color=colors_list, alpha=0.8)
    axes[1].axvline(0.05, color="#00e87a", linewidth=1, linestyle="--", label="p=0.05")
    axes[1].set_title("ADF p-value (< 0.05 = stationary)", fontsize=10)
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.1)

    # Sharpe
    vals = [methods[n]["metrics"]["Sharpe (ann.)"] for n in names]
    axes[2].barh(names, vals, color=colors_list, alpha=0.8)
    axes[2].axvline(0, color="gray", linewidth=0.5)
    axes[2].set_title("Annualized Sharpe Ratio", fontsize=10)
    axes[2].grid(True, alpha=0.1)

    plt.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{PAIR['prefix']}_hedge_compare_metrics.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    p = PAIR['prefix']
    print(f"  - {p}_hedge_compare_zscores.png")
    print(f"  - {p}_hedge_compare_betas.png")
    print(f"  - {p}_hedge_compare_distributions.png")
    print(f"  - {p}_hedge_compare_metrics.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare hedge ratio methods")
    parser.add_argument("--pair", choices=["wdo", "di"], default="di", help="Which pair to test")
    args = parser.parse_args()
    PAIR = PAIR_CONFIGS[args.pair]
    run_analysis()
