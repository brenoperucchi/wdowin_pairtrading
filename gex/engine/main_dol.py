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
from gex.engine.mt5_prices import init_mt5_robust

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

def _detect_active_wdo():
    """
    Detecta automaticamente o contrato WDO futuro ativo com maior volume.
    """
    syms = mt5.symbols_get("WDO*")
    if not syms:
        return None
        
    best = None
    best_score = -1
    
    for s in syms:
        # Apenas contratos normais tipo WDOM26, WDOQ26, etc.
        if not re.match(r'^WDO[A-Z]\d{2}$', s.name):
            continue
            
        mt5.symbol_select(s.name, True)
        tick = mt5.symbol_info_tick(s.name)
        if tick is None or tick.last == 0:
            continue
            
        score = s.session_deals
        if score > best_score:
            best_score = score
            best = s.name
            
    return best

def get_wdo_price():
    """
    Busca o preço atual do contrato ativo WDO do MT5.
    """
    if not init_mt5_robust(MT5_PATH):
        print("MT5 DOL: Erro ao inicializar. Usando fallback manual.")
        return None, None
        
    wdo_symbol = _detect_active_wdo()
    if wdo_symbol is None:
        mt5.symbol_select("WDO$N", True)
        tick = mt5.symbol_info_tick("WDO$N")
        if tick and tick.last > 0:
            wdo_symbol = "WDO$N"
            
    if not wdo_symbol:
        print("MT5 DOL: Nenhum contrato WDO ativo encontrado.")
        mt5.shutdown()
        return None, None
        
    tick = mt5.symbol_info_tick(wdo_symbol)
    price = tick.last if tick else None
    
    # Pegar timestamp
    bar_time = datetime.datetime.now()
    
    mt5.shutdown()
    return price, wdo_symbol

