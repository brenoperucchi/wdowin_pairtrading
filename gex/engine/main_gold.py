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

def get_gold_spot_and_chain():
    """
    Obtém o preço spot do Ouro (GC=F) e a grade de opções do ETF proxy GLD.
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados de Ouro (GLD)...")
    gld_ticker = yf.Ticker("GLD")
    gc_ticker = yf.Ticker("GC=F")
    
    # 1. Buscar preço Spot real do Ouro (Futuro COMEX próximo)
    hist_gc = gc_ticker.history(period="1d")
    if not hist_gc.empty:
        current_spot = hist_gc['Close'].iloc[-1]
    else:
        # Se falhar, usa GLD * 10
        hist_gld = gld_ticker.history(period="1d")
        current_gld_temp = hist_gld['Close'].iloc[-1] if not hist_gld.empty else 235.0
        current_spot = current_gld_temp * 10.0
        
    # 2. Buscar preço Spot do ETF GLD
    hist_gld = gld_ticker.history(period="1d")
    if not hist_gld.empty:
        current_gld = hist_gld['Close'].iloc[-1]
    else:
        current_gld = current_spot / 10.0
        
    print(f"      XAUUSD Spot Price: ${current_spot:.2f} | GLD ETF Spot Price: ${current_gld:.2f}")
    
    # 3. Buscar datas de vencimento
    expirations = gld_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para GLD.")
        return None, None, None, None
        
    # 4. Baixar a grade de opções (com loop de fallback filtrando por liquidez real)
    opt_chain = None
    front_expiry = None
    best_active_count = 0
    
    for expiry in expirations[:10]:
        try:
            chain = gld_ticker.option_chain(expiry)
            calls_oi = chain.calls['openInterest'] if 'openInterest' in chain.calls.columns else pd.Series(dtype=int)
            puts_oi = chain.puts['openInterest'] if 'openInterest' in chain.puts.columns else pd.Series(dtype=int)
            
            active_calls = calls_oi[calls_oi > 0].count()
            active_puts = puts_oi[puts_oi > 0].count()
            active_count = active_calls + active_puts
            
            if active_count >= 15:
                opt_chain = chain
                front_expiry = expiry
                best_active_count = active_count
                break
                
            if active_count > best_active_count:
                best_active_count = active_count
                opt_chain = chain
                front_expiry = expiry
        except Exception:
            continue
            
    if opt_chain is None:
        front_expiry = expirations[0]
        opt_chain = gld_ticker.option_chain(front_expiry)
        
    print(f"      Próximo vencimento ativo selecionado: {front_expiry}")
    calls = opt_chain.calls
    puts = opt_chain.puts
    
    # Verificar se o Yahoo Finance está com problemas de Open Interest zerado ou muito baixo (comum em DTE zero de manhã)
    atm_lower = current_gld * 0.90
    atm_upper = current_gld * 1.10
    near_atm_calls = calls[(calls['strike'] >= atm_lower) & (calls['strike'] <= atm_upper)]
    near_atm_puts = puts[(puts['strike'] >= atm_lower) & (puts['strike'] <= atm_upper)]
    
    total_near_oi = (
        (near_atm_calls['openInterest'].fillna(0).astype(int).gt(0).sum() if 'openInterest' in calls.columns else 0) +
        (near_atm_puts['openInterest'].fillna(0).astype(int).gt(0).sum() if 'openInterest' in puts.columns else 0)
    )
    
    use_volume_fallback = total_near_oi < 5
    if use_volume_fallback:
        print(f"      [Aviso] Pouco Open Interest detectado perto do ATM ({total_near_oi} contratos). Ativando fallback para Volume!")
        
    options = []
    
    # Processar Calls
    for _, row in calls.iterrows():
        oi = int(row['openInterest']) if 'openInterest' in calls.columns and not pd.isna(row['openInterest']) else 0
        volume = int(row['volume']) if 'volume' in calls.columns and not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
            
        iv = float(row['impliedVolatility']) if 'impliedVolatility' in calls.columns and not pd.isna(row['impliedVolatility']) else 0.12
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
        oi = int(row['openInterest']) if 'openInterest' in puts.columns and not pd.isna(row['openInterest']) else 0
        volume = int(row['volume']) if 'volume' in puts.columns and not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
            
        iv = float(row['impliedVolatility']) if 'impliedVolatility' in puts.columns and not pd.isna(row['impliedVolatility']) else 0.12
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
    return current_spot, current_gld, df_options, front_expiry

def run_gold_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do Ouro (GLD).
    """
    print("=" * 60)
    print("  GEX ENGINE - Gold / XAUUSD Pipeline")
    print("=" * 60)
    
    # 1. Carregar dados reais
    current_spot, current_gld, df_options, expiry_str = get_gold_spot_and_chain()
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
    
    print(f"\n[2/5] Parâmetros de precificação (base 252 dias):")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      r = {r*100:.2f}% | T = {T:.4f}")
    
    # Agrupar strikes do GLD por $5.0 (equivalente a $50.0 de Spot Gold) para evitar poluicao visual (alinhado com SPY e QQQ)
    df_options['strike_round'] = (df_options['strike'] / 5.0).round() * 5.0
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_gld, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = black_scholes_gamma(S=current_gld, K=row['strike'], T=T, sigma=row['iv'], r=r)
            gex_contrib = row['oi'] * gamma * (current_gld ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        # Converter strike do GLD para equivalente XAUUSD spot (* 10)
        strike_gold = strike_gld * 10.0
        gex_per_strike[strike_gold] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv,
            'strike_gld': strike_gld
        }
        
    # Selecionar strikes próximos do ATM (dentro de ±5% do spot)
    all_strikes = sorted(gex_per_strike.keys())
    lower_bound = current_spot * 0.95
    upper_bound = current_spot * 1.05
    nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Fallback: se poucos strikes dentro de ±5%, expandir para ±10%
    if len(nearby_strikes) < 4:
        lower_bound = current_spot * 0.90
        upper_bound = current_spot * 1.10
        nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Limitar a no máximo 16 strikes mais próximos do ATM
    num_walls = 16
    nearby_strikes.sort(key=lambda s: abs(s - current_spot))
    selected_strikes = sorted(nearby_strikes[:num_walls])
    
    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [${lower_bound:.2f}, ${upper_bound:.2f}]")
    
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
            
    # Montar Walls básicas em Gold
    walls_basic = []
    for strike_gold in selected_strikes:
        info = gex_per_strike[strike_gold]
        
        walls_basic.append({
            "price": round(strike_gold, 2),
            "type": "Wall",
            "width": width_map.get(strike_gold, 1),
            "style": 0,
            "strike_spy": int(info['strike_gld']),  # Armazenar strike do GLD
            "gex": info['gex_net']
        })
        
    # Adicionar MidWalls entre as Walls consecutivas usando target spacing
    walls_basic_sorted = sorted(walls_basic, key=lambda x: x['price'])
    walls = []
    
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]['price']
            w2 = walls_basic_sorted[i+1]['price']
            diff = w2 - w1
            
            target_spacing = 25.0  # Espacamento alvo de 25.0 pontos em Gold spot
            num_steps = int(round(diff / target_spacing))
            num_steps = max(2, num_steps)
            
            step = diff / num_steps
            for j in range(1, num_steps):
                mid_price = w1 + j * step
                walls.append({
                    "price": round(mid_price, 2),
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0
                })
            
    # 4. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip)
    sweep_prices = np.linspace(current_gld * 0.90, current_gld * 1.10, 200)
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
    max_gamma_gld = float(prices[max_gamma_idx])
    max_gamma_gold = max_gamma_gld * 10.0
    
    # MinGamma
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_gld = float(prices[min_gamma_idx])
    min_gamma_gold = min_gamma_gld * 10.0
    
    # GammaFlip
    flip_gld = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_gld)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_gld = float(cross)
                
    if flip_gld is None:
        flip_gld = current_gld
        
    flip_gold = flip_gld * 10.0
    
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_gold, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_gold, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_gold, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_GOLD.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_gld >= flip_gld else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_gld >= flip_gld else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_gld >= flip_gld else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - GOLD / XAUUSD",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    XAUUSD Spot Atual: ${current_spot:.2f}",
        f"    Gamma Flip Point:  ${flip_gold:.2f}",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : XAUUSD ${min_gamma_gold:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : XAUUSD ${flip_gold:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : XAUUSD ${max_gamma_gold:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE GLD   | EQUIVALENTE XAUUSD | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65
    ]
    
    # Adicionar as Walls ordenadas no relatório
    walls_for_report = sorted([w for w in walls if w['type'] == 'Wall'], key=lambda x: x['price'], reverse=True)
    for w in walls_for_report:
        oi_m = w['gex'] / 1e6
        report_lines.append(f"  {w['type']:<10} | ${w['strike_spy']:<12.1f} | {w['price']:<18.2f} | $ {oi_m:>17.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest no ETF proxy GLD.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print(f"      Relatório escrito em: {report_path}")
    
    # 5. Salvar cache para unificação
    save_walls_to_cache(walls, ticker="gold_xau", ref_date=expiry_str)
    
    # 6. Re-compilar o indicador TradingView unificado
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)
    
    print("\n" + "=" * 60)
    print("  Pipeline Gold/XAUUSD concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_gold_gex_pipeline()
