import datetime
import numpy as np
import pandas as pd
from .black76 import black76_gamma
from .mt5_prices import get_b3_expected_win_contract

def calculate_gex_profile(options_df, current_win, current_ibov, iv=0.20, expiry_days=27, r=0.1425, use_anchored_factor=True, ref_date=None):
    """
    Calcula o perfil GEX completo e gera as Jumba Walls.
    
    Se use_anchored_factor=True: usa o fator sincronizado do contrato WIN ativo (current_win / current_ibov),
    ajustando perfeitamente o carry real até o vencimento do contrato futuro ativo (inclusive nos dias de rolagem).
    Se use_anchored_factor=False: usa o fator teórico dinâmico até o vencimento do contrato WIN.
    """
    if ref_date is None:
        ref_date = datetime.date.today()
    elif isinstance(ref_date, datetime.datetime):
        ref_date = ref_date.date()

    # Filtrar apenas o Vencimento Mais Proximo (Front-Month) com liquidez minima
    MIN_CONTRACTS = 5
    MIN_STRIKES = 3
    options_df = options_df.copy()
    all_expiries = sorted(options_df['expiry'].unique())
    
    front_month = None
    for exp in all_expiries:
        exp_df = options_df[options_df['expiry'] == exp]
        n_contracts = len(exp_df)
        n_strikes = exp_df['strike'].nunique()
        if n_contracts >= MIN_CONTRACTS and n_strikes >= MIN_STRIKES:
            front_month = exp
            break
        else:
            print(f"  [Skip] Vencimento {exp} ignorado: {n_contracts} contratos, {n_strikes} strikes (min: {MIN_CONTRACTS}/{MIN_STRIKES})")
    
    if front_month is None:
        # Fallback: usar o vencimento com mais contratos
        front_month = options_df.groupby('expiry').size().idxmax()
        print(f"  [Fallback] Nenhum vencimento atingiu o minimo. Usando {front_month} (maior OI).")
    
    options_df = options_df[options_df['expiry'] == front_month].copy()
    print(f"  Front-Month Selecionado: {front_month} ({len(options_df)} contratos, {options_df['strike'].nunique()} strikes)")
    
    # --- 1. Fator de conversao IBOV -> WIN (Sincronizado com o Contrato Ativo) ---
    expected_win, _, win_expiry_date = get_b3_expected_win_contract(ref_date)
    win_expiry_days = max(1, int(np.busday_count(ref_date.isoformat(), win_expiry_date.isoformat())))
    T = max(1/252, expiry_days / 252)
    T_win = max(1/252, win_expiry_days / 252)
    
    mt5_factor = (current_win / current_ibov) if (current_win and current_ibov and current_ibov > 0) else None
    theo_win_factor = (1 + r) ** T_win
    
    if use_anchored_factor and mt5_factor is not None and (0.995 <= mt5_factor <= 1.045):
        factor = mt5_factor
        mode_desc = f"SINCRONIZADO MT5 ({expected_win}, {win_expiry_days}d uteis ate {win_expiry_date})"
    else:
        factor = theo_win_factor if not use_anchored_factor else (mt5_factor or theo_win_factor)
        mode_desc = f"TEORICO DI ({expected_win}, {win_expiry_days}d uteis ate {win_expiry_date})"
    
    print(f"  Taxa de Juros (r): {r*100:.2f}% | Modo: {mode_desc}")
    print(f"  Fator IBOV->WIN Aplicado: {factor:.6f} (MT5 Real: {mt5_factor:.6f} | Teorico {win_expiry_days}d: {theo_win_factor:.6f})")
    print(f"  T Opcoes (anos): {T:.4f} ({expiry_days}d uteis), IV: {iv:.4f}")
    
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
    
    # --- 7. Market Gamma Curve (Janela Operacional Local ±4.5%): MaxGamma, MinGamma, GammaFlip ---
    # Restringe a curva Gamma aos strikes dentro da janela operacional ativa (selected_strikes)
    # para que Calls/Puts muito fora do dinheiro (ex: 200k-250k) não distorçam o GammaFlip!
    options_local = options_df[options_df['strike_round'].isin(selected_strikes)].copy()
    if options_local.empty:
        options_local = options_df

    min_wall_win = min(gex_per_strike[s]['strike_win'] for s in selected_strikes)
    max_wall_win = max(gex_per_strike[s]['strike_win'] for s in selected_strikes)
    f_low = max(current_win * 0.955, min_wall_win)
    f_high = min(current_win * 1.045, max_wall_win)
    if f_low >= f_high:
        f_low = current_win * 0.96
        f_high = current_win * 1.04

    sweep_prices = np.linspace(f_low, f_high, 200)
    gamma_curve = []
    call_put_balance_curve = []

    for s_hyp in sweep_prices:
        gex_total = 0.0
        call_gex = 0.0
        put_gex = 0.0
        for _, row in options_local.iterrows():
            k_win = row['strike'] * factor
            gamma = black76_gamma(F=s_hyp, K=k_win, T=T, sigma=iv)
            contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01

            if row['type'].upper() == 'PUT':
                put_gex += contrib
                gex_total -= contrib
            else:
                call_gex += contrib
                gex_total += contrib

        gamma_curve.append((s_hyp, gex_total))
        # Equilíbrio normalizado entre Call GEX local e Put GEX local (para dias unidirecionais)
        call_put_balance_curve.append(call_gex - put_gex)

    gamma_curve_arr = np.array(gamma_curve)
    prices = gamma_curve_arr[:, 0]
    gex_values = gamma_curve_arr[:, 1]

    # MaxGamma: ponto onde GEX positivo (ou menos negativo) é máximo na janela operacional
    max_gamma_idx = int(np.argmax(gex_values))
    max_gamma_price = float(prices[max_gamma_idx])

    # MinGamma: ponto onde GEX negativo é mais intenso na janela operacional
    min_gamma_idx = int(np.argmin(gex_values))
    min_gamma_price = float(prices[min_gamma_idx])

    # GammaFlip: onde GEX cruza zero dentro da janela operacional (mais próximo do preço atual)
    flip_price = None
    atm_win = current_win
    best_flip_dist = float('inf')

    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:  # Mudanca de sinal real na janela operacional
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)

            dist = abs(cross - atm_win)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_price = float(cross)

    if flip_price is None:
        # Quando todos os strikes locais têm o mesmo sinal líquido (ex: domínio de Puts),
        # usa o ponto de inflexão / menor |GEX| entre MinGamma e MaxGamma próximo ao ATM (±2.5%)
        near_mask = (prices >= current_win * 0.975) & (prices <= current_win * 1.025)
        if np.any(near_mask):
            near_prices = prices[near_mask]
            near_abs_gex = np.abs(gex_values[near_mask])
            flip_price = float(near_prices[int(np.argmin(near_abs_gex))])
        else:
            flip_price = float(atm_win)
    
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
        "gex": 0,
        "factor": factor
    })
    
    print(f"  MaxGamma:  {max_gamma_price:.1f}")
    print(f"  MinGamma:  {min_gamma_price:.1f}")
    print(f"  GammaFlip: {flip_price:.1f}")
    
    return walls
