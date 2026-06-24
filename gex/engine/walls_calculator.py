import numpy as np
import pandas as pd
from .black76 import black76_gamma

def calculate_gex_profile(options_df, current_win, current_ibov, iv=0.20, expiry_days=27, r=0.1425):
    """
    Calcula o perfil GEX completo e gera as Jumba Walls.
    
    Algoritmo (engenharia reversa do Jumba Trader):
    
    1. GRID: 8 Walls em cada strike IBOV (a cada 1000 pts), convertidos para WIN
       pelo fator teorico derivado da taxa de juros (r).
    2. MidWalls: Ponto medio entre cada par de Walls consecutivas (500 pts IBOV).
    3. Width: Proporcional ao |GEX_net| de cada strike.
       - Width 3 = strike com maior GEX (Wall principal)
       - Width 2 = segundo maior GEX (Wall secundaria)
       - Width 1 = demais
    4. Tres niveis especiais derivados da Market Gamma Curve:
       - MaxGamma: preco hipotetico onde gamma positivo e maximo
       - MinGamma: preco hipotetico onde gamma negativo e maximo (mais negativo)
       - GammaFlip: preco onde GEX_net cruza zero
    """
    
    # Filtrar apenas o Vencimento Mais Proximo (Front-Month)
    options_df = options_df.copy()
    front_month = options_df['expiry'].min()
    options_df = options_df[options_df['expiry'] == front_month].copy()
    print(f"  Front-Month Selecionado: {front_month} ({len(options_df)} contratos)")
    
    # --- 1. Fator de conversao IBOV -> WIN Teorico ---
    T = max(1/252, expiry_days / 252)
    factor = (1 + r) ** T
    
    print(f"  Taxa de Juros (r): {r*100:.2f}%")
    print(f"  Fator Teorico IBOV->WIN: {factor:.6f} (MT5 era {current_win/current_ibov:.6f})")
    print(f"  T (anos): {T:.4f}, IV: {iv}")
    
    # --- 2. Calcular GEX por strike IBOV (1000 em 1000) ---
    # Agrupar OI por strike arredondado para o 1000 mais proximo
    options_df['strike_round'] = (options_df['strike'] / 1000).round() * 1000
    
    # GEX por strike IBOV
    gex_per_strike = {}
    
    for strike_ibov, group in options_df.groupby('strike_round'):
        strike_win = strike_ibov * factor
        gex_net = 0.0
        
        for _, row in group.iterrows():
            gamma = black76_gamma(F=current_win, K=strike_win, T=T, sigma=iv)
            gex_contribution = row['oi'] * gamma * (current_win ** 2) * 0.01
            
            if row['type'].upper() == 'PUT':
                gex_contribution = -gex_contribution
                
            gex_net += gex_contribution
            
        gex_per_strike[strike_ibov] = {
            'strike_win': strike_win,
            'gex_net': gex_net,
            'abs_gex': abs(gex_net)
        }
    
    # --- 3. Selecionar os 16 strikes mais proximos do ATM ---
    all_strikes = sorted(gex_per_strike.keys())
    
    # Encontrar o strike ATM (mais proximo do IBOV spot)
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_ibov))
    atm_idx = all_strikes.index(atm_strike)
    
    # Pegar 8 abaixo e 8 acima (16 total) para cobertura ampla
    num_walls = 16
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(all_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    
    selected_strikes = all_strikes[start_idx:end_idx]
    
    print(f"  ATM strike: {atm_strike} | Selected: {selected_strikes[0]}-{selected_strikes[-1]}")
    
    # --- 4. Classificar Width por GEX ---
    strike_gex_list = [(s, gex_per_strike[s]) for s in selected_strikes]
    sorted_by_gex = sorted(strike_gex_list, key=lambda x: x[1]['abs_gex'], reverse=True)
    
    width_map = {}
    for rank, (strike, _) in enumerate(sorted_by_gex):
        if rank == 0:
            width_map[strike] = 3   # Principal
        elif rank <= 2:
            width_map[strike] = 2   # Secundaria
        else:
            width_map[strike] = 1   # Terciaria
    
    # --- 5. Montar Walls ---
    walls = []
    
    for strike_ibov in selected_strikes:
        info = gex_per_strike[strike_ibov]
        walls.append({
            "price": round(info['strike_win'], 3),
            "type": "Wall",
            "color": "#ffffff",  # White
            "width": width_map.get(strike_ibov, 1),
            "style": 0,
            "strike_ibov": int(strike_ibov),
            "gex": float(info['gex_net'])
        })
    
    # --- 6. Montar MidWalls (ponto medio entre Walls consecutivas) ---
    for i in range(len(walls) - 1):
        mid_price = round((walls[i]['price'] + walls[i+1]['price']) / 2, 3)
        walls.append({
            "price": mid_price,
            "type": "MidWall",
            "color": "#808080",  # clGray
            "width": 1,
            "style": 0,
            "gex": 0
        })
    
    # --- 7. Market Gamma Curve: MaxGamma, MinGamma, GammaFlip ---
    # Varrer de 0.80*F ate 1.20*F em 200 pontos
    f_low = current_win * 0.80
    f_high = current_win * 1.20
    sweep_prices = np.linspace(f_low, f_high, 200)
    
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in options_df.iterrows():
            k_win = row['strike'] * factor
            gamma = black76_gamma(F=s_hyp, K=k_win, T=T, sigma=iv)
            contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01
            
            if row['type'].upper() == 'PUT':
                contrib = -contrib
                
            gex_total += contrib
            
        gamma_curve.append((s_hyp, gex_total))
    
    gamma_curve_arr = np.array(gamma_curve)
    prices = gamma_curve_arr[:, 0]
    gex_values = gamma_curve_arr[:, 1]
    
    # MaxGamma: ponto onde GEX positivo e maximo
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_price = float(prices[max_gamma_idx])
    
    # MinGamma: ponto onde GEX negativo e mais negativo
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_price = float(prices[min_gamma_idx])
    
    # GammaFlip: onde GEX cruza zero (mais proximo do ATM)
    flip_price = None
    atm_win = current_ibov * factor
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:  # Mudanca de sinal
            # Interpolacao linear
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - atm_win)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_price = float(cross)
    
    if flip_price is None:
        flip_price = atm_win  # fallback
    
    # Adicionar niveis especiais
    walls.append({
        "price": round(max_gamma_price, 3),
        "type": "MaxGamma",
        "color": "#00ff00",  # clGreen
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_price, 3),
        "type": "MinGamma",
        "color": "#ff0000",  # clRed
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_price, 3),
        "type": "GammaFlip",
        "color": "#ffff00",  # clYellow
        "width": 2,
        "style": 0,
        "gex": 0
    })
    
    print(f"  MaxGamma:  {max_gamma_price:.1f}")
    print(f"  MinGamma:  {min_gamma_price:.1f}")
    print(f"  GammaFlip: {flip_price:.1f}")
    
    return walls
