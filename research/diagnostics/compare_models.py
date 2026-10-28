# research/compare_models.py
"""
WIN×WDO ML Direction — Model Comparison & Reporting
=====================================================
Generates comparative analysis across all (model, threshold) combinations.

Outputs:
  - Summary table (console + CSV)
  - Equity curves plot
  - Threshold heatmap
  - Feature importance (XGBoost)
  - Directional accuracy per model
"""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPORT_DIR = PROJECT_ROOT / "data" / "reports"
WFA_DIR = PROJECT_ROOT / "data" / "processed" / "wfa_results"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

MODELS = ["baseline", "hmm", "lstm", "xgb"]
Z_THRESHOLDS = [1.5, 1.8, 2.0, 2.2]

# Dark theme for plots
plt.rcParams.update({
    "figure.facecolor": "#070c10",
    "axes.facecolor": "#0a0e12",
    "axes.edgecolor": "#1c2e3a",
    "axes.labelcolor": "#8a9aaa",
    "xtick.color": "#5a7080",
    "ytick.color": "#5a7080",
    "text.color": "#cdd8de",
    "grid.color": "#1c2e3a",
    "font.family": "monospace",
    "font.size": 9,
})


def load_results() -> pd.DataFrame:
    """Load backtest results from CSV."""
    path = REPORT_DIR / "ml_backtest_results.csv"
    if not path.exists():
        print(f"[ERROR] Results not found: {path}")
        print("Run `python research/backtest_ml_zscore.py` first.")
        sys.exit(1)
    return pd.read_csv(path)


def plot_equity_curves():
    """
    Plot equity curves for each model at z=1.8 (or best threshold).
    """
    fig, ax = plt.subplots(figsize=(14, 6))
    colors = {
        "baseline": "#3a5060",
        "hmm": "#f5a623",
        "lstm": "#00d4ff",
        "xgb": "#00e87a",
    }

    for model in MODELS:
        # Try z=1.8 first, or find any available
        for z in [1.8, 1.5, 2.0, 2.2]:
            trades_path = WFA_DIR / model / f"trades_z{z}.parquet"
            if trades_path.exists():
                break
        else:
            continue

        trades = pd.read_parquet(trades_path)
        if len(trades) == 0:
            continue

        trades = trades.sort_values("dt_out")
        equity = trades["pnl_brl"].cumsum()

        label = f"{model.upper()} (z={z})"
        ax.plot(range(len(equity)), equity.values,
                color=colors.get(model, "#ffffff"),
                linewidth=1.5 if model != "baseline" else 1,
                alpha=0.9, label=label)

    ax.axhline(0, color="#1c2e3a", linewidth=0.5)
    ax.set_xlabel("Trade #")
    ax.set_ylabel("PnL Acumulado (R$)")
    ax.set_title("EQUITY CURVES — ML Direction + Z-Score Timing", fontsize=12, color="#c8a444")
    ax.legend(loc="upper left", fontsize=8, facecolor="#0a0e12", edgecolor="#1c2e3a")
    ax.grid(True, alpha=0.3)

    path = REPORT_DIR / "ml_equity_curves.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Equity curves saved: {path}")


def plot_threshold_heatmap(results: pd.DataFrame):
    """
    Plot heatmap of PnL by (model, threshold).
    """
    pivot = results.pivot_table(
        index="model", columns="threshold",
        values="total_pnl", aggfunc="first"
    )

    fig, ax = plt.subplots(figsize=(8, 4))

    # Manual heatmap
    data = pivot.values
    models = list(pivot.index)
    thresholds = list(pivot.columns)

    im = ax.imshow(data, aspect="auto", cmap="RdYlGn",
                   vmin=data.min(), vmax=data.max())

    ax.set_xticks(range(len(thresholds)))
    ax.set_xticklabels([f"z={t}" for t in thresholds])
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([m.upper() for m in models])

    # Annotate cells
    for i in range(len(models)):
        for j in range(len(thresholds)):
            val = data[i, j]
            color = "#000000" if abs(val) > abs(data).max() * 0.5 else "#cdd8de"
            ax.text(j, i, f"R${val:.0f}", ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)

    ax.set_title("PnL POR MODELO × THRESHOLD", fontsize=12, color="#c8a444")
    fig.colorbar(im, ax=ax, label="PnL (R$)", shrink=0.8)

    path = REPORT_DIR / "ml_threshold_heatmap.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Threshold heatmap saved: {path}")