def run_dol_gex_pipeline():
    """
    Executa o pipeline completo de GEX para o Dólar Futuro B3 (DOL / WDO).
    """
    print("=" * 60)
    print("  GEX ENGINE - Dólar Futuro B3 (DOL / WDO) Pipeline")
    print("=" * 60)
    
    today = datetime.date.today()
    
    # 1. Buscar preço atual do WDO do MT5
    current_wdo, active_contract = get_wdo_price()
    if not current_wdo:
        print("\nMT5 fechado ou indisponível.")
        # Solicitar preço manual ou usar fallback de data
        current_wdo = 5200.0  # Fallback padrão representativo (5.20 BRL)
        active_contract = "WDOM26"
        print(f"Usando fallback WDO: {current_wdo} ({active_contract})")
    else:
        print(f"MT5 WDO Activo: {active_contract} | Preço: {current_wdo:.2f}")
        
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
        # Filtra apenas vencimentos que não expiraram (>= hoje)
        today_str = today.isoformat()
        df_options = df_options[df_options['expiry'].str[:10] >= today_str].copy()
        
        # 3. Filtrar pelo vencimento mais próximo
        front_month = df_options['expiry'].min()
        df_front = df_options[df_options['expiry'] == front_month].copy()
        print(f"      Front-Month DOL Selecionado: {front_month} ({len(df_front)} contratos)")
        
        # 4. Parâmetros temporais
        expiry_date = datetime.datetime.strptime(front_month[:10], "%Y-%m-%d").date()
        expiry_str = expiry_date.strftime("%Y-%m-%d")
        
        # Dias úteis
        expiry_days = int(np.busday_count(today.isoformat(), expiry_date.isoformat()))
        expiry_days = max(1, expiry_days)
        T = max(1/252, expiry_days / 252)
        
        r = 0.1425  # Selic ~14.25%
        iv = 0.12  # IV padrão histórica estável para USD/BRL
        
        print(f"\n[2/5] Parâmetros de Cálculo Black-76:")
        print(f"      Vencimento: {expiry_date} | Dias úteis: {expiry_days}")
        print(f"      Taxa Selic (r): {r*100:.2f}% | Volatilidade Padrão (IV): {iv*100:.2f}%")
        
        # 5. Tentativa de IV Dinâmico via ATM Call do MT5
        try:
            if init_mt5_robust():
                atm_strike = min(df_front['strike'].unique(), key=lambda s: abs(s - current_wdo))
                atm_calls = df_front[(df_front['strike'] == atm_strike) & (df_front['type'] == 'CALL')]
                if not atm_calls.empty:
                    atm_ticker = atm_calls.iloc[0]['ticker']
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
                            K=atm_strike,
                            T=T,
                            r=r,
                            is_call=True,
                            initial_guess=0.12
                        )
                        if 0.02 <= dynamic_iv <= 0.60:
                            iv = dynamic_iv
                            print(f"      [MT5] Opção ATM {atm_ticker} capturada: R$ {c_market:.2f} -> IV Calculada: {iv*100:.2f}%")
                            print(f"      Opção ATM {atm_ticker} -> Preço MT5: R$ {c_market:.2f} -> IV Calculada: {iv*100:.2f}%")
                mt5.shutdown()
        except Exception as e:
            print(f"      Aviso: Não foi possível obter IV dinâmico ({e}). Usando padrão 12%.")
            
        # 6. Agrupar strikes e calcular GEX
        print(f"\n[3/5] Calculando GEX por Strike DOL...")
        df_front['strike_round'] = (df_front['strike'] / 10).round() * 10
        
        gex_per_strike = {}
        multiplier = 50
        
        for strike_round, group in df_front.groupby('strike_round'):
            gex_net = 0.0
            
            for _, row in group.iterrows():
                gamma = black76_gamma(F=current_wdo, K=row['strike'], T=T, sigma=iv)
                gex_contrib = row['oi'] * gamma * (current_wdo ** 2) * 0.01 * multiplier
                if row['type'] == 'PUT':
                    gex_contrib = -gex_contrib
                gex_net += gex_contrib
                
            gex_per_strike[strike_round] = {
                'gex_net': gex_net,
                'abs_gex': abs(gex_net)
            }
            
        # strikes mais próximos do ATM
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
                "price": round(strike_round, 2),
                "type": "Wall",
                "width": width_map.get(strike_round, 1),
                "style": 0,
                "strike_spy": int(strike_round),
                "gex": info['gex_net']
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
                
        # 7. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip)
        sweep_prices = np.linspace(current_wdo * 0.90, current_wdo * 1.10, 200)
        gamma_curve = []
        
        for s_hyp in sweep_prices:
            gex_total = 0.0
            for _, row in df_front.iterrows():
                gamma = black76_gamma(F=s_hyp, K=row['strike'], T=T, sigma=iv)
                contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01 * multiplier
                if row['type'] == 'PUT':
                    contrib = -contrib
                gex_total += contrib
            gamma_curve.append((s_hyp, gex_total))
            
        gamma_curve_arr = np.array(gamma_curve)
        prices = gamma_curve_arr[:, 0]
        gex_values = gamma_curve_arr[:, 1]
        
        max_gamma_idx = np.argmax(gex_values)
        max_gamma_dol = float(prices[max_gamma_idx])
        
        min_gamma_idx = np.argmin(gex_values)
        min_gamma_dol = float(prices[min_gamma_idx])
        
        flip_dol = None
        best_flip_dist = float('inf')
        
        for i in range(len(gex_values) - 1):
            if gex_values[i] * gex_values[i+1] < 0:
                x0, x1 = prices[i], prices[i+1]
                y0, y1 = gex_values[i], gex_values[i+1]
                cross = x0 - y0 * (x1 - x0) / (y1 - y0)
                dist = abs(cross - current_wdo)
                if dist < best_flip_dist:
                    best_flip_dist = dist
                    flip_dol = float(cross)
                    
        if flip_dol is None:
            flip_dol = current_wdo
            
        # Adicionar níveis especiais
        walls.append({
            "price": round(max_gamma_dol, 2),
            "type": "MaxGamma",
            "width": 3,
            "style": 0,
            "gex": float(gex_values[max_gamma_idx])
        })
        
        walls.append({
            "price": round(min_gamma_dol, 2),
            "type": "MinGamma",
            "width": 3,
            "style": 0,
            "gex": float(gex_values[min_gamma_idx])
        })
        
        walls.append({
            "price": round(flip_dol, 2),
            "type": "GammaFlip",
            "width": 2,
            "style": 0,
            "gex": 0.0
        })
    
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
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - DOLAR FUTURO (DOL / WDO)",
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
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE REAL':12s} | {'EQUIVALENTE DOL':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65
    ]
    
    display_walls = [w for w in walls if w['type'] == 'Wall']
    for w in sorted(display_walls, key=lambda x: x['strike_spy'], reverse=True):
        width_stars = "*" * w['width']
        type_str = "WALL " + width_stars
        gex_m = w['gex'] / 1_000_000
        # Exibe em formato real 5.120, etc.
        real_strike = w['strike_spy'] / 1000
        report_lines.append(f"  {type_str:10s} | ${real_strike:<11.3f} | DOL {w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest das opcoes na B3.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    report_content = "\n".join(report_lines)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
        
    print(f"      Relatório escrito em: {report_path}")
    
    # Salvar cache e atualizar TradingView
    tv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    try:
        save_walls_to_cache(walls, ticker="usd_brl", ref_date=today)
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
        
    print("\n" + "=" * 60)
    print("  Pipeline Dólar concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_dol_gex_pipeline()
