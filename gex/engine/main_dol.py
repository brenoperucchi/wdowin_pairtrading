import datetime
import os
import sys
import re
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

# Adicionar a pasta raiz ao sys.path para importações locais
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gex.engine.black76 import black76_gamma, implied_volatility_newton_raphson
from gex.engine.b3_dol_parser import get_b3_dol_options_data
from gex.engine.tradingview_exporter import save_walls_to_cache, export_unified_tradingview
from gex.engine.mt5_prices import init_mt5_robust, get_b3_expected_wdo_contract
from gex.engine.walls_calculator import annotate_wall_structure

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

WDO_MONTH_CODES = {
    1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
    7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'
}

def _wdo_symbol_for_expiry(expiry_str):
    """Mapeia uma data de vencimento de opção DOL (ex: '2026-11-02') ao respectivo contrato WDO (ex: 'WDOX26')."""
    d = datetime.date.fromisoformat(expiry_str[:10])
    code = WDO_MONTH_CODES[d.month]
    return f"WDO{code}{str(d.year)[2:]}"

def _detect_active_wdo(ref_date=None):
    """
    Detecta automaticamente o contrato WDO futuro ativo.
    Respeita o calendário oficial da B3: no último dia útil do mês (dia de formação
    da PTAX de liquidação), toda a liquidez rola para o contrato do mês seguinte (m+2),
    evitando que às 07h30 da manhã o detector selecione o contrato que está vencendo.
    """
    expected_wdo, expiring_wdo = get_b3_expected_wdo_contract(ref_date)

    syms = mt5.symbols_get("WDO*")
    if not syms:
        return None

    # 1. Priorizar o contrato esperado pelo calendário oficial de rolagem B3
    if expected_wdo:
        mt5.symbol_select(expected_wdo, True)
        tick_exp = mt5.symbol_info_tick(expected_wdo)
        rates_exp = mt5.copy_rates_from_pos(expected_wdo, mt5.TIMEFRAME_D1, 0, 2)
        if (tick_exp is not None and tick_exp.last > 0) or (rates_exp is not None and len(rates_exp) > 0):
            return expected_wdo

    best = None
    best_score = -1
    now_ts = datetime.datetime.now().timestamp()

    for s in syms:
        # Apenas contratos normais tipo WDOM26, WDOQ26, etc.
        if not re.match(r'^WDO[A-Z]\d{2}$', s.name):
            continue
        # Nunca selecionar o contrato que está fechando PTAX / expirando hoje
        if expiring_wdo and s.name == expiring_wdo:
            continue
        if getattr(s, "expiration_time", 0) > 0 and s.expiration_time < now_ts - 86400:
            continue

        mt5.symbol_select(s.name, True)
        tick = mt5.symbol_info_tick(s.name)
        if tick is None or tick.last == 0:
            continue
        if tick.time > 0 and (now_ts - tick.time) > 10 * 86400:
            continue

        score = int(getattr(s, "session_deals", 0) or 0) * 1_000_000
        if score == 0:
            rates = mt5.copy_rates_from_pos(s.name, mt5.TIMEFRAME_D1, 0, 2)
            if rates is not None and len(rates) > 0:
                score = int(rates[-1]["tick_volume"])
        if score > best_score:
            best_score = score
            best = s.name

    return best

def _get_synced_m5_price(symbol, target_ts=None):
    """Busca o preço M5 sincronizado às 16:55 (ou no mesmo timestamp `target_ts`) para um contrato WDO."""
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 500)
    if rates is not None and len(rates) > 0:
        if target_ts is not None:
            for b in reversed(rates):
                if b[0] == target_ts:
                    return float(b[4]), b[0]
        for b in reversed(rates):
            dt = datetime.datetime.fromtimestamp(b[0], datetime.timezone.utc)
            if dt.hour == 16 and dt.minute == 55:
                return float(b[4]), b[0]
        return float(rates[-1][4]), rates[-1][0]

    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 2)
    if rates_d1 is not None and len(rates_d1) > 0:
        return float(rates_d1[-1][4]), rates_d1[-1][0]

    tick = mt5.symbol_info_tick(symbol)
    if tick and tick.last > 0:
        return float(tick.last), int(tick.time)
    return None, None

