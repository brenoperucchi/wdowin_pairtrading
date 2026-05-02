import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from core.config import SYMBOL_A, TIMEFRAME, MT5_PATH

def init_mt5():
    mt5.initialize(path=MT5_PATH)

def fetch(symbol, n):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    return np.array([r[4] for r in rates], dtype=float)

def calc_nwe_with_bands(prices, bandwidth, lookback, mult_mae=3.0):
    n = len(prices)
    nwe = np.zeros(n)
    mae = np.zeros(n)
    
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            nwe[t] = prices[t]
            continue
        i_arr = np.arange(lb + 1)
        w = np.exp(-(i_arr * i_arr) / (2 * bandwidth * bandwidth))
        p_slice = prices[t - lb : t + 1][::-1]
        nwe[t] = np.sum(p_slice * w) / np.sum(w)
        
    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            continue
        nwe_slice = nwe[t - lb : t + 1]
        p_slice = prices[t - lb : t + 1]
        err = np.abs(p_slice - nwe_slice)
        mae[t] = np.mean(err) * mult_mae
        
    upper = nwe + mae
    lower = nwe - mae
    return nwe, upper, lower

def main():
    init_mt5()
    # Pega apenas os ultimos 2 dias de pregao (~250 barras M5) para ficar legível
    win = fetch(SYMBOL_A, 250)
    mt5.shutdown()

    bw, lb = 8, 20
    nwe, upper, lower = calc_nwe_with_bands(win, bw, lb, mult_mae=3.0)
    
    threshold_pct = 0.14
    # A margem de 0.14% pra cima da lower e pra baixo da upper
    lower_limit = lower * (1 + threshold_pct / 100.0)
    upper_limit = upper * (1 - threshold_pct / 100.0)
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14, 7))
    
    x = np.arange(len(win))
    
    # Preco
    ax.plot(x, win, color='white', linewidth=2, label="Preço (WIN)")
    
    # NWE Central
    # Vamos colorir de verde qd sobe e vermelho qd desce
    is_up = np.zeros(len(nwe), dtype=bool)
    is_up[1:] = nwe[1:] >= nwe[:-1]
    is_up[0] = True
    
    for i in range(1, len(win)):
        color = 'mediumspringgreen' if is_up[i] else 'crimson'
        ax.plot(x[i-1:i+1], nwe[i-1:i+1], color=color, linewidth=2)
        
    # Bandas MAE (como no dashboard)
    ax.plot(x, upper, color='crimson', linestyle='--', alpha=0.5, label="Banda NWE Superior (MAE)")
    ax.plot(x, lower, color='mediumspringgreen', linestyle='--', alpha=0.5, label="Banda NWE Inferior (MAE)")
    
    # Threshold de 0.14% (A zona onde o trade é permitido)
    ax.plot(x, upper_limit, color='yellow', linestyle=':', linewidth=2, label=f"Limite de Venda (-{threshold_pct}%)")
    ax.plot(x, lower_limit, color='cyan', linestyle=':', linewidth=2, label=f"Limite de Compra (+{threshold_pct}%)")
    
    # Zonas de Permissão (Fill)
    # Entre upper_limit e upper -> Venda permitida
    ax.fill_between(x, upper_limit, upper, color='yellow', alpha=0.2, label="ZONA PERMITIDA VENDA")
    # Entre lower e lower_limit -> Compra permitida
    ax.fill_between(x, lower, lower_limit, color='cyan', alpha=0.2, label="ZONA PERMITIDA COMPRA")

    ax.set_title(f"Visualização do Filtro NWE {threshold_pct}% (Apenas trades DENTRO das faixas coloridas são aceitos)", fontsize=14)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.15)
    
    plt.tight_layout()
    os.makedirs(".planning/docs/assets", exist_ok=True)
    out_path = ".planning/docs/assets/nwe_visual_filter.png"
    plt.savefig(out_path, dpi=150)
    print(f"Grafico salvo em: {out_path}")

if __name__ == "__main__":
    main()
