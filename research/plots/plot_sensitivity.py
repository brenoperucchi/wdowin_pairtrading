"""Generate 4 sensitivity charts: Calmar Ratio vs each tuned parameter."""
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv('data/reports/lstm_tuning_v2_results.csv')
df1 = pd.read_csv('data/reports/lstm_tuning_results.csv')
df1['z_threshold'] = 2.2

all_df = pd.concat([df, df1], ignore_index=True)
all_df = all_df.drop_duplicates(subset=['target_thr','seq_len','hidden_dim','z_threshold'], keep='first')

params = [
    ('target_thr', 'Target Threshold (pts)', 'Sensibilidade ao Target Threshold'),
    ('seq_len', 'Sequence Length (barras M30)', 'Sensibilidade ao Comprimento da Sequência'),
    ('hidden_dim', 'Hidden Dimension (neurônios)', 'Sensibilidade ao Tamanho do Cérebro'),
    ('z_threshold', 'Z-Score Threshold', 'Sensibilidade ao Z-Score Threshold'),
]
colors = ['#2196F3', '#FF5722', '#4CAF50', '#9C27B0']

fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('Análise de Sensibilidade — Calmar Ratio por Parâmetro\n(média ± desvio das demais configurações)',
             fontsize=16, fontweight='bold', y=0.98)

for idx, (param, xlabel, title) in enumerate(params):
    ax = axes[idx // 2][idx % 2]
    grouped = all_df.groupby(param)['calmar_ratio'].agg(['mean', 'std', 'max', 'min', 'count']).sort_index()
    x = grouped.index.values
    y_mean = grouped['mean'].values
    y_std = grouped['std'].fillna(0).values
    y_max = grouped['max'].values

    ax.fill_between(x, y_mean - y_std, y_mean + y_std, alpha=0.2, color=colors[idx])
    ax.plot(x, y_mean, 'o-', color=colors[idx], linewidth=2.5, markersize=10, label='Média', zorder=5)
    ax.plot(x, y_max, 's--', color=colors[idx], alpha=0.5, linewidth=1.5, markersize=7, label='Melhor caso')

    best_idx = np.argmax(y_mean)
    ax.scatter(x[best_idx], y_mean[best_idx], s=200, color='gold', edgecolors='black',
               linewidth=2, zorder=10, marker='*')
    ax.annotate(f'Best: {x[best_idx]}', (x[best_idx], y_mean[best_idx]),
                textcoords='offset points', xytext=(10, 10), fontsize=11, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='black'))

    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel('Calmar Ratio', fontsize=12)
    ax.set_title(title, fontsize=13, fontweight='bold')
    ax.axhline(y=0, color='red', linestyle=':', alpha=0.3)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(x)

plt.tight_layout(rect=[0, 0, 1, 0.95])
out = 'data/reports/lstm_sensitivity_calmar.png'
plt.savefig(out, dpi=150, bbox_inches='tight')
plt.close()
print(f'Saved: {out}')
