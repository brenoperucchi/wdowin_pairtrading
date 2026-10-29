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


def get_dow_spot_and_chain():
    """
    Obtém as grades de opções completas da CBOE para DIA e _DJX (Multi-Vencimento até 45 dias).
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar DIA + _DJX (Multi-Vencimento)...")
    dia_spot, df_dia, ref_dia = fetch_cboe_chain("DIA", max_dte=45, strike_range_pct=0.08, default_iv=0.14)
    djx_spot, df_djx, ref_djx = fetch_cboe_chain("_DJX", max_dte=45, strike_range_pct=0.08, default_iv=0.14)

    if (df_dia is None or df_dia.empty) and (df_djx is None or df_djx.empty):
        print("      ERRO: Não foi possível obter opções de DIA nem _DJX da CBOE.")
        return None, None, None, None

    if not dia_spot and djx_spot:
        dia_spot = djx_spot
    if not djx_spot and dia_spot:
        djx_spot = dia_spot

    frames = []
    if df_dia is not None and not df_dia.empty:
        df_dia = df_dia.copy()
        df_dia["mult"] = 100.0
        frames.append(df_dia)
        print(f"      DIA  CBOE: Spot ${dia_spot:.2f} | {len(df_dia)} séries ativas | OI Total: {int(df_dia['oi'].sum()):,d}")

    if df_djx is not None and not df_djx.empty:
        df_djx = df_djx.copy()
        djx_dia_ratio = dia_spot / djx_spot if djx_spot > 0 else 1.0
        df_djx["strike"] = df_djx["strike"] * djx_dia_ratio
        df_djx["mult"] = 100.0 / djx_dia_ratio
        frames.append(df_djx)
        print(f"      _DJX CBOE: Spot {djx_spot:.2f} | {len(df_djx)} séries ativas | OI Total: {int(df_djx['oi'].sum()):,d}")

    df_combined = pd.concat(frames, ignore_index=True)
    ref_str = ref_dia or ref_djx
    current_spot = dia_spot * 100.0
    print(f"      Grade consolidada (DIA + _DJX): {len(df_combined)} séries | Ref: {ref_str}")
    return current_spot, dia_spot, df_combined, ref_str


def run_dow_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do Dow Jones (DIA + _DJX -> US30).
    """
    print("=" * 60)
    print("  GEX ENGINE - Dow Jones / US30 Pipeline (CBOE DIA + _DJX)")
    print("=" * 60)

    current_spot, current_dia, df_options, expiry_str = get_dow_spot_and_chain()
    if df_options is None or df_options.empty:
        print("ERRO: Não foi possível obter os dados de opções.")
        sys.exit(1)

    today = datetime.date.today()
    r = 0.0515
    q = 0.0190

    fallback_ratio = 100.0
    conv_ratio, price_dow_mt5, ratio_msg = get_synchronized_etf_ratio(current_dia, "US30", fallback_ratio)
    if price_dow_mt5 and price_dow_mt5 > 0:
        current_spot = price_dow_mt5

    print(f"\n[2/5] Parâmetros de precificação Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      r = {r*100:.2f}% | q = {q*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (DIA + _DJX) e gerando Jumba Walls...")
    df_options["strike_round"] = (df_options["strike"] / 1.0).round() * 1.0

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    mult = df_options["mult"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_dia / K) + (r - q + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_bs = (np.exp(-q * T) * pdf_d1) / (current_dia * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_bs * (current_dia ** 2) * 0.01 * mult * sign

    gex_per_strike = {}
    for strike_dia, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        strike_dow = float(strike_dia) * conv_ratio
        gex_per_strike[strike_dow] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
            "strike_dia": float(strike_dia),
        }

    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - (current_dia * conv_ratio)))
    atm_idx = all_strikes.index(atm_strike)

    num_walls = 16
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(all_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    selected_strikes = all_strikes[start_idx:end_idx]

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
    for strike_dow in selected_strikes:
        info = gex_per_strike[strike_dow]
        price_futures = info["strike_dia"] * conv_ratio
        walls_basic.append({
            "price": round(price_futures, 2),
            "type": "Wall",
            "width": width_map.get(strike_dow, 1),
            "style": 0,
            "strike_spy": int(round(info["strike_dia"])),
            "gex": info["gex_net"],
        })

    walls = sorted(walls_basic, key=lambda x: x["price"])

    # 4. Calcular Market Gamma Curve
    sweep_prices = np.linspace(current_dia * 0.92, current_dia * 1.08, 250)
    max_dia, max_val, min_dia, min_val, flip_dia = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=r, q=q
    )

    max_gamma_dow = max_dia * conv_ratio
    min_gamma_dow = min_dia * conv_ratio
    flip_dow = flip_dia * conv_ratio

    walls.append({
        "price": round(max_gamma_dow, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_dow, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_dow, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
    })

    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_DOW.txt")

    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_spot >= flip_dow else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_spot >= flip_dow else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = (
        "Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
        if current_spot >= flip_dow else
        "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta."
    )

    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - DOW JONES / US30 (CBOE)",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    US30 Spot Atual:    {current_spot:.2f}  (DIA: ${current_dia:.2f})",
        f"    Gamma Flip Point:   {flip_dow:.2f}",
        f"    Regime de Gamma:    {regime}",
        f"    Vies do Dia:        {bias}",
        f"    Dinamica de MM:     {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : US30 {min_gamma_dow:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : US30 {flip_dow:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : US30 {max_gamma_dow:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        "  TIPO       | STRIKE DIA   | EQUIVALENTE US30   | GEX NET ($ Milhoes)    | LARGURA",
        "-" * 65,
    ]

    walls_for_report = sorted([w for w in walls if w["type"] == "Wall"], key=lambda x: x["price"], reverse=True)
    for w in walls_for_report:
        oi_m = w["gex"] / 1e6
        report_lines.append(f"  {w['type']:<10} | ${w['strike_spy']:<12.1f} | {w['price']:<18.2f} | $ {oi_m:>17.2f}M | Width {w['width']}")

    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o Open Interest consolidado da CBOE (DIA + _DJX).",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65,
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"      Relatório escrito em: {report_path}")

    save_walls_to_cache(walls, ticker="dow_us30", ref_date=today.isoformat(), current_price=current_spot)
    tv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    export_unified_tradingview(output_path=tv_file)

    print("\n" + "=" * 60)
    print("  Pipeline Dow/US30 concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_dow_gex_pipeline()