def get_wdo_price(ref_date=None):
    """
    Busca o preço M5 sincronizado do contrato WDO ativo no MT5 e também o mapa de preços
    dos demais contratos WDO (para cálculo exato do diferencial de carry na rolagem).
    """
    if not init_mt5_robust(MT5_PATH):
        print("MT5 DOL: Erro ao inicializar. Usando fallback manual.")
        return None, None, {}

    wdo_symbol = _detect_active_wdo(ref_date)
    if wdo_symbol is None:
        mt5.symbol_select("WDO$N", True)
        tick = mt5.symbol_info_tick("WDO$N")
        if tick and tick.last > 0:
            wdo_symbol = "WDO$N"

    if not wdo_symbol:
        print("MT5 DOL: Nenhum contrato WDO ativo encontrado.")
        mt5.shutdown()
        return None, None, {}

    price, target_ts = _get_synced_m5_price(wdo_symbol)
    contract_prices = {}
    if price:
        contract_prices[wdo_symbol] = price

    # Captura preços sincronizados no mesmo instante (16:55) para todos os contratos WDO recentes
    syms = mt5.symbols_get("WDO*") or []
    for s in syms:
        if re.match(r'^WDO[A-Z]\d{2}$', s.name) and s.name != wdo_symbol:
            p_other, _ = _get_synced_m5_price(s.name, target_ts=target_ts)
            if p_other and p_other > 0:
                contract_prices[s.name] = p_other

    mt5.shutdown()
    return price, wdo_symbol, contract_prices

