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


def get_uup_spot_and_chain():
    """
    Obtém o preço spot e a grade completa de opções do ETF UUP na CBOE (Multi-Vencimento até 120 dias).
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar DXY (UUP Multi-Vencimento)...")
    current_uup, df_options, ref_str = fetch_cboe_chain("UUP", max_dte=120, strike_range_pct=0.14, default_iv=0.08)
    if df_options is None or df_options.empty or not current_uup:
        print("      ERRO: Não foi possível obter opções de UUP da CBOE.")
        return None, None, None, None, None

    current_dxy = current_uup * 3.55
    conv_factor = current_dxy / current_uup if current_uup > 0 else 3.55
    print(f"      UUP CBOE: Spot ${current_uup:.2f} | {len(df_options)} séries ativas | OI Total: {int(df_options['oi'].sum()):,d}")
    print(f"      Referência: {ref_str}")
    return current_dxy, current_uup, df_options, ref_str, conv_factor


def run_dxy_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do DXY / Dollar Index (UUP CBOE).
    """
    print("=" * 60)
    print("  GEX ENGINE - DXY / Dollar Index Pipeline (CBOE UUP Multi-Vencimento)")
    print("=" * 60)

    current_dxy, current_uup, df_options, expiry_str, conv_factor = get_uup_spot_and_chain()
    if df_options is None or df_options.empty:
        print("ERRO: Não foi possível obter os dados de opções.")
        sys.exit(1)

    conv_ratio, price_dxy_mt5, ratio_msg = get_synchronized_etf_ratio(current_uup, "USDX", conv_factor)
    if price_dxy_mt5 and price_dxy_mt5 > 0:
        current_dxy = price_dxy_mt5
        conv_factor = conv_ratio

    today = datetime.date.today()
    r = 0.0515
    q = 0.0

    print(f"\n[2/5] Parâmetros de precificação Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      r = {r*100:.2f}% | Multiplicador UUP->DXY: {conv_factor:.6f}")

    print(f"\n[3/5] Calculando GEX Institucional (UUP) e gerando Jumba Walls...")
    df_options["strike_round"] = (df_options["strike"] / 0.50).round() * 0.50

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)
    multiplier = 100.0

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_uup / K) + (r - q + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_bs = (np.exp(-q * T) * pdf_d1) / (current_uup * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_bs * (current_uup ** 2) * 0.01 * multiplier * sign

    gex_per_strike = {}
    for strike_uup, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        strike_dxy = float(strike_uup) * conv_factor
        gex_per_strike[strike_dxy] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
            "strike_uup": float(strike_uup),
        }

    all_strikes = sorted(gex_per_strike.keys())
    center_dxy = current_uup * conv_factor
    lower_bound = center_dxy * 0.92
    upper_bound = center_dxy * 1.08
    nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    if len(nearby_strikes) < 4:
        lower_bound = center_dxy * 0.85
        upper_bound = center_dxy * 1.15
        nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    num_walls = 16
    nearby_strikes.sort(key=lambda s: abs(s - center_dxy))
    selected_strikes = sorted(nearby_strikes[:num_walls])

    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound:.2f}, {upper_bound:.2f}]")

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
    for strike_dxy in selected_strikes:
        info = gex_per_strike[strike_dxy]
        walls_basic.append({
            "price": round(strike_dxy, 2),
            "type": "Wall",
            "width": width_map.get(strike_dxy, 1),
            "style": 0,
            "strike_spy": round(info["strike_uup"], 2),
            "gex": info["gex_net"],
        })

    walls_basic_sorted = sorted(walls_basic, key=lambda x: x["price"])
    walls = []
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            mid_price = (walls_basic_sorted[i]["price"] + walls_basic_sorted[i + 1]["price"]) / 2
            walls.append({
                "price": round(mid_price, 2),
                "type": "MidWall",
                "width": 1,
                "style": 0,
                "gex": 0.0,
            })

    # 4. Calcular Market Gamma Curve
    sweep_prices = np.linspace(current_uup * 0.92, current_uup * 1.08, 250)
    max_uup, max_val, min_uup, min_val, flip_uup = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=r, q=q, multiplier=multiplier
    )

    max_gamma_dxy = max_uup * conv_factor
    min_gamma_dxy = min_uup * conv_factor
    flip_dxy = flip_uup * conv_factor

    walls.append({
        "price": round(max_gamma_dxy, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_dxy, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_dxy, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
    })

    print(f"\n[4/5] Exportando indicadores e relatórios...")
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_DXY.txt")

    save_walls_to_cache(walls, ticker="dxy_uup", ref_date=today.isoformat(), current_price=current_dxy)
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline DXY concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_dxy_gex_pipeline()
