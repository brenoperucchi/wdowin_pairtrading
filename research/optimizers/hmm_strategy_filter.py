import pandas as pd
import numpy as np

def analyze_hmm_filter():
    print("Analisando impacto do HMM no Setup Definitivo...")
    
    # Load Regimes
    regimes = pd.read_csv("win_m30_regimes.csv")
    regimes['dt'] = pd.to_datetime(regimes['dt'])
    # Ensure dt is the index for fast lookup
    regimes.set_index('dt', inplace=True)
    
    # Load Trades
    trades = pd.read_csv("backtest_win_trades.csv")
    trades['entry_time'] = pd.to_datetime(trades['entry_time'])
    
    # Map each trade to the corresponding M30 Regime
    # Floor the entry_time to the nearest 30min bin
    trades['regime_dt'] = trades['entry_time'].dt.floor('30min')
    
    # Regimes index is datetime, we can map directly
    regime_map = regimes['regime_name'].to_dict()
    trades['regime'] = trades['regime_dt'].map(regime_map)
    
    # Drop trades where regime is NaN (e.g. before the HMM window started)
    trades.dropna(subset=['regime'], inplace=True)
    
    print(f"\nTrades Mapeados: {len(trades)}")
    
    # Results array
    results = []
    
    for direction in ["BUY", "SELL"]:
        for reg in ["BULL", "BEAR", "CHOP"]:
            mask = (trades['dir'] == direction) & (trades['regime'] == reg)
            subset = trades[mask]
            
            n_trades = len(subset)
            if n_trades == 0:
                continue
                
            pnl_arr = subset['pnl'].values
            total_pnl = pnl_arr.sum()
            
            # Max Drawdown for this subset 
            # (Note: This is DD purely inside this regime bucket)
            eq = np.cumsum(pnl_arr)
            pk = np.maximum.accumulate(eq)
            dd = (pk - eq).max() if len(eq) > 0 else 0
            
            win_rate = (len(pnl_arr[pnl_arr > 0]) / n_trades * 100) if n_trades > 0 else 0
            rf = total_pnl / dd if dd > 0 else total_pnl
            
            results.append({
                'Direction': direction,
                'Regime': reg,
                'Trades': n_trades,
                'WinRate(%)': win_rate,
                'PnL': total_pnl,
                'MaxDD': dd,
                'RF': rf
            })
            
    res_df = pd.DataFrame(results)
    
    print("\n--- PERFORMANCE POR REGIME ---")
    print(res_df.to_string(index=False, float_format="%.2f"))
    
    # Test Blocking Strategies
    # What if BUY avoids BEAR? What if SELL avoids BULL? etc
    print("\n\n--- TESTE DE PORTFÓLIO (FILTROS) ---")
    
    # Baseline
    base_eq = np.cumsum(trades['pnl'].values)
    base_pk = np.maximum.accumulate(base_eq)
    base_dd = (base_pk - base_eq).max()
    base_pnl = trades['pnl'].sum()
    base_rf = base_pnl / base_dd if base_dd > 0 else 0
    print(f"BASELINE        -> PnL: R${base_pnl:.0f} | MaxDD: R${base_dd:.0f} | RF: {base_rf:.2f}")
    
    # Heurística Dinâmica: Bloquear buckets que tem PnL negativo ou RF muito fraco
    bad_buckets = res_df[(res_df['PnL'] < 0) | (res_df['RF'] < 2.0)]
    
    if len(bad_buckets) == 0:
        print(">> O sistema é robusto em TODOS os Regimes. Nenhum Filtro HMM é necessário!")
    else:
        print("\nBuckets Tóxicos Identificados (Bloqueios Sugeridos):")
        for _, row in bad_buckets.iterrows():
            print(f"  - Bloquear {row['Direction']} em mercado {row['Regime']} (PnL: {row['PnL']:.1f}, RF: {row['RF']:.2f})")
            
        # Simulate Filtered Timeline
        def is_blocked(row):
            for _, bad in bad_buckets.iterrows():
                if row['dir'] == bad['Direction'] and row['regime'] == bad['Regime']:
                    return True
            return False
            
        trades['blocked'] = trades.apply(is_blocked, axis=1)
        valid_trades = trades[~trades['blocked']]
        
        filt_eq = np.cumsum(valid_trades['pnl'].values)
        if len(filt_eq) > 0:
            filt_pk = np.maximum.accumulate(filt_eq)
            filt_dd = (filt_pk - filt_eq).max()
            filt_pnl = valid_trades['pnl'].sum()
            filt_rf = filt_pnl / filt_dd if filt_dd > 0 else 0
            
            print(f"\nCOMPILADO FINO -> PnL: R${filt_pnl:.0f} | MaxDD: R${filt_dd:.0f} | RF: {filt_rf:.2f}")
            print(f"Ganho Financeiro Absoluto: R${(filt_pnl - base_pnl):.0f}")
            print(f"Redução de Drawdown: R${(base_dd - filt_dd):.0f}")
            print(f"Melhora do RF: {((filt_rf / base_rf) - 1)*100:.1f}%")
        else:
            print("\nFiltro bloqueou 100% dos trades.")

if __name__ == '__main__':
    analyze_hmm_filter()
