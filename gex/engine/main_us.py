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


def get_spx_and_spy_combined():
    """
    Obtém as grades de opções completas da CBOE para o índice institucional _SPX
    e para o ETF SPY (agregando múltiplos vencimentos até 45 dias),
    normalizando tudo na escala do SPX.
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar _SPX + SPY (Multi-Vencimento)...")
    spx_spot, df_spx, ref_spx = fetch_cboe_chain("_SPX", max_dte=45, strike_range_pct=0.08, default_iv=0.16)
    spy_spot, df_spy, ref_spy = fetch_cboe_chain("SPY", max_dte=45, strike_range_pct=0.08, default_iv=0.16)

    if (df_spx is None or df_spx.empty) and (df_spy is None or df_spy.empty):
        print("      ERRO: Não foi possível obter opções de _SPX nem SPY da CBOE.")
        return None, None, None, None

    if not spx_spot and spy_spot:
        spx_spot = spy_spot * 10.0
    if not spy_spot and spx_spot:
        spy_spot = spx_spot / 10.0

    spx_spy_ratio = spx_spot / spy_spot if spy_spot > 0 else 10.0

    frames = []
    if df_spx is not None and not df_spx.empty:
        df_spx = df_spx.copy()
        df_spx["mult"] = 100.0
        frames.append(df_spx)
        print(f"      _SPX CBOE: Spot {spx_spot:.2f} | {len(df_spx)} séries ativas | OI Total: {int(df_spx['oi'].sum()):,d}")

    if df_spy is not None and not df_spy.empty:
        df_spy = df_spy.copy()
        # Converter strike do SPY para equivalente na escala SPX:
        # Como S_spx = S_spy * ratio e Gamma_spx = Gamma_spy / ratio,
        # para manter o mesmo Dollar Gamma (OI * Gamma * S^2 * 0.01 * 100),
        # na escala SPX o multiplicador equivalente é 100 / ratio (~10.0).
        df_spy["strike"] = df_spy["strike"] * spx_spy_ratio
        df_spy["mult"] = 100.0 / spx_spy_ratio
        frames.append(df_spy)
        print(f"      SPY  CBOE: Spot ${spy_spot:.2f} | {len(df_spy)} séries ativas | OI Total: {int(df_spy['oi'].sum()):,d}")

    df_combined = pd.concat(frames, ignore_index=True)
    ref_str = ref_spx or ref_spy
    print(f"      Grade consolidada (_SPX + SPY): {len(df_combined)} séries | Ref: {ref_str}")
    return spx_spot, spy_spot, df_combined, ref_str


def run_us_gex_pipeline():
    """
    Executa o pipeline diário completo para o GEX do SP500 (_SPX + SPY -> US500).
    """
    print("=" * 60)
    print("  GEX ENGINE - S&P 500 / US500 Pipeline (CBOE _SPX + SPY)")
    print("=" * 60)

    spx_spot, spy_spot, df_options, expiry_str = get_spx_and_spy_combined()
    if df_options is None or df_options.empty:
        print("ERRO: Não foi possível obter os dados de opções.")
        sys.exit(1)

    today = datetime.date.today()
    r = 0.0515   # SOFR ~5.15%
    q = 0.0130   # Dividend Yield SPX ~1.30%

    # Sincronização MT5 usando o preço do índice SPX como base (~1.0 ratio com US500)
    conv_ratio, price_es_mt5, ratio_msg = get_synchronized_etf_ratio(spx_spot, "US500", 1.0)
    current_us500 = price_es_mt5 if (price_es_mt5 and price_es_mt5 > 0) else spx_spot * conv_ratio

    print(f"\n[2/5] Parâmetros do Modelo Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      r = {r*100:.2f}% | q = {q*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    # 3. Agrupar strikes na grade de 25 pontos do SPX (ou 10 pontos perto do ATM)
    print(f"\n[3/5] Calculando GEX Institucional (_SPX + SPY) e gerando Jumba Walls...")
    df_options["strike_round"] = (df_options["strike"] / 10.0).round() * 10.0

    # Cálculo vetorizado de GEX por contrato no spot atual do SPX
    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    mult = df_options["mult"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)

    sqrt_T = np.sqrt(T)
    d1 = (np.log(spx_spot / K) + (r - q + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_bs = (np.exp(-q * T) * pdf_d1) / (spx_spot * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_bs * (spx_spot ** 2) * 0.01 * mult * sign

    gex_per_strike = {}
    for strike_spx, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        gex_per_strike[float(strike_spx)] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
        }

    # 4. Calcular Market Gamma Curve (MaxGamma, MinGamma, GammaFlip) antes de filtrar as Walls
    # para garantir que todas as linhas entre MinGamma, preço atual do CFD e MaxGamma sejam incluídas.
    sweep_prices = np.linspace(spx_spot * 0.93, spx_spot * 1.07, 250)
    max_spx, max_val, min_spx, min_val, flip_spx = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=r, q=q
    )

    live_spx_equiv = (current_us500 / conv_ratio) if conv_ratio > 0 else spx_spot
    low_ref = min(spx_spot, live_spx_equiv)
    high_ref = max(spx_spot, live_spx_equiv)

    # Cobrir todo o intervalo entre MinGamma e MaxGamma (+ margem de 20 pts) e pelo menos ±2.5% do spot/CFD
    lower_bound = min(min_spx - 20.0, low_ref * 0.975)
    upper_bound = max(max_spx + 20.0, high_ref * 1.025)
    candidate_strikes = [s for s in sorted(gex_per_strike.keys()) if lower_bound <= s <= upper_bound]
    if len(candidate_strikes) < 16:
        all_s = sorted(gex_per_strike.keys(), key=lambda s: abs(s - live_spx_equiv))
        candidate_strikes = sorted(all_s[:32])

    # Selecionar até 48 strikes cobrindo de MinGamma a MaxGamma centrado entre o spot e o CFD atual
    center_spx = 0.5 * (low_ref + high_ref)
    atm_strike = min(candidate_strikes, key=lambda s: abs(s - center_spx))
    atm_idx = candidate_strikes.index(atm_strike)
    num_walls = min(48, len(candidate_strikes))
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(candidate_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    selected_strikes = candidate_strikes[start_idx:end_idx]

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

    spx_spy_ratio = spx_spot / spy_spot if spy_spot > 0 else 10.0
    walls_basic = []
    for strike_spx in selected_strikes:
        info = gex_per_strike[strike_spx]
        price_es = strike_spx * conv_ratio
        walls_basic.append({
            "price": round(price_es, 2),
            "type": "Wall",
            "width": width_map.get(strike_spx, 1),
            "style": 0,
            "strike_spy": int(round(strike_spx / spx_spy_ratio)),
            "gex": info["gex_net"],
        })

    walls = sorted(walls_basic, key=lambda x: x["price"])

    max_gamma_es = max_spx * conv_ratio
    min_gamma_es = min_spx * conv_ratio
    flip_es = flip_spx * conv_ratio

    walls.append({
        "price": round(max_gamma_es, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_es, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_es, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
    })

    # 5. Exportar Relatório e Indicador
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_US.txt")

    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_us500 >= flip_es else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_us500 >= flip_es else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = (
        "Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
        if current_us500 >= flip_es else
        "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta."
    )

    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - S&P 500 / US500 (CBOE)",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    US500 Atual:       {current_us500:.2f}  (SPX: {spx_spot:.2f} | SPY: ${spy_spot:.2f})",
        f"    Gamma Flip Point:  {flip_es:.2f}",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : US500 {min_gamma_es:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : US500 {flip_es:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : US500 {max_gamma_es:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE SPY':12s} | {'EQUIVALENTE ES':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65,
    ]

    display_walls = [w for w in walls if w["type"] == "Wall"]
    for w in sorted(display_walls, key=lambda x: x["price"], reverse=True):
        width_stars = "*" * w["width"]
        type_str = "WALL " + width_stars
        gex_m = w["gex"] / 1_000_000
        report_lines.append(f"  {type_str:10s} | ${w['strike_spy']:<11.2f} | ES {w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")

    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o Open Interest consolidado da CBOE (_SPX + SPY).",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65,
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"      Relatório escrito em: {report_path}")

    tv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    try:
        save_walls_to_cache(walls, ticker="sp500_es", ref_date=today, current_price=current_us500)
        export_unified_tradingview(output_path=tv_path)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")

    print("\n" + "=" * 60)
    print("  Pipeline US concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_us_gex_pipeline()
