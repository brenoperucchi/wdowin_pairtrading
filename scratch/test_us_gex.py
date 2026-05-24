import datetime
import os
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

# Adicionar a pasta raiz ao path para poder importar da engine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gex.engine.black76 import black76_gamma

def get_spy_spot_and_chain():
    """
    Obtém o preço spot atual do SPY e a grade de opções completa
    para o vencimento mais próximo (normalmente 0DTE ou 1DTE).
    """
    print("[1] Conectando ao Yahoo Finance para buscar dados de SPY...")
    spy_ticker = yf.Ticker("SPY")
    
    # 1. Buscar preço Spot do SPY
    # Tenta usar o histórico de hoje para obter o preço mais recente
    hist = spy_ticker.history(period="1d")
    if not hist.empty:
        current_spy = hist['Close'].iloc[-1]
    else:
        # Fallback para fast_info
        current_spy = spy_ticker.info.get('regularMarketPrice', 530.0) # Fallback padrão se falhar
        
    print(f"    SPY Spot Price: ${current_spy:.2f} | Equivalente SPX/ES ~ {current_spy * 10:.2f}")
    
    # 2. Buscar datas de vencimento
    expirations = spy_ticker.options
    if not expirations:
        print("    ERRO: Nenhuma data de vencimento encontrada para SPY.")
        return None, None, None
        
    # Selecionar o vencimento mais próximo (Front-Month ou 0DTE/1DTE)
    front_expiry = expirations[0]
    print(f"    Próximo vencimento identificado (Front-Month): {front_expiry}")
    
    # 3. Baixar a grade de opções
    opt_chain = spy_ticker.option_chain(front_expiry)
    calls = opt_chain.calls
    puts = opt_chain.puts
    
    options = []
    
    # Processar Calls
    for _, row in calls.iterrows():
        oi = int(row['openInterest']) if not pd.isna(row['openInterest']) else 0
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.20
        if oi > 0:
            options.append({
                "ticker": row['contractSymbol'],
                "type": "CALL",
                "strike": float(row['strike']),
                "expiry": front_expiry,
                "oi": oi,
                "iv": iv
            })
            
    # Processar Puts
    for _, row in puts.iterrows():
        oi = int(row['openInterest']) if not pd.isna(row['openInterest']) else 0
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.20
        if oi > 0:
            options.append({
                "ticker": row['contractSymbol'],
                "type": "PUT",
                "strike": float(row['strike']),
                "expiry": front_expiry,
                "oi": oi,
                "iv": iv
            })
            
    df_options = pd.DataFrame(options)
    print(f"    {len(df_options)} contratos de opções de SPY ativos carregados.")
    return current_spy, df_options, front_expiry

