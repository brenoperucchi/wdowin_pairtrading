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


def get_rut_and_iwm_combined():
    """
    Obtém as grades de opções completas da CBOE para o índice institucional _RUT
    e para o ETF IWM (agregando múltiplos vencimentos até 45 dias),
    normalizando tudo na escala do Russell 2000 (_RUT).
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar _RUT + IWM (Multi-Vencimento)...")
    rut_spot, df_rut, ref_rut = fetch_cboe_chain("_RUT", max_dte=45, strike_range_pct=0.08, default_iv=0.22)
    iwm_spot, df_iwm, ref_iwm = fetch_cboe_chain("IWM", max_dte=45, strike_range_pct=0.08, default_iv=0.22)

    if (df_rut is None or df_rut.empty) and (df_iwm is None or df_iwm.empty):
        print("      ERRO: Não foi possível obter opções de _RUT nem IWM da CBOE.")
        return None, None, None, None

    if not rut_spot and iwm_spot:
        rut_spot = iwm_spot * 10.0
    if not iwm_spot and rut_spot:
        iwm_spot = rut_spot / 10.0

    rut_iwm_ratio = rut_spot / iwm_spot if iwm_spot > 0 else 10.0

    frames = []
    if df_rut is not None and not df_rut.empty:
        df_rut = df_rut.copy()
        df_rut["mult"] = 100.0
        frames.append(df_rut)
        print(f"      _RUT CBOE: Spot {rut_spot:.2f} | {len(df_rut)} séries ativas | OI Total: {int(df_rut['oi'].sum()):,d}")

    if df_iwm is not None and not df_iwm.empty:
        df_iwm = df_iwm.copy()
        df_iwm["strike"] = df_iwm["strike"] * rut_iwm_ratio
        df_iwm["mult"] = 100.0 / rut_iwm_ratio
        frames.append(df_iwm)
        print(f"      IWM  CBOE: Spot ${iwm_spot:.2f} | {len(df_iwm)} séries ativas | OI Total: {int(df_iwm['oi'].sum()):,d}")

    df_combined = pd.concat(frames, ignore_index=True)
    ref_str = ref_rut or ref_iwm
    print(f"      Grade consolidada (_RUT + IWM): {len(df_combined)} séries | Ref: {ref_str}")
    return rut_spot, iwm_spot, ref_str, df_combined


def run_russell_gex_pipeline():
    print("=" * 60)
    print("  GEX ENGINE - Russell 2000 / US2000 Pipeline (CBOE _RUT + IWM)")
    print("=" * 60)

    rut_spot, iwm_spot, expiry_str, df_options = get_rut_and_iwm_combined()
    if df_options is None or df_options.empty:
        print("      ERRO: Não foi possível obter a grade de opções de _RUT/IWM.")
        sys.exit(1)

    today = datetime.date.today()
    r = 0.0515
    q = 0.0120

    conv_ratio, price_rut_mt5, ratio_msg = get_synchronized_etf_ratio(
        etf_spot_price=rut_spot,
        symbol_mt5="US2000",
        fallback_ratio=1.0,
    )
    current_rut = price_rut_mt5 if (price_rut_mt5 and price_rut_mt5 > 0) else rut_spot * conv_ratio
    rut_iwm_ratio = rut_spot / iwm_spot if iwm_spot > 0 else 10.0

    print(f"\n[2/5] Parâmetros de precificação Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      r = {r*100:.2f}% | q = {q*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (_RUT + IWM) e gerando Magic Walls Walls...")
    # Agrupar strikes na escala RUT a cada 10 pontos (~$1.0 no IWM)
    df_options["strike_round"] = (df_options["strike"] / 10.0).round() * 10.0

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    mult = df_options["mult"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)

    sqrt_T = np.sqrt(T)
    d1 = (np.log(rut_spot / K) + (r - q + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_bs = (np.exp(-q * T) * pdf_d1) / (rut_spot * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_bs * (rut_spot ** 2) * 0.01 * mult * sign

    gex_per_strike = {}
    for strike_rut, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        gex_per_strike[float(strike_rut)] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
        }

    # 4. Market Gamma Curve antes de filtrar as Walls para cobrir [MinGamma, MaxGamma] + preço atual
    sweep_prices = np.linspace(rut_spot * 0.92, rut_spot * 1.08, 250)
    max_rut, max_val, min_rut, min_val, flip_rut_base = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=r, q=q
    )

    max_gamma_rut = max_rut * conv_ratio
    min_gamma_rut = min_rut * conv_ratio
    flip_rut = flip_rut_base * conv_ratio

    live_rut_equiv = (current_rut / conv_ratio) if conv_ratio > 0 else rut_spot
    low_ref = min(rut_spot, live_rut_equiv)
    high_ref = max(rut_spot, live_rut_equiv)

    all_strikes = sorted(gex_per_strike.keys())
    lower_bound = min(min_rut - 20.0, low_ref * 0.96)
    upper_bound = max(max_rut + 20.0, high_ref * 1.04)
    filtered_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    if len(filtered_strikes) < 3:
        filtered_strikes = sorted(all_strikes, key=lambda s: abs(s - live_rut_equiv))[:32]
        filtered_strikes = sorted(filtered_strikes)

    center_rut = 0.5 * (low_ref + high_ref)
    atm_strike = min(filtered_strikes, key=lambda s: abs(s - center_rut))
    atm_idx = filtered_strikes.index(atm_strike)

    num_walls = min(36, len(filtered_strikes))
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(filtered_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    selected_strikes = filtered_strikes[start_idx:end_idx]

    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound*conv_ratio:.0f}, {upper_bound*conv_ratio:.0f}]")

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
    for strike_rut in selected_strikes:
        info = gex_per_strike[strike_rut]
        price_futures = strike_rut * conv_ratio
        walls_basic.append({
            "price": round(price_futures, 2),
            "type": "Wall",
            "width": width_map.get(strike_rut, 1),
            "style": 0,
            "strike_spy": round(strike_rut / rut_iwm_ratio, 1),
            "gex": info["gex_net"],
        })

    walls = sorted(walls_basic, key=lambda x: x["price"])

    walls.append({
        "price": round(max_gamma_rut, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_rut, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_rut, 2),
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
    report_file = os.path.join(docs_dir, "DAILY_REPORT_RUSSELL.txt")

    is_positive_gamma = current_rut >= flip_rut
    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if is_positive_gamma else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if is_positive_gamma else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write("  RELATORIO DIARIO DE TENDENCIA E MAGIC WALLS WALLS - RUSSELL 2000 / US2000 (CBOE)\n")
        f.write(f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}\n")
        f.write("=================================================================\n\n")
        f.write("[+] STATUS DO MERCADO (REGIME GEX):\n")
        f.write(f"    Russell 2000 Spot/CFD Atual: {current_rut:.2f}  (RUT: {rut_spot:.2f} | IWM: ${iwm_spot:.2f})\n")
        f.write(f"    Gamma Flip Point:           {flip_rut:.2f}\n")
        f.write(f"    Regime de Gamma:            {regime}\n")
        f.write(f"    Vies do Dia:                {bias}\n\n")
        f.write("[+] NIVEIS CRITICOS DA CURVA GAMMA:\n")
        f.write(f"    [-] MIN GAMMA (Piso de Queda Livre)   : US2000 {min_gamma_rut:.2f}\n")
        f.write(f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : US2000 {flip_rut:.2f}\n")
        f.write(f"    [+] MAX GAMMA (Teto de Exaustao)      : US2000 {max_gamma_rut:.2f}\n")

    print(f"      Relatório escrito em: {report_file}")

    tv_file = os.path.join(docs_dir, "magicwalls_tradingview.pine")
    save_walls_to_cache(walls, ticker="RUSSELL_US2000", ref_date=today, current_price=current_rut)
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline Russell 2000 / US2000 concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_russell_gex_pipeline()
