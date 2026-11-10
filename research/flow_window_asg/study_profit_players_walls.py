# -*- coding: utf-8 -*-
"""
research/flow_window_asg/study_profit_players_walls.py
======================================================
Estudo empírico completo dos 4 Players (Institucional/Gringo, HFT, Varejo, RLP)
nos dados nativos do Profit (.trd tick-a-tick de 45 bytes + .min M1/M5 de 128 bytes
nos 213 pregões de 2026) especificamente sobre as MagicWalls e MidWalls (WIN e WDO).

Objetivos:
  1. Mapear nos arquivos .trd (tick-a-tick com corretoras B3 compradora/vendedora e flag 2/3/4/13)
     como cada player atua dentro do raio das MagicWalls/MidWalls:
       - Reconstrução de Boleta Original (Sweep/TWAP no mesmo ms/s + mesma corretora agressora)
       - Separação Agressor vs. Passivo (Pedra) por perfil:
           * 🏦 Institucional / Gringo Direcional (JPM 16, Merrill 13, Goldman 23/238, Morgan 40/92,
             Citi 77/107/308, Tullett 127, Santander 27, Safra 59, BGC 122, Ágora 688 + Sweeps/Posição em UBS/BTG/Itaú/Bradesco)
           * ⚡ HFT / Market Maker Eletrônico (Ideal 1618/3093 + giro rápido de lote pequeno/médio em UBS 8, Genial 120, BTG 85, CM 88)
           * 🧑‍💻 Varejo Puro (XP 3, Toro 4090, Clear, Genial 120, CM 88, Inter 1099, Modal 147, Futura 93, Mirae 262 em boletas pequenas)
           * 🔄 RLP (flag == 13) e Direto Institucional (flag == 4)
  2. Medir a probabilidade real de DEFESA (Pullback/Reversão) vs. ROMPIMENTO (Continuação)
     em cada toque na Wall conforme a assinatura dos 4 players.
  3. Calibrar a ponte exata entre os campos nativos do .trd e os campos nativos do .min M1/M5
     (buy_qty, sell_qty, buy_trd, sell_trd, rlp_qty, avg_buy_lot, avg_sell_lot, M1 wick absorption)
     para que os 213 pregões de 2026 tenham a decomposição completa dos 4 players sem depender do MT5.
"""
import os
import re
import sys
import json
import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.profit_statarb_engine import PROFIT_ASSET_DIRS, TRD_DTYPE
from core.profit_mt5_flow_engine import load_daily_magic_walls

# Classificação oficial auditada de códigos de corretoras B3
PURE_INST_CODES = {
    13,    # Merrill Lynch (BofA)
    16,    # JP Morgan
    23,    # Goldman Sachs
    27,    # Santander
    40,    # Morgan Stanley
    45,    # Credit Suisse / UBS Inst
    59,    # Safra
    77,    # Citi Inst
    92,    # Morgan Stanley
    107,   # Citibank
    122,   # BGC Liquidez
    127,   # Tullett Prebon
    191,   # Itaú BBA Inst
    238,   # Goldman Sachs
    308,   # Citigroup
    688,   # Ágora / Bradesco Inst
}

MIXED_INST_BANKS = {
    8,     # UBS (HFT + Gringo Inst)
    39,    # Bradesco
    72,    # Bradesco
    85,    # BTG Pactual
    114,   # Itaú
}

PURE_HFT_CODES = {
    1618,  # Ideal HFT
    3093,  # Ideal
}

RETAIL_RLP_CODES = {
    3,     # XP / Rico / Clear
    88,    # CM Capital
    93,    # Nova Futura
    120,   # Genial
    147,   # Ativa / Modal
    262,   # Mirae
    1099,  # Banco Inter
    4090,  # Toro
    6003,  # C6 / Outros Varejo
}

BROKER_NAMES = {
    3: "XP", 8: "UBS", 13: "MERRILL", 16: "JPMORGAN", 23: "GOLDMAN",
    27: "SANTANDER", 39: "BRADESCO", 40: "MORGAN", 45: "UBS", 59: "SAFRA",
    72: "BRADESCO", 77: "CITI", 85: "BTG", 88: "CM_CAPITAL", 92: "MORGAN",
    93: "FUTURA", 107: "CITI", 114: "ITAU", 120: "GENIAL", 122: "BGC",
    127: "TULLETT", 147: "MODAL", 191: "ITAU", 238: "GOLDMAN", 262: "MIRAE",
    308: "CITI", 688: "AGORA", 1099: "INTER", 1618: "IDEAL", 3093: "IDEAL",
    4090: "TORO",
}