def run_us_gex_simulation():
    """
    Executa a simulação de GEX e Jumba Walls para o SPY / SP500.
    """
    print("=" * 60)
    print("  SIMULAÇÃO DE GEX & JUMBA WALLS - MERCADO AMERICANO (SPY)")
    print("=" * 60)
    
    # 1. Carregar dados do mercado real
    current_spy, df_options, expiry_str = get_spy_spot_and_chain()
    if df_options is None or df_options.empty:
        print("Erro: Não foi possível obter os dados de opções.")
        return
        
    # 2. Calcular tempo para o vencimento (T)
    # yyyy-mm-dd
    expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    
    # Calcular dias úteis
    expiry_days = int(np.busday_count(today.isoformat(), expiry_date.isoformat()))
    expiry_days = max(1, expiry_days) # Pelo menos 1 dia útil para 0DTE hoje
    T = max(1/252, expiry_days / 252)
    
    # Taxa de juros livre de risco nos EUA (SOFR aprox. 5.15%)
    r = 0.0515
    # Dividend Yield do S&P 500 (aprox. 1.30%)
    q = 0.0130
    
    print("\n[2] Parâmetros de Simulação:")
    print(f"    Dias úteis para o vencimento: {expiry_days} dia(s)")
    print(f"    T (anos): {T:.4f}")
    print(f"    Taxa de Juros Livre de Risco (r): {r*100:.2f}%")
    print(f"    Dividend Yield do S&P 500 (q):    {q*100:.2f}%")
    
    # Fator de conversão spot para futuro (Custo de Carrego Líquido)
    # No caso do SPY, para plotar no Futuro ES, podemos aproximar ES = SPY_Spot * 10 * carry_factor
    carry_factor = np.exp((r - q) * T)
    print(f"    Fator Spot-Futuro Carry: {carry_factor:.6f}")
    
    # 3. Calcular GEX por Strike (agrupado por $1 em SPY, equivalente a 10 pts no SPX)
    print("\n[3] Calculando GEX por Strike...")
    
    # Agrupar strikes a cada $1.00 de SPY (equivalente a 10 pontos de SPX/ES)
    df_options['strike_round'] = (df_options['strike'] / 1.0).round() * 1.0
    
    gex_per_strike = {}
    
    # Para o SPY, o multiplicador de contrato padrão é 100
    multiplier = 100
    
    for strike_spy, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        
        # Obter volatilidade média das opções do strike ou usar a média do grupo
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            # Calcular Gamma (utilizando Black-76 sobre o spot SPY como base forward)
            gamma = black76_gamma(F=current_spy, K=row['strike'], T=T, sigma=row['iv'])
            
            # GEX em dólares de exposição de ações: 
            # GEX = OI * Gamma * Spot^2 * 0.01 * Multiplier
            gex_contrib = row['oi'] * gamma * (current_spy ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        gex_per_strike[strike_spy] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv
        }
        
    # --- 4. Selecionar os 16 strikes mais próximos do ATM ---
    all_strikes = sorted(gex_per_strike.keys())
    
    # Strike ATM
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_spy))
    atm_idx = all_strikes.index(atm_strike)
    
    # Pegar 8 abaixo e 8 acima (16 total)
    num_walls = 16
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(all_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    
    selected_strikes = all_strikes[start_idx:end_idx]
    
    # --- 5. Classificar o Width por GEX ---
    strike_gex_list = [(s, gex_per_strike[s]) for s in selected_strikes]
    sorted_by_gex = sorted(strike_gex_list, key=lambda x: x[1]['abs_gex'], reverse=True)
    
    width_map = {}
    for rank, (strike, _) in enumerate(sorted_by_gex):
        if rank == 0:
            width_map[strike] = 3   # Principal
        elif rank <= 2:
            width_map[strike] = 2   # Secundária
        else:
            width_map[strike] = 1   # Terciária
            
    # --- 6. Montar as Walls e equivalentes no ES / SPX ---
    walls = []
    for strike_spy in selected_strikes:
        info = gex_per_strike[strike_spy]
        
        # Preço projetado do futuro ES equivalente (SPY * 10 * carry_factor)
        price_es = strike_spy * 10 * carry_factor
        
        walls.append({
            "strike_spy": strike_spy,
            "price_es": round(price_es, 2),
            "gex": info['gex_net'],
            "width": width_map.get(strike_spy, 1),
            "type": "Wall"
        })
        
    # --- 7. Simular Curva Gamma e achar Max/Min Gamma e GammaFlip ---
    # Varrer faixa de 0.90 * current_spy até 1.10 * current_spy
    sweep_prices = np.linspace(current_spy * 0.90, current_spy * 1.10, 200)
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in df_options.iterrows():
            gamma = black76_gamma(F=s_hyp, K=row['strike'], T=T, sigma=row['iv'])
            contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01 * multiplier
            if row['type'] == 'PUT':
                contrib = -contrib
            gex_total += contrib
        gamma_curve.append((s_hyp, gex_total))
        
    gamma_curve_arr = np.array(gamma_curve)
    prices = gamma_curve_arr[:, 0]
    gex_values = gamma_curve_arr[:, 1]
    
    # MaxGamma: ponto de pico de gamma positivo
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_spy = float(prices[max_gamma_idx])
    max_gamma_es = max_gamma_spy * 10 * carry_factor
    
    # MinGamma: ponto de pico de gamma negativo (mais negativo)
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_spy = float(prices[min_gamma_idx])
    min_gamma_es = min_gamma_spy * 10 * carry_factor
    
    # GammaFlip: onde cruza o zero mais perto do ATM
    flip_spy = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_spy)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_spy = float(cross)
                
    if flip_spy is None:
        flip_spy = current_spy # fallback
        
    flip_es = flip_spy * 10 * carry_factor
    
    # --- 8. Exibir Relatório de Jumba Walls de SP500 / ES ---
    # Tenta forçar o terminal a aceitar UTF-8 no Windows para evitar quebras
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    print("\n" + "=" * 60)
    print("  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - S&P 500 / ES")
    print(f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}")
    print("=" * 60)
    
    print(f"\n[+] STATUS DO MERCADO (REGIME GEX):")
    print(f"    SPY Spot Atual:    ${current_spy:.2f}  (Equiv. ES: ~{current_spy * 10:.1f})")
    print(f"    Gamma Flip Point:  ${flip_spy:.2f}  (Equiv. ES:  {flip_es:.2f})")
    
    if current_spy >= flip_spy:
        regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)"
        bias = "ALTA / LATERALIZACAO"
        desc = "Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas. Favorece dias direcionais calmos com suporte nas Walls principais."
    else:
        regime = "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
        bias = "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
        desc = "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta. Isso amplifica oscilacoes bruscas e gera picos de volatilidade extrema."
        
    print(f"    Regime de Gamma:   {regime}")
    print(f"    Vies do Dia:       {bias}")
    print(f"    Dinamica de MM:    {desc}\n")
    
    print("[+] NIVEIS CRITICOS DA CURVA GAMMA:")
    print(f"    [-] MIN GAMMA (Piso de Aceleracao da Queda) : ES {min_gamma_es:.2f} | SPY ${min_gamma_spy:.2f}")
    print(f"    [o] GAMMA FLIP (Divisor de Aguas / Pivot)  : ES {flip_es:.2f} | SPY ${flip_spy:.2f}")
    print(f"    [+] MAX GAMMA (Teto Gravitacional/Compress): ES {max_gamma_es:.2f} | SPY ${max_gamma_spy:.2f}\n")
    
    print("[+] JUMBA WALLS DETECTADAS ( Strikes Proximos ):")
    print("-" * 65)
    print(f"  {'TIPO':10s} | {'STRIKE SPY':12s} | {'EQUIVALENTE ES':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}")
    print("-" * 65)
    
    # Separar as walls para ordenar e mostrar de forma mais legível
    for w in sorted(walls, key=lambda x: x['strike_spy'], reverse=True):
        width_stars = "*" * w['width']
        type_str = "WALL " + width_stars
        gex_m = w['gex'] / 1_000_000
        
        # Dar cor ou ênfase visual dependendo do GEX
        print(f"  {type_str:10s} | ${w['strike_spy']:<11.2f} | ES {w['price_es']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")
        
    print("-" * 65)
    print("Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest das opcoes.")
    print("Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.")
    print("=" * 60)

if __name__ == "__main__":
    run_us_gex_simulation()
