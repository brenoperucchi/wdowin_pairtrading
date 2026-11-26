import datetime
import numpy as np
import pandas as pd
from .black76 import black76_gamma
from .mt5_prices import get_b3_expected_win_contract

def calculate_gex_profile(options_df, current_win, current_ibov, iv=0.20, expiry_days=27, r=0.1425, use_anchored_factor=True, ref_date=None):
    """
    Calcula o perfil GEX completo e gera as Magic Walls Walls.
    
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
        factor = theo_win_factor
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
    
    # --- 3. Selecionar os 20 strikes mais proximos do ATM ---
    all_strikes = sorted(gex_per_strike.keys())
    
    # Encontrar o strike ATM (mais proximo do IBOV spot)
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_ibov))
    atm_idx = all_strikes.index(atm_strike)
    
    # Pegar 10 abaixo e 10 acima (20 total) para cobertura ampla
    num_walls = 20
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
    # e expande a varredura sob demanda para evitar artefatos de borda quando não há mudança de sinal local.
    options_local = options_df[options_df['strike_round'].isin(selected_strikes)].copy()
    if options_local.empty:
        options_local = options_df

    def _eval_curve(df_src, p_arr):
        F_sw = p_arr[:, None]
        k_arr = (df_src['strike'].to_numpy(dtype=float) * factor)[None, :]
        oi_arr = df_src['oi'].to_numpy(dtype=float)
        type_arr = df_src['type'].str.upper().to_numpy()
        is_put = (type_arr == 'PUT')

        d1 = (np.log(F_sw / k_arr) + 0.5 * (iv ** 2) * T) / (iv * np.sqrt(T))
        gamma_mat = np.exp(-0.5 * d1 ** 2) / (np.sqrt(2 * np.pi) * F_sw * iv * np.sqrt(T))
        contrib_mat = oi_arr[None, :] * gamma_mat * (F_sw ** 2) * 0.01

        call_gex = np.sum(contrib_mat * (~is_put[None, :]), axis=1)
        put_gex = np.sum(contrib_mat * is_put[None, :], axis=1)
        return call_gex - put_gex

    def _nearest_zero_cross(p_arr, g_arr, spot):
        cross_price = None
        best_dist = float('inf')
        for i in range(len(g_arr) - 1):
            if g_arr[i] * g_arr[i + 1] < 0:
                x0, x1 = p_arr[i], p_arr[i + 1]
                y0, y1 = g_arr[i], g_arr[i + 1]
                cross = x0 - y0 * (x1 - x0) / (y1 - y0)
                dist = abs(cross - spot)
                if dist < best_dist:
                    best_dist = dist
                    cross_price = float(cross)
        return cross_price

    min_wall_win = min(gex_per_strike[s]['strike_win'] for s in selected_strikes)
    max_wall_win = max(gex_per_strike[s]['strike_win'] for s in selected_strikes)
    f_low = max(current_win * 0.955, min_wall_win)
    f_high = min(current_win * 1.045, max_wall_win)
    if f_low >= f_high:
        f_low = current_win * 0.96
        f_high = current_win * 1.04

    prices = np.linspace(f_low, f_high, 200)
    gex_values = _eval_curve(options_local, prices)
    atm_win = current_win

    flip_price = _nearest_zero_cross(prices, gex_values, atm_win)
    need_wide = (
        flip_price is None
        or float(np.min(gex_values)) >= 0.0
        or float(np.max(gex_values)) <= 0.0
    )

    prices_wide = None
    gex_wide = None
    if need_wide:
        w_low = min(float(options_df['strike'].min() * factor), current_win * 0.85)
        w_high = max(float(options_df['strike'].max() * factor), current_win * 1.15)
        if w_low < w_high:
            prices_wide = np.linspace(w_low, w_high, 600)
            gex_wide = _eval_curve(options_df, prices_wide)

    if flip_price is None and gex_wide is not None:
        flip_price = _nearest_zero_cross(prices_wide, gex_wide, atm_win)

    if flip_price is None:
        g_spot = float(_eval_curve(options_df, np.array([atm_win], dtype=float))[0])
        flip_price = float(min_wall_win if g_spot >= 0.0 else max_wall_win)

    # MaxGamma: pico positivo real (local -> expandido -> acima do flip)
    if float(np.max(gex_values)) > 0.0:
        max_gamma_idx = int(np.argmax(gex_values))
        max_gamma_price = float(prices[max_gamma_idx])
        max_gamma_val = float(gex_values[max_gamma_idx])
    elif gex_wide is not None and float(np.max(gex_wide)) > 0.0:
        max_wide_idx = int(np.argmax(gex_wide))
        max_gamma_price = float(prices_wide[max_wide_idx])
        max_gamma_val = float(gex_wide[max_wide_idx])
    else:
        above_mask = prices >= flip_price
        sub_p = prices[above_mask] if np.any(above_mask) else prices
        sub_g = gex_values[above_mask] if np.any(above_mask) else gex_values
        sub_idx = int(np.argmax(sub_g))
        max_gamma_price = float(sub_p[sub_idx])
        max_gamma_val = float(sub_g[sub_idx])

    # MinGamma: vale negativo real (local -> expandido -> abaixo do MaxGamma)
    if float(np.min(gex_values)) < 0.0:
        min_gamma_idx = int(np.argmin(gex_values))
        min_gamma_price = float(prices[min_gamma_idx])
        min_gamma_val = float(gex_values[min_gamma_idx])
    elif gex_wide is not None and float(np.min(gex_wide)) < 0.0:
        min_wide_idx = int(np.argmin(gex_wide))
        min_gamma_price = float(prices_wide[min_wide_idx])
        min_gamma_val = float(gex_wide[min_wide_idx])
    else:
        below_mask = prices <= max_gamma_price
        sub_p = prices[below_mask] if np.any(below_mask) else prices
        sub_g = gex_values[below_mask] if np.any(below_mask) else gex_values
        sub_idx = int(np.argmin(sub_g))
        min_gamma_price = float(sub_p[sub_idx])
        min_gamma_val = float(sub_g[sub_idx])
    
    # Adicionar niveis especiais
    walls.append({
        "price": round(max_gamma_price, 3),
        "type": "MaxGamma",
        "color": "#00ff00",  # clGreen
        "width": 3,
        "style": 0,
        "gex": max_gamma_val
    })
    
    walls.append({
        "price": round(min_gamma_price, 3),
        "type": "MinGamma",
        "color": "#ff0000",  # clRed
        "width": 3,
        "style": 0,
        "gex": min_gamma_val
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

    annotate_wall_structure(walls, current_win, band_pct=0.045)

    print(f"  MaxGamma:  {max_gamma_price:.1f}")
    print(f"  MinGamma:  {min_gamma_price:.1f}")
    print(f"  GammaFlip: {flip_price:.1f}")
    
    return walls


def annotate_wall_structure(walls, spot_price, band_pct=0.045):
    """
    Anota metadados estruturais nas Walls sem alterar `type`, `price` ou `width` oficial:
    - `gex_side`: 'CALL' (gex > 0), 'PUT' (gex < 0) ou 'NEUTRAL'
    - `is_local_call_wall`: maior barreira de Call dentro da banda operacional
    - `is_local_put_wall`: maior barreira de Put dentro da banda operacional
    - `is_strike_flip`: transição estrutural Put->Call mais próxima do preço
    - `local_wall_tier`: 'PRIMARY', 'SECONDARY' ou 'STANDARD'
    """
    if not walls:
        return walls

    wall_items = sorted(
        [w for w in walls if isinstance(w, dict) and w.get("type") == "Wall" and float(w.get("price", 0.0) or 0.0) > 0],
        key=lambda w: float(w.get("price", 0.0)),
    )
    if not wall_items:
        return walls

    def _get_gex(w):
        if w.get("gex_raw") is not None:
            return float(w.get("gex_raw") or 0.0)
        return float(w.get("gex") or 0.0)

    for w in wall_items:
        g_val = _get_gex(w)
        w["gex_side"] = "CALL" if g_val > 0 else ("PUT" if g_val < 0 else "NEUTRAL")
        w["is_local_call_wall"] = False
        w["is_local_put_wall"] = False
        w["is_strike_flip"] = False
        w["local_wall_tier"] = "STANDARD"

    spot = float(spot_price or 0.0)
    if spot > 0:
        low_b = spot * (1.0 - band_pct)
        high_b = spot * (1.0 + band_pct)
        local_walls = [w for w in wall_items if low_b <= float(w["price"]) <= high_b]
    else:
        local_walls = list(wall_items)
    if not local_walls:
        local_walls = list(wall_items)

    call_candidates = [w for w in local_walls if _get_gex(w) > 0] or [w for w in wall_items if _get_gex(w) > 0]
    if call_candidates:
        dom_call = max(call_candidates, key=lambda w: _get_gex(w))
        dom_call["is_local_call_wall"] = True

    put_candidates = [w for w in local_walls if _get_gex(w) < 0] or [w for w in wall_items if _get_gex(w) < 0]
    if put_candidates:
        dom_put = min(put_candidates, key=lambda w: _get_gex(w))
        dom_put["is_local_put_wall"] = True

    max_abs_gex = max((abs(_get_gex(w)) for w in wall_items), default=0.0)
    max_local_abs_gex = max((abs(_get_gex(w)) for w in local_walls), default=max_abs_gex)

    best_flip_wall = None
    best_flip_dist = float("inf")
    for i in range(len(wall_items) - 1):
        w_prev, w_curr = wall_items[i], wall_items[i + 1]
        g_prev, g_curr = _get_gex(w_prev), _get_gex(w_curr)
        if g_prev * g_curr < 0 and max_abs_gex > 0 and max(abs(g_prev), abs(g_curr)) >= 0.05 * max_abs_gex:
            mid_p = (float(w_prev["price"]) + float(w_curr["price"])) / 2.0
            dist = abs(mid_p - spot) if spot > 0 else i
            if dist < best_flip_dist:
                best_flip_dist = dist
                best_flip_wall = w_curr if g_curr > 0 else w_prev
    if best_flip_wall is not None:
        best_flip_wall["is_strike_flip"] = True

    for w in wall_items:
        w_width = int(w.get("width", 1) or 1)
        abs_g = abs(_get_gex(w))
        if w_width >= 3 or w["is_local_call_wall"] or w["is_local_put_wall"]:
            w["local_wall_tier"] = "PRIMARY"
        elif w_width == 2 or w["is_strike_flip"] or (max_local_abs_gex > 0 and abs_g >= 0.35 * max_local_abs_gex):
            w["local_wall_tier"] = "SECONDARY"
        else:
            w["local_wall_tier"] = "STANDARD"

    return walls
