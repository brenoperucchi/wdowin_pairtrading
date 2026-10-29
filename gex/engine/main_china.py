import datetime
import os
import sys
import numpy as np
import pandas as pd

# Adicionar a pasta raiz ao sys.path para importações locais
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gex.engine.cboe_fetcher import fetch_cboe_chain, compute_multi_expiry_gamma_curve
from gex.engine.tradingview_exporter import save_walls_to_cache, export_unified_tradingview
from gex.engine.mt5_prices import get_synchronized_etf_ratio


def get_china_spot_and_chain():
    """
    Obtém o preço spot e a grade completa de opções do ETF FXI na CBOE (Multi-Vencimento até 90 dias).
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar China 50 (FXI Multi-Vencimento)...")
    current_fxi, df_options, ref_str = fetch_cboe_chain("FXI", max_dte=90, strike_range_pct=0.14, default_iv=0.26)
    if df_options is None or df_options.empty or not current_fxi:
        print("      ERRO: Não foi possível obter opções de FXI da CBOE.")
        return None, None, None, None

    current_spot = current_fxi * 400.0
    print(f"      FXI CBOE: Spot ${current_fxi:.2f} | {len(df_options)} séries ativas | OI Total: {int(df_options['oi'].sum()):,d}")
    print(f"      Referência: {ref_str}")
    return current_spot, current_fxi, ref_str, df_options


def run_china_gex_pipeline():
    print("=" * 60)
    print("  GEX ENGINE - China Large-Cap / CHINA50 Pipeline (CBOE FXI Multi-Vencimento)")
    print("=" * 60)

    current_spot, current_fxi, expiry_str, df_options = get_china_spot_and_chain()
    if df_options is None or df_options.empty:
        print("      ERRO: Não foi possível obter a grade de opções de FXI.")
        sys.exit(1)

    today = datetime.date.today()
    rd = 0.0515
    rf = 0.0150

    conv_ratio, price_china_mt5, ratio_msg = get_synchronized_etf_ratio(
        etf_spot_price=current_fxi,
        symbol_mt5="CHINA50",
        fallback_ratio=400.0,
    )
    current_china_price = price_china_mt5 if (price_china_mt5 and price_china_mt5 > 0) else current_fxi * conv_ratio

    print(f"\n[2/5] Parâmetros de precificação Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      rd = {rd*100:.2f}% | rf = {rf*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (FXI) e gerando Jumba Walls...")
    df_options["strike_round"] = (df_options["strike"] / 0.50).round() * 0.50

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)
    multiplier = 100.0

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_fxi / K) + (rd - rf + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_gk = (np.exp(-rf * T) * pdf_d1) / (current_fxi * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_gk * (current_fxi ** 2) * 0.01 * multiplier * sign

    gex_per_strike = {}
    for strike_fxi, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        strike_china = float(strike_fxi) * conv_ratio
        gex_per_strike[strike_china] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
            "strike_fxi": float(strike_fxi),
        }

    all_strikes = sorted(gex_per_strike.keys())
    current_china_approx = current_fxi * conv_ratio

    range_pct = 0.10
    lower_bound = current_china_approx * (1 - range_pct)
    upper_bound = current_china_approx * (1 + range_pct)
    filtered_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    if len(filtered_strikes) < 6:
        filtered_strikes = sorted(all_strikes, key=lambda s: abs(s - current_china_approx))[:12]
        filtered_strikes = sorted(filtered_strikes)

    atm_strike = min(filtered_strikes, key=lambda s: abs(s - current_china_approx))
    atm_idx = filtered_strikes.index(atm_strike)

    num_walls = min(14, len(filtered_strikes))
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(filtered_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    selected_strikes = filtered_strikes[start_idx:end_idx]

    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound:.0f}, {upper_bound:.0f}]")

    strike_gex_list = [(s, gex_per_strike[s]) for s in selected_strikes]
    sorted_by_gex = sorted(strike_gex_list, key=lambda x: x[1]["abs_gex"], reverse=True)

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
        price_futures = info["strike_fxi"] * conv_ratio
        walls_basic.append({
            "price": round(price_futures, 1),
            "type": "Wall",
            "width": width_map.get(strike_china, 1),
            "style": 0,
            "strike_spy": float(info["strike_fxi"]),
            "gex": info["gex_net"],
        })

    walls_basic_sorted = sorted(walls_basic, key=lambda x: x["price"])
    walls = []
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]["price"]
            w2 = walls_basic_sorted[i + 1]["price"]
            if (w2 - w1) <= 600.0:
                mid_price = round((w1 + w2) / 2, 1)
                walls.append({
                    "price": mid_price,
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0,
                })

    # 4. Market Gamma Curve
    sweep_prices = np.linspace(current_fxi * 0.90, current_fxi * 1.10, 250)
    max_fxi, max_val, min_fxi, min_val, flip_fxi = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=rd, q=rf, multiplier=multiplier
    )

    max_gamma_china = max_fxi * conv_ratio
    min_gamma_china = min_fxi * conv_ratio
    flip_china = flip_fxi * conv_ratio

    walls.append({
        "price": round(max_gamma_china, 1),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_china, 1),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_china, 1),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
        "factor": conv_ratio,
    })

    # 5. Relatório e Exportação
    print("\n[4/5] Exportando indicadores e relatórios...")
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "gex", "docs")
    os.makedirs(docs_dir, exist_ok=True)
    report_file = os.path.join(docs_dir, "DAILY_REPORT_CHINA.txt")

    is_positive_gamma = current_china_price >= flip_china
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if is_positive_gamma else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if is_positive_gamma else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write("  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - CHINA 50 / CHINA50 (CBOE)\n")
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
    save_walls_to_cache(walls, ticker="CHINA_FXI", ref_date=today, current_price=current_china_price)
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline China Large-Cap / CHINA50 concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_china_gex_pipeline()
