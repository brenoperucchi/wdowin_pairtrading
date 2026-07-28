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

def garman_kohlhagen_gamma(S, K, T, sigma, rd=0.0515, rf=0.0150):
    """
    Calcula a Gamma de Garman-Kohlhagen / Black-Scholes para precificação em moedas estrangeiras (CNY/HKD).
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (rd - rf + 0.5 * (sigma ** 2)) * T) / (sigma * np.sqrt(T))
    n_d1 = norm.pdf(d1)
    gamma = np.exp(-rf * T) * n_d1 / (S * sigma * np.sqrt(T))
    return gamma

def get_china_spot_and_chain():
    """
    Obtém o preço spot do China Large-Cap e a grade de opções do ETF proxy FXI.
    """
    print("[1/5] Conectando ao Yahoo Finance para buscar dados da China (FXI)...")
    fxi_ticker = yf.Ticker("FXI")
    
    hist_fxi = fxi_ticker.history(period="1d")
    if not hist_fxi.empty:
        current_fxi = hist_fxi['Close'].iloc[-1]
    else:
        current_fxi = 30.0
        
    current_spot = current_fxi * 400.0  # estimativa inicial spot
    print(f"      FXI ETF Spot Price: ${current_fxi:.2f}")
    
    expirations = fxi_ticker.options
    if not expirations:
        print("      ERRO: Nenhuma data de vencimento encontrada para FXI.")
        return None, None, None, None
        
    opt_chain = None
    front_expiry = None
    best_active_count = 0
    
    for expiry in expirations[:10]:
        try:
            chain = fxi_ticker.option_chain(expiry)
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
                opt_chain = chain
                front_expiry = expiry
                best_active_count = active_count
        except Exception:
            continue
            
    if opt_chain is None:
        front_expiry = expirations[0]
        opt_chain = fxi_ticker.option_chain(front_expiry)
        
    print(f"      Próximo vencimento ativo selecionado: {front_expiry}")
    
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
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.24
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
        iv = float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else 0.24
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
    return current_spot, current_fxi, front_expiry, df_options

def run_china_gex_pipeline():
    print("=" * 60)
    print("  GEX ENGINE - China Large-Cap / CHINA50 Pipeline")
    print("=" * 60)
    
    current_spot, current_fxi, expiry_str, df_options = get_china_spot_and_chain()
    if df_options is None or df_options.empty:
        print("      ERRO: Não foi possível obter a grade de opções de FXI.")
        return
        
    today = datetime.date.today()
    expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    
    expiry_days = int(np.busday_count(today.isoformat(), expiry_date.isoformat()))
    expiry_days = max(1, expiry_days)
    T = max(1/252, expiry_days / 252)
    
    rd = 0.0515   # US SOFR ~5.15%
    rf = 0.0150   # PBOC ~1.50%
    
    # Sincronização MT5
    conv_ratio, _, ratio_msg = get_synchronized_etf_ratio(
        etf_spot_price=current_fxi,
        symbol_mt5="CHINA50",
        fallback_ratio=400.0
    )
    
    print(f"\n[2/5] Parâmetros de precificação (base 252 dias):")
    print(f"      Vencimento: {expiry_str} | Dias úteis: {expiry_days}")
    print(f"      rd = {rd*100:.2f}% | rf = {rf*100:.2f}% | T = {T:.4f}")
    print(f"      Sincronização MT5: {ratio_msg}")
    
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options['strike_round'] = df_options['strike'].round(1)
    
    gex_per_strike = {}
    multiplier = 100
    
    for strike_fxi, group in df_options.groupby('strike_round'):
        gex_net = 0.0
        avg_iv = group['iv'].mean()
        
        for _, row in group.iterrows():
            gamma = garman_kohlhagen_gamma(S=current_fxi, K=row['strike'], T=T, sigma=row['iv'], rd=rd, rf=rf)
            gex_contrib = row['oi'] * gamma * (current_fxi ** 2) * 0.01 * multiplier
            
            if row['type'] == 'PUT':
                gex_contrib = -gex_contrib
                
            gex_net += gex_contrib
            
        strike_china = strike_fxi * conv_ratio
        gex_per_strike[strike_china] = {
            'gex_net': gex_net,
            'abs_gex': abs(gex_net),
            'avg_iv': avg_iv,
            'strike_fxi': strike_fxi
        }
        
    all_strikes = sorted(gex_per_strike.keys())
    current_china_approx = current_fxi * conv_ratio
    
    range_pct = 0.15
    lower_bound = current_china_approx * (1 - range_pct)
    upper_bound = current_china_approx * (1 + range_pct)
    filtered_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]
    
    if len(filtered_strikes) < 3:
        filtered_strikes = sorted(all_strikes, key=lambda s: abs(s - current_china_approx))[:8]
        filtered_strikes = sorted(filtered_strikes)
    
    atm_strike = min(filtered_strikes, key=lambda s: abs(s - current_china_approx))
    atm_idx = filtered_strikes.index(atm_strike)
    
    num_walls = min(8, len(filtered_strikes))
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
    for strike_china in selected_strikes:
        info = gex_per_strike[strike_china]
        price_futures = info['strike_fxi'] * conv_ratio
        
        walls_basic.append({
            "price": round(price_futures, 1),
            "type": "Wall",
            "width": width_map.get(strike_china, 1),
            "style": 0,
            "strike_spy": float(info['strike_fxi']),
            "gex": info['gex_net']
        })
        
    walls_basic_sorted = sorted(walls_basic, key=lambda x: x['price'])
    walls = []
    
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]['price']
            w2 = walls_basic_sorted[i+1]['price']
            if (w2 - w1) <= 600.0:
                mid_price = round((w1 + w2) / 2, 1)
                walls.append({
                    "price": mid_price,
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0
                })
                
    # 4. Market Gamma Curve
    sweep_prices = np.linspace(current_fxi * 0.90, current_fxi * 1.10, 200)
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
    
    max_gamma_idx = np.argmax(gex_values)
    max_gamma_china = float(prices[max_gamma_idx]) * conv_ratio
    
    min_gamma_idx = np.argmin(gex_values)
    min_gamma_china = float(prices[min_gamma_idx]) * conv_ratio
    
    flip_fxi = None
    best_flip_dist = float('inf')
    
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i+1] < 0:
            x0, x1 = prices[i], prices[i+1]
            y0, y1 = gex_values[i], gex_values[i+1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            
            dist = abs(cross - current_fxi)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_fxi = float(cross)
                
    if flip_fxi is None:
        flip_fxi = current_fxi
        
    flip_china = flip_fxi * conv_ratio
    
    walls.append({
        "price": round(max_gamma_china, 1),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[max_gamma_idx])
    })
    
    walls.append({
        "price": round(min_gamma_china, 1),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": float(gex_values[min_gamma_idx])
    })
    
    walls.append({
        "price": round(flip_china, 1),
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
    report_file = os.path.join(docs_dir, "DAILY_REPORT_CHINA.txt")
    
    current_china_price = current_fxi * conv_ratio
    is_positive_gamma = current_fxi >= flip_fxi
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if is_positive_gamma else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if is_positive_gamma else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write("  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - CHINA 50 / CHINA50\n")
        f.write(f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}\n")
        f.write("=================================================================\n\n")
        f.write("[+] STATUS DO MERCADO (REGIME GEX):\n")
        f.write(f"    China 50 Spot/CFD Atual:  {current_china_price:.1f}  (FXI Spot: ${current_fxi:.2f})\n")
        f.write(f"    Gamma Flip Point:         {flip_china:.1f}\n")
        f.write(f"    Regime de Gamma:          {regime}\n")
        f.write(f"    Vies do Dia:              {bias}\n\n")
        f.write("[+] NIVEIS CRITICOS DA CURVA GAMMA:\n")
        f.write(f"    [-] MIN GAMMA (Piso de Queda Livre)   : CHINA50 {min_gamma_china:.1f}\n")
        f.write(f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : CHINA50 {flip_china:.1f}\n")
        f.write(f"    [+] MAX GAMMA (Teto de Exaustao)      : CHINA50 {max_gamma_china:.1f}\n")
        
    print(f"      Relatório escrito em: {report_file}")
    
    tv_file = os.path.join(docs_dir, "jumba_tradingview.pine")
    save_walls_to_cache(walls, ticker="CHINA_FXI", ref_date=today)
    export_unified_tradingview(output_path=tv_file)
    
    print("\n" + "=" * 60)
    print("  Pipeline China Large-Cap / CHINA50 concluído com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_china_gex_pipeline()
