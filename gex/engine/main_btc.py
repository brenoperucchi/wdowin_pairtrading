import datetime
import os
import sys
import re
import numpy as np
import pandas as pd
import requests
from scipy.stats import norm

# Adicionar a pasta raiz ao sys.path para importações locais
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gex.engine.tradingview_exporter import save_walls_to_cache, export_unified_tradingview

def black_scholes_gamma(S, K, T, sigma, r=0.05):
    """
    Calcula a Gamma de Black-Scholes para opções sobre Spot (estilo ações/cripto).
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    n_prime_d1 = norm.pdf(d1)
    gamma = n_prime_d1 / (S * sigma * np.sqrt(T))
    return gamma

def get_deribit_btc_options():
    """
    Consome a API da Deribit e retorna o preço spot do BTC e a grade de opções.
    """
    print("[1/5] Conectando à API da Deribit para buscar dados de opções de BTC...")
    url = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option"
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        res_data = response.json()
    except Exception as e:
        print(f"      ERRO ao conectar com a Deribit: {e}")
        return None, None, None
        
    results = res_data.get('result', [])
    if not results:
        print("      ERRO: Nenhum dado de opção retornado pela Deribit.")
        return None, None, None
        
    print(f"      {len(results)} instrumentos de opções brutos retornados.")
    
    # Extrair Spot Price (usar o preço do índice do primeiro contrato válido)
    current_btc = None
    for r in results:
        idx_val = r.get('underlying_price')
        if idx_val and idx_val > 1000:
            current_btc = float(idx_val)
            break
            
    if not current_btc:
        current_btc = 70000.0  # Fallback padrão
        
    print(f"      BTC Index Spot Price: ${current_btc:.2f}")
    
    # Processar os instrumentos
    options = []
    month_map = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
    }
    
    for r in results:
        name = r.get('instrument_name', '')
        # Formato esperado: BTC-29MAY26-70000-C
        match = re.match(r"^BTC-(\d+)([A-Z]{3})(\d+)-(\d+)-([CP])$", name)
        if not match:
            continue
            
        day_str, month_str, year_str, strike_str, type_char = match.groups()
        
        day = int(day_str)
        month = month_map.get(month_str, 1)
        year = int("20" + year_str)
        
        expiry_date = datetime.date(year, month, day)
        expiry_str = expiry_date.strftime("%Y-%m-%d")
        
        strike = float(strike_str)
        opt_type = "CALL" if type_char == "C" else "PUT"
        
        oi = float(r.get('open_interest', 0))
        iv = float(r.get('mark_iv', 0.50)) / 100.0  # Deribit retorna IV em % inteira (ex: 50.0 para 50%)
        if iv <= 0:
            iv = 0.50  # Fallback
            
        if oi > 0:
            options.append({
                "ticker": name,
                "type": opt_type,
                "strike": strike,
                "expiry": expiry_str,
                "oi": oi,
                "iv": iv
            })
            
    df_options = pd.DataFrame(options)
    
    if df_options.empty:
        print("      ERRO: Nenhuma opção parseada com Open Interest ativo.")
        return None, None, None
        
    # Encontrar o vencimento ativo mais próximo
    all_expiries = sorted(df_options['expiry'].unique())
    front_expiry = all_expiries[0]
    print(f"      Próximo vencimento ativo (Front-Month): {front_expiry}")
    
    df_front = df_options[df_options['expiry'] == front_expiry].copy()
    print(f"      {len(df_front)} contratos de opções do vencimento mais próximo ativos carregados.")
    
    return current_btc, df_front, front_expiry

def run_btc_gex_pipeline():
    """
    Executa o pipeline completo do Bitcoin GEX.
    """
    print("=" * 60)
    print("  GEX ENGINE - Bitcoin / BTC Pipeline")
    print("=" * 60)
    
    # 1. Obter dados da API Deribit
    current_btc, df_options, expiry_str = get_deribit_btc_options()
    if df_options is None or df_options.empty:
        print("ERRO: Dados Deribit inválidos.")
        sys.exit(1)
        
    # 2. Parâmetros temporais (Opções Cripto rodam 24/7/365 de forma contínua)
    expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    expiry_days = (expiry_date - today).days
    expiry_days = max(1, expiry_days)  # Pelo menos 1 dia para hoje
    T = max(1/365, expiry_days / 365)
    
    r = 0.0515  # SOFR ~5.15% como proxy internacional
    
    print(f"\n[2/5] Parâmetros de Cálculo Cripto (365 Dias/Ano):")
    print(f"      Vencimento: {expiry_str} | Dias corridos: {expiry_days}")
    print(f"      Taxa (r): {r*100:.2f}% | T: {T:.4f}")
    
    # 3. Agrupar strikes a cada $1,000
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = (df_options['strike'] / 1000).round() * 1000
    
    gex_per_strike = {}
    
    for strike_round, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            # Modelo Black-Scholes para cripto Spot
            gamma = black_scholes_gamma(S=current_btc, K=row['strike'], T=T, sigma=row['iv'], r=r)
            
            # GEX = OI * Gamma * Spot^2 * 0.01 (Multiplicador de contrato é 1 BTC na Deribit)
            gex_contrib = row['oi'] * gamma * (current_btc ** 2) * 0.01
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        gex_per_strike[strike_round] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv
        }
        
    # strikes mais próximos do ATM
    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_btc))
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
            "strike_spy": int(strike_round),  # reusar strike_spy como nome genérico para o exporter
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
            
    # 4. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip)
    sweep_prices = np.linspace(current_btc * 0.90, current_btc * 1.10, 200)
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in df_options.iterrows():
            gamma = black_scholes_gamma(S=s_hyp, K=row['strike'], T=T, sigma=row['iv'], r=r)
            contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01
            if row['type'] == 'PUT':
                contrib = -contrib
            gex_total += contrib
        gamma_curve.append((s_hyp, gex_total))
        
    gamma_curve_arr = np.array(gamma_curve)
    prices = gamma_curve_arr[:, 0]
    gex_values = gamma_curve_arr[:, 1]
    
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_btc = float(prices[max_gamma_idx])
    
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_btc = float(prices[min_gamma_idx])
    
    flip_btc = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_btc)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_btc = float(cross)
                
    if flip_btc is None:
        flip_btc = current_btc
        
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_btc, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_btc, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_btc, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Caches
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_BTC.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_btc >= flip_btc else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_btc >= flip_btc else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_btc >= flip_btc else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - BITCOIN / BTC-USD",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    Bitcoin Spot Atual: ${current_btc:.2f}",
        f"    Gamma Flip Point:   ${flip_btc:.2f}",
        f"    Regime de Gamma:    {regime}",
        f"    Vies do Dia:        {bias}",
        f"    Dinamica de MM:     {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : BTC ${min_gamma_btc:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : BTC ${flip_btc:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : BTC ${max_gamma_btc:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE BTC':12s} | {'EQUIVALENTE USD':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65
    ]
    
    display_walls = [w for w in walls if w['type'] == 'Wall']
    for w in sorted(display_walls, key=lambda x: x['strike_spy'], reverse=True):
        width_stars = "*" * w['width']
        type_str = "WALL " + width_stars
        gex_m = w['gex'] / 1_000_000
        report_lines.append(f"  {type_str:10s} | ${w['strike_spy']:<11.2f} | BTC ${w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest das opcoes na Deribit.",
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
        save_walls_to_cache(walls, ticker="btc_usd", ref_date=today)
        export_unified_tradingview(output_path=tv_path)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")
        
    print("\n" + "=" * 60)
    print("  Pipeline Bitcoin concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_btc_gex_pipeline()
