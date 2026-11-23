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


def get_gold_spot_and_chain():
    """
    Obtém o preço spot e a grade completa de opções do ETF GLD na CBOE (Multi-Vencimento até 45 dias).
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar Ouro (GLD Multi-Vencimento)...")
    current_gld, df_options, ref_str = fetch_cboe_chain("GLD", max_dte=45, strike_range_pct=0.10, default_iv=0.16)
    if df_options is None or df_options.empty or not current_gld:
        print("      ERRO: Não foi possível obter opções de GLD da CBOE.")
        return None, None, None, None

    current_spot = current_gld * 10.88
    print(f"      GLD CBOE: Spot ${current_gld:.2f} | {len(df_options)} séries ativas | OI Total: {int(df_options['oi'].sum()):,d}")
    print(f"      Referência: {ref_str}")
    return current_spot, current_gld, df_options, ref_str


def run_gold_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do Ouro (GLD CBOE -> XAUUSD).
    """
    print("=" * 60)
    print("  GEX ENGINE - Gold / XAUUSD Pipeline (CBOE GLD Multi-Vencimento)")
    print("=" * 60)

    current_spot, current_gld, df_options, expiry_str = get_gold_spot_and_chain()
    if df_options is None or df_options.empty:
        print("ERRO: Não foi possível obter os dados de opções.")
        sys.exit(1)

    today = datetime.date.today()
    r = 0.0515

    fallback_ratio = current_spot / current_gld if current_gld > 0 else 10.88
    conv_ratio, price_xau_mt5, ratio_msg = get_synchronized_etf_ratio(current_gld, "XAUUSD", fallback_ratio)
    if price_xau_mt5 and price_xau_mt5 > 0:
        current_spot = price_xau_mt5

    print(f"\n[2/5] Parâmetros de precificação Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      r = {r*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (GLD) e gerando Magic Walls Walls...")
    # Agrupar strikes do GLD por $2.0 (~$22 no XAUUSD) para maior resolução
    df_options["strike_round"] = (df_options["strike"] / 2.0).round() * 2.0

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)
    multiplier = 100.0

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_gld / K) + (r + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_bs = pdf_d1 / (current_gld * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_bs * (current_gld ** 2) * 0.01 * multiplier * sign

    gex_per_strike = {}
    for strike_gld, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        strike_gold = float(strike_gld) * conv_ratio
        gex_per_strike[strike_gold] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
            "strike_gld": float(strike_gld),
        }

    all_strikes = sorted(gex_per_strike.keys())
    center_gold = current_gld * conv_ratio
    lower_bound = center_gold * 0.95
    upper_bound = center_gold * 1.05
    nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    if len(nearby_strikes) < 8:
        lower_bound = center_gold * 0.90
        upper_bound = center_gold * 1.10
        nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    num_walls = 16
    nearby_strikes.sort(key=lambda s: abs(s - center_gold))
    selected_strikes = sorted(nearby_strikes[:num_walls])

    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [${lower_bound:.2f}, ${upper_bound:.2f}]")

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
    for strike_gold in selected_strikes:
        info = gex_per_strike[strike_gold]
        walls_basic.append({
            "price": round(strike_gold, 2),
            "type": "Wall",
            "width": width_map.get(strike_gold, 1),
            "style": 0,
            "strike_spy": int(round(info["strike_gld"])),
            "gex": info["gex_net"],
        })

    walls_basic_sorted = sorted(walls_basic, key=lambda x: x["price"])
    walls = []
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]["price"]
            w2 = walls_basic_sorted[i + 1]["price"]
            mid_price = round((w1 + w2) / 2, 2)
            walls.append({
                "price": mid_price,
                "type": "MidWall",
                "width": 1,
                "style": 0,
                "gex": 0.0,
            })

    # 4. Calcular Market Gamma Curve
    sweep_prices = np.linspace(current_gld * 0.90, current_gld * 1.10, 250)
    max_gld, max_val, min_gld, min_val, flip_gld = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=r, q=0.0, multiplier=multiplier
    )

    max_gamma_gold = max_gld * conv_ratio
    min_gamma_gold = min_gld * conv_ratio
    flip_gold = flip_gld * conv_ratio

    walls.append({
        "price": round(max_gamma_gold, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_gold, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_gold, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
    })

    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_GOLD.txt")

    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_spot >= flip_gold else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_spot >= flip_gold else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = (
        "Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
        if current_spot >= flip_gold else
        "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta."
    )

    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E MAGIC WALLS WALLS - GOLD / XAUUSD (CBOE)",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    XAUUSD Spot Atual: ${current_spot:.2f}  (GLD: ${current_gld:.2f})",
        f"    Gamma Flip Point:  ${flip_gold:.2f}",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : XAUUSD ${min_gamma_gold:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : XAUUSD ${flip_gold:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : XAUUSD ${max_gamma_gold:.2f}",
        "",
        "[+] MAGIC WALLS WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE GLD   | EQUIVALENTE XAUUSD | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65,
    ]

    walls_for_report = sorted([w for w in walls if w["type"] == "Wall"], key=lambda x: x["price"], reverse=True)
    for w in walls_for_report:
        oi_m = w["gex"] / 1e6
        report_lines.append(f"  {w['type']:<10} | ${w['strike_spy']:<12.1f} | {w['price']:<18.2f} | $ {oi_m:>17.2f}M | Width {w['width']}")

    report_lines.extend([
        "-" * 65,
        "Nota: As Magic Walls Walls acima mapeiam o Open Interest consolidado da CBOE no ETF GLD.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65,
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"      Relatório escrito em: {report_path}")

    save_walls_to_cache(walls, ticker="gold_xau", ref_date=today.isoformat(), current_price=current_spot)
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "magicwalls_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline Gold/XAUUSD concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_gold_gex_pipeline()