def find_all_trd_files(asset: str):
    prefixes = ("WIN",) if asset == "WIN" else ("WDO", "DOL")
    by_date = {}
    for d in PROFIT_ASSET_DIRS:
        if not os.path.exists(d):
            continue
        for folder in os.listdir(d):
            if not any(folder.startswith(p) for p in prefixes):
                continue
            fp_dir = os.path.join(d, folder)
            if not os.path.isdir(fp_dir):
                continue
            for fn in os.listdir(fp_dir):
                m = re.search(r"_0_1_1_1_0_(\d{8})\.trd$", fn)
                if not m:
                    continue
                ymd = m.group(1)
                iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
                fp = os.path.join(fp_dir, fn)
                sz = os.path.getsize(fp)
                if sz < 200000:
                    continue
                # Prefer WDO over DOL if both exist, or larger file
                is_wdo_native = folder.startswith("WDO")
                score = (1 if (asset == "WIN" or is_wdo_native) else 0, sz)
                if iso not in by_date or score > by_date[iso][0]:
                    by_date[iso] = (score, fp)
    return [(iso, by_date[iso][1]) for iso in sorted(by_date.keys())]


def analyze_trd_session_players(filepath: str, asset: str, iso_date: str):
    """
    Lê um arquivo .trd completo em NumPy vetorizado:
      1. Reconstrói a Boleta Original Agressora (Sweep/Burst): agrupa fills consecutivos
         no mesmo segundo/ms, mesma direção (flag 2 ou 3) e mesma corretora agressora,
         calculando o tamanho real da boleta (sweep_qty) e quantos níveis de preço varreu.
      2. Classifica tanto o LADO AGRESSOR quanto o LADO PASSIVO de cada negócio em:
         - INST (Institucional / Gringo Direcional)
         - HFT (Market Maker / Giro Eletrônico)
         - RETAIL (Varejo / Pessoa Física)
         - RLP (flag == 13) / DIRECT_INST (flag == 4)
      3. Agrega em barras M5 e analisa cada toque nas MagicWalls / MidWalls do dia.
    """
    sz = os.path.getsize(filepath)
    n_ticks = sz // 45
    if n_ticks <= 0:
        return None
    arr = np.fromfile(filepath, dtype=TRD_DTYPE, count=n_ticks)
    valid = (arr["qty"] > 0) & (arr["px"] > 0)
    arr = arr[valid]
    if len(arr) < 1000:
        return None

    is_win = (asset == "WIN")
    # Se for DOL cheio (lote múltiplo de 5), normaliza para equivalente mini ou ajusta threshold
    is_dol_full = ("DOL" in os.path.basename(filepath).upper()) and not ("WDO" in os.path.basename(filepath).upper())

    frac_day = arr["dt"] - np.floor(arr["dt"])
    sec_of_day = np.floor(frac_day * 86400.0 + 1e-6).astype(np.int32)
    min_of_day = sec_of_day // 60
    m5_bin = (min_of_day // 5) * 5

    # Filtrar horário regular 09:00 .. 18:25
    reg_mask = (min_of_day >= 540) & (min_of_day <= 1105)
    arr = arr[reg_mask]
    sec_of_day = sec_of_day[reg_mask]
    min_of_day = min_of_day[reg_mask]
    m5_bin = m5_bin[reg_mask]
    if len(arr) < 1000:
        return None

    flags = arr["flag"]
    qty = arr["qty"].astype(np.float64)
    px = arr["px"].astype(np.float64)
    b_brk = arr["b_brk"].astype(np.int32)
    s_brk = arr["s_brk"].astype(np.int32)

    # ── 1. Reconstrução Vetorizada de Boleta Agressora (Sweep/Burst no mesmo segundo + mesma corretora + mesma flag) ──
    is_buy_agg = (flags == 2)
    is_sell_agg = (flags == 3)
    is_book = is_buy_agg | is_sell_agg
    is_rlp = (flags == 13)
    is_direct = (flags == 4)

    agg_brk = np.where(is_buy_agg, b_brk, np.where(is_sell_agg, s_brk, 0))
    pas_brk = np.where(is_buy_agg, s_brk, np.where(is_sell_agg, b_brk, 0))

    # Chave de agrupamento de boleta agressora contígua: muda quando muda (sec_of_day, flags, agg_brk)
    change = np.empty(len(arr), dtype=bool)
    change[0] = True
    change[1:] = (
        (sec_of_day[1:] != sec_of_day[:-1])
        | (flags[1:] != flags[:-1])
        | (agg_brk[1:] != agg_brk[:-1])
        | (~is_book[1:])
    )
    sweep_id = np.cumsum(change) - 1
    sweep_totals = np.bincount(sweep_id, weights=np.where(is_book, qty, 0.0))
    tick_sweep_qty = sweep_totals[sweep_id]

    # Limiares de boleta reconstruída (Sweep Institucional vs HFT vs Varejo)
    inst_sweep_thr = 30.0 if is_win else (25.0 if is_dol_full else 12.0)
    ret_max_lot = 10.0 if is_win else (5.0 if is_dol_full else 3.0)
    inst_pas_lot_thr = 25.0 if is_win else (20.0 if is_dol_full else 10.0)

    # Máscaras de códigos de corretora (vetorizadas via np.isin)
    pure_inst_list = np.array(sorted(PURE_INST_CODES), dtype=np.int32)
    mixed_inst_list = np.array(sorted(MIXED_INST_BANKS), dtype=np.int32)
    pure_hft_list = np.array(sorted(PURE_HFT_CODES), dtype=np.int32)
    retail_list = np.array(sorted(RETAIL_RLP_CODES), dtype=np.int32)

    agg_is_pure_inst = np.isin(agg_brk, pure_inst_list)
    agg_is_mixed_bank = np.isin(agg_brk, mixed_inst_list)
    agg_is_pure_hft = np.isin(agg_brk, pure_hft_list)
    agg_is_retail_brk = np.isin(agg_brk, retail_list)

    pas_is_pure_inst = np.isin(pas_brk, pure_inst_list)
    pas_is_mixed_bank = np.isin(pas_brk, mixed_inst_list)
    pas_is_pure_hft = np.isin(pas_brk, pure_hft_list)
    pas_is_retail_brk = np.isin(pas_brk, retail_list)

    # Classificação do AGRESSOR em cada fill do Book Central:
    # - INST_AGGR: Corretora Institucional Pura OU Banco Misto com Sweep >= inst_sweep_thr OU qualquer Sweep gigante (>= 2*inst_sweep_thr)
    # - HFT_AGGR: Ideal (1618/3093) OU UBS (8)/Genial (120)/BTG (85) em giro rápido (< inst_sweep_thr)
    # - RET_AGGR: Corretora de Varejo com boleta pequena (<= ret_max_lot)
    is_inst_agg = is_book & (
        agg_is_pure_inst
        | (agg_is_mixed_bank & (tick_sweep_qty >= inst_sweep_thr))
        | (tick_sweep_qty >= inst_sweep_thr * 1.8)
    )
    is_ret_agg = is_book & (~is_inst_agg) & (
        (agg_is_retail_brk & (tick_sweep_qty <= ret_max_lot * 2.0))
        | ((~agg_is_pure_hft) & (~agg_is_mixed_bank) & (tick_sweep_qty <= ret_max_lot))
    )
    is_hft_agg = is_book & (~is_inst_agg) & (~is_ret_agg)

    # Classificação do PASSIVO (Quem estava na pedra absorvendo):
    is_inst_pas = is_book & (
        pas_is_pure_inst
        | (pas_is_mixed_bank & (qty >= inst_pas_lot_thr * 0.5))
        | (qty >= inst_pas_lot_thr)
    )
    is_ret_pas = is_book & (~is_inst_pas) & (
        (pas_is_retail_brk & (qty <= ret_max_lot * 1.5))
        | ((~pas_is_pure_hft) & (~pas_is_mixed_bank) & (qty <= ret_max_lot))
    )
    is_hft_pas = is_book & (~is_inst_pas) & (~is_ret_pas)

    sign_agg = np.where(is_buy_agg, 1.0, np.where(is_sell_agg, -1.0, 0.0))
    # Nota: para o PASSIVO, se a agressão foi de VENDA (flag=3, sign_agg=-1), o passivo COMPROU (+qty)!
    # Se a agressão foi de COMPRA (flag=2, sign_agg=+1), o passivo VENDEU (-qty)!
    sign_pas = -sign_agg

    inst_agg_signed = np.where(is_inst_agg, sign_agg * qty, 0.0)
    inst_pas_signed = np.where(is_inst_pas, sign_pas * qty, 0.0)
    hft_agg_signed = np.where(is_hft_agg, sign_agg * qty, 0.0)
    hft_pas_signed = np.where(is_hft_pas, sign_pas * qty, 0.0)
    ret_agg_signed = np.where(is_ret_agg, sign_agg * qty, 0.0)
    ret_pas_signed = np.where(is_ret_pas, sign_pas * qty, 0.0)

    # ── 2. Agregar por Barra M5 e testar Correlação com Métricas .min (Ticket Médio, RLP, Delta) ──
    uniq_m5, m5_start, m5_counts = np.unique(m5_bin, return_index=True, return_counts=True)
    m5_records = []
    for i in range(len(uniq_m5)):
        s0 = m5_start[i]
        s1 = s0 + m5_counts[i]
        sl_px = px[s0:s1]
        sl_q = qty[s0:s1]
        sl_buy = is_buy_agg[s0:s1]
        sl_sell = is_sell_agg[s0:s1]
        sl_rlp = is_rlp[s0:s1]

        bq = float(np.sum(sl_q[sl_buy]))
        sq = float(np.sum(sl_q[sl_sell]))
        bt = int(np.sum(sl_buy))
        st = int(np.sum(sl_sell))
        rq = float(np.sum(sl_q[sl_rlp]))
        rt = int(np.sum(sl_rlp))

        i_agg = float(np.sum(inst_agg_signed[s0:s1]))
        i_pas = float(np.sum(inst_pas_signed[s0:s1]))
        h_agg = float(np.sum(hft_agg_signed[s0:s1]))
        h_pas = float(np.sum(hft_pas_signed[s0:s1]))
        r_agg = float(np.sum(ret_agg_signed[s0:s1]))
        r_pas = float(np.sum(ret_pas_signed[s0:s1]))

        m5_records.append({
            "t_min": int(uniq_m5[i]),
            "open": float(sl_px[0]),
            "high": float(np.max(sl_px)),
            "low": float(np.min(sl_px)),
            "close": float(sl_px[-1]),
            "buy_qty": bq,
            "sell_qty": sq,
            "buy_trd": bt,
            "sell_trd": st,
            "rlp_qty": rq,
            "rlp_trd": rt,
            "avg_buy_lot": bq / max(1, bt),
            "avg_sell_lot": sq / max(1, st),
            "inst_aggr_delta": i_agg,
            "inst_pass_delta": i_pas,
            "inst_total_net": i_agg + i_pas,
            "hft_aggr_delta": h_agg,
            "hft_pass_delta": h_pas,
            "hft_total_net": h_agg + h_pas,
            "ret_aggr_delta": r_agg,
            "ret_pass_delta": r_pas,
            "ret_total_net": r_agg + r_pas,
        })

    # ── 3. Analisar Toques nas MagicWalls / MidWalls do Dia ──
    walls = load_daily_magic_walls(asset, iso_date)
    wall_touches = []
    if walls and len(m5_records) >= 10:
        rad = 60.0 if is_win else 2.5
        for idx, b in enumerate(m5_records[:-4]):
            if idx < 2:
                continue
            o, h, l, c = b["open"], b["high"], b["low"], b["close"]
            prev_c = m5_records[idx - 1]["close"]
            # Desfecho nas próximas 3 barras (15m)
            next_high = max(x["high"] for x in m5_records[idx + 1 : idx + 4])
            next_low = min(x["low"] for x in m5_records[idx + 1 : idx + 4])
            next_close = m5_records[idx + 3]["close"]

            for w in walls:
                wp = float(w["price"])
                if not (l - rad <= wp <= h + rad):
                    continue
                # Direção do teste: veio de cima (suporte, test_dir = 1) ou veio de baixo (resistência, test_dir = -1)
                test_dir = 1 if prev_c >= wp else -1
                mfe_reversao = (next_high - c) if test_dir == 1 else (c - next_low)
                mae_rompimento = (c - next_low) if test_dir == 1 else (next_high - c)
                net_15m_reversao = (next_close - c) * test_dir

                wall_touches.append({
                    "date": iso_date,
                    "t_min": b["t_min"],
                    "wall_price": wp,
                    "wall_type": w["type"],
                    "test_dir": test_dir,  # +1 = suporte (compra no fade), -1 = resistência (venda no fade)
                    "inst_aggr_favor": b["inst_aggr_delta"] * test_dir,
                    "inst_pass_favor": b["inst_pass_delta"] * test_dir,
                    "inst_net_favor": b["inst_total_net"] * test_dir,
                    "ret_aggr_favor": b["ret_aggr_delta"] * test_dir,
                    "ret_net_favor": b["ret_total_net"] * test_dir,
                    "hft_net_favor": b["hft_total_net"] * test_dir,
                    "rlp_qty": b["rlp_qty"],
                    "lot_ratio_favor": (b["avg_buy_lot"] / max(0.1, b["avg_sell_lot"])) if test_dir == 1 else (b["avg_sell_lot"] / max(0.1, b["avg_buy_lot"])),
                    "mfe_rev": mfe_reversao,
                    "mae_brk": mae_rompimento,
                    "net_15m_rev": net_15m_reversao,
                })

    return {
        "date": iso_date,
        "asset": asset,
        "n_ticks": len(arr),
        "tot_book_vol": float(np.sum(qty[is_book])),
        "tot_rlp_vol": float(np.sum(qty[is_rlp])),
        "tot_direct_vol": float(np.sum(qty[is_direct])),
        "inst_agg_share": float(np.sum(qty[is_inst_agg])) / max(1.0, float(np.sum(qty[is_book]))) * 100.0,
        "hft_agg_share": float(np.sum(qty[is_hft_agg])) / max(1.0, float(np.sum(qty[is_book]))) * 100.0,
        "ret_agg_share": float(np.sum(qty[is_ret_agg])) / max(1.0, float(np.sum(qty[is_book]))) * 100.0,
        "m5_records": m5_records,
        "wall_touches": wall_touches,
    }


def main():
    for asset in ("WIN", "WDO"):
        files = find_all_trd_files(asset)
        print(f"\n=======================================================")
        print(f"ANALISANDO {asset}: {len(files)} sessões .trd completas")
        print(f"=======================================================")
        all_touches = []
        all_m5 = []
        for iso, fp in files:
            res = analyze_trd_session_players(fp, asset, iso)
            if not res:
                continue
            all_touches.extend(res["wall_touches"])
            all_m5.extend(res["m5_records"])
            print(
                f"  {iso} ({os.path.basename(fp):32s}): {res['n_ticks']:9,d} ticks | "
                f"InstAgg={res['inst_agg_share']:4.1f}% | HFT={res['hft_agg_share']:4.1f}% | Varejo={res['ret_agg_share']:4.1f}% | "
                f"RLP/Book={res['tot_rlp_vol']/max(1,res['tot_book_vol'])*100:4.1f}% | Toques Wall={len(res['wall_touches'])}"
            )

        if not all_touches:
            continue

        # Estatísticas dos toques nas Walls por assinatura de player
        rev_thr = 120.0 if asset == "WIN" else 4.0
        print(f"\n--- ESTATÍSTICAS DE TOQUES NAS WALLS ({asset} · Total={len(all_touches)} toques) ---")

        def report_subset(label, pred):
            sub = [t for t in all_touches if pred(t)]
            if not sub:
                return
            win_rev = sum(1 for t in sub if t["net_15m_rev"] > 0)
            hit_target = sum(1 for t in sub if t["mfe_rev"] >= rev_thr and t["mfe_rev"] > t["mae_brk"])
            avg_rev = float(np.mean([t["net_15m_rev"] for t in sub]))
            avg_mfe = float(np.mean([t["mfe_rev"] for t in sub]))
            avg_mae = float(np.mean([t["mae_brk"] for t in sub]))
            print(
                f"  {label:52s} | N={len(sub):4d} | WR_15m={win_rev/len(sub)*100:5.1f}% | "
                f"Hit_{rev_thr:.0f}p={hit_target/len(sub)*100:5.1f}% | AvgNet15m={avg_rev:+6.1f} | MFE/MAE={avg_mfe/max(0.1,avg_mae):.2f}x"
            )

        report_subset("0. Todos os Toques na Wall (Sem Filtro)", lambda t: True)
        report_subset("1. Defesa Institucional (InstNet > 0 e Varejo < 0)", lambda t: t["inst_net_favor"] > 0 and t["ret_aggr_favor"] < 0)
        report_subset("2. Absorção Passiva Inst (InstPass > 0 contra Agressão)", lambda t: t["inst_pass_favor"] > 0 and t["ret_aggr_favor"] < 0)
        report_subset("3. Ignição Institucional a Favor da Reversão (InstAgg > 0)", lambda t: t["inst_aggr_favor"] > 0 and t["lot_ratio_favor"] >= 1.05)
        report_subset("4. Rompimento: Inst Agredindo CONTRA a Wall (Fade perde!)", lambda t: t["inst_aggr_favor"] < 0 and t["inst_net_favor"] < 0 and t["lot_ratio_favor"] < 0.95)
        report_subset("5. Combo Elite Defesa (InstNet>0 + LotRatio>=1.03)", lambda t: (t["inst_net_favor"] > 0 or t["inst_aggr_favor"] > 0) and t["lot_ratio_favor"] >= 1.03)


if __name__ == "__main__":
    main()
