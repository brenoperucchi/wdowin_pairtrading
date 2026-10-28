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

def bs_gamma(S, K, T, sigma, r, q=0.0):
    """
    Calcula a Gamma de Black-Scholes para opções de ETFs/índices.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r - q + 0.5 * (sigma ** 2)) * T) / (sigma * np.sqrt(T))
    n_d1 = norm.pdf(d1)
    gamma = (np.exp(-q * T) * n_d1) / (S * sigma * np.sqrt(T))
    return gamma

def get_uup_spot_and_chain():
    """
    Obtém o preço spot do DXY (Dollar Index) e a grade de opções do ETF proxy UUP
    para o vencimento mais próximo (Front-Month).
    
    NOTA: UUP rastreia o Dollar Index (DXY).
      UUP ≈ DXY * 0.2718 (fator aproximado de escala)
      Para converter strikes do UUP para DXY:
        DXY = UUP * (DXY_spot / UUP_spot)
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados do DXY (UUP)...")
    uup_ticker = yf.Ticker("UUP")
    dxy_ticker = yf.Ticker("DX-Y.NYB")
    
    # 1. Buscar preço Spot real do DXY
    hist_dxy = dxy_ticker.history(period="5d")
    if not hist_dxy.empty:
        current_dxy = hist_dxy['Close'].iloc[-1]
    else:
        current_dxy = dxy_ticker.info.get('regularMarketPrice', 104.00)
        
    # 2. Buscar preço Spot do ETF UUP
    hist_uup = uup_ticker.history(period="1d")
    if not hist_uup.empty:
        current_uup = hist_uup['Close'].iloc[-1]
    else:
        current_uup = uup_ticker.info.get('regularMarketPrice', 28.00)

    # Fator de conversão UUP -> DXY
    conversion_factor = current_dxy / current_uup if current_uup > 0 else 3.70
        
    print(f"      DXY Index: {current_dxy:.2f} | UUP ETF Spot Price: ${current_uup:.2f}")
    print(f"      Fator de Conversão UUP->DXY: {conversion_factor:.4f}")
    
    # 3. Buscar datas de vencimento
    expirations = uup_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para UUP.")
        return None, None, None, None, None
        
    # 4. Baixar a grade de opções (com fallback para evitar vencimentos expirados/vazios)
    opt_chain = None
    front_expiry = None
    
    for expiry in expirations[:3]:
        try:
            chain = uup_ticker.option_chain(expiry)
            calls_active = len(chain.calls)
            puts_active = len(chain.puts)
            if (calls_active + puts_active) > 10:
                opt_chain = chain
                front_expiry = expiry
                break
        except Exception:
            continue
            
    if opt_chain is None:
        front_expiry = expirations[0]
        opt_chain = uup_ticker.option_chain(front_expiry)
        
    print(f"      Próximo vencimento ativo selecionado: {front_expiry}")
    calls = opt_chain.calls
    puts = opt_chain.puts
    
    options = []
    
    # Processar Calls
    for _, row in calls.iterrows():
        oi = int(row['openInterest']) if not pd.isna(row['openInterest']) else 0
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.08
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
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.08
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
    return current_dxy, current_uup, df_options, front_expiry, conversion_factor

