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

def black_scholes_gamma(S, K, T, sigma, r=0.0515):
    """
    Calcula a Gamma de Black-Scholes padrão para USD.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * (sigma ** 2)) * T) / (sigma * np.sqrt(T))
    n_d1 = norm.pdf(d1)
    gamma = n_d1 / (S * sigma * np.sqrt(T))
    return gamma

def get_russell_spot_and_chain():
    """
    Obtém o preço spot do Russell 2000 (^RUT) e a grade de opções do ETF proxy IWM.
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados do Russell 2000 (IWM)...")
    iwm_ticker = yf.Ticker("IWM")
    rut_ticker = yf.Ticker("^RUT")
    
    # 1. Buscar preço Spot real do Russell 2000 Index
    hist_rut = rut_ticker.history(period="1d")
    if not hist_rut.empty:
        current_spot = hist_rut['Close'].iloc[-1]
    else:
        # Se falhar, usa IWM * 10.0
        hist_iwm = iwm_ticker.history(period="1d")
        current_iwm_temp = hist_iwm['Close'].iloc[-1] if not hist_iwm.empty else 220.0
        current_spot = current_iwm_temp * 10.0
        
    # 2. Buscar preço Spot do ETF IWM
    hist_iwm = iwm_ticker.history(period="1d")
    if not hist_iwm.empty:
        current_iwm = hist_iwm['Close'].iloc[-1]
    else:
        current_iwm = current_spot / 10.0
        
    print(f"      Russell 2000 Spot Index: {current_spot:.2f} | IWM ETF Spot Price: ${current_iwm:.2f}")
    
    # 3. Buscar datas de vencimento
    expirations = iwm_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para IWM.")
        return None, None, None, None
        
    front_expiry = expirations[0]
    print(f"      Próximo vencimento (Front-Month): {front_expiry}")
    
    opt_chain = iwm_ticker.option_chain(front_expiry)
    calls = opt_chain.calls
    puts = opt_chain.puts
    options = []
    
    total_oi_calls = calls['openInterest'].fillna(0).astype(int).gt(0).sum()
    total_oi_puts = puts['openInterest'].fillna(0).astype(int).gt(0).sum()
    total_active_oi = total_oi_calls + total_oi_puts
    
    use_volume_fallback = total_active_oi < 15
    if use_volume_fallback:
        print(f"      [Aviso] Pouco Open Interest detectado ({total_active_oi} contratos). Ativando fallback para Volume!")
    
    for _, row in calls.iterrows():
        oi = int(row['openInterest']) if not pd.isna(row['openInterest']) else 0
        volume = int(row['volume']) if not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.18
        if oi > 0:
            options.append({
                "ticker": row['contractSymbol'],
                "type": "CALL",
                "strike": float(row['strike']),
                "expiry": front_expiry,
                "oi": oi,
                "iv": iv
            })
            
    for _, row in puts.iterrows():
        oi = int(row['openInterest']) if not pd.isna(row['openInterest']) else 0
        volume = int(row['volume']) if not pd.isna(row['volume']) else 0
        if use_volume_fallback and oi == 0:
            oi = volume
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.18
        if oi > 0:
            options.append({
                "ticker": row['contractSymbol'],
                "type": "PUT",
                "strike": float(row['strike']),
                "expiry": front_expiry,
                "oi": oi,
                "iv": iv
            })
            
    print(f"      {len(options)} contratos de opções ativos carregados.")
    df_options = pd.DataFrame(options)
    return current_spot, current_iwm, front_expiry, df_options

