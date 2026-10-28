import datetime
import os
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

# Adicionar a pasta raiz ao sys.path para importações locais
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gex.engine.tradingview_exporter import save_walls_to_cache, export_unified_tradingview
from gex.engine.mt5_prices import get_synchronized_etf_ratio

def black_scholes_gamma(S, K, T, sigma, r):
    """
    Calcula a Gamma de Black-Scholes padrão.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * (sigma ** 2)) * T) / (sigma * np.sqrt(T))
    n_d1 = norm.pdf(d1)
    gamma = n_d1 / (S * sigma * np.sqrt(T))
    return gamma

def get_dow_spot_and_chain():
    """
    Obtém o preço spot do Dow Jones (^DJI) e a grade de opções do ETF proxy DIA.
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados do Dow Jones (DIA)...")
    dia_ticker = yf.Ticker("DIA")
    dji_ticker = yf.Ticker("^DJI")
    
    # 1. Buscar preço Spot real do Dow Jones Index
    hist_dji = dji_ticker.history(period="1d")
    if not hist_dji.empty:
        current_spot = hist_dji['Close'].iloc[-1]
    else:
        # Se falhar, usa DIA * 100
        hist_dia = dia_ticker.history(period="1d")
        current_dia_temp = hist_dia['Close'].iloc[-1] if not hist_dia.empty else 390.0
        current_spot = current_dia_temp * 100.0
        
    # 2. Buscar preço Spot do ETF DIA
    hist_dia = dia_ticker.history(period="1d")
    if not hist_dia.empty:
        current_dia = hist_dia['Close'].iloc[-1]
    else:
        current_dia = current_spot / 100.0
        
    print(f"      US30 Spot Index: {current_spot:.2f} | DIA ETF Spot Price: ${current_dia:.2f}")
    
    # 3. Buscar datas de vencimento
    expirations = dia_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para DIA.")
        return None, None, None, None
        
    front_expiry = expirations[0]
    print(f"      Próximo vencimento (Front-Month): {front_expiry}")
    
    # 4. Baixar a grade de opções
    opt_chain = dia_ticker.option_chain(front_expiry)
    calls = opt_chain.calls
    puts = opt_chain.puts
    
    options = []
    
    # Verificar se o Yahoo Finance está com problemas de Open Interest zerado (comum em DTE zero de manhã)
    total_oi_calls = calls['openInterest'].fillna(0).astype(int).gt(0).sum()
    total_oi_puts = puts['openInterest'].fillna(0).astype(int).gt(0).sum()
    total_active_oi = total_oi_calls + total_oi_puts
    
    use_volume_fallback = total_active_oi < 15
    if use_volume_fallback:
        print(f"      [Aviso] Pouco Open Interest detectado ({total_active_oi} contratos). Ativando fallback para Volume!")
    
    # Processar Calls
    for _, row in calls.iterrows():
        oi = int(row['openInterest']) if not pd.isna(row['openInterest']) else 0
        volume = int(row['volume']) if not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
            
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.12
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
        volume = int(row['volume']) if not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
            
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.12
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
    print(f"      {len(df_options)} contratos de opções ativos carregados.")
    return current_spot, current_dia, df_options, front_expiry

