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
from gex.engine.mt5_prices import get_synchronized_etf_ratio

def get_qqq_and_nq_prices():
    """
    Busca o preço Spot do QQQ, a grade de opções e o preço atual do futuro NQ.
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados de QQQ e NQ...")
    
    qqq_ticker = yf.Ticker("QQQ")
    
    # 1. Buscar preço Spot do QQQ
    hist_qqq = qqq_ticker.history(period="1d")
    if not hist_qqq.empty:
        current_qqq = hist_qqq['Close'].iloc[-1]
    else:
        current_qqq = qqq_ticker.info.get('regularMarketPrice', 440.0)
        
    # 2. Buscar preço do Futuro NQ (NQ=F)
    nq_ticker = yf.Ticker("NQ=F")
    hist_nq = nq_ticker.history(period="1d")
    if not hist_nq.empty:
        current_nq = hist_nq['Close'].iloc[-1]
    else:
        current_nq = nq_ticker.info.get('regularMarketPrice', current_qqq * 42.0)
        
    print(f"      QQQ Spot Price: ${current_qqq:.2f} | NQ Futuro Price: {current_nq:.2f}")
    print(f"      Fator de Conversão Dinâmico NQ/QQQ: {current_nq / current_qqq:.6f}")
    
    # 3. Buscar datas de vencimento de opções do QQQ
    expirations = qqq_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para QQQ.")
        return None, None, None, None
        
    # 4. Baixar a grade de opções (com loop de fallback para evitar vencimentos vazios no dia da expiração)
    opt_chain = None
    front_expiry = None
    
    for expiry in expirations[:3]:
        try:
            chain = qqq_ticker.option_chain(expiry)
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
        opt_chain = qqq_ticker.option_chain(front_expiry)
        
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
    return current_qqq, current_nq, df_options, front_expiry

def run_nq_gex_pipeline():
    """
    Executa o pipeline completo do Nasdaq 100 GEX.
    """
    print("=" * 60)
    print("  GEX ENGINE - Nasdaq 100 / NQ Pipeline")
    print("=" * 60)
    
    # 1. Buscar preços e grade
    current_qqq, current_nq, df_options, expiry_str = get_qqq_and_nq_prices()
    if df_options is None or df_options.empty:
        print("ERRO: Opções inválidas.")
        sys.exit(1)
        
    # 2. Parâmetros temporais
    expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    expiry_days = int(np.busday_count(today.isoformat(), expiry_date.isoformat()))
    expiry_days = max(1, expiry_days)
    T = max(1/252, expiry_days / 252)
    
    r = 0.0515  # SOFR
    fallback_ratio = current_nq / current_qqq if current_qqq > 0 else 41.0
    conv_ratio, price_nq_mt5, ratio_msg = get_synchronized_etf_ratio(current_qqq, "USTEC", fallback_ratio)
    if price_nq_mt5 and price_nq_mt5 > 0:
        current_nq = price_nq_mt5
    
    print(f"\n[2/5] Parâmetros de Cálculo:")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      Taxa (r): {r*100:.2f}% | Multiplicador NQ/QQQ: {conv_ratio:.6f}")
    print(f"      Sincronização MT5: {ratio_msg}")
    
    # 3. Agrupar strikes e calcular GEX por nível
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    # Agrupar strikes do QQQ por $5.0 em vez de $1.0 para expandir o espaçamento das walls no Nasdaq (NQ)
    df_options['strike_round'] = (df_options['strike'] / 5.0).round() * 5.0
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_qqq, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        # Strike correspondente em NQ futuro
        strike_nq = strike_qqq * conv_ratio
        
        for _, row in group.iterrows():
            gamma = black76_gamma(F=current_nq, K=strike_nq, T=T, sigma=row['iv'])
            gex_contrib = row['oi'] * gamma * (current_nq ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        gex_per_strike[strike_qqq] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv
        }
        
    # strikes mais próximos do ATM
    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_qqq))
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
            
    # Montar as Walls (NQ Futuro equivalente)
    walls_basic = []
    for strike_qqq in selected_strikes:
        info = gex_per_strike[strike_qqq]
        price_nq = strike_qqq * conv_ratio
        
        walls_basic.append({
            "price": round(price_nq, 2),
            "type": "Wall",
            "width": width_map.get(strike_qqq, 1),
            "style": 0,
            "strike_spy": int(strike_qqq),  # reusar strike_spy como nome genérico para o exporter
            "gex": info['gex_net']
        })
        
    # Ordenar
    walls = sorted(walls_basic, key=lambda x: x['price'])
            
    # 4. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip)
    sweep_prices = np.linspace(current_nq * 0.90, current_nq * 1.10, 200)
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in df_options.iterrows():
            gamma = black76_gamma(F=s_hyp, K=row['strike'] * conv_ratio, T=T, sigma=row['iv'])
            contrib = row['oi'] * gamma * (s_hyp ** 2) * 0.01 * multiplier
            if row['type'] == 'PUT':
                contrib = -contrib
            gex_total += contrib
        gamma_curve.append((s_hyp, gex_total))
        
    gamma_curve_arr = np.array(gamma_curve)
    prices = gamma_curve_arr[:, 0]
    gex_values = gamma_curve_arr[:, 1]
    
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_nq = float(prices[max_gamma_idx])
    
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_nq = float(prices[min_gamma_idx])
    
    flip_nq = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_nq)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_nq = float(cross)
                
    if flip_nq is None:
        flip_nq = current_nq
        
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_nq, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_nq, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_nq, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Caches
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_NQ.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_nq >= flip_nq else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_nq >= flip_nq else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_nq >= flip_nq else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - NASDAQ 100 / NQ",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    NQ Futuro Atual:   {current_nq:.2f}  (QQQ Spot: ${current_qqq:.2f})",
        f"    Gamma Flip Point:  {flip_nq:.2f}",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : NQ {min_gamma_nq:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : NQ {flip_nq:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : NQ {max_gamma_nq:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE QQQ':12s} | {'EQUIVALENTE NQ':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65
    ]
    
    display_walls = [w for w in walls if w['type'] == 'Wall']
    for w in sorted(display_walls, key=lambda x: x['strike_spy'], reverse=True):
        width_stars = "*" * w['width']
        type_str = "WALL " + width_stars
        gex_m = w['gex'] / 1_000_000
        report_lines.append(f"  {type_str:10s} | ${w['strike_spy']:<11.2f} | NQ {w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")
        
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
    
    # Salvar cache e atualizar TradingView
    tv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    try:
        save_walls_to_cache(walls, ticker="nasdaq_nq", ref_date=today)
        export_unified_tradingview(output_path=tv_path)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")
        
    print("\n" + "=" * 60)
    print("  Pipeline Nasdaq concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_nq_gex_pipeline()
