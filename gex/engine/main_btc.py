import datetime
import os
import sys
import re
import numpy as np
import pandas as pd
import requests

# Adicionar a pasta raiz ao sys.path para importações locais
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gex.engine.cboe_fetcher import fetch_cboe_chain, compute_multi_expiry_gamma_curve
from gex.engine.tradingview_exporter import save_walls_to_cache, export_unified_tradingview
from gex.engine.mt5_prices import get_global_mt5_price
from gex.engine.chain_archive import archive_payload


def get_deribit_and_ibit_btc_options():
    """
    Consome a API da Deribit (agregando todos os vencimentos dos próximos 45 dias)
    + a grade institucional do ETF IBIT na CBOE, convertida para a escala do BTC.
    """
    print("[1/5] Conectando à API da Deribit + CBOE (IBIT) para buscar opções de BTC (Multi-Vencimento)...")
    url = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option"

    results = []
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        res_data = response.json()
        results = res_data.get("result", [])
        # Arquivo diário da resposta bruta da Deribit (permite recalcular este dia no futuro)
        archive_payload("deribit", "BTC", url, res_data)
    except Exception as e:
        print(f"      [Aviso] Erro ao conectar com a Deribit: {e}")

    current_btc = None
    for r in results:
        idx_val = r.get("underlying_price")
        if idx_val and idx_val > 1000:
            current_btc = float(idx_val)
            break

    if not current_btc:
        price_mt5, _ = get_global_mt5_price("BTCUSD")
        if not (price_mt5 and price_mt5 > 1000):
            print("      ERRO: sem preço real do BTC (Deribit e MT5 indisponíveis). Abortando para não publicar níveis errados.")
            sys.exit(1)
        current_btc = price_mt5

    print(f"      BTC Index Spot Price: ${current_btc:.2f} | Instrumentos Deribit brutos: {len(results)}")

    today = datetime.date.today()
    month_map = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }

    min_strike = current_btc * 0.82
    max_strike = current_btc * 1.18
    options = []

    for r in results:
        name = r.get("instrument_name", "")
        match = re.match(r"^BTC-(\d+)([A-Z]{3})(\d+)-(\d+)-([CP])$", name)
        if not match:
            continue

        day_str, month_str, year_str, strike_str, type_char = match.groups()
        day = int(day_str)
        month = month_map.get(month_str, 1)
        year = int("20" + year_str)

        try:
            expiry_date = datetime.date(year, month, day)
        except ValueError:
            continue

        dte_days = (expiry_date - today).days
        if dte_days < 0 or dte_days > 45:
            continue

        strike = float(strike_str)
        if not (min_strike <= strike <= max_strike):
            continue

        opt_type = "CALL" if type_char == "C" else "PUT"
        oi = float(r.get("open_interest") or 0.0)
        iv = float(r.get("mark_iv") or 50.0) / 100.0
        if iv <= 0.01 or iv > 5.0:
            iv = 0.50

        if oi > 0:
            T = max(1.0 / 365.0, max(1, dte_days) / 365.0)
            options.append({
                "ticker": name,
                "type": opt_type,
                "strike": strike,
                "expiry": expiry_date.isoformat(),
                "T": T,
                "oi": oi,
                "iv": iv,
                "mult": 1.0,  # 1 contrato Deribit = 1 BTC
            })

    deribit_count = len(options)
    deribit_oi = sum(o["oi"] for o in options)
    print(f"      Deribit (<=45 DTE): {deribit_count} séries ativas | OI Total: {deribit_oi:,.1f} BTC")

    # 2. Somar a liquidez institucional do ETF IBIT na CBOE (convertida para equivalente BTC)
    ibit_spot, df_ibit, _ = fetch_cboe_chain("IBIT", max_dte=45, strike_range_pct=0.15, default_iv=0.50)
    if df_ibit is not None and not df_ibit.empty and ibit_spot and ibit_spot > 0:
        btc_ibit_ratio = current_btc / ibit_spot
        # Na escala BTC, S_btc = S_ibit * ratio, Gamma_btc = Gamma_ibit / ratio.
        # 1 contrato IBIT = 100 cotas. Logo mult equivalente em BTC = 100 / ratio.
        ibit_mult_btc = 100.0 / btc_ibit_ratio
        for _, row in df_ibit.iterrows():
            options.append({
                "ticker": row["ticker"],
                "type": row["type"],
                "strike": float(row["strike"]) * btc_ibit_ratio,
                "expiry": row["expiry"],
                "T": float(row["T"]),
                "oi": float(row["oi"]),
                "iv": float(row["iv"]),
                "mult": ibit_mult_btc,
            })
        print(f"      IBIT CBOE (<=45 DTE): Spot ${ibit_spot:.2f} | {len(df_ibit)} séries | OI: {int(df_ibit['oi'].sum()):,d} contratos")

    df_options = pd.DataFrame(options)
    if df_options.empty:
        print("      ERRO: Nenhuma opção de BTC carregada.")
        return None, None, None

    all_expiries = sorted(df_options["expiry"].unique())
    front_expiry = all_expiries[0]
    exp_summary = df_options.groupby("expiry")["oi"].sum()
    top_expiry = exp_summary.idxmax()
    ref_str = f"{front_expiry} (Multi-Exp: {len(all_expiries)} vencs, Top: {top_expiry})"
    print(f"      Total consolidado (Deribit + IBIT): {len(df_options)} séries | Ref: {ref_str}")
    return current_btc, df_options, ref_str


