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


def get_ndx_and_qqq_combined():
    """
    Obtém as grades de opções completas da CBOE para o índice institucional _NDX
    e para o ETF QQQ (agregando múltiplos vencimentos até 45 dias),
    normalizando tudo na escala do NDX.
    """
    print("[1/5] Conectando à API Oficial da CBOE para buscar _NDX + QQQ (Multi-Vencimento)...")
    ndx_spot, df_ndx, ref_ndx = fetch_cboe_chain("_NDX", max_dte=45, strike_range_pct=0.08, default_iv=0.20)
    qqq_spot, df_qqq, ref_qqq = fetch_cboe_chain("QQQ", max_dte=45, strike_range_pct=0.08, default_iv=0.20)

    if (df_ndx is None or df_ndx.empty) and (df_qqq is None or df_qqq.empty):
        print("      ERRO: Não foi possível obter opções de _NDX nem QQQ da CBOE.")
        return None, None, None, None

    if not ndx_spot and qqq_spot:
        ndx_spot = qqq_spot * 41.0
    if not qqq_spot and ndx_spot:
        qqq_spot = ndx_spot / 41.0

    ndx_qqq_ratio = ndx_spot / qqq_spot if qqq_spot > 0 else 41.0

    frames = []
    if df_ndx is not None and not df_ndx.empty:
        df_ndx = df_ndx.copy()
        df_ndx["mult"] = 100.0
        frames.append(df_ndx)
        print(f"      _NDX CBOE: Spot {ndx_spot:.2f} | {len(df_ndx)} séries ativas | OI Total: {int(df_ndx['oi'].sum()):,d}")

    if df_qqq is not None and not df_qqq.empty:
        df_qqq = df_qqq.copy()
        df_qqq["strike"] = df_qqq["strike"] * ndx_qqq_ratio
        df_qqq["mult"] = 100.0 / ndx_qqq_ratio
        frames.append(df_qqq)
        print(f"      QQQ  CBOE: Spot ${qqq_spot:.2f} | {len(df_qqq)} séries ativas | OI Total: {int(df_qqq['oi'].sum()):,d}")

    df_combined = pd.concat(frames, ignore_index=True)
    ref_str = ref_ndx or ref_qqq
    print(f"      Grade consolidada (_NDX + QQQ): {len(df_combined)} séries | Ref: {ref_str}")
    return ndx_spot, qqq_spot, df_combined, ref_str


def run_nq_gex_pipeline():
    """
    Executa o pipeline completo do Nasdaq 100 GEX (_NDX + QQQ -> USTEC).
    """
    print("=" * 60)
    print("  GEX ENGINE - Nasdaq 100 / USTEC Pipeline (CBOE _NDX + QQQ)")
    print("=" * 60)

    ndx_spot, qqq_spot, df_options, expiry_str = get_ndx_and_qqq_combined()
    if df_options is None or df_options.empty:
        print("ERRO: Opções inválidas.")
        sys.exit(1)

    today = datetime.date.today()
    r = 0.0515
    q = 0.0080

    conv_ratio, price_nq_mt5, ratio_msg = get_synchronized_etf_ratio(ndx_spot, "USTEC", 1.0)
    current_nq = price_nq_mt5 if (price_nq_mt5 and price_nq_mt5 > 0) else ndx_spot * conv_ratio
    ndx_qqq_ratio = ndx_spot / qqq_spot if qqq_spot > 0 else 41.0

    print(f"\n[2/5] Parâmetros de Cálculo Multi-Vencimento CBOE:")
    print(f"      Referência: {expiry_str}")
    print(f"      Taxa (r): {r*100:.2f}% | q: {q*100:.2f}%")
    print(f"      Sincronização MT5: {ratio_msg}")

    print(f"\n[3/5] Calculando GEX Institucional (_NDX + QQQ) e gerando Jumba Walls...")
    # Agrupar strikes na escala NDX a cada 100 pontos (~$2.50 no QQQ)
    df_options["strike_round"] = (df_options["strike"] / 100.0).round() * 100.0

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    mult = df_options["mult"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)

    sqrt_T = np.sqrt(T)
    d1 = (np.log(ndx_spot / K) + (r - q + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_bs = (np.exp(-q * T) * pdf_d1) / (ndx_spot * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_bs * (ndx_spot ** 2) * 0.01 * mult * sign

    gex_per_strike = {}
    for strike_ndx, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        gex_per_strike[float(strike_ndx)] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
        }

    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - ndx_spot))
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
    for strike_ndx in selected_strikes:
        info = gex_per_strike[strike_ndx]
        price_nq = strike_ndx * conv_ratio
        walls_basic.append({
            "price": round(price_nq, 2),
            "type": "Wall",
            "width": width_map.get(strike_ndx, 1),
            "style": 0,
            "strike_spy": int(round(strike_ndx / ndx_qqq_ratio)),
            "gex": info["gex_net"],
        })

    walls = sorted(walls_basic, key=lambda x: x["price"])

    # 4. Calcular Market Gamma Curve
    sweep_prices = np.linspace(ndx_spot * 0.92, ndx_spot * 1.08, 250)
    max_ndx, max_val, min_ndx, min_val, flip_ndx = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=r, q=q
    )

    max_gamma_nq = max_ndx * conv_ratio
    min_gamma_nq = min_ndx * conv_ratio
    flip_nq = flip_ndx * conv_ratio

    walls.append({
        "price": round(max_gamma_nq, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_nq, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_nq, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
    })

    # 5. Exportar Relatório e Caches
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_NQ.txt")

    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_nq >= flip_nq else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_nq >= flip_nq else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = (
        "Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
        if current_nq >= flip_nq else
        "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta."
    )

    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - NASDAQ 100 / USTEC (CBOE)",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    USTEC Atual:       {current_nq:.2f}  (NDX: {ndx_spot:.2f} | QQQ: ${qqq_spot:.2f})",
        f"    Gamma Flip Point:  {flip_nq:.2f}",
        f"    Regime de Gamma:   {regime}",
        f"    Vies do Dia:       {bias}",
        f"    Dinamica de MM:    {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : NQ {min_gamma_nq:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : NQ {flip_nq:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : NQ {max_gamma_nq:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE QQQ':12s} | {'EQUIVALENTE NQ':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65,
    ]

    display_walls = [w for w in walls if w["type"] == "Wall"]
    for w in sorted(display_walls, key=lambda x: x["price"], reverse=True):
        width_stars = "*" * w["width"]
        type_str = "WALL " + width_stars
        gex_m = w["gex"] / 1_000_000
        report_lines.append(f"  {type_str:10s} | ${w['strike_spy']:<11.2f} | NQ {w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")

    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o Open Interest consolidado da CBOE (_NDX + QQQ).",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65,
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"      Relatório escrito em: {report_path}")

    tv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    try:
        save_walls_to_cache(walls, ticker="nasdaq_nq", ref_date=today, current_price=current_nq)
        export_unified_tradingview(output_path=tv_path)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")

    print("\n" + "=" * 60)
    print("  Pipeline Nasdaq concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_nq_gex_pipeline()
