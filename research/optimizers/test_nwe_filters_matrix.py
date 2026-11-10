"""
PESQUISA E AUDITORIA DE FILTROS NWE (DIREÇÃO, BANDAS E ROOM-TO-RUN)
==================================================================
Testa nas 11 estratégias da carteira se filtros baseados na NWE agregam valor:
  - NWE_SLOPE_DIR: slope da NWE50 a favor (slope > 0 p/ compra, < 0 p/ venda)
  - NWE_SLOPE_ANTI_CRASH: bloqueia se a NWE estiver acelerando contra (evita faca caindo)
  - NWE_ROOM_TO_RUN: exige espaço até a banda oposta (pos50 <= 0.70 p/ compra, >= 0.30 p/ venda)
  - NWE_DUAL_SLOPE: NWE30 e NWE50 apontando para o mesmo lado
  - NWE_BANDWIDTH_MIN: exige largura mínima de bandas (elimina marasmo)

Mede:
  - Lucro Líquido (com custos reais)
  - Profit Factor
  - Max Drawdown
  - Ret/DD
  - In-Sample (11/05-31/08) vs Out-Of-Sample (01/09-04/11)
"""
import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.discover_gex_nwe_setups as disc
from research.mt5_loader import load_win_and_wdo_aligned, load_m5_m1_wdo_gex
import research.optimizers.optimize_existing_16_setups as o16
import research.optimizers.wdo_mt5_sim as wsim