def run_btc_gex_pipeline():
    """
    Executa o pipeline completo do Bitcoin GEX (Deribit Multi-Vencimento + CBOE IBIT).
    """
    print("=" * 60)
    print("  GEX ENGINE - Bitcoin / BTC Pipeline (Deribit + CBOE IBIT)")
    print("=" * 60)

    current_btc, df_options, expiry_str = get_deribit_and_ibit_btc_options()
    if df_options is None or df_options.empty:
        print("ERRO: Dados de opções de BTC inválidos.")
        sys.exit(1)

    price_btc_mt5, bar_time = get_global_mt5_price("BTCUSD")
    if price_btc_mt5 and price_btc_mt5 > 0:
        time_str = bar_time.strftime("%H:%M:%S UTC") if bar_time else "Agora"
        print(f"      [Sincronização MT5] BTCUSD MT5: ${price_btc_mt5:.2f} @ {time_str} (Deribit: ${current_btc:.2f})")
        current_btc = price_btc_mt5
    else:
        print(f"      [Deribit Spot] Deribit Spot BTC: ${current_btc:.2f}")

    today = datetime.date.today()
    r = 0.0515

    print(f"\n[2/5] Parâmetros de Cálculo Cripto (Multi-Vencimento Deribit + IBIT):")
    print(f"      Referência: {expiry_str}")
    print(f"      Taxa (r): {r*100:.2f}%")

    # 3. Agrupar strikes a cada $1,000
    print(f"\n[3/5] Calculando GEX e gerando Jumba Walls...")
    df_options["strike_round"] = (df_options["strike"] / 1000.0).round() * 1000.0

    K = df_options["strike"].to_numpy()
    T = np.maximum(df_options["T"].to_numpy(), 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy(), 0.01)
    oi = df_options["oi"].to_numpy()
    mult = df_options["mult"].to_numpy()
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)

    sqrt_T = np.sqrt(T)
    d1 = (np.log(current_btc / K) + (r + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_bs = pdf_d1 / (current_btc * sigma * sqrt_T)

    df_options["gex_contrib"] = oi * gamma_bs * (current_btc ** 2) * 0.01 * mult * sign

    gex_per_strike = {}
    for strike_round, group in df_options.groupby("strike_round"):
        gex_net = float(group["gex_contrib"].sum())
        if abs(gex_net) <= 0:
            continue
        gex_per_strike[float(strike_round)] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "avg_iv": float(group["iv"].mean()),
        }

    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_btc))
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
    for strike_round in selected_strikes:
        info = gex_per_strike[strike_round]
        walls_basic.append({
            "price": round(strike_round, 2),
            "type": "Wall",
            "width": width_map.get(strike_round, 1),
            "style": 0,
            "strike_spy": int(strike_round),
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
    sweep_prices = np.linspace(current_btc * 0.90, current_btc * 1.10, 250)
    max_gamma_btc, max_val, min_gamma_btc, min_val, flip_btc = compute_multi_expiry_gamma_curve(
        df_options, sweep_prices, r=r, q=0.0
    )

    walls.append({
        "price": round(max_gamma_btc, 2),
        "type": "MaxGamma",
        "width": 3,
        "style": 0,
        "gex": max_val,
    })
    walls.append({
        "price": round(min_gamma_btc, 2),
        "type": "MinGamma",
        "width": 3,
        "style": 0,
        "gex": min_val,
    })
    walls.append({
        "price": round(flip_btc, 2),
        "type": "GammaFlip",
        "width": 2,
        "style": 0,
        "gex": 0.0,
    })

    # 5. Exportar Relatório e Caches
    print(f"\n[4/5] Exportando indicadores e relatórios...")
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT_BTC.txt")

    regime = "POSITIVE GAMMA (Zona de Baixa Volatilidade / Hedge Comprado)" if current_btc >= flip_btc else "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)"
    bias = "ALTA / LATERALIZACAO" if current_btc >= flip_btc else "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)"
    desc = (
        "Os Market Makers estao comprados em Gamma. Eles amortecem os movimentos de preco comprando nas quedas e vendendo nas altas."
        if current_btc >= flip_btc else
        "Os Market Makers estao vendidos em Gamma. Eles aceleram a tendencia vendendo nas quedas e comprando nas altas para zerar o delta."
    )

    report_lines = [
        "=" * 65,
        "  RELATORIO DIARIO DE TENDENCIA E JUMBA WALLS - BITCOIN / BTC-USD",
        f"  Vencimento de Referencia: {expiry_str} | Data Ref: {today.strftime('%d/%m/%Y')}",
        "=" * 65,
        "",
        "[+] STATUS DO MERCADO (REGIME GEX):",
        f"    Bitcoin Spot Atual: ${current_btc:.2f}",
        f"    Gamma Flip Point:   ${flip_btc:.2f}",
        f"    Regime de Gamma:    {regime}",
        f"    Vies do Dia:        {bias}",
        f"    Dinamica de MM:     {desc}",
        "",
        "[+] NIVEIS CRITICOS DA CURVA GAMMA:",
        f"    [-] MIN GAMMA (Piso de Queda Livre)   : BTC ${min_gamma_btc:.2f}",
        f"    [o] GAMMA FLIP (Divisor/Pivot do Dia)  : BTC ${flip_btc:.2f}",
        f"    [+] MAX GAMMA (Teto Gravitacional)    : BTC ${max_gamma_btc:.2f}",
        "",
        "[+] JUMBA WALLS DETECTADAS (Strikes Proximos):",
        "-" * 65,
        f"  {'TIPO':10s} | {'STRIKE BTC':12s} | {'EQUIVALENTE USD':16s} | {'GEX NET ($ Milhoes)':22s} | {'LARGURA'}",
        "-" * 65,
    ]

    display_walls = [w for w in walls if w["type"] == "Wall"]
    for w in sorted(display_walls, key=lambda x: x["strike_spy"], reverse=True):
        width_stars = "*" * w["width"]
        type_str = "WALL " + width_stars
        gex_m = w["gex"] / 1_000_000
        report_lines.append(f"  {type_str:10s} | ${w['strike_spy']:<11.2f} | BTC ${w['price']:<12.2f} | $ {gex_m:>18.2f}M | Width {w['width']}")

    report_lines.extend([
        "-" * 65,
        "Nota: As Jumba Walls acima mapeiam o Open Interest consolidado da Deribit + CBOE IBIT.",
        "Zonas com largura 3 (***) sao os maiores imas gravitacionais e fortes suportes/resistencias.",
        "=" * 65,
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"      Relatório escrito em: {report_path}")

    tv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jumba_tradingview.pine")
    try:
        save_walls_to_cache(walls, ticker="btc_usd", ref_date=today, current_price=current_btc)
        export_unified_tradingview(output_path=tv_path)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")

    print("\n" + "=" * 60)
    print("  Pipeline Bitcoin concluído com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    run_btc_gex_pipeline()