def plot_directional_accuracy():
    """
    Plot standalone directional accuracy per model.
    """
    from research.models.features import make_target

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    model_names = ["hmm", "lstm", "xgb"]
    colors = {"hmm": "#f5a623", "lstm": "#00d4ff", "xgb": "#00e87a"}

    for ax, model_name in zip(axes, model_names):
        pred_path = WFA_DIR / model_name / "predictions_oos.parquet"
        if not pred_path.exists():
            ax.set_title(f"{model_name.upper()}: N/A", color="#ff3860")
            continue

        preds = pd.read_parquet(pred_path)
        valid = preds["fwd_ret_pts"].notna()
        if valid.sum() == 0:
            continue

        actual = make_target(preds.loc[valid, "fwd_ret_pts"])
        predicted = preds.loc[valid, "direction"]

        # Confusion-style accuracy per class
        classes = ["BUY", "FLAT", "SELL"]
        accs = []
        for cls in classes:
            mask = actual == cls
            if mask.sum() > 0:
                correct = (predicted[mask] == cls).sum()
                accs.append(correct / mask.sum() * 100)
            else:
                accs.append(0)

        overall = (predicted.values == actual.values).mean() * 100

        bars = ax.bar(classes, accs, color=colors[model_name], alpha=0.7, edgecolor="#1c2e3a")
        ax.axhline(33.3, color="#ff3860", linestyle="--", linewidth=0.8, label="Random (33%)")
        ax.set_title(f"{model_name.upper()} — OOS Acc: {overall:.1f}%",
                     fontsize=10, color=colors[model_name])
        ax.set_ylabel("Accuracy (%)")
        ax.set_ylim(0, 100)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.2, axis="y")

        # Annotate bars
        for bar, acc in zip(bars, accs):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                    f"{acc:.0f}%", ha="center", fontsize=8, color=colors[model_name])

    fig.suptitle("ACURÁCIA DIRECIONAL — OOS (Walk-Forward)", fontsize=12, color="#c8a444")
    fig.tight_layout()

    path = REPORT_DIR / "ml_directional_accuracy.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Directional accuracy saved: {path}")


def generate_report(results: pd.DataFrame):
    """Generate full text report."""
    lines = []
    lines.append("=" * 70)
    lines.append("ML DIRECTION MODELS — COMPARATIVE REPORT")
    lines.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)

    # Best overall
    best = results.loc[results["total_pnl"].idxmax()]
    lines.append(f"\nBEST COMBINATION: {best['model'].upper()} z={best['threshold']}")
    lines.append(f"  PnL: R${best['total_pnl']:.2f}")
    lines.append(f"  Win Rate: {best['win_rate']}%")
    lines.append(f"  Profit Factor: {best['profit_factor']}")
    lines.append(f"  Max Drawdown: R${best['max_drawdown']:.2f}")
    lines.append(f"  Trades/month: {best['trades_per_month']}")

    # Baseline at z=1.8
    bl = results[(results["model"] == "baseline") & (results["threshold"] == 1.8)]
    if len(bl) > 0:
        bl = bl.iloc[0]
        lines.append(f"\nBASELINE (z=1.8): PnL=R${bl['total_pnl']:.2f}, "
                      f"WR={bl['win_rate']}%, PF={bl['profit_factor']}")
        alpha = best["total_pnl"] - bl["total_pnl"]
        lines.append(f"ALPHA over baseline: R${alpha:.2f}")

    # Full table
    lines.append(f"\n{'=' * 70}")
    lines.append("FULL RESULTS")
    lines.append(f"{'=' * 70}")
    lines.append(results.to_string(index=False))

    # Per-model summary
    lines.append(f"\n{'=' * 70}")
    lines.append("PER-MODEL BEST (across thresholds)")
    lines.append(f"{'=' * 70}")
    for model in MODELS:
        subset = results[results["model"] == model]
        if len(subset) == 0:
            continue
        best_row = subset.loc[subset["total_pnl"].idxmax()]
        lines.append(f"  {model.upper():>10} | best z={best_row['threshold']} | "
                      f"PnL=R${best_row['total_pnl']:.2f} | "
                      f"WR={best_row['win_rate']}% | "
                      f"PF={best_row['profit_factor']} | "
                      f"DD=R${best_row['max_drawdown']:.2f}")

    report = "\n".join(lines)
    path = REPORT_DIR / "ml_comparison_report.txt"
    path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {path}")
    print(report)


def main():
    print("=" * 70)
    print("ML Direction — Model Comparison")
    print("=" * 70)

    results = load_results()
    print(f"Loaded {len(results)} result rows")

    # Generate all outputs
    generate_report(results)
    plot_equity_curves()
    plot_threshold_heatmap(results)
    plot_directional_accuracy()

    print(f"\nAll reports saved to {REPORT_DIR}/")


if __name__ == "__main__":
    main()
