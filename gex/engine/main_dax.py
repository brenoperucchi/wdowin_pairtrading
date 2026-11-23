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


def get_dax_spot_and_chain():
    """
    Obtém as grades de opções completas da CBOE para EWG (Alemanha) + FEZ (Euro Stoxx 50)
    com agregação Multi-Vencimento até 120 dias, normalizadas na escala do EWG.
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar DAX 40 (EWG + FEZ Multi-Vencimento)...")
    current_ewg, df_ewg, ref_ewg = fetch_cboe_chain("EWG", max_dte=120, strike_range_pct=0.14, default_iv=0.18)
    current_fez, df_fez, ref_fez = fetch_cboe_chain("FEZ", max_dte=120, strike_range_pct=0.14, default_iv=0.18)

    if (df_ewg is None or df_ewg.empty) and (df_fez is None or df_fez.empty):
        print("      ERRO: Não foi possível obter opções de EWG nem FEZ da CBOE.")
        return None, None, None, None

    if not current_ewg and current_fez:
        current_ewg = current_fez * 0.78

    frames = []
    if df_ewg is not None and not df_ewg.empty:
        df_ewg = df_ewg.copy()
        df_ewg["mult"] = 100.0
        frames.append(df_ewg)
        print(f"      EWG CBOE: Spot ${current_ewg:.2f} | {len(df_ewg)} séries ativas | OI Total: {int(df_ewg['oi'].sum()):,d}")

    if df_fez is not None and not df_fez.empty and current_fez and current_fez > 0:
        df_fez = df_fez.copy()
        ewg_fez_ratio = current_ewg / current_fez
        df_fez["strike"] = df_fez["strike"] * ewg_fez_ratio
        df_fez["mult"] = (100.0 / ewg_fez_ratio) * 0.5  # Peso complementar de 50% para EuroStoxx FEZ
        frames.append(df_fez)
        print(f"      FEZ CBOE: Spot ${current_fez:.2f} | {len(df_fez)} séries ativas | OI Total: {int(df_fez['oi'].sum()):,d}")

    df_combined = pd.concat(frames, ignore_index=True)
    ref_str = ref_ewg or ref_fez
    current_spot = current_ewg * 617.0
    print(f"      Grade consolidada (EWG + FEZ): {len(df_combined)} séries | Ref: {ref_str}")
    return current_spot, current_ewg, ref_str, df_combined


def run_dax_gex_pipeline():
    print("=" * 60)
    print("  GEX ENGINE - DAX 40 / DE40 Pipeline (CBOE EWG + FEZ)")
    print("=" * 60)

    current_spot, current_ewg, expiry_str, df_options = get_dax_spot_and_chain()
    if df_options is None or df_options.empty:
        print("      ERRO: Não foi possível obter a grade de opções de EWG/FEZ.")
        sys.exit(1)

    today = datetime.date.today()
    rd = 0.0515
    rf = 0.0250

    conv_ratio, price_dax_mt5, ratio_msg = get_synchronized_etf_ratio(
        etf_spot_price=current_ewg,
        symbol_mt5="DE40",
        fallback_ratio=current_spot / current_ewg,
    )
    current_dax_price = price_dax_mt5 if (price_dax_mt5 and price_dax_mt5 > 0) else current_ewg * conv_ratio

    print(f"\n[2/5] Parâmetros de precificação Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      rd = {rd*100:.2f}% | rf = {rf*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (EWG + FEZ) e gerando Magic Walls Walls...")
    # Agrupar strikes na escala EWG a cada $0.50 (~308 pontos no DAX)
    df_options["strike_round"] = (df_options["strike"] / 0.50).round() * 0.50

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    mult = df_options["mult"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_ewg / K) + (rd - rf + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_gk = (np.exp(-rf * T) * pdf_d1) / (current_ewg * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_gk * (current_ewg ** 2) * 0.01 * mult * sign

    gex_per_strike = {}
    for strike_ewg, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        strike_dax = float(strike_ewg) * conv_ratio
        gex_per_strike[strike_dax] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
            "strike_ewg": float(strike_ewg),
        }

    all_strikes = sorted(gex_per_strike.keys())
    current_dax_approx = current_ewg * conv_ratio

    range_pct = 0.08
    lower_bound = current_dax_approx * (1 - range_pct)
    upper_bound = current_dax_approx * (1 + range_pct)
    filtered_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    if len(filtered_strikes) < 6:
        filtered_strikes = sorted(all_strikes, key=lambda s: abs(s - current_dax_approx))[:14]
        filtered_strikes = sorted(filtered_strikes)

    atm_strike = min(filtered_strikes, key=lambda s: abs(s - current_dax_approx))
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
    for strike_dax in selected_strikes:
        info = gex_per_strike[strike_dax]
        price_futures = info["strike_ewg"] * conv_ratio
        walls_basic.append({
            "price": round(price_futures, 2),
            "type": "Wall",
            "width": width_map.get(strike_dax, 1),
            "style": 0,
            "strike_spy": round(float(info["strike_ewg"]), 2),
            "gex": info["gex_net"],
        })

    walls_basic_sorted = sorted(walls_basic, key=lambda x: x["price"])
    walls = []
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]["price"]
            w2 = walls_basic_sorted[i + 1]["price"]
            if (w2 - w1) <= 800.0:
                mid_price = round((w1 + w2) / 2.0, 2)
                walls.append({
                    "price": mid_price,
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0,
                })

    # 4. Market Gamma Curve
    sweep_prices = np.linspace(current_ewg * 0.90, current_ewg * 1.10, 250)
    max_ewg, max_val, min_ewg, min_val, flip_ewg = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=rd, q=rf
    )

    max_gamma_dax = max_ewg * conv_ratio
    min_gamma_dax = min_ewg * conv_ratio
    flip_dax = flip_ewg * conv_ratio

    walls.append({
        "price": round(max_gamma_dax, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_dax, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_dax, 2),
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
    report_file = os.path.join(docs_dir, "DAILY_REPORT_DAX.txt")

    is_positive_gamma = current_dax_price >= flip_dax
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if is_positive_gamma else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if is_positive_gamma else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write("  RELATORIO DIARIO DE TENDENCIA E MAGIC WALLS WALLS - DAX 40 / DE40 (CBOE)\n")
        f.write(f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}\n")
        f.write("=================================================================\n\n")
        f.write("[+] STATUS DO MERCADO (REGIME GEX):\n")
        f.write(f"    DAX 40 Spot/CFD Atual: {current_dax_price:.2f}  (EWG Spot: ${current_ewg:.2f})\n")
        f.write(f"    Gamma Flip Point:     {flip_dax:.2f}\n")
        f.write(f"    Regime de Gamma:      {regime}\n")
        f.write(f"    Vies do Dia:          {bias}\n\n")
        f.write("[+] NIVEIS CRITICOS DA CURVA GAMMA:\n")
        f.write(f"    [-] MIN GAMMA (Piso de Queda Livre)   : DE40 {min_gamma_dax:.2f}\n")
        f.write(f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : DE40 {flip_dax:.2f}\n")
        f.write(f"    [+] MAX GAMMA (Teto de Exaustao)      : DE40 {max_gamma_dax:.2f}\n")

    print(f"      Relatório escrito em: {report_file}")

    tv_file = os.path.join(docs_dir, "magicwalls_tradingview.pine")
    save_walls_to_cache(walls, ticker="DAX_DE40", ref_date=today, current_price=current_dax_price)
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline DAX 40 / DE40 concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_dax_gex_pipeline()
