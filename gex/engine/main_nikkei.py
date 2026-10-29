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


def get_nikkei_spot_and_chain():
    """
    Obtém o preço spot e a grade completa de opções do ETF EWJ na CBOE (Multi-Vencimento até 90 dias).
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar Nikkei 225 (EWJ Multi-Vencimento)...")
    current_ewj, df_options, ref_str = fetch_cboe_chain("EWJ", max_dte=90, strike_range_pct=0.12, default_iv=0.20)
    if df_options is None or df_options.empty or not current_ewj:
        print("      ERRO: Não foi possível obter opções de EWJ da CBOE.")
        return None, None, None, None

    current_spot = current_ewj * 675.0
    print(f"      EWJ CBOE: Spot ${current_ewj:.2f} | {len(df_options)} séries ativas | OI Total: {int(df_options['oi'].sum()):,d}")
    print(f"      Referência: {ref_str}")
    return current_spot, current_ewj, ref_str, df_options


def run_nikkei_gex_pipeline():
    print("=" * 60)
    print("  GEX ENGINE - Nikkei 225 / JP225 Pipeline (CBOE EWJ Multi-Vencimento)")
    print("=" * 60)

    current_spot, current_ewj, expiry_str, df_options = get_nikkei_spot_and_chain()
    if df_options is None or df_options.empty:
        print("      ERRO: Não foi possível obter a grade de opções de EWJ.")
        sys.exit(1)

    today = datetime.date.today()
    rd = 0.0515
    rf = 0.0050

    conv_ratio, price_jp_mt5, ratio_msg = get_synchronized_etf_ratio(
        etf_spot_price=current_ewj,
        symbol_mt5="JP225",
        fallback_ratio=current_spot / current_ewj,
    )
    current_jp_price = price_jp_mt5 if (price_jp_mt5 and price_jp_mt5 > 0) else current_ewj * conv_ratio

    print(f"\n[2/5] Parâmetros de precificação Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      rd = {rd*100:.2f}% | rf = {rf*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (EWJ) e gerando Jumba Walls...")
    df_options["strike_round"] = (df_options["strike"] / 1.0).round() * 1.0

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)
    multiplier = 100.0

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_ewj / K) + (rd - rf + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_gk = (np.exp(-rf * T) * pdf_d1) / (current_ewj * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_gk * (current_ewj ** 2) * 0.01 * multiplier * sign

    gex_per_strike = {}
    for strike_ewj, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        strike_jp = float(strike_ewj) * conv_ratio
        gex_per_strike[strike_jp] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
            "strike_ewj": float(strike_ewj),
        }

    all_strikes = sorted(gex_per_strike.keys())
    current_jp_approx = current_ewj * conv_ratio

    range_pct = 0.08
    lower_bound = current_jp_approx * (1 - range_pct)
    upper_bound = current_jp_approx * (1 + range_pct)
    filtered_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    if len(filtered_strikes) < 6:
        filtered_strikes = sorted(all_strikes, key=lambda s: abs(s - current_jp_approx))[:14]
        filtered_strikes = sorted(filtered_strikes)

    atm_strike = min(filtered_strikes, key=lambda s: abs(s - current_jp_approx))
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
    for strike_jp in selected_strikes:
        info = gex_per_strike[strike_jp]
        price_futures = info["strike_ewj"] * conv_ratio
        walls_basic.append({
            "price": round(price_futures, 1),
            "type": "Wall",
            "width": width_map.get(strike_jp, 1),
            "style": 0,
            "strike_spy": float(info["strike_ewj"]),
            "gex": info["gex_net"],
        })

    walls = sorted(walls_basic, key=lambda x: x["price"])

    # 4. Market Gamma Curve
    sweep_prices = np.linspace(current_ewj * 0.90, current_ewj * 1.10, 250)
    max_ewj, max_val, min_ewj, min_val, flip_ewj = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=rd, q=rf, multiplier=multiplier
    )

    max_gamma_jp = max_ewj * conv_ratio
    min_gamma_jp = min_ewj * conv_ratio
    flip_jp = flip_ewj * conv_ratio

    walls.append({
        "price": round(max_gamma_jp, 1),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_jp, 1),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_jp, 1),
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
    report_file = os.path.join(docs_dir, "DAILY_REPORT_NIKKEI.txt")

    is_positive_gamma = current_jp_price >= flip_jp
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if is_positive_gamma else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if is_positive_gamma else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write("  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - NIKKEI 225 / JP225 (CBOE)\n")
        f.write(f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}\n")
        f.write("=================================================================\n\n")
        f.write("[+] STATUS DO MERCADO (REGIME GEX):\n")
        f.write(f"    Nikkei 225 Spot/CFD Atual: {current_jp_price:.1f}  (EWJ Spot: ${current_ewj:.2f})\n")
        f.write(f"    Gamma Flip Point:         {flip_jp:.1f}\n")
        f.write(f"    Regime de Gamma:          {regime}\n")
        f.write(f"    Vies do Dia:              {bias}\n\n")
        f.write("[+] NIVEIS CRITICOS DA CURVA GAMMA:\n")
        f.write(f"    [-] MIN GAMMA (Piso de Queda Livre)   : JP225 {min_gamma_jp:.1f}\n")
        f.write(f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : JP225 {flip_jp:.1f}\n")
        f.write(f"    [+] MAX GAMMA (Teto de Exaustao)      : JP225 {max_gamma_jp:.1f}\n")

    print(f"      Relatório escrito em: {report_file}")

    tv_file = os.path.join(docs_dir, "jumba_tradingview.pine")
    save_walls_to_cache(walls, ticker="NIKKEI_JP225", ref_date=today, current_price=current_jp_price)
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline Nikkei 225 / JP225 concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_nikkei_gex_pipeline()
