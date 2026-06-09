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

def garman_kohlhagen_gamma(S, K, T, sigma, rd, rf):
    """
    Calcula a Gamma de Garman-Kohlhagen (1983) para opções de moedas.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (rd - rf + 0.5 * (sigma ** 2)) * T) / (sigma * np.sqrt(T))
    n_d1 = norm.pdf(d1)
    gamma = (np.exp(-rf * T) * n_d1) / (S * sigma * np.sqrt(T))
    return gamma

def get_fxy_spot_and_chain():
    """
    Obtém o preço spot do USDJPY e a grade de opções do ETF proxy FXY
    para o vencimento mais próximo (Front-Month).
    
    NOTA: FXY rastreia o Yen japonês vs USD (inversamente correlacionado ao USDJPY).
      FXY sobe quando o Yen fortalece (USDJPY cai).
      Para converter strikes do FXY para USDJPY:
        USDJPY_equiv = strike_fxy * (USDJPY_spot / FXY_spot)
      GEX de Calls no FXY = pressão de QUEDA no USDJPY (inversão).
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados de USD/JPY (FXY)...")
    fxy_ticker = yf.Ticker("FXY")
    jpy_ticker = yf.Ticker("JPY=X")
    
    # 1. Buscar preço Spot real do USDJPY
    hist_jpy = jpy_ticker.history(period="1d")
    if not hist_jpy.empty:
        current_usdjpy = hist_jpy['Close'].iloc[-1]
    else:
        current_usdjpy = jpy_ticker.info.get('regularMarketPrice', 150.00)
        
    # 2. Buscar preço Spot do ETF FXY
    hist_fxy = fxy_ticker.history(period="1d")
    if not hist_fxy.empty:
        current_fxy = hist_fxy['Close'].iloc[-1]
    else:
        current_fxy = fxy_ticker.info.get('regularMarketPrice', 57.00)
    
    # Fator de conversão FXY -> USDJPY
    conv_factor = current_usdjpy / current_fxy if current_fxy > 0 else 2.79
        
    print(f"      USDJPY Spot Rate: {current_usdjpy:.3f} | FXY ETF Spot Price: ${current_fxy:.2f}")
    print(f"      Fator de Conversão FXY->USDJPY: {conv_factor:.4f}")
    
    # 3. Buscar datas de vencimento
    expirations = fxy_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para FXY.")
        return None, None, None, None, None
        
    # 4. Baixar a grade de opções (com fallback para evitar vencimentos expirados/vazios)
    opt_chain = None
    front_expiry = None
    
    for expiry in expirations[:3]:
        try:
            chain = fxy_ticker.option_chain(expiry)
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
        opt_chain = fxy_ticker.option_chain(front_expiry)
        
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
    return current_usdjpy, current_fxy, df_options, front_expiry, conv_factor