def run_dow_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do Dow Jones (DIA).
    """
    print("=" * 60)
    print("  GEX ENGINE - Dow Jones / US30 Pipeline")
    print("=" * 60)
    
    # 1. Carregar dados reais
    current_spot, current_dia, df_options, expiry_str = get_dow_spot_and_chain()
    if df_options is None or df_options.empty:
        print("ERRO: Não foi possível obter os dados de opções.")
        sys.exit(1)
        
    # 2. Calcular tempo de vencimento T e parâmetros
    expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    
    # Dias úteis para expiração
    expiry_days = int(np.busday_count(today.isoformat(), expiry_date.isoformat()))
    expiry_days = max(1, expiry_days)  # Mínimo de 1 dia útil para 0DTE hoje
    T = max(1/252, expiry_days / 252)
    
    r = 0.0515   # US SOFR ~ 5.15%
    q = 0.0190   # Dividend Yield DIA ~ 1.90%
    
    # Fator de Carrego Líquido e Sincronização MT5
    carry_factor = np.exp((r - q) * T)
    fallback_ratio = 100.0 * carry_factor
    conv_ratio, price_dow_mt5, ratio_msg = get_synchronized_etf_ratio(current_dia, "US30", fallback_ratio)
    
    print(f"\n[2/5] Parâmetros de precificação (base 252 dias):")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      r = {r*100:.2f}% | q = {q*100:.2f}% | carry_factor = {carry_factor:.6f}")
    print(f"      Sincronização MT5: {ratio_msg}")
    
    # 3. Agrupar strikes por $1.0 de DIA (equivalente a $100.0 de Spot Dow Jones)
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = (df_options['strike'] / 1.0).round() * 1.0
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_dia, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = black_scholes_gamma(S=current_dia, K=row['strike'], T=T, sigma=row['iv'], r=r)
            gex_contrib = row['oi'] * gamma * (current_dia ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        # Converter strike do DIA para equivalente US30 spot (* 100)
        strike_dow = strike_dia * 100.0
        gex_per_strike[strike_dow] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv,
            'strike_dia': strike_dia
        }
        
    # Selecionar os 16 strikes mais próximos do ATM
    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_spot))
    atm_idx = all_strikes.index(atm_strike)
    
    num_walls = 16
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(all_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    
    selected_strikes = all_strikes[start_idx:end_idx]
    
    # Classificar Width por intensidade GEX
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
            
    # Montar Walls básicas em Dow Jones
    walls_basic = []
    for strike_dow in selected_strikes:
        info = gex_per_strike[strike_dow]
        price_futures = info['strike_dia'] * conv_ratio
        
        walls_basic.append({
            "price": round(price_futures, 2),
            "type": "Wall",
            "width": width_map.get(strike_dow, 1),
            "style": 0,
            "strike_spy": int(info['strike_dia']),  # Armazenar strike do DIA
            "gex": info['gex_net']
        })
        
    # Ordenar
    walls = sorted(walls_basic, key=lambda x: x['price'])
            
    # 4. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip)
    sweep_prices = np.linspace(current_dia * 0.90, current_dia * 1.10, 200)
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in df_options.iterrows():
            gamma = black_scholes_gamma(S=s_hyp, K=row['strike'], T=T, sigma=row['iv'], r=r)
            contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01 * multiplier
            if row['type'] == 'PUT':
                contrib = -contrib
            gex_total += contrib
        gamma_curve.append((s_hyp, gex_total))
        
    gamma_curve_arr = np.array(gamma_curve)
    prices = gamma_curve_arr[:, 0]
    gex_values = gamma_curve_arr[:, 1]
    
    # MaxGamma
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_dia = float(prices[max_gamma_idx])
    max_gamma_dow = max_gamma_dia * conv_ratio
    
    # MinGamma
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_dia = float(prices[min_gamma_idx])
    min_gamma_dow = min_gamma_dia * conv_ratio
    
    # GammaFlip
    flip_dia = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_dia)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_dia = float(cross)
                
    if flip_dia is None:
        flip_dia = current_dia
        
    flip_dow = flip_dia * conv_ratio
    
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_dow, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_dow, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_dow, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_DOW.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_dia >= flip_dia else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_dia >= flip_dia else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_dia >= flip_dia else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - DOW JONES / US30",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    US30 Spot Atual:    {current_spot:.2f}",
        f"    Gamma Flip Point:   {flip_dow:.2f}",
        f"    Regime de Gamma:    {regime}",
        f"    Vies do Dia:        {bias}",
        f"    Dinamica de MM:     {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : US30 {min_gamma_dow:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : US30 {flip_dow:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : US30 {max_gamma_dow:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE DIA   | EQUIVALENTE US30   | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65
    ]
    
    # Adicionar as Walls ordenadas no relatório
    walls_for_report = sorted([w for w in walls if w['type'] == 'Wall'], key=lambda x: x['price'], reverse=True)
    for w in walls_for_report:
        oi_m = w['gex'] / 1e6
        report_lines.append(f"  {w['type']:<10} | ${w['strike_spy']:<12.1f} | {w['price']:<18.2f} | $ {oi_m:>17.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest no ETF proxy DIA.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print(f"      Relatório escrito em: {report_path}")
    
    # 5. Salvar cache para unificação
    save_walls_to_cache(walls, ticker="dow_us30", ref_date=today.isoformat())
    
    # 6. Re-compilar o indicador TradingView unificado
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)
    
    print("\n" + "=" * 60)
    print("  Pipeline Dow/US30 concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_dow_gex_pipeline()
