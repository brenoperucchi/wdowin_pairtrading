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

def get_fxb_spot_and_chain():
    """
    Obtém o preço spot do GBPUSD e a grade de opções do ETF proxy FXB
    para o vencimento mais próximo (Front-Month).
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados de GBP/USD (FXB)...")
    fxb_ticker = yf.Ticker("FXB")
    gbp_ticker = yf.Ticker("GBPUSD=X")
    
    # 1. Buscar preço Spot real do GBPUSD
    hist_gbp = gbp_ticker.history(period="1d")
    if not hist_gbp.empty:
        current_spot = hist_gbp['Close'].iloc[-1]
    else:
        current_spot = gbp_ticker.info.get('regularMarketPrice', 1.3400)
        
    # 2. Buscar preço Spot do ETF FXB
    hist_fxb = fxb_ticker.history(period="1d")
    if not hist_fxb.empty:
        current_fxb = hist_fxb['Close'].iloc[-1]
    else:
        current_fxb = fxb_ticker.info.get('regularMarketPrice', current_spot * 100.0)
        
    print(f"      GBPUSD Spot Rate: {current_spot:.5f} | FXB ETF Spot Price: ${current_fxb:.2f}")
    
    # 3. Buscar datas de vencimento
    expirations = fxb_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para FXB.")
        return None, None, None, None
        
    # 4. Baixar a grade de opções (com fallback para evitar vencimentos expirados/vazios)
    opt_chain = None
    front_expiry = None
    
    for expiry in expirations[:3]:
        try:
            chain = fxb_ticker.option_chain(expiry)
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
        opt_chain = fxb_ticker.option_chain(front_expiry)
        
    print(f"      Próximo vencimento ativo selecionado: {front_expiry}")
    calls = opt_chain.calls
    puts = opt_chain.puts
    
    total_oi_calls = calls['openInterest'].fillna(0).astype(int).gt(0).sum()
    total_oi_puts = puts['openInterest'].fillna(0).astype(int).gt(0).sum()
    total_active_oi = total_oi_calls + total_oi_puts
    
    use_volume_fallback = total_active_oi < 15
    if use_volume_fallback:
        print(f"      [Aviso] Pouco Open Interest detectado ({total_active_oi} contratos). Ativando fallback para Volume!")
        
    options = []
    
    # Processar Calls
    for _, row in calls.iterrows():
        oi = int(row['openInterest']) if not pd.isna(row['openInterest']) else 0
        volume = int(row['volume']) if not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
            
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
        volume = int(row['volume']) if not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
            
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
    return current_spot, current_fxb, df_options, front_expiry

def run_gbp_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do GBP/USD (FXB).
    """
    print("=" * 60)
    print("  GEX ENGINE - GBP/USD Pipeline")
    print("=" * 60)
    
    # 1. Carregar dados reais
    current_gbp, current_fxb, df_options, expiry_str = get_fxb_spot_and_chain()
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
    rd = 0.0515   # US SOFR (Taxa Doméstica) ~ 5.15%
    rf = 0.0525   # BoE rate (Taxa Estrangeira Libra) ~ 5.25%
    
    fallback_ratio = (current_gbp / current_fxb) if current_fxb > 0 else 0.0104
    conv_ratio, price_gbp_mt5, ratio_msg = get_synchronized_etf_ratio(current_fxb, "GBPUSD", fallback_ratio)
    if price_gbp_mt5 and price_gbp_mt5 > 0:
        current_gbp = price_gbp_mt5
    
    print(f"\n[2/5] Parâmetros de Garman-Kohlhagen (base 252 dias):")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      rd (USD) = {rd*100:.2f}% | rf (GBP) = {rf*100:.2f}% | T = {T:.4f}")
    print(f"      Sincronização MT5: {ratio_msg}")
    
    # 3. Agrupar strikes por 10 pips de GBPUSD (equivalente a 0.10 pontos de strike no FXB)
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = (df_options['strike'] / 0.10).round() * 0.10
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_fxb, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = garman_kohlhagen_gamma(S=current_fxb, K=row['strike'], T=T, sigma=row['iv'], rd=rd, rf=rf)
            # GEX em dólares da moeda secundária
            gex_contrib = row['oi'] * gamma * (current_fxb ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        # Converter strike do FXB para equivalente GBPUSD spot via conv_ratio MT5
        strike_gbp = strike_fxb * conv_ratio
        gex_per_strike[strike_gbp] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv,
            'strike_fxb': strike_fxb
        }
        
    # Selecionar strikes próximos do ATM (dentro de ±5% do spot)
    all_strikes = sorted(gex_per_strike.keys())
    lower_bound = current_gbp * 0.95
    upper_bound = current_gbp * 1.05
    nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Fallback: se poucos strikes dentro de ±5%, expandir para ±10%
    if len(nearby_strikes) < 4:
        lower_bound = current_gbp * 0.90
        upper_bound = current_gbp * 1.10
        nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    # Limitar a no máximo 16 strikes mais próximos do ATM
    num_walls = 16
    nearby_strikes.sort(key=lambda s: abs(s - current_gbp))
    selected_strikes = sorted(nearby_strikes[:num_walls])
    
    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound:.4f}, {upper_bound:.4f}]")
    
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
            
    # Montar Walls básicas em GBPUSD (5 casas decimais de precisão)
    walls_basic = []
    for strike_gbp in selected_strikes:
        info = gex_per_strike[strike_gbp]
        
        walls_basic.append({
            "price": round(strike_gbp, 5),
            "type": "Wall",
            "width": width_map.get(strike_gbp, 1),
            "style": 0,
            "strike_spy": int(info['strike_fxb']),  # Armazenar strike do FXB
            "gex": info['gex_net']
        })
        
    # Adicionar MidWalls (ponto médio entre Walls consecutivas)
    walls_basic_sorted = sorted(walls_basic, key=lambda x: x['price'])
    walls = []
    
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]['price']
            w2 = walls_basic_sorted[i+1]['price']
            # Apenas criar MidWall se a distância entre walls consecutivas for normal (<= 250 pips)
            if (w2 - w1) <= 0.0250:
                mid_price = round((w1 + w2) / 2, 5)
                walls.append({
                    "price": mid_price,
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0
                })
            
    # 4. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip)
    sweep_prices = np.linspace(current_fxb * 0.95, current_fxb * 1.05, 200)
    gamma_curve = []
    
    for s_hyp in sweep_prices:
        gex_total = 0.0
        for _, row in df_options.iterrows():
            gamma = garman_kohlhagen_gamma(S=s_hyp, K=row['strike'], T=T, sigma=row['iv'], rd=rd, rf=rf)
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
    max_gamma_fxb = float(prices[max_gamma_idx])
    max_gamma_gbp = max_gamma_fxb * conv_ratio
    
    # MinGamma
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_fxb = float(prices[min_gamma_idx])
    min_gamma_gbp = min_gamma_fxb * conv_ratio
    
    # GammaFlip
    flip_fxb = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_fxb)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_fxb = float(cross)
                
    if flip_fxb is None:
        flip_fxb = current_fxb
        
    flip_gbp = flip_fxb * conv_ratio
    
    # Adicionar níveis especiais
    walls.append({
        "price": round(max_gamma_gbp, 4),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_gbp, 4),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_gbp, 4),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0
    })
    
    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_GBP.txt")
    
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_fxb >= flip_fxb else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_fxb >= flip_fxb else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = ("Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
            if current_fxb >= flip_fxb else 
            "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta.")
            
    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - GBP/USD",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    GBPUSD Spot Atual: {current_gbp:.5f}",
        f"    Gamma Flip Point:  {flip_gbp:.5f}",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : GBPUSD {min_gamma_gbp:.5f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : GBPUSD {flip_gbp:.5f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : GBPUSD {max_gamma_gbp:.5f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE FXB   | EQUIVALENTE GBPUSD | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65
    ]
    
    # Adicionar as Walls ordenadas no relatório
    walls_for_report = sorted([w for w in walls if w['type'] == 'Wall'], key=lambda x: x['price'], reverse=True)
    for w in walls_for_report:
        oi_m = w['gex'] / 1e6
        report_lines.append(f"  {w['type']:<10} | ${w['strike_spy']:<12.1f} | {w['price']:<18.4f} | $ {oi_m:>17.2f}M | Width {w['width']}")
        
    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o posicionamento do Open Interest no ETF proxy FXB.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65
    ])
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print(f"      Relatório escrito em: {report_path}")
    
    # 5. Salvar cache para unificação
    save_walls_to_cache(walls, ticker="gbp_usd", ref_date=today.isoformat())
    
    # 6. Re-compilar o indicador TradingView unificado
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)
    
    print("\n" + "=" * 60)
    print("  Pipeline GBP/USD concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_gbp_gex_pipeline()