def run_dxy_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do DXY / Dollar Index (UUP).
    """
    print("=" * 60)
    print("  GEX ENGINE - DXY / Dollar Index Pipeline")
    print("=" * 60)
    
    # 1. Carregar dados reais
    current_dxy, current_uup, df_options, expiry_str, conv_factor = get_uup_spot_and_chain()
    if df_options is None or df_options.empty:
        print("ERRO: Não foi possível obter os dados de opções.")
        sys.exit(1)
        
    # 2. Calcular tempo de vencimento T e parâmetros
    expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    
    # Dias úteis para expiração (calendário financeiro de 252 dias)
    expiry_days = int(np.busday_count(today.isoformat(), expiry_date.isoformat()))
    expiry_days = max(1, expiry_days)  # Mínimo de 1 dia útil para 0DTE hoje
    T = max(1/252, expiry_days / 252)
    
    # Parâmetros de Black-Scholes (UUP é um ETF em USD, sem dividend yield significativo)
    r = 0.0515   # US SOFR ~ 5.15%
    q = 0.0      # UUP não paga dividendos relevantes
    
    print(f"\n[2/5] Parâmetros de precificação (base 252 dias):")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      r = {r*100:.2f}% | q = {q*100:.2f}% | T = {T:.4f}")
    print(f"      Multiplicador UUP->DXY: {conv_factor:.6f}")
    
    # 3. Agrupar strikes por 0.50 pontos de UUP
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = (df_options['strike'] / 0.50).round() * 0.50
    
    gex_per_strike = {}
    multiplier = 100  # 100 ações por contrato de opção
    
    for strike_uup, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = bs_gamma(S=current_uup, K=row['strike'], T=T, sigma=row['iv'], r=r, q=q)
            gex_contrib = row['oi'] * gamma * (current_uup ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        # Converter strike do UUP para equivalente DXY
        strike_dxy = strike_uup * conv_factor
        gex_per_strike[strike_dxy] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv,
            'strike_uup': strike_uup
        }
        
    # Selecionar strikes próximos do ATM (dentro de ±5% do spot)
    all_strikes = sorted(gex_per_strike.keys())
    lower_bound = current_dxy * 0.95
    upper_bound = current_dxy * 1.05
    nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Fallback: se poucos strikes dentro de ±5%, expandir para ±10%
    if len(nearby_strikes) < 4:
        lower_bound = current_dxy * 0.90
        upper_bound = current_dxy * 1.10
        nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Limitar a no máximo 16 strikes mais próximos do ATM
    num_walls = 16
    nearby_strikes.sort(key=lambda s: abs(s - current_dxy))
    selected_strikes = sorted(nearby_strikes[:num_walls])
    
    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound:.2f}, {upper_bound:.2f}]")
    
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
            
    # Montar Walls básicas em DXY
    walls_basic = []
    for strike_dxy in selected_strikes:
        info = gex_per_strike[strike_dxy]
        
        walls_basic.append({
            "price": round(strike_dxy, 2),
            "type": "Wall",
            "width": width_map.get(strike_dxy, 1),
            "style": 0,
            "strike_spy": round(info['strike_uup'], 2),  # Armazenar strike do UUP
            "gex": info['gex_net']
        })
        
    # Adicionar MidWalls entre as Walls consecutivas
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
    sweep_prices = np.linspace(current_uup * 0.95, current_uup * 1.05, 200)
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in df_options.iterrows():
            gamma = bs_gamma(S=s_hyp, K=row['strike'], T=T, sigma=row['iv'], r=r, q=q)
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
    max_gamma_uup = float(prices[max_gamma_idx])
    max_gamma_dxy = max_gamma_uup * conv_factor
    
    # MinGamma
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_uup = float(prices[min_gamma_idx])
    min_gamma_dxy = min_gamma_uup * conv_factor
    
    # GammaFlip
    flip_uup = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_uup)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_uup = float(cross)
                
    if flip_uup is None:
        flip_uup = current_uup
        
    flip_dxy = flip_uup * conv_factor
    
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_dxy, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_dxy, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_dxy, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_DXY.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_uup >= flip_uup else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_uup >= flip_uup else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_uup >= flip_uup else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - DXY (Dollar Index)",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    DXY Index Atual:   {current_dxy:.2f}",
        f"    UUP ETF Spot:      ${current_uup:.2f}",
        f"    Gamma Flip Point:  DXY {flip_dxy:.2f}",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : DXY {min_gamma_dxy:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : DXY {flip_dxy:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : DXY {max_gamma_dxy:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE UUP   | EQUIVALENTE DXY    | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65
    ]
    
    # Adicionar as Walls ordenadas no relatório
    walls_for_report = sorted([w for w in walls if w['type'] == 'Wall'], key=lambda x: x['price'], reverse=True)
    for w in walls_for_report:
        oi_m = w['gex'] / 1e6
        uup_strike = w.get('strike_spy', 0)
        report_lines.append(f"  {w['type']:<10} | ${uup_strike:<12.2f} | {w['price']:<18.2f} | $ {oi_m:>17.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest no ETF proxy UUP.",
        "UUP rastreia o Dollar Index (DXY). Strikes convertidos para DXY via fator de escala.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print(f"      Relatório escrito em: {report_path}")
    
    # 5. Salvar cache para unificação
    save_walls_to_cache(walls, ticker="dxy_uup", ref_date=today.isoformat())
    
    # 6. Re-compilar o indicador TradingView unificado
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)
    
    print("\n" + "=" * 60)
    print("  Pipeline DXY / Dollar Index concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_dxy_gex_pipeline()