# ─────────────────────────────────────────────────────────────────────────────
# 1. TESTES NWE NO WIN (EST-01, EST-04, EST-07, EST-13, EST-14, EST-15, EST-16)
# ─────────────────────────────────────────────────────────────────────────────
def test_win_nwe_filters():
    print("=" * 100)
    print("  TESTANDO FILTROS NWE NO MINI-ÍNDICE (WIN)")
    print("=" * 100)

    df_win, gex_win = load_win_and_wdo_aligned()
    closes = df_win["close"].values
    n50_c, n50_u, n50_l, _, n50_s = disc.compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = disc.compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)

    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    bw50 = np.maximum(1.0, n50_u - n50_l)
    pos50 = (closes - n50_l) / bw50
    dates = df_win["session_date"].values
    t_mins = df_win["t_min"].values

    # Dicionário de filtros NWE callable: f(date, tmin, dir) -> bool
    def make_nwe_filter(mode):
        if mode == "BASE_SEM_FILTRO_NWE":
            return None

        # Pré-computa máscara por índice de barra
        if mode == "NWE_SLOPE_FAVOR":
            # slope50 > 0 p/ compra, slope50 < 0 p/ venda
            mask_buy = n50_s > 0.0
            mask_sell = n50_s < 0.0
        elif mode == "NWE_SLOPE_FORTE":
            # slope50 >= 3.0 p/ compra, slope50 <= -3.0 p/ venda
            mask_buy = n50_s >= 3.0
            mask_sell = n50_s <= -3.0
        elif mode == "NWE_ANTI_CRASH":
            # Não compra se estiver caindo como pedra (slope <= -7.0); não vende se foguete (slope >= 7.0)
            mask_buy = n50_s > -7.0
            mask_sell = n50_s < 7.0
        elif mode == "NWE_ROOM_TO_RUN_70":
            # Compra se pos50 <= 0.70; Venda se pos50 >= 0.30
            mask_buy = pos50 <= 0.70
            mask_sell = pos50 >= 0.30
        elif mode == "NWE_ROOM_TO_RUN_60":
            # Mais estrito: pos50 <= 0.60 na compra, >= 0.40 na venda
            mask_buy = pos50 <= 0.60
            mask_sell = pos50 >= 0.40
        elif mode == "NWE_DUAL_SLOPE":
            # slope30 e slope50 ambos a favor
            mask_buy = (n50_s > 0.0) & (n30_s > 0.0)
            mask_sell = (n50_s < 0.0) & (n30_s < 0.0)
        elif mode == "NWE_VOL_MIN":
            # Largura da banda acima do percentil 20 (evita congestão sem range)
            p20 = np.percentile(bw50, 20)
            mask_buy = bw50 >= p20
            mask_sell = bw50 >= p20
        elif mode == "NWE_COMBO_TENDENCIA":
            # slope a favor + espaço na banda (room to run <= 0.75)
            mask_buy = (n50_s > 0.0) & (pos50 <= 0.75)
            mask_sell = (n50_s < 0.0) & (pos50 >= 0.25)
        else:
            return None

        # Lookup dict (date, tmin)
        lut_buy = {(dates[i], int(t_mins[i])): bool(mask_buy[i]) for i in range(len(dates))}
        lut_sell = {(dates[i], int(t_mins[i])): bool(mask_sell[i]) for i in range(len(dates))}

        def _f(d_str, tm, s_dir):
            if s_dir == 1:
                return lut_buy.get((d_str, tm), True)
            return lut_sell.get((d_str, tm), True)

        return _f

    nwe_modes = [
        "BASE_SEM_FILTRO_NWE",
        "NWE_SLOPE_FAVOR",
        "NWE_SLOPE_FORTE",
        "NWE_ANTI_CRASH",
        "NWE_ROOM_TO_RUN_70",
        "NWE_ROOM_TO_RUN_60",
        "NWE_DUAL_SLOPE",
        "NWE_VOL_MIN",
        "NWE_COMBO_TENDENCIA",
    ]

    win_configs = [
        (1, "EST-01 Scalper Hibrido NY", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
        (4, "EST-04 Pullback Reteste Wall", "BE_WALL_2STAGE", 15.0, "TP_MIDWALL"),
        (7, "EST-07 Breakout Momentum NY", "BE_WALL_SHIELD", 15.0, "TP_MIDWALL"),  # Já otimizado para MidWall
    ]

    for est_id, name, be_m, buf, tp_m in win_configs:
        print(f"\n--- {name} (Config Otimizada: {be_m} | {tp_m}) ---")
        best_res = None
        best_mode = ""

        for mode in nwe_modes:
            flt = make_nwe_filter(mode)
            tr, st = o16.simulate_single_est_slot(
                est_id, df_win, gex_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                entry_override="CURRENT", be_mode=be_m, wall_shield_buf=buf, tp_mode=tp_m,
                cost_pts=10.0, sig_filter=flt
            )
            m = o16.calc_slot_summary(tr, st, mode)

            # In-Sample (11/05-31/08) vs Out-of-Sample (01/09-04/11)
            df_t = pd.DataFrame(tr)
            if len(df_t) > 0:
                is_df = df_t[df_t["date"] <= "2026-08-31"]
                oos_df = df_t[df_t["date"] > "2026-08-31"]
                is_net = is_df["pnl_brl"].sum() if len(is_df) > 0 else 0.0
                oos_net = oos_df["pnl_brl"].sum() if len(oos_df) > 0 else 0.0
            else:
                is_net, oos_net = 0.0, 0.0

            if best_res is None or (m["NetBRL"] > best_res["NetBRL"] and m["PF"] >= best_res["PF"] * 0.98) or (m["Ret_DD"] > best_res["Ret_DD"] * 1.15 and m["NetBRL"] >= best_res["NetBRL"] * 0.90):
                best_res = m
                best_mode = mode

            print(f"  {mode:22s} | Tr={m['Trades']:3d} | WR={m['WinRate']:4.1f}% | PF={m['PF']:4.2f} | Net=R$ {m['NetBRL']:6.0f} | DD=R$ {m['MaxDD_BRL']:4.0f} | RetDD={m['Ret_DD']:4.2f} | IS={is_net:5.0f} | OOS={oos_net:5.0f}")

        print(f"  >> MELHOR FILTRO NWE: {best_mode} (Net=R$ {best_res['NetBRL']} | Ret/DD={best_res['Ret_DD']})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. TESTES NWE NO DÓLAR (WDO-02, WDO-07, WDO-09, WDO-10)
# ─────────────────────────────────────────────────────────────────────────────
def test_wdo_nwe_filters():
    print("\n" + "=" * 100)
    print("  TESTANDO FILTROS NWE NO MINI-DÓLAR (WDO)")
    print("=" * 100)

    df_wdo, gex_wdo = wsim.load_wdo_mt5_raw()
    closes = df_wdo["close"].values
    n50_c, n50_u, n50_l, _, n50_s = wsim.compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = wsim.compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    rsi7 = wsim.compute_rsi7_series(closes)

    bw50 = np.maximum(0.5, n50_u - n50_l)
    pos50 = (closes - n50_l) / bw50
    dates = df_wdo["session_date"].values
    t_mins = df_wdo["t_min"].values

    def make_wdo_nwe_filter(mode):
        if mode == "BASE_SEM_FILTRO_NWE":
            return None

        if mode == "NWE_SLOPE_FAVOR":
            mask_buy = n50_s > 0.0
            mask_sell = n50_s < 0.0
        elif mode == "NWE_SLOPE_FORTE":
            mask_buy = n50_s >= 0.15
            mask_sell = n50_s <= -0.15
        elif mode == "NWE_ANTI_CRASH":
            mask_buy = n50_s > -0.30
            mask_sell = n50_s < 0.30
        elif mode == "NWE_ROOM_TO_RUN_70":
            mask_buy = pos50 <= 0.70
            mask_sell = pos50 >= 0.30
        elif mode == "NWE_ROOM_TO_RUN_60":
            mask_buy = pos50 <= 0.60
            mask_sell = pos50 >= 0.40
        elif mode == "NWE_DUAL_SLOPE":
            mask_buy = (n50_s > 0.0) & (n30_s > 0.0)
            mask_sell = (n50_s < 0.0) & (n30_s < 0.0)
        elif mode == "NWE_VOL_MIN":
            p20 = np.percentile(bw50, 20)
            mask_buy = bw50 >= p20
            mask_sell = bw50 >= p20
        elif mode == "NWE_COMBO_TENDENCIA":
            mask_buy = (n50_s > 0.0) & (pos50 <= 0.75)
            mask_sell = (n50_s < 0.0) & (pos50 >= 0.25)
        else:
            return None

        lut_buy = {(dates[i], int(t_mins[i])): bool(mask_buy[i]) for i in range(len(dates))}
        lut_sell = {(dates[i], int(t_mins[i])): bool(mask_sell[i]) for i in range(len(dates))}

        def _f(d_str, tm, s_dir):
            if s_dir == 1:
                return lut_buy.get((d_str, tm), True)
            return lut_sell.get((d_str, tm), True)

        return _f

    wdo_modes = [
        "BASE_SEM_FILTRO_NWE",
        "NWE_SLOPE_FAVOR",
        "NWE_SLOPE_FORTE",
        "NWE_ANTI_CRASH",
        "NWE_ROOM_TO_RUN_70",
        "NWE_ROOM_TO_RUN_60",
        "NWE_DUAL_SLOPE",
        "NWE_VOL_MIN",
        "NWE_COMBO_TENDENCIA",
    ]

    for sid in [2, 7, 9, 10]:
        print(f"\n--- WDO-{sid:02d} ---")
        best_res = None
        best_mode = ""

        for mode in wdo_modes:
            flt = make_wdo_nwe_filter(mode)
            tr = wsim.simulate_wdo_core_slot(sid, df_wdo, gex_wdo, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7, cost_pts=0.5, sig_filter=flt)
            s = wsim.summarize_wdo_trades(tr, mode)

            df_t = pd.DataFrame(tr)
            if len(df_t) > 0 and "date" in df_t.columns:
                is_df = df_t[df_t["date"] <= "2026-08-31"]
                oos_df = df_t[df_t["date"] > "2026-08-31"]
                is_net = is_df["pnl_brl"].sum() if len(is_df) > 0 else 0.0
                oos_net = oos_df["pnl_brl"].sum() if len(oos_df) > 0 else 0.0
            else:
                is_net, oos_net = 0.0, 0.0

            net_val = s["R$_com_custo"]
            dd_val = s["DD_com_custo"]
            ret_dd_val = s["RetDD_com_custo"]
            pf_val = s["PF_com_custo"]

            if best_res is None or (net_val > best_res["Net"] and pf_val >= best_res["PF"] * 0.98) or (ret_dd_val > best_res["RetDD"] * 1.15 and net_val >= best_res["Net"] * 0.90):
                best_res = dict(Net=net_val, PF=pf_val, DD=dd_val, RetDD=ret_dd_val)
                best_mode = mode

            print(f"  {mode:22s} | Tr={s['Trades']:3d} | WR={s['WR%']:4.1f}% | PF={pf_val:4.2f} | Net=R$ {net_val:6.0f} | DD=R$ {dd_val:4.0f} | RetDD={ret_dd_val:4.2f}")

        print(f"  >> MELHOR FILTRO NWE: {best_mode} (Net=R$ {best_res['Net']} | Ret/DD={best_res['RetDD']})")


if __name__ == "__main__":
    test_win_nwe_filters()
    test_wdo_nwe_filters()

