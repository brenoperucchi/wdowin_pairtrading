"""
Generate distribution and sensitivity charts from grid search results.
3 models × 3 params = 9 sensitivity charts + model comparison.
"""
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

REPORT_DIR = Path('data/reports')
OUT_DIR = REPORT_DIR


def load_results():
    df = pd.read_csv(REPORT_DIR / 'grid_search_all_models.csv')
    print(f"Loaded {len(df)} results")
    print(f"  HMM:     {(df.model=='HMM').sum()}")
    print(f"  LSTM:    {(df.model=='LSTM').sum()}")
    print(f"  XGBoost: {(df.model=='XGBoost').sum()}")
    return df


def plot_model_comparison(df):
    """Box plot comparing Calmar ratio across models."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('Comparação entre Modelos — Distribuição de Métricas (30% OOS)',
                 fontsize=15, fontweight='bold')

    metrics = [
        ('calmar_ratio', 'Calmar Ratio (PnL/|DD|)'),
        ('total_pnl', 'PnL Total (R$)'),
        ('profit_factor', 'Profit Factor'),
    ]
    colors = {'HMM': '#2196F3', 'LSTM': '#FF5722', 'XGBoost': '#4CAF50'}

    for ax, (metric, label) in zip(axes, metrics):
        data = []
        labels = []
        for model in ['HMM', 'LSTM', 'XGBoost']:
            subset = df[df.model == model][metric].dropna()
            # Cap extreme outliers for visualization
            q99 = subset.quantile(0.99) if len(subset) > 10 else subset.max()
            subset = subset.clip(upper=q99)
            data.append(subset)
            labels.append(f"{model}\n(n={len(subset)})")

        bp = ax.boxplot(data, labels=labels, patch_artist=True, widths=0.6,
                        showmeans=True, meanline=True,
                        meanprops=dict(color='black', linewidth=2, linestyle='--'))

        for patch, model in zip(bp['boxes'], ['HMM', 'LSTM', 'XGBoost']):
            patch.set_facecolor(colors[model])
            patch.set_alpha(0.4)

        ax.set_ylabel(label, fontsize=12)
        ax.axhline(y=0, color='red', linestyle=':', alpha=0.3)
        ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out = OUT_DIR / 'grid_model_comparison.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {out}")


def plot_sensitivity_per_model(df):
    """3×3 grid: one row per model, one column per parameter."""
    models_config = {
        'HMM': {
            'params': [
                ('param1_value', 'ret_threshold', 'Ret Threshold'),
                ('param2_value', 'covariance_type', 'Covariance Type'),
                ('param3_value', 'n_iter', 'N Iterations'),
            ],
            'color': '#2196F3'
        },
        'LSTM': {
            'params': [
                ('param1_value', 'seq_len', 'Sequence Length'),
                ('param2_value', 'hidden_dim', 'Hidden Dim'),
                ('param3_value', 'dropout', 'Dropout'),
            ],
            'color': '#FF5722'
        },
        'XGBoost': {
            'params': [
                ('param1_value', 'max_depth', 'Max Depth'),
                ('param2_value', 'n_estimators', 'N Estimators'),
                ('param3_value', 'learning_rate', 'Learning Rate'),
            ],
            'color': '#4CAF50'
        },
    }

    fig, axes = plt.subplots(3, 3, figsize=(20, 16))
    fig.suptitle('Análise de Sensibilidade por Modelo — Calmar Ratio\n(média ± desvio, marcando melhor valor)',
                 fontsize=16, fontweight='bold', y=0.98)

    for row, (model, cfg) in enumerate(models_config.items()):
        subset = df[df.model == model].copy()
        color = cfg['color']

        for col, (col_name, param_name, param_label) in enumerate(cfg['params']):
            ax = axes[row][col]

            grouped = subset.groupby(col_name)['calmar_ratio'].agg(['mean', 'std', 'max', 'count'])
            grouped = grouped.sort_index()

            x = grouped.index
            y_mean = grouped['mean'].values
            y_std = grouped['std'].fillna(0).values
            y_max = grouped['max'].values

            # For categorical params (covariance_type), use bar chart
            if param_name == 'covariance_type':
                x_pos = range(len(x))
                bars = ax.bar(x_pos, y_mean, color=color, alpha=0.6, edgecolor=color)
                ax.errorbar(x_pos, y_mean, yerr=y_std, fmt='none', color='black', capsize=5)
                ax.set_xticks(x_pos)
                ax.set_xticklabels(x, fontsize=10)

                # Mark best
                best_idx = np.argmax(y_mean)
                bars[best_idx].set_alpha(1.0)
                bars[best_idx].set_edgecolor('gold')
                bars[best_idx].set_linewidth(3)
                ax.annotate(f'★ Best', (best_idx, y_mean[best_idx]),
                           textcoords='offset points', xytext=(0, 10),
                           fontsize=10, fontweight='bold', ha='center', color='goldenrod')
            else:
                x_num = x.astype(float)
                ax.fill_between(x_num, y_mean - y_std, y_mean + y_std, alpha=0.15, color=color)
                ax.plot(x_num, y_mean, 'o-', color=color, linewidth=2, markersize=8, label='Média', zorder=5)
                ax.plot(x_num, y_max, 's--', color=color, alpha=0.4, linewidth=1, markersize=5, label='Max')

                best_idx = np.argmax(y_mean)
                ax.scatter(x_num.iloc[best_idx], y_mean[best_idx], s=200, color='gold',
                          edgecolors='black', linewidth=2, zorder=10, marker='*')
                ax.annotate(f'Best: {x.iloc[best_idx]}',
                           (x_num.iloc[best_idx], y_mean[best_idx]),
                           textcoords='offset points', xytext=(10, 10),
                           fontsize=10, fontweight='bold',
                           arrowprops=dict(arrowstyle='->', color='black'))

            ax.set_xlabel(param_label, fontsize=11)
            ax.set_ylabel('Calmar Ratio', fontsize=11)
            ax.set_title(f'{model} — {param_label}', fontsize=12, fontweight='bold')
            ax.axhline(y=0, color='red', linestyle=':', alpha=0.3)
            ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = OUT_DIR / 'grid_sensitivity_all_models.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {out}")


def plot_pnl_distribution(df):
    """Histogram of PnL distribution per model."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('Distribuição de PnL por Modelo — Todas as Configurações (30% OOS)',
                 fontsize=15, fontweight='bold')

    colors = {'HMM': '#2196F3', 'LSTM': '#FF5722', 'XGBoost': '#4CAF50'}

    for ax, model in zip(axes, ['HMM', 'LSTM', 'XGBoost']):
        subset = df[df.model == model]['total_pnl'].dropna()
        positive_pct = (subset > 0).mean() * 100

        ax.hist(subset, bins=30, color=colors[model], alpha=0.7, edgecolor='white')
        ax.axvline(x=0, color='red', linewidth=2, linestyle='--', label='Breakeven')
        ax.axvline(x=subset.median(), color='black', linewidth=2, linestyle='-',
                  label=f'Mediana: R${subset.median():.0f}')

        ax.set_xlabel('PnL (R$)', fontsize=12)
        ax.set_ylabel('Frequência', fontsize=12)
        ax.set_title(f'{model} — {positive_pct:.0f}% lucrativas (n={len(subset)})',
                    fontsize=12, fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out = OUT_DIR / 'grid_pnl_distribution.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {out}")


def print_summary(df):
    """Print summary stats per model."""
    print(f"\n{'='*70}")
    print("SUMMARY STATISTICS")
    print(f"{'='*70}")

    for model in ['HMM', 'LSTM', 'XGBoost']:
        subset = df[df.model == model]
        print(f"\n  {model} ({len(subset)} configs):")
        print(f"    Calmar:  mean={subset.calmar_ratio.mean():.2f} | "
              f"max={subset.calmar_ratio.max():.2f} | "
              f"std={subset.calmar_ratio.std():.2f}")
        print(f"    PnL:     mean=R${subset.total_pnl.mean():.0f} | "
              f"max=R${subset.total_pnl.max():.0f} | "
              f"positive={( subset.total_pnl > 0).mean()*100:.0f}%")
        print(f"    PF:      mean={subset.profit_factor.mean():.2f} | "
              f"max={subset.profit_factor.max():.2f}")

    # Top 3 per model
    for model in ['HMM', 'LSTM', 'XGBoost']:
        subset = df[df.model == model].head(3)
        print(f"\n  TOP 3 {model}:")
        for _, r in subset.iterrows():
            print(f"    {r.param1_name}={r.param1_value} {r.param2_name}={r.param2_value} "
                  f"{r.param3_name}={r.param3_value} → "
                  f"Calmar={r.calmar_ratio} PnL=R${r.total_pnl:.0f} PF={r.profit_factor}")


if __name__ == "__main__":
    df = load_results()
    print_summary(df)
    plot_model_comparison(df)
    plot_sensitivity_per_model(df)
    plot_pnl_distribution(df)
    print("\nAll charts generated!")
