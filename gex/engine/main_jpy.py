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


def get_fxy_spot_and_chain():
    """
    Obtém o preço spot e a grade completa de opções do ETF FXY na CBOE (Multi-Vencimento até 120 dias).
    NOTA: FXY rastreia o Yen vs USD (inversamente correlacionado ao USDJPY).
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar USD/JPY (FXY Multi-Vencimento)...")
    current_fxy, df_options, ref_str = fetch_cboe_chain("FXY", max_dte=120, strike_range_pct=0.14, default_iv=0.10)
    if df_options is None or df_options.empty or not current_fxy:
        print("      ERRO: Não foi possível obter opções de FXY da CBOE.")
        return None, None, None, None, None

    # Estimativa inicial (substituída pelo ratio sincronizado do MT5 ou pelo último ratio válido em cache)
    current_usdjpy = 157.85
    conv_factor = current_usdjpy / current_fxy if current_fxy > 0 else 2.71
    print(f"      FXY CBOE: Spot ${current_fxy:.2f} | {len(df_options)} séries ativas | OI Total: {int(df_options['oi'].sum()):,d}")
    print(f"      Referência: {ref_str}")
    return current_usdjpy, current_fxy, df_options, ref_str, conv_factor


def run_jpy_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do USD/JPY (FXY CBOE).
    IMPORTANTE: FXY é inversamente correlacionado ao USDJPY.
      USDJPY = K_constant / FXY_price  =>  strike_jpy = current_usdjpy * (current_fxy / strike_fxy)
      Invertemos o sinal do GEX (Calls no FXY = alta do Yen = queda do USDJPY).
    """
    print("=" * 60)
    print("  GEX ENGINE - USD/JPY Pipeline (CBOE FXY Multi-Vencimento)")
    print("=" * 60)

    current_usdjpy, current_fxy, df_options, expiry_str, conv_factor = get_fxy_spot_and_chain()
    if df_options is None or df_options.empty:
        print("ERRO: Não foi possível obter os dados de opções.")
        sys.exit(1)

    fallback_ratio = conv_factor
    conv_ratio, price_jpy_mt5, ratio_msg = get_synchronized_etf_ratio(current_fxy, "USDJPY", fallback_ratio)
    if price_jpy_mt5 and price_jpy_mt5 > 0:
        current_usdjpy = price_jpy_mt5
        conv_factor = conv_ratio

    # Preço USDJPY sincronizado com o fechamento do FXY:
    sync_usdjpy = current_fxy * conv_factor

    today = datetime.date.today()
    rd = 0.0515
    rf = 0.0050

    print(f"\n[2/5] Parâmetros de Garman-Kohlhagen (Multi-Vencimento CBOE):")
    print(f"      Referência: {expiry_str}")
    print(f"      rd (USD) = {rd*100:.2f}% | rf (JPY) = {rf*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (FXY) e gerando Jumba Walls...")
    df_options["strike_round"] = (df_options["strike"] / 0.50).round() * 0.50

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)
    multiplier = 100.0

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_fxy / K) + (rd - rf + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_gk = (np.exp(-rf * T) * pdf_d1) / (current_fxy * sigma * sqrt_T)

    # Inverter sinal para referencial USDJPY (-sign)
    df_options["gex_contrib"] = -oi * gamma_gk * (current_fxy ** 2) * 0.01 * multiplier * sign

    gex_per_strike = {}
    for strike_fxy, group in df_options.groupby("strike_round"):
        if strike_fxy <= 0:
            continue
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        # Conversão inversa exata: se FXY sobe (strike_fxy > current_fxy), USDJPY cai (< sync_usdjpy)
        strike_jpy = float(sync_usdjpy * (current_fxy / float(strike_fxy)))
        gex_per_strike[strike_jpy] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
            "strike_fxy": float(strike_fxy),
        }

    all_strikes = sorted(gex_per_strike.keys())
    lower_bound = sync_usdjpy * 0.92
    upper_bound = sync_usdjpy * 1.08
    nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    if len(nearby_strikes) < 6:
        lower_bound = sync_usdjpy * 0.85
        upper_bound = sync_usdjpy * 1.15
        nearby_strikes = [s for s in all_strikes if lower_bound <= s <= upper_bound]

    num_walls = 16
    nearby_strikes.sort(key=lambda s: abs(s - sync_usdjpy))
    selected_strikes = sorted(nearby_strikes[:num_walls])

    print(f"      Strikes selecionados: {len(selected_strikes)} dentro de [{lower_bound:.3f}, {upper_bound:.3f}]")

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
    for strike_jpy in selected_strikes:
        info = gex_per_strike[strike_jpy]
        walls_basic.append({
            "price": round(strike_jpy, 3),
            "type": "Wall",
            "width": width_map.get(strike_jpy, 1),
            "style": 0,
            "strike_spy": round(info["strike_fxy"], 2),
            "gex": info["gex_net"],
        })

    walls_basic_sorted = sorted(walls_basic, key=lambda x: x["price"])
    walls = []
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            w1 = walls_basic_sorted[i]["price"]
            w2 = walls_basic_sorted[i + 1]["price"]
            if (w2 - w1) <= 3.50:
                mid_price = round((w1 + w2) / 2, 3)
                walls.append({
                    "price": mid_price,
                    "type": "MidWall",
                    "width": 1,
                    "style": 0,
                    "gex": 0.0,
                })

    # 4. Calcular Market Gamma Curve (com sinal invertido para USDJPY)
    sweep_prices = np.linspace(current_fxy * 0.90, current_fxy * 1.10, 250)
    max_fxy, max_val, min_fxy, min_val, flip_fxy = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=rd, q=rf, multiplier=multiplier, invert_sign=True
    )

    max_gamma_jpy = sync_usdjpy * (current_fxy / max_fxy)
    min_gamma_jpy = sync_usdjpy * (current_fxy / min_fxy)
    flip_jpy = sync_usdjpy * (current_fxy / flip_fxy)

    walls.append({
        "price": round(max_gamma_jpy, 3),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_jpy, 3),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_jpy, 3),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
    })

    print(f"\n[4/5] Exportando indicadores e relatórios...")
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_JPY.txt")

    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_usdjpy >= flip_jpy else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_usdjpy >= flip_jpy else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = (
        "Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
        if current_usdjpy >= flip_jpy else
        "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta."
    )

    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - USD/JPY (CBOE)",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    USDJPY Spot Atual:  {current_usdjpy:.3f}  (FXY: ${current_fxy:.2f})",
        f"    Gamma Flip Point:   {flip_jpy:.3f}",
        f"    Regime de Gamma:    {regime}",
        f"    Vies do Dia:        {bias}",
        f"    Dinamica de MM:     {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : USDJPY {min_gamma_jpy:.3f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : USDJPY {flip_jpy:.3f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : USDJPY {max_gamma_jpy:.3f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE FXY   | EQUIVALENTE USDJPY | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65,
    ]

    walls_for_report = sorted([w for w in walls if w["type"] == "Wall"], key=lambda x: x["price"], reverse=True)
    for w in walls_for_report:
        oi_m = w["gex"] / 1e6
        fxy_strike = w.get("strike_spy", 0)
        report_lines.append(f"  {w['type']:<10} | ${fxy_strike:<12.2f} | {w['price']:<18.3f} | $ {oi_m:>17.2f}M | Width {w['width']}")

    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o Open Interest consolidado da CBOE no ETF FXY.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65,
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"      Relatório escrito em: {report_path}")

    save_walls_to_cache(walls, ticker="usd_jpy", ref_date=today.isoformat(), current_price=current_usdjpy)
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline USD/JPY concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_jpy_gex_pipeline()