def run_dol_gex_pipeline():
    """
    Executa o pipeline completo de GEX para o Dólar Futuro B3 (DOL / WDO).
    """
    print("=" * 60)
    print("  GEX ENGINE - Dólar Futuro B3 (DOL / WDO) Pipeline")
    print("=" * 60)
    
    today = datetime.date.today()
    
    # 1. Buscar preço atual do WDO do MT5 (sincronizado M5 16:55 + mapa de contratos para carry)
    current_wdo, active_contract, contract_prices = get_wdo_price(today)
    if not current_wdo:
        print("\nMT5 fechado ou indisponível.")
        current_wdo = 5200.0  # Fallback padrão representativo (5.20 BRL)
        active_contract, _ = get_b3_expected_wdo_contract(today)
        contract_prices = {active_contract: current_wdo}
        print(f"Usando fallback WDO: {current_wdo} ({active_contract})")
    else:
        print(f"MT5 WDO Ativo: {active_contract} | Preço Sincronizado: {current_wdo:.2f}")
        if len(contract_prices) > 1:
            prices_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(contract_prices.items()))
            print(f"      Curva Futura WDO (MT5 16:55): {prices_str}")
        
    # 2. Carregar opções do CSV da B3
    df_options = get_b3_dol_options_data()
    
    is_contingency = False
    if df_options.empty:
        print("\n[Aviso] B3 DOL: Nenhuma opção DOL com Open Interest encontrada no CSV.")
        print("        Gerando grade de suportes/resistências institucionais (Contingência R$ 50)...")
        is_contingency = True
        
    if is_contingency:
        # Ponto médio (arredondado para o R$ 50 mais próximo)
        mid_point = round(current_wdo / 50) * 50
        
        # Gerar 8 walls acima e 8 walls abaixo
        walls_basic = []
        for i in range(-8, 9):
            if i == 0:
                continue
            strike_val = mid_point + i * 50
            # Principal mais perto, menor mais longe
            w_width = 3 if abs(i) == 1 else (2 if abs(i) <= 3 else 1)
            
            walls_basic.append({
                "price": float(strike_val),
                "type": "Wall",
                "width": w_width,
                "style": 0,
                "strike_spy": int(strike_val),
                "gex": 0.0
            })
            
        # Adicionar MidWalls
        walls_basic_sorted = sorted(walls_basic, key=lambda x: x['price'])
        walls = []
        
        for i in range(len(walls_basic_sorted)):
            walls.append(walls_basic_sorted[i])
            if i < len(walls_basic_sorted) - 1:
                mid_price = (walls_basic_sorted[i]['price'] + walls_basic_sorted[i+1]['price']) / 2
                walls.append({
                    "price": round(mid_price, 2),
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0
                })
                
        # Níveis especiais simulados
        max_gamma_dol = float(mid_point + 150)
        min_gamma_dol = float(mid_point - 150)
        flip_dol = float(mid_point)
        
        walls.append({
            "price": max_gamma_dol,
            "type": "MaxGamma",
            "width": 3,
            "style": 0,
            "gex": 0.0
        })
        walls.append({
            "price": min_gamma_dol,
            "type": "MinGamma",
            "width": 3,
            "style": 0,
            "gex": 0.0
        })
        walls.append({
            "price": flip_dol,
            "type": "GammaFlip",
            "width": 2,
            "style": 0,
            "gex": 0.0
        })
        
        expiry_date = today + datetime.timedelta(days=10) # data representativa
        expiry_str = expiry_date.strftime("%Y-%m-%d")
        
    else:
        # Filtra apenas vencimentos que não expiraram nem vencem na abertura de hoje (> today_str)
        today_str = today.isoformat()
        df_future_opts = df_options[df_options['expiry'].str[:10] > today_str].copy()
        df_options = df_future_opts if not df_future_opts.empty else df_options[df_options['expiry'].str[:10] >= today_str].copy()
        
        r = 0.1400  # Selic ~14.00%
        iv = 0.12  # IV padrão histórica estável para USD/BRL
        
        # 3. Selecionar série(s) de opções e ajustar pelo diferencial de Carry quando o WDO já rolou
        all_expiries = sorted(df_options['expiry'].unique())
        front_month = all_expiries[0]
        front_wdo_sym = _wdo_symbol_for_expiry(front_month)
        front_exp_date = datetime.date.fromisoformat(front_month[:10])
        front_exp_days = max(1, int(np.busday_count(today_str, front_exp_date.isoformat())))
        
        # Se o contrato futuro ativo (ex: WDOZ26) já rolou além da série que está vencendo (ex: WDOX26, <= 2 dias úteis),
        # incluímos tanto a série que está liquidando PTAX (deslocada pelo carry exato WDOZ26/WDOX26)
        # quanto a nova série do contrato ativo (ex: 2026-12-01, DOLZ26, carry=1.0)!
        selected_expiries = [front_month]
        if front_wdo_sym != active_contract and len(all_expiries) > 1:
            for exp_cand in all_expiries[1:]:
                if _wdo_symbol_for_expiry(exp_cand) == active_contract:
                    selected_expiries.append(exp_cand)
                    break
        
        df_front = df_options[df_options['expiry'].isin(selected_expiries)].copy()
        
        # Calcular carry_ratio e T para cada série incluída
        expiry_meta = {}
        for exp_val in selected_expiries:
            opt_wdo_sym = _wdo_symbol_for_expiry(exp_val)
            exp_dt = datetime.date.fromisoformat(exp_val[:10])
            b_days = max(1, int(np.busday_count(today_str, exp_dt.isoformat())))
            t_val = max(1/252, b_days / 252)
            
            if opt_wdo_sym == active_contract:
                carry_ratio = 1.0
            elif opt_wdo_sym in contract_prices and contract_prices[opt_wdo_sym] > 0:
                carry_ratio = current_wdo / contract_prices[opt_wdo_sym]
            else:
                # Fallback teórico de 1 mês de carry DI (~21 dias úteis)
                carry_ratio = (1 + r) ** (21 / 252)
                
            expiry_meta[exp_val] = {
                "opt_wdo_sym": opt_wdo_sym,
                "expiry_date": exp_dt,
                "expiry_days": b_days,
                "T": t_val,
                "carry_ratio": carry_ratio,
                "carry_pts": current_wdo - (current_wdo / carry_ratio),
            }
            print(
                f"      Série DOL Selecionada: {exp_val[:10]} ({opt_wdo_sym} -> {active_contract}) | "
                f"{len(df_front[df_front['expiry'] == exp_val])} contratos | "
                f"Dias úteis: {b_days} | Carry Ratio: {carry_ratio:.6f} ({expiry_meta[exp_val]['carry_pts']:+.1f} pts)"
            )
            
        # Série principal de referência para o relatório (prioriza a do contrato ativo se disponível)
        primary_exp = selected_expiries[-1]
        expiry_date = expiry_meta[primary_exp]["expiry_date"]
        expiry_days = expiry_meta[primary_exp]["expiry_days"]
        T = expiry_meta[primary_exp]["T"]
        
        print(f"\n[2/5] Parâmetros de Cálculo Black-76:")
        print(f"      Vencimento Ref: {expiry_date} | Dias úteis: {expiry_days}")
        print(f"      Taxa Selic (r): {r*100:.2f}% | Volatilidade Padrão (IV): {iv*100:.2f}%")
        
        # Mapear cada opção para a escala do contrato WDO ativo via carry_ratio
        df_front['carry_ratio'] = df_front['expiry'].map(lambda e: expiry_meta[e]['carry_ratio'])
        df_front['T_opt'] = df_front['expiry'].map(lambda e: expiry_meta[e]['T'])
        df_front['strike_wdo'] = df_front['strike'] * df_front['carry_ratio']
        
        # 5. Tentativa de IV Dinâmico via ATM Call do MT5
        try:
            if init_mt5_robust():
                atm_idx_opt = (df_front['strike_wdo'] - current_wdo).abs().idxmin()
                atm_strike_raw = df_front.loc[atm_idx_opt, 'strike']
                atm_calls = df_front[(df_front['strike'] == atm_strike_raw) & (df_front['type'] == 'CALL')]
                if not atm_calls.empty:
                    atm_row = atm_calls.iloc[0]
                    atm_ticker = atm_row['ticker']
                    mt5.symbol_select(atm_ticker, True)
                    
                    c_market = None
                    tick_opt = mt5.symbol_info_tick(atm_ticker)
                    if tick_opt and tick_opt.last > 0:
                        c_market = tick_opt.last
                    else:
                        rates_d1 = mt5.copy_rates_from_pos(atm_ticker, mt5.TIMEFRAME_D1, 0, 5)
                        if rates_d1 is not None and len(rates_d1) > 0:
                            c_market = float(rates_d1[-1][4])
                            
                    if c_market and c_market > 0:
                        dynamic_iv = implied_volatility_newton_raphson(
                            C_market=c_market,
                            F=current_wdo,
                            K=float(atm_row['strike_wdo']),
                            T=float(atm_row['T_opt']),
                            r=r,
                            is_call=True,
                            initial_guess=0.12
                        )
                        if 0.02 <= dynamic_iv <= 0.60:
                            iv = dynamic_iv
                            print(f"      [MT5] Opção ATM {atm_ticker} capturada: R$ {c_market:.2f} -> IV Calculada: {iv*100:.2f}%")
                mt5.shutdown()
        except Exception as e:
            print(f"      Aviso: Não foi possível obter IV dinâmico ({e}). Usando padrão 12%.")
            
        # 6. Agrupar strikes na escala do contrato ativo (de 10 em 10 pts originais ajustados pelo carry) e calcular GEX
        print(f"\n[3/5] Calculando GEX por Strike DOL (Escala {active_contract})...")
        # Mantém agrupamento de 10 em 10 pts validado no backtest OOS (evita micro-walls 25/75)
        df_front['strike_base_10'] = (df_front['strike'] / 10.0).round() * 10.0
        df_front['strike_round'] = ((df_front['strike_base_10'] * df_front['carry_ratio']) * 2).round() / 2
        
        gex_per_strike = {}
        multiplier = 50
        
        for strike_round, group in df_front.groupby('strike_round'):
            gex_net = 0.0
            base_strike_rep = int(round(float(group['strike_base_10'].iloc[0])))
            
            for _, row in group.iterrows():
                gamma = black76_gamma(F=current_wdo, K=float(row['strike_wdo']), T=float(row['T_opt']), sigma=iv)
                gex_contrib = row['oi'] * gamma * (current_wdo ** 2) * 0.01 * multiplier
                if row['type'] == 'PUT':
                    gex_contrib = -gex_contrib
                gex_net += gex_contrib
                
            gex_per_strike[strike_round] = {
                'gex_net': gex_net,
                'abs_gex': abs(gex_net),
                'base_strike': base_strike_rep
            }
            
        # 16 strikes mais próximos do ATM na escala do contrato WDO ativo
        all_strikes = sorted(gex_per_strike.keys())
        atm_strike = min(all_strikes, key=lambda s: abs(s - current_wdo))
        atm_idx = all_strikes.index(atm_strike)
        
        num_walls = 16
        start_idx = max(0, atm_idx - num_walls // 2)
        end_idx = min(len(all_strikes), start_idx + num_walls)
        start_idx = max(0, end_idx - num_walls)
        
        selected_strikes = all_strikes[start_idx:end_idx]
        
        # Classificar Width por GEX
        strike_gex_list = [(s, gex_per_strike[s]) for s in selected_strikes]
        sorted_by_gex = sorted(strike_gex_list, key=lambda x: x[1]['abs_gex'], reverse=True)
        
        width_map = {}
        for rank, (strike, _) in enumerate(sorted_by_gex):
            if rank == 0:
                width_map[strike] = 3
            elif rank <= 2:
                width_map[strike] = 2
            else:
                width_map[strike] = 1
                
        # Montar as Walls
        walls_basic = []
        for strike_round in selected_strikes:
            info = gex_per_strike[strike_round]
            walls_basic.append({
                "price": round(float(strike_round), 2),
                "type": "Wall",
                "width": width_map.get(strike_round, 1),
                "style": 0,
                "strike_spy": int(info['base_strike']),
                "gex": info['gex_net']
            })
            
        # Adicionar MidWalls (arredondadas para 0.25 / 0.50 WDO)
        walls_basic_sorted = sorted(walls_basic, key=lambda x: x['price'])
        walls = []
        for i in range(len(walls_basic_sorted)):
            walls.append(walls_basic_sorted[i])
            if i < len(walls_basic_sorted) - 1:
                mid_price = (walls_basic_sorted[i]['price'] + walls_basic_sorted[i+1]['price']) / 2
                walls.append({
                    "price": round(mid_price, 2),
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0
                })
                
        # 7. Calcular Market Gamma Curve na Janela Operacional Local (selected_strikes)
        df_local = df_front[df_front['strike_round'].isin(selected_strikes)].copy()
        if df_local.empty:
            df_local = df_front

        def _compute_gamma_curve(df_src, prices_arr):
            curve_vals = np.empty(len(prices_arr), dtype=float)
            strikes_arr = df_src['strike_wdo'].to_numpy(dtype=float)
            t_arr = df_src['T_opt'].to_numpy(dtype=float)
            oi_arr = df_src['oi'].to_numpy(dtype=float)
            signs_arr = np.where(df_src['type'].to_numpy() == 'PUT', -1.0, 1.0)
            for idx_p, s_hyp in enumerate(prices_arr):
                gex_total = 0.0
                for k_val, t_val, oi_val, sgn in zip(strikes_arr, t_arr, oi_arr, signs_arr):
                    gamma = black76_gamma(F=float(s_hyp), K=float(k_val), T=float(t_val), sigma=iv)
                    gex_total += sgn * oi_val * gamma * (float(s_hyp) ** 2) * 0.01 * multiplier
                curve_vals[idx_p] = gex_total
            return curve_vals

        def _find_nearest_zero_cross(p_arr, g_arr):
            cross_price = None
            best_dist = float('inf')
            for i in range(len(g_arr) - 1):
                if g_arr[i] * g_arr[i + 1] < 0:
                    x0, x1 = p_arr[i], p_arr[i + 1]
                    y0, y1 = g_arr[i], g_arr[i + 1]
                    cross = x0 - y0 * (x1 - x0) / (y1 - y0)
                    dist = abs(cross - current_wdo)
                    if dist < best_dist:
                        best_dist = dist
                        cross_price = float(cross)
            return cross_price

        min_wall_wdo = float(min(selected_strikes))
        max_wall_wdo = float(max(selected_strikes))
        f_low = max(current_wdo * 0.96, min_wall_wdo)
        f_high = min(current_wdo * 1.04, max_wall_wdo)
        if f_low >= f_high:
            f_low = current_wdo * 0.97
            f_high = current_wdo * 1.03

        prices = np.linspace(f_low, f_high, 200)
        gex_values = _compute_gamma_curve(df_local, prices)

        max_gamma_idx = int(np.argmax(gex_values))
        max_gamma_dol = float(prices[max_gamma_idx])
        max_gamma_val = float(gex_values[max_gamma_idx])

        flip_dol = _find_nearest_zero_cross(prices, gex_values)
        need_wide = (
            flip_dol is None
            or float(np.min(gex_values)) >= 0.0
            or float(np.max(gex_values)) <= 0.0
        )

        prices_wide = None
        gex_wide = None
        if need_wide:
            wide_low = float(df_front['strike_wdo'].min())
            wide_high = float(df_front['strike_wdo'].max())
            if wide_low < wide_high:
                prices_wide = np.linspace(wide_low, wide_high, 600)
                gex_wide = _compute_gamma_curve(df_front, prices_wide)

        if flip_dol is None and gex_wide is not None:
            flip_dol = _find_nearest_zero_cross(prices_wide, gex_wide)

        if flip_dol is None:
            gex_spot = float(_compute_gamma_curve(df_front, [current_wdo])[0])
            flip_dol = min_wall_wdo if gex_spot >= 0.0 else max_wall_wdo

        if float(np.min(gex_values)) < 0.0:
            min_gamma_idx = int(np.argmin(gex_values))
            min_gamma_dol = float(prices[min_gamma_idx])
            min_gamma_val = float(gex_values[min_gamma_idx])
        elif gex_wide is not None and float(np.min(gex_wide)) < 0.0:
            min_wide_idx = int(np.argmin(gex_wide))
            min_gamma_dol = float(prices_wide[min_wide_idx])
            min_gamma_val = float(gex_wide[min_wide_idx])
        else:
            below_mask = prices <= max_gamma_dol
            sub_prices = prices[below_mask] if np.any(below_mask) else prices
            sub_gex = gex_values[below_mask] if np.any(below_mask) else gex_values
            sub_idx = int(np.argmin(sub_gex))
            min_gamma_dol = float(sub_prices[sub_idx])
            min_gamma_val = float(sub_gex[sub_idx])

        # Adicionar níveis especiais
        walls.append({
            "price": round(max_gamma_dol, 2),
            "type": "MaxGamma",
            "width": 3,
            "style": 0,
            "gex": max_gamma_val
        })
        
        walls.append({
            "price": round(min_gamma_dol, 2),
            "type": "MinGamma",
            "width": 3,
            "style": 0,
            "gex": min_gamma_val
        })
        
        walls.append({
            "price": round(flip_dol, 2),
            "type": "GammaFlip",
            "width": 2,
            "style": 0,
            "gex": 0.0
        })

        annotate_wall_structure(walls, current_wdo, band_pct=0.035)
    
    # 8. Exportar Relatório e Caches
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_DOL.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_wdo >= flip_dol else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_wdo >= flip_dol else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_wdo >= flip_dol else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E MAGIC WALLS WALLS - DOLAR FUTURO (DOL / WDO)",
        f"  Vencimento de Referencia: {expiry_date} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    Dólar Futuro Atual: {current_wdo:.2f} ({active_contract})",
        f"    Gamma Flip Point:   {flip_dol:.2f}",
        f"    Regime de Gamma:    {regime}",
        f"    Vies do Dia:        {bias}",
        f"    Dinamica de MM:     {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Aceleracao)    : DOL {min_gamma_dol:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : DOL {flip_dol:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : DOL {max_gamma_dol:.2f}",
        "",
        "[+] MAGIC WALLS WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE REAL':12s} | {'EQUIVALENTE DOL':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65
    ]
    
    display_walls = [w for w in walls if w['type'] == 'Wall']
    for w in sorted(display_walls, key=lambda x: x['price'], reverse=True):
        width_stars = "*" * w['width']
        type_str = "WALL " + width_stars
        gex_m = w['gex'] / 1_000_000
        # Exibe em formato real 5.120, etc.
        real_strike = w['strike_spy'] / 1000
        report_lines.append(f"  {type_str:10s} | ${real_strike:<11.3f} | DOL {w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Magic Walls Walls acima mapeiam o posicionamento do Open Interest das opcoes na B3.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    report_content = "\n".join(report_lines)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
        
    print(f"      Relatório escrito em: {report_path}")
    
    # Salvar cache e atualizar TradingView
    tv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "magicwalls_tradingview.pine")
    try:
        save_walls_to_cache(walls, ticker="usd_brl", ref_date=today, current_price=current_wdo)
        export_unified_tradingview(output_path=tv_path)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")
        
    # Exportar para o ProfitChart (Nelogica)
    print("\n      Exportando para ProfitChart...")
    try:
        from .profit_exporter import deploy_to_nelogica
        deploy_to_nelogica(walls, ticker="DOL", current_price=current_wdo)
    except Exception as e:
        print(f"      Aviso: Falha no deploy Nelogica ({e})")
        
    # Exportar para o MetaTrader 5 (Common\Files e mt5\Files)
    try:
        from .mt5_exporter import export_wdo_to_mt5_common
        export_wdo_to_mt5_common(walls, ref_date=today, session_date=today, current_wdo=current_wdo)
    except Exception as e:
        print(f"      Aviso: Falha no export MT5 WDO ({e})")

    print("\n" + "=" * 60)
    print("  Pipeline Dólar concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_dol_gex_pipeline()
