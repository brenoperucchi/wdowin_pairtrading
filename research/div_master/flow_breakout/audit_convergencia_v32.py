# -*- coding: utf-8 -*-
"""
Auditoria completa de Robustez (9 testes + Placebo sem convergência + Correlação com E22_WIN)
para os setups de Rompimento e Continuação com CONVERGÊNCIA NO FLUXO (F1 -> F2) estilo v3.2.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import (
    win_cache, DS_WIN, XW, get_e22_signals, eval_e22, sim_win_exact
)
from research.div_master.wdo_especialista.robustez_final import days_cache as wdo_cache, DS as DS_WDO, X as X_WDO
from research.div_master.flow_breakout.busca_convergencia_v32 import collect_asset_conv


def sim_win_df(df: pd.DataFrame, sl: float, tp_val: float, tmax: int, mode: str = "padrao"):
    """Simula WIN M1 tick-a-tick usando sim_win_exact com as penalidades de estresse oficiais."""
    cost, stop_slip, entry_slip, adv_m1, inv = 10.0, 5.0, 0.0, False, False
    if mode == "stop2t":
        stop_slip = 10.0
    elif mode == "custo2x":
        cost = 20.0
    elif mode == "pesado":
        cost, stop_slip, entry_slip = 20.0, 10.0, 5.0
    elif mode == "pior_m1":
        adv_m1 = True
    elif mode == "invertida":
        inv = True

    pnls, xts = [], []
    for r in df.itertuples():
        D = DS_WIN[r.date]
        dr = -int(r.dir) if inv else int(r.dir)
        p, xt = sim_win_exact(
            D, r.e, r.ep, dr, sl, tp_val, 0.0, 0.0, int(tmax),
            XW["tick"], cost, stop_slip, entry_slip, adv_m1=adv_m1
        )
        pnls.append(p)
        xts.append(xt)
    out = df[["date", "tm"]].copy()
    out["pnl"] = pnls
    out["xt"] = xts
    return out


def full_audit_win(name: str, df_all: pd.DataFrame, mask_base: pd.Series, conv_col: str,
                   sl: float, tp_val: float, tmax: int, e22_daily: pd.Series | None = None):
    print(f"\n{'=' * 112}")
    print(f"AUDITORIA COMPLETA: {name} (WIN | SL={sl:.0f} TP={tp_val:.0f} tmax={tmax})")
    print(f"{'=' * 112}")

    df_conv = df_all[mask_base & df_all[conv_col]].copy()
    df_plac = df_all[mask_base & (~df_all[conv_col])].copy()

    for m_label, mode, mgmt_mode, sub in [
        ("1. UM_POR_VEZ (Padrão 10/5)",      "padrao",    "UM",    df_conv),
        ("2. LIVRE (Sem bloqueio)",          "padrao",    "LIVRE", df_conv),
        ("3. Stop 2 ticks (10/10)",          "stop2t",    "UM",    df_conv),
        ("4. Custo 2x (20/5)",               "custo2x",   "UM",    df_conv),
        ("5. Pesado (20/10/+5e)",            "pesado",    "UM",    df_conv),
        ("6. Pior M1 (H/L simultâneo=SL)",   "pior_m1",   "UM",    df_conv),
        ("7. Invertida (Direção oposta)",    "invertida", "UM",    df_conv),
        ("8. PLACEBO SEM Convergência",      "padrao",    "UM",    df_plac),
    ]:
        if len(sub) < 10:
            print(f"  {m_label:<34}: <10 ops")
            continue
        sim_df = sim_win_df(sub, sl, tp_val, tmax, mode)
        tf = bt.mgmt(sim_df, "pnl", "xt", mgmt_mode)
        s = bt.stats(tf, "pnl", "xt")
        print(f"  {m_label:<34}: {s['ops']:4d} ops | WR {s['wr']:5.1f}% | PF {s['pf']:4.2f} | "
              f"Net {s['net']:+7.0f} | DD {s['dd']:5.0f} | Ret/DD {s['rdd']:6.2f} | {s['meses']} "
              f"(H1 {s['h1']:+5.0f} / H2 {s['h2']:+5.0f} / OOS {s['oos']:+5.0f})")

        if m_label.startswith("1.") and e22_daily is not None:
            d_pnl = tf.groupby("date")["pnl"].sum()
            idx = sorted(set(d_pnl.index) | set(e22_daily.index))
            s1 = d_pnl.reindex(idx, fill_value=0.0)
            s2 = e22_daily.reindex(idx, fill_value=0.0)
            corr = float(s1.corr(s2))
            print(f"     -> Correlação diária de PnL vs E22_WIN (produção): {corr:+.3f}")

    # 9. Platô de vizinhança (SL x TP)
    print("  9. Platô de Vizinhança (SL × TP no modo UM_POR_VEZ):")
    step = 20.0
    for d_sl in (-step, 0.0, step):
        row_str = f"     SL={sl+d_sl:4.0f}: "
        for d_tp in (-step, 0.0, step):
            sim_df = sim_win_df(df_conv, sl + d_sl, tp_val + d_tp, tmax, "padrao")
            tf = bt.mgmt(sim_df, "pnl", "xt", "UM")
            s = bt.stats(tf, "pnl", "xt")
            row_str += f"[TP={tp_val+d_tp:4.0f}: {s['ops']}op PF {s['pf']:.2f} R/DD {s['rdd']:5.2f} ({s['meses']})]  "
        print(row_str)


def main():
    t0 = time.time()
    df_win = collect_asset_conv("WIN", "wall", True)

    r_prod = get_e22_signals("all", M.V32_PROD)
    s_e22, e22_tf = eval_e22(r_prod)
    _, e22_tf2 = eval_e22(r_prod, mult=2.0)
    e22_daily = e22_tf.groupby("date")["pnl"].sum()

    # Candidato 1: WIN BRK_F1F2 | conv_k1w2 | near&crs | hh!=11 | ext50<0.5
    m_c1 = (
        (df_win["family"] == "BRK_F1F2")
        & df_win["near_wall"]
        & df_win["crossed_wall"]
        & (df_win["hh"] != 11)
        & (df_win["ext50_trend"] < 0.5)
        & df_win["w2_fav"]
    )
    full_audit_win("C1a_BRK_K1_NEAR_CRS (SL280 TP280 t24)", df_win, m_c1, "conv_k1_ok", 280.0, 280.0, 24, e22_daily)
    full_audit_win("C1b_BRK_K1_NEAR_CRS (SL280 TP240 t18 - 11/11m)", df_win, m_c1, "conv_k1_ok", 280.0, 240.0, 18, e22_daily)

    # Candidato 2: WIN BRK_F1F2 | conv_k1w2 | cross_w | hh!=11 | ext50<0.5
    m_c2 = (
        (df_win["family"] == "BRK_F1F2")
        & df_win["crossed_wall"]
        & (df_win["hh"] != 11)
        & (df_win["ext50_trend"] < 0.5)
        & df_win["w2_fav"]
    )
    full_audit_win("C2_BRK_K1_CROSS (SL280 TP280 t24 - Ret/DD 10.23)", df_win, m_c2, "conv_k1_ok", 280.0, 280.0, 24, e22_daily)

    # Candidato 3: WIN BRK_F1F2 | conv | near&crs | hh!=11 | ext50<0.5 (onda da própria barra k, 207 ops)
    m_c3 = (
        (df_win["family"] == "BRK_F1F2")
        & df_win["near_wall"]
        & df_win["crossed_wall"]
        & (df_win["hh"] != 11)
        & (df_win["ext50_trend"] < 0.5)
    )
    full_audit_win("C3_BRK_FLOW_NEAR_CRS (207 ops, SL280 TP280 t24)", df_win, m_c3, "conv_ok", 280.0, 280.0, 24, e22_daily)

    # Candidato 4: WIN BRK_F1F2 | conv_w2+ | cross_w | hh!=11 | ext50<0.5 (181 ops, 11/11m)
    m_c4 = (
        (df_win["family"] == "BRK_F1F2")
        & df_win["crossed_wall"]
        & (df_win["hh"] != 11)
        & (df_win["ext50_trend"] < 0.5)
        & df_win["w2_fav"]
    )
    full_audit_win("C4_BRK_W2POS_CROSS (181 ops, 11/11m, SL280 TP240 t18)", df_win, m_c4, "conv_ok", 280.0, 240.0, 18, e22_daily)

    # Portfólio E22_WIN (Divergência) + BRK_F1F2 (Rompimento c/ Convergência F1->F2)
    print(f"\n{'=' * 112}")
    print("PORTFÓLIO WIN: E22_WIN (Divergência na Wall) + BRK_F1F2 (Rompimento c/ Convergência F1->F2)")
    print(f"{'=' * 112}")
    print(f"  Sozinho E22_WIN (1ct)              : {s_e22['ops']:3d} ops | PF {s_e22['pf']:.2f} | Net {s_e22['net']:+6.0f} | DD {s_e22['dd']:4.0f} | R/DD {s_e22['rdd']:5.2f} | {s_e22['meses']}")
    for lbl, mask, col, sl, tp, tm in [
        ("C1a_BRK_K1 (122op TP280)", m_c1, "conv_k1_ok", 280.0, 280.0, 24),
        ("C1b_BRK_K1 (122op TP240)", m_c1, "conv_k1_ok", 280.0, 240.0, 18),
        ("C2_BRK_K1_CRS (139op)",    m_c2, "conv_k1_ok", 280.0, 280.0, 24),
        ("C3_BRK_FLOW (207op)",      m_c3, "conv_ok",    280.0, 280.0, 24),
        ("C4_BRK_W2+ (181op 11/11)", m_c4, "conv_ok",    280.0, 240.0, 18),
    ]:
        tf_b = bt.mgmt(sim_win_df(df_win[mask & df_win[col]], sl, tp, tm, "padrao"), "pnl", "xt", "UM")
        p_11 = bt.portfolio(e22_tf, tf_b, "pnl", "pnl", "xt", "xt", mult_w=1.0)
        p_21 = bt.portfolio(e22_tf2, tf_b, "pnl", "pnl", "xt", "xt", mult_w=1.0)
        d1 = e22_tf.groupby("date")["pnl"].sum()
        d2 = tf_b.groupby("date")["pnl"].sum()
        idx = sorted(set(d1.index) | set(d2.index))
        corr = float(d1.reindex(idx, fill_value=0.0).corr(d2.reindex(idx, fill_value=0.0)))
        print(f"  E22 (1ct) + {lbl:<24} : {p_11['ops']:3d} ops | Net {p_11['net']:+6.0f} | DD {p_11['dd']:4.0f} | R/DD {p_11['rdd']:5.2f} | {p_11['meses']} | corr={corr:+.3f}")
        print(f"  E22 (2ct) + {lbl:<24} : {p_21['ops']:3d} ops | Net {p_21['net']:+6.0f} | DD {p_21['dd']:4.0f} | R/DD {p_21['rdd']:5.2f} | {p_21['meses']} | corr={corr:+.3f}")

    print(f"\nConcluído em {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
