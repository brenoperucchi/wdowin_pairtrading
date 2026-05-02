import pandas as pd, numpy as np

df = pd.read_csv('backtest_v2_trades.csv')
print(f'Total trades: {len(df)}')
print()

rows = []
for model in ['V1_OLS', 'V2_KALMAN']:
    m = df[df['model'] == model]
    for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell']:
        t = m[m['leg'] == leg]
        if len(t) == 0:
            rows.append([model, leg, 0, 0, 0, 0, 0, 0, 0, 0, 0])
            continue
        w = len(t[t['pnl'] > 0])
        wr = w / len(t) * 100
        p = t['pnl'].sum()
        a = t['pnl'].mean()
        gp = t[t['pnl'] > 0]['pnl'].sum()
        gl = abs(t[t['pnl'] <= 0]['pnl'].sum()) + 0.001
        pf = gp / gl
        bars = t['bars_held'].mean()
        tp = len(t[t['exit_reason'] == 'TP'])
        sl = len(t[t['exit_reason'] == 'SL'])
        fc = len(t[t['exit_reason'] == 'FORCE_CLOSE'])
        rows.append([model, leg, len(t), wr, p, a, pf, bars, tp, sl, fc])

result = pd.DataFrame(rows, columns=['Model', 'Leg', 'Trades', 'WR%', 'PnL', 'Avg', 'PF', 'Bars', 'TP', 'SL', 'FC'])
print(result.to_string(index=False))
print()

# Totals
for model in ['V1_OLS', 'V2_KALMAN']:
    m = df[df['model'] == model]
    print(f'{model} TOTAL: {len(m)} trades, PnL=R${m["pnl"].sum():.0f}')
print()

# SL distance stats
print('SL Distance (pontos):')
for model in ['V1_OLS', 'V2_KALMAN']:
    m = df[df['model'] == model]
    for leg in ['wdo_buy', 'wdo_sell', 'win_buy', 'win_sell']:
        t = m[m['leg'] == leg]
        if len(t) > 0:
            print(f'  {model} {leg}: avg={t["sl_dist"].mean():.1f} med={t["sl_dist"].median():.1f}')
