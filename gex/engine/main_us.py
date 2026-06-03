import datetime
import os
import sys
import re
import numpy as np
import pandas as pd
import yfinance as yf

# Adicionar a pasta raiz ao sys.path para importações locais
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gex.engine.black76 import black76_gamma
from gex.engine.tradingview_exporter import save_walls_to_cache, export_unified_tradingview

def get_spy_spot_and_chain():
    """
    Obtém o preço spot atual do SPY e a grade de opções completa
    para o vencimento mais próximo (0DTE/1DTE/Front-Month).
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados de SPY...")
    spy_ticker = yf.Ticker("SPY")
    
    # 1. Buscar preço Spot do SPY
    hist = spy_ticker.history(period="1d")
    if not hist.empty:
        current_spy = hist['Close'].iloc[-1]
    else:
        current_spy = spy_ticker.info.get('regularMarketPrice', 530.0)
        
    print(f"      SPY Spot Price: ${current_spy:.2f} | Equivalente SPX/ES ~ {current_spy * 10:.2f}")
    
    # 2. Buscar datas de vencimento
    expirations = spy_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para SPY.")
        return None, None, None
        
    # 3. Baixar a grade de opções (com loop de fallback para evitar vencimentos vazios no dia da expiração)
    opt_chain = None
    front_expiry = None
    
    for expiry in expirations[:3]:
        try:
            chain = spy_ticker.option_chain(expiry)
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
        opt_chain = spy_ticker.option_chain(front_expiry)
        
    print(f"      Próximo vencimento ativo selecionado: {front_expiry}")
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
        volume = int(row['volume']) if not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
            
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
    print(f"      {len(df_options)} contratos de opções ativos carregados.")
    return current_spy, df_options, front_expiry

def run_us_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do SP500 (SPY / ES).
    """
    print("=" * 60)
    print("  GEX ENGINE - S&P 500 / ES Pipeline")
    print("=" * 60)
    
    # 1. Carregar dados reais
    current_spy, df_options, expiry_str = get_spy_spot_and_chain()
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
    
    r = 0.0515   # SOFR ~5.15%
    q = 0.0130   # Dividend Yield SPX ~1.30%
    
    # Fator de Carrego Líquido para o Futuro ES
    carry_factor = np.exp((r - q) * T)
    
    print(f"\n[2/5] Parâmetros do Modelo Black-76:")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      r = {r*100:.2f}% | q = {q*100:.2f}% | carry_factor = {carry_factor:.6f}")
    
    # 3. Agrupar strikes e calcular GEX por nível
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = (df_options['strike'] / 1.0).round() * 1.0
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_spy, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = black76_gamma(F=current_spy, K=row['strike'], T=T, sigma=row['iv'])
            gex_contrib = row['oi'] * gamma * (current_spy ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        gex_per_strike[strike_spy] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv
        }
        
    # Selecionar os 16 strikes mais próximos do ATM
    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_spy))
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
            
    # Montar Walls básicas (ES Futuro equivalente)
    walls_basic = []
    for strike_spy in selected_strikes:
        info = gex_per_strike[strike_spy]
        price_es = strike_spy * 10 * carry_factor
        
        walls_basic.append({
            "price": round(price_es, 2),
            "type": "Wall",
            "width": width_map.get(strike_spy, 1),
            "style": 0,
            "strike_spy": int(strike_spy),
            "gex": info['gex_net']
        })
        
    # Adicionar MidWalls entre as Walls consecutivas
    # Ordenar primeiro para garantir os pontos médios corretos
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
    
    # MaxGamma
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_spy = float(prices[max_gamma_idx])
    max_gamma_es = max_gamma_spy * 10 * carry_factor
    
    # MinGamma
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_spy = float(prices[min_gamma_idx])
    min_gamma_es = min_gamma_spy * 10 * carry_factor
    
    # GammaFlip
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
        flip_spy = current_spy
        
    flip_es = flip_spy * 10 * carry_factor
    
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_es, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_es, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_es, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    # Relatório de Tendência Diária
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_US.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_spy >= flip_spy else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_spy >= flip_spy else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_spy >= flip_spy else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - S&P 500 / ES",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    SPY Spot Atual:    ${current_spy:.2f}  (Equiv. ES: ~{current_spy * 10:.1f})",
        f"    Gamma Flip Point:  ${flip_spy:.2f}  (Equiv. ES:  {flip_es:.2f})",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : ES {min_gamma_es:.2f} | SPY ${min_gamma_spy:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : ES {flip_es:.2f} | SPY ${flip_spy:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : ES {max_gamma_es:.2f} | SPY ${max_gamma_spy:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE SPY':12s} | {'EQUIVALENTE ES':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65
    ]
    
    # Apenas para exibição arrumada das walls principais
    display_walls = [w for w in walls if w['type'] == 'Wall']
    for w in sorted(display_walls, key=lambda x: x['strike_spy'], reverse=True):
        width_stars = "*" * w['width']
        type_str = "WALL " + width_stars
        gex_m = w['gex'] / 1_000_000
        report_lines.append(f"  {type_str:10s} | ${w['strike_spy']:<11.2f} | ES {w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest das opcoes.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    report_content = "\n".join(report_lines)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
        
    print(f"      Relatório escrito em: {report_path}")
    
    # Exportar Pine Script unificado para o TradingView
    tv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    try:
        save_walls_to_cache(walls, ticker="sp500_es", ref_date=today)
        export_unified_tradingview(output_path=tv_path)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")
    
    print("\n" + "=" * 60)
    print("  Pipeline US concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_us_gex_pipeline()