def run_jpy_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do USD/JPY (FXY).
    
    IMPORTANTE: FXY é inversamente correlacionado ao USDJPY.
    - Call no FXY = aposta na alta do Yen = queda do USDJPY
    - Put no FXY = aposta na queda do Yen = alta do USDJPY
    
    Para converter a perspectiva dos dealers para USDJPY,
    INVERTEMOS o sinal do GEX: Calls viram negativas e Puts viram positivas
    no referencial do USDJPY.
    """
    print("=" * 60)
    print("  GEX ENGINE - USD/JPY Pipeline")
    print("=" * 60)
    
    # 1. Carregar dados reais
    current_usdjpy, current_fxy, df_options, expiry_str, conv_factor = get_fxy_spot_and_chain()
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
    
    # Parâmetros de Garman-Kohlhagen
    rd = 0.0515   # US SOFR (Taxa Doméstica USD) ~ 5.15%
    rf = 0.0050   # BoJ rate (Taxa Estrangeira Yen) ~ 0.50%
    
    print(f"\n[2/5] Parâmetros de Garman-Kohlhagen (base 252 dias):")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      rd (USD) = {rd*100:.2f}% | rf (JPY) = {rf*100:.2f}% | T = {T:.4f}")
    
    # 3. Agrupar strikes por 0.20 pontos de FXY (equivalente a ~0.56 pontos de USDJPY)
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = (df_options['strike'] / 0.20).round() * 0.20
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_fxy, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = garman_kohlhagen_gamma(S=current_fxy, K=row['strike'], T=T, sigma=row['iv'], rd=rd, rf=rf)
            # GEX em dólares
            gex_contrib = row['oi'] * gamma * (current_fxy ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        # Converter strike do FXY para equivalente USDJPY usando fator de escala
        # FXY é inversamente correlacionado ao USDJPY, mas a escala é proporcional
        strike_jpy = strike_fxy * conv_factor
        
        # INVERTER o sinal do GEX para o referencial USDJPY
        # (Call no FXY = Yen sobe = USDJPY cai, então GEX positivo no FXY vira negativo no USDJPY)
        gex_per_strike[strike_jpy] = {
            'gex_net': -gex_net,  # Sinal invertido!
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv,
            'strike_fxy': strike_fxy
        }
        
    # Selecionar strikes próximos do ATM (dentro de ±10% do spot USDJPY para ter número de strikes adequado)
    all_strikes = sorted(gex_per_strike.keys())
    lower_bound = current_usdjpy * 0.90
    upper_bound = current_usdjpy * 1.10
    nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Fallback: se poucos strikes dentro de ±10%, expandir para ±15%
    if len(nearby_strikes) < 4:
        lower_bound = current_usdjpy * 0.85
        upper_bound = current_usdjpy * 1.15
        nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Limitar a no máximo 16 strikes mais próximos do ATM
    num_walls = 16
    nearby_strikes.sort(key=lambda s: abs(s - current_usdjpy))
    selected_strikes = sorted(nearby_strikes[:num_walls])
    
    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound:.3f}, {upper_bound:.3f}]")
    
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
            
    # Montar Walls básicas em USDJPY
    walls_basic = []
    for strike_jpy in selected_strikes:
        info = gex_per_strike[strike_jpy]
        
        walls_basic.append({
            "price": round(strike_jpy, 3),
            "type": "Wall",
            "width": width_map.get(strike_jpy, 1),
            "style": 0,
            "strike_spy": round(info['strike_fxy'], 2),  # Armazenar strike do FXY
            "gex": info['gex_net']
        })
        
    # Adicionar MidWalls entre as Walls consecutivas
    walls_basic_sorted = sorted(walls_basic, key=lambda x: x['price'])
    walls = []
    
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]['price']
            w2 = walls_basic_sorted[i+1]['price']
            diff = w2 - w1
            
            target_spacing = 0.10  # 10 pips (0.10 Yen)
            num_steps = int(round(diff / target_spacing))
            num_steps = max(2, num_steps)
            
            step = diff / num_steps
            for j in range(1, num_steps):
                mid_price = w1 + j * step
                walls.append({
                    "price": round(mid_price, 3),
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0
                })
            
    # 4. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip)
    sweep_prices = np.linspace(current_fxy * 0.90, current_fxy * 1.10, 200)
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in df_options.iterrows():
            gamma = garman_kohlhagen_gamma(S=s_hyp, K=row['strike'], T=T, sigma=row['iv'], rd=rd, rf=rf)
            contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01 * multiplier
            if row['type'] == 'PUT':
                contrib = -contrib
            gex_total += contrib
        # Inverter para referencial USDJPY
        gamma_curve.append((s_hyp, -gex_total))
        
    gamma_curve_arr = np.array(gamma_curve)
    prices_fxy = gamma_curve_arr[:, 0]
    gex_values = gamma_curve_arr[:, 1]
    
    # MaxGamma (no referencial USDJPY)
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_fxy = float(prices_fxy[max_gamma_idx])
    max_gamma_jpy = max_gamma_fxy * conv_factor
    
    # MinGamma
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_fxy = float(prices_fxy[min_gamma_idx])
    min_gamma_jpy = min_gamma_fxy * conv_factor
    
    # GammaFlip
    flip_fxy = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices_fxy[i], prices_fxy[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_fxy)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_fxy = float(cross)
                
    if flip_fxy is None:
        flip_fxy = current_fxy
        
    flip_jpy = flip_fxy * conv_factor
    
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_jpy, 3),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_jpy, 3),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_jpy, 3),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_JPY.txt")
    
    # Regime baseado no referencial USDJPY: acima do flip = gamma positivo = lateraliza
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_usdjpy >= flip_jpy else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_usdjpy >= flip_jpy else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_usdjpy >= flip_jpy else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - USD/JPY",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    USDJPY Spot Atual:  {current_usdjpy:.3f}",
        f"    FXY ETF Spot:       ${current_fxy:.2f}",
        f"    Fator de Conv.:     {conv_factor:.4f}",
        f"    Gamma Flip Point:   {flip_jpy:.3f}",
        f"    Regime de Gamma:    {regime}",
        f"    Vies do Dia:        {bias}",
        f"    Dinamica de MM:     {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : USDJPY {min_gamma_jpy:.3f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : USDJPY {flip_jpy:.3f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : USDJPY {max_gamma_jpy:.3f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE FXY   | EQUIVALENTE USDJPY | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65
    ]
    
    # Adicionar as Walls ordenadas no relatório
    walls_for_report = sorted([w for w in walls if w['type'] == 'Wall'], key=lambda x: x['price'], reverse=True)
    for w in walls_for_report:
        oi_m = w['gex'] / 1e6
        fxy_strike = w.get('strike_spy', 0)
        report_lines.append(f"  {w['type']:<10} | ${fxy_strike:<12.2f} | {w['price']:<18.3f} | $ {oi_m:>17.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest no ETF proxy FXY.",
        "FXY rastreia o Yen vs USD (inversamente correlacionado ao USDJPY).",
        "GEX foi invertido para refletir a perspectiva USDJPY.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print(f"      Relatório escrito em: {report_path}")
    
    # 5. Salvar cache para unificação
    save_walls_to_cache(walls, ticker="usd_jpy", ref_date=expiry_str)
    
    # 6. Re-compilar o indicador TradingView unificado
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)
    
    print("\n" + "=" * 60)
    print("  Pipeline USD/JPY concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_jpy_gex_pipeline()