def run_russell_gex_pipeline():
    print("=" * 60)
    print("  GEX ENGINE - Russell 2000 / US2000 Pipeline")
    print("=" * 60)
    
    current_spot, current_iwm, expiry_str, df_options = get_russell_spot_and_chain()
    if df_options is None or df_options.empty:
        print("      ERRO: Não foi possível obter a grade de opções de IWM.")
        return
        
    today = datetime.date.today()
    expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    
    expiry_days = int(np.busday_count(today.isoformat(), expiry_date.isoformat()))
    expiry_days = max(1, expiry_days)
    T = max(1/252, expiry_days / 252)
    
    r = 0.0515   # US SOFR ~5.15%
    
    # Sincronização MT5
    conv_ratio, _, ratio_msg = get_synchronized_etf_ratio(
        etf_spot_price=current_iwm,
        symbol_mt5="US2000",
        fallback_ratio=current_spot / current_iwm
    )
    
    print(f"\n[2/5] Parâmetros de precificação (base 252 dias):")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      r = {r*100:.2f}% | T = {T:.4f}")
    print(f"      Sincronização MT5: {ratio_msg}")
    
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = df_options['strike'].round(1)
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_iwm, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = black_scholes_gamma(S=current_iwm, K=row['strike'], T=T, sigma=row['iv'], r=r)
            gex_contrib = row['oi'] * gamma * (current_iwm ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        strike_rut = strike_iwm * conv_ratio
        gex_per_strike[strike_rut] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv,
            'strike_iwm': strike_iwm
        }
        
    all_strikes = sorted(gex_per_strike.keys())
    current_rut_approx = current_iwm * conv_ratio
    
    range_pct = 0.15
    lower_bound = current_rut_approx * (1 - range_pct)
    upper_bound = current_rut_approx * (1 + range_pct)
    filtered_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    if len(filtered_strikes) < 3:
        filtered_strikes = sorted(all_strikes, key=lambda s: abs(s - current_rut_approx))[:8]
        filtered_strikes = sorted(filtered_strikes)
    
    atm_strike = min(filtered_strikes, key=lambda s: abs(s - current_rut_approx))
    atm_idx = filtered_strikes.index(atm_strike)
    
    num_walls = min(16, len(filtered_strikes))
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(filtered_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    selected_strikes = filtered_strikes[start_idx:end_idx]
    
    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound:.0f}, {upper_bound:.0f}]")
    
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
            
    walls_basic = []
    for strike_rut in selected_strikes:
        info = gex_per_strike[strike_rut]
        price_futures = info['strike_iwm'] * conv_ratio
        
        walls_basic.append({
            "price": round(price_futures, 2),
            "type": "Wall",
            "width": width_map.get(strike_rut, 1),
            "style": 0,
            "strike_spy": float(info['strike_iwm']),
            "gex": info['gex_net']
        })
        
    walls = sorted(walls_basic, key=lambda x: x['price'])
                
    # 4. Market Gamma Curve
    sweep_prices = np.linspace(current_iwm * 0.90, current_iwm * 1.10, 200)
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
    
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_rut = float(prices[max_gamma_idx]) * conv_ratio
    
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_rut = float(prices[min_gamma_idx]) * conv_ratio
    
    flip_iwm = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_iwm)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_iwm = float(cross)
                
    if flip_iwm is None:
        flip_iwm = current_iwm
        
    flip_rut = flip_iwm * conv_ratio
    
    walls.append({
        "price": round(max_gamma_rut, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_rut, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_rut, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
        "factor": conv_ratio
    })
    
    # 5. Relatório e Exportação
    print("\n[4/5] Exportando indicadores e relatórios...")
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "gex", "docs")
    os.makedirs(docs_dir, exist_ok=True)
    report_file = os.path.join(docs_dir, "DAILY_REPORT_RUSSELL.txt")
    
    current_rut_price = current_iwm * conv_ratio
    is_positive_gamma = current_iwm >= flip_iwm
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if is_positive_gamma else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if is_positive_gamma else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write("  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - RUSSELL 2000 / US2000\n")
        f.write(f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}\n")
        f.write("=================================================================\n\n")
        f.write("[+] STATUS DO MERCADO (REGIME GEX):\n")
        f.write(f"    Russell 2000 Spot/CFD Atual: {current_rut_price:.2f}  (IWM Spot: ${current_iwm:.2f})\n")
        f.write(f"    Gamma Flip Point:           {flip_rut:.2f}\n")
        f.write(f"    Regime de Gamma:            {regime}\n")
        f.write(f"    Vies do Dia:                {bias}\n\n")
        f.write("[+] NIVEIS CRITICOS DA CURVA GAMMA:\n")
        f.write(f"    [-] MIN GAMMA (Piso de Queda Livre)   : US2000 {min_gamma_rut:.2f}\n")
        f.write(f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : US2000 {flip_rut:.2f}\n")
        f.write(f"    [+] MAX GAMMA (Teto de Exaustao)      : US2000 {max_gamma_rut:.2f}\n")
        
    print(f"      Relatório escrito em: {report_file}")
    
    tv_file = os.path.join(docs_dir, "jumba_tradingview.pine")
    save_walls_to_cache(walls, ticker="RUSSELL_US2000", ref_date=today)
    export_unified_tradingview(output_path=tv_file)
    
    print("\n" + "=" * 60)
    print("  Pipeline Russell 2000 / US2000 concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_russell_gex_pipeline()
