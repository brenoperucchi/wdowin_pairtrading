# -*- coding: utf-8 -*-
"""
Análise completa de Portfólio, Distância Estrutural do Pivô e Auditoria de Robustez da SYM_TOP1
em WIN e WDO.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import (
    win_cache, DS_WIN, XW, get_e22_signals, eval_e22
)
from research.div_master.wdo_especialista.robustez_final import (
    days_cache as wdo_cache, DS as DS_WDO, X as X_WDO, make_P as make_P_wdo
)
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo, OPT_OPEN
from research.div_master.test_sym_top1 import collect_sym_top1, sim_asset


def analyze_pivot_distance():
    """Mostra por que stops < 12 pts no WDO são violinados no modo CONF: distância da entrada ep até o pivô px2."""
    print("=" * 115)
    print("1. ANATOMIA DA ENTRADA CONF NA SYM_TOP1: DISTÂNCIA DA ENTRADA (conf+1) ATÉ O EXTREMO DO PIVÔ (px2)")
    print("=" * 115)
    for asset, cache in (("WDO", wdo_cache), ("WIN", win_cache)):
        P = dict(M.PARAMS[asset])
        dists = []
        for d in sorted(cache):
            fb, w_all, w_wall, D = cache[d]
            atr = M.atr_series(fb, P["tick"])
            cands = M.engine_v32(fb, w_wall, P, "common", atr=atr, opt=OPT_OPEN)
            seq = {1: 0, -1: 0}
            for c in cands:
                conf = c["conf"]
                if conf + 1 >= len(fb):
                    continue
                s = seq[c["dir"]]
                seq[c["dir"]] += 1
                if s > 1:
                    continue
                tm = bt.hm(fb[conf + 1]["time"])
                if tm // 60 == 11 or tm not in D["pos"]:
                    continue
                e = D["pos"][tm]
                if e < 1:
                    continue
                ep = float(D["o5"][e])
                dr = int(c["dir"])
                dist_piv = dr * (ep - float(c["px2"]))
                dists.append(dist_piv)
        arr = np.array(dists)
        print(f"  {asset}: N={len(arr)} sinais | Distância (ep -> px2): "
              f"P25={np.percentile(arr, 25):.1f} | Mediana={np.median(arr):.1f} | "
              f"Média={np.mean(arr):.1f} | P75={np.percentile(arr, 75):.1f} | P90={np.percentile(arr, 90):.1f} pts")


def audit_sym_top1_variants():
    print("\n" + "=" * 115)
    print("2. AUDITORIA DE 9 TESTES DA SYM_TOP1 EM WDO E WIN (E COMPARAÇÃO COM STRICT !SUPER)")
    print("=" * 115)
    df_w = collect_sym_top1("WIN", nodiv=False, strict_no_super=False)
    df_w_nd = collect_sym_top1("WIN", nodiv=True, strict_no_super=False)
    df_d = collect_sym_top1("WDO", nodiv=False, strict_no_super=False)
    df_d_nd = collect_sym_top1("WDO", nodiv=True, strict_no_super=False)

    df_w_ns = collect_sym_top1("WIN", nodiv=False, strict_no_super=True)
    df_d_ns = collect_sym_top1("WDO", nodiv=False, strict_no_super=True)

    configs = [
        ("WDO SYM_TOP1 (SL14 TP11 fix t24)",       df_d,    df_d_nd, "WDO", 14.0, "fix",    11.0, 24),
        ("WDO SYM_TOP1 (SL14 TP10 fix t24 - 9/11)",df_d,    df_d_nd, "WDO", 14.0, "fix",    10.0, 24),
        ("WDO SYM_TOP1 (SL14 ProxWall t18)",       df_d,    df_d_nd, "WDO", 14.0, "nw_all",  0.0, 18),
        ("WDO SYM_TOP1 (SL14 ProxWall t24)",       df_d,    df_d_nd, "WDO", 14.0, "nw_all",  0.0, 24),
        ("WDO SYM_TOP1 !sup_estrito (SL14 ProxW t24)", df_d_ns, df_d_nd, "WDO", 14.0, "nw_all", 0.0, 24),
        ("WIN SYM_TOP1 (SL280 TP240 fix t24)",     df_w,    df_w_nd, "WIN", 280.0, "fix",  240.0, 24),
        ("WIN SYM_TOP1 (SL280 TP280 fix t12)",     df_w,    df_w_nd, "WIN", 280.0, "fix",  280.0, 12),
        ("WIN SYM_TOP1 !sup_estrito (SL280 TP240 t24)", df_w_ns, df_w_nd, "WIN", 280.0, "fix", 240.0, 24),
    ]

    for title, df_main, df_plac, asset, sl, tpm, tpv, tmax in configs:
        print(f"\n--- {title} ---")
        for lbl, mode, mgmt, sub in [
            ("1. UM_POR_VEZ (Padrão)", "padrao",    "UM",    df_main),
            ("2. LIVRE",               "padrao",    "LIVRE", df_main),
            ("3. Stop +2 ticks",       "stop2t",    "UM",    df_main),
            ("4. Custo 2x",            "custo2x",   "UM",    df_main),
            ("5. Pesado",              "pesado",    "UM",    df_main),
            ("6. Invertida",           "invertida", "UM",    df_main),
            ("7. Placebo SEM div",     "padrao",    "UM",    df_plac),
        ]:
            s, _ = sim_asset(sub, asset, sl, tpm, tpv, 0.0, 0.0, tmax, mode=mode, mgmt=mgmt)
            print(f"  {lbl:<24}: {s['ops']:3d} ops | WR {s['wr']:5.1f}% | PF {s['pf']:4.2f} | "
                  f"Net {s['net']:+6.0f} | DD {s['dd']:5.0f} | R/DD {s['rdd']:5.2f} | {s['meses']} "
                  f"(H1 {s['h1']:+5.0f} / H2 {s['h2']:+5.0f} / OOS {s['oos']:+5.0f})")


def portfolio_analysis():
    print("\n" + "=" * 115)
    print("3. IMPACTO NO PORTFÓLIO: SYM_TOP1 vs E22_WIN (PRODUÇÃO) E V1a_WDO (CAMPEÃ WDO)")
    print("=" * 115)

    # 1) E22_WIN (Produção: V32_PROD all | OPC | !super, seq<=1 | 10h-16h | ext50>-0.5&sl>-0.5 | SL200 BE180->20 t12)
    r_e22 = get_e22_signals("all", M.V32_PROD)
    s_e22_1, tf_e22_1 = eval_e22(r_e22, mult=1.0)
    s_e22_2, tf_e22_2 = eval_e22(r_e22, mult=2.0)

    # 2) V1a_WDO (Campeã WDO: V32_OPEN wall | CONF | d_wall<=3.5 | hh!=11 | ext30>0 | SL14 ProxWall t24)
    P_wdo = make_P_wdo(zone=3.5, pierce_max=6.0)
    r_v1a = run_v32_wdo(P_wdo, "wall", "common", OPT_OPEN, "CONF",
                        lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
    s_v1a, tf_v1a = eval_wdo(r_v1a, 14.0, "nw", 0.0, 24, "UM")
    s_v1a_tp12, tf_v1a_tp12 = eval_wdo(r_v1a, 14.0, "fix", 12.0, 24, "UM")

    # 3) SYM_TOP1 em WIN e WDO
    df_w = collect_sym_top1("WIN", nodiv=False, strict_no_super=False)
    df_d = collect_sym_top1("WDO", nodiv=False, strict_no_super=False)

    s_sym_w240, tf_sym_w240 = sim_asset(df_w, "WIN", 280.0, "fix", 240.0, 0.0, 0.0, 24)
    s_sym_w280, tf_sym_w280 = sim_asset(df_w, "WIN", 280.0, "fix", 280.0, 0.0, 0.0, 12)
    # SYM_TOP1 WIN apenas na manhã (09:00-10:00, onde E22 não opera!)
    df_w_morn = df_w[df_w["tm"] < 600].copy()
    s_sym_wm, tf_sym_wm = sim_asset(df_w_morn, "WIN", 280.0, "fix", 240.0, 0.0, 0.0, 24)

    s_sym_d11, tf_sym_d11 = sim_asset(df_d, "WDO", 14.0, "fix", 11.0, 0.0, 0.0, 24)
    s_sym_d10, tf_sym_d10 = sim_asset(df_d, "WDO", 14.0, "fix", 10.0, 0.0, 0.0, 24)
    s_sym_dnw18, tf_sym_dnw18 = sim_asset(df_d, "WDO", 14.0, "nw_all", 0.0, 0.0, 0.0, 18)
    s_sym_dnw24, tf_sym_dnw24 = sim_asset(df_d, "WDO", 14.0, "nw_all", 0.0, 0.0, 0.0, 24)

    # Sinais de SYM_TOP1_WDO que NÃO estão em V1a_WDO (ex: quando ext30 <= 0 ou âncora dia)
    v1a_keys = {(r["date"], r["tm"]) for r in r_v1a}
    df_d_extra = df_d[~df_d.apply(lambda r: (r["date"], r["tm"]) in v1a_keys, axis=1)].copy()
    s_sym_d_ext, tf_sym_d_ext = sim_asset(df_d_extra, "WDO", 14.0, "nw_all", 0.0, 0.0, 0.0, 18)

    def combine_folios(named_dfs):
        parts = []
        for _, df_part in named_dfs:
            c = df_part[["date", "tm", "pnl", "xt"]].copy()
            parts.append(c)
        all_df = pd.concat(parts, ignore_index=True).sort_values(["date", "tm"]).reset_index(drop=True)
        st = bt.stats(all_df, "pnl", "xt")
        # Correlação entre o 1º e o último componente
        d1 = named_dfs[0][1].groupby("date")["pnl"].sum()
        d2 = named_dfs[-1][1].groupby("date")["pnl"].sum()
        idx = sorted(set(d1.index) | set(d2.index))
        corr = float(d1.reindex(idx, fill_value=0.0).corr(d2.reindex(idx, fill_value=0.0))) if len(named_dfs) >= 2 else 0.0
        return st, corr

    print("\n--- A. ESTRATÉGIAS INDIVIDUAIS ---")
    for name, s in [
        ("E22_WIN Produção (1 ct)",            s_e22_1),
        ("E22_WIN Produção (2 ct)",            s_e22_2),
        ("V1a_WDO Campeã (1 ct, ProxWall)",    s_v1a),
        ("SYM_TOP1_WIN (SL280 TP240 t24)",     s_sym_w240),
        ("SYM_TOP1_WIN (SL280 TP280 t12)",     s_sym_w280),
        ("SYM_TOP1_WIN Manhã <10h (SL280 TP240)", s_sym_wm),
        ("SYM_TOP1_WDO (SL14 TP11 t24)",       s_sym_d11),
        ("SYM_TOP1_WDO (SL14 TP10 t24)",       s_sym_d10),
        ("SYM_TOP1_WDO (SL14 ProxWall t18)",   s_sym_dnw18),
        ("SYM_TOP1_WDO (SL14 ProxWall t24)",   s_sym_dnw24),
        ("SYM_TOP1_WDO Exclusivos fora da V1a",s_sym_d_ext),
    ]:
        print(f"  {name:<38}: {s['ops']:3d} ops | WR {s['wr']:5.1f}% | PF {s['pf']:4.2f} | "
              f"Net {s['net']:+7.0f} | DD {s['dd']:4.0f} | R/DD {s['rdd']:5.2f} | {s['meses']} "
              f"(H1 {s['h1']:+5.0f} / H2 {s['h2']:+5.0f} / OOS {s['oos']:+5.0f})")

    print("\n--- B. CARTEIRAS SIMÉTRICAS PURAS (SYM_TOP1_WIN + SYM_TOP1_WDO) ---")
    for name, pairs in [
        ("SYM_TOP1: WIN(TP240) + WDO(TP12 t24 - original)", [("W", tf_sym_w240), ("D", sim_asset(df_d, "WDO", 14.0, "fix", 12.0, 0.0, 0.0, 24)[1])]),
        ("SYM_TOP1: WIN(TP240) + WDO(TP11 t24)",            [("W", tf_sym_w240), ("D", tf_sym_d11)]),
        ("SYM_TOP1: WIN(TP240) + WDO(ProxWall t18)",        [("W", tf_sym_w240), ("D", tf_sym_dnw18)]),
        ("SYM_TOP1: WIN(TP280 t12) + WDO(ProxWall t18)",    [("W", tf_sym_w280), ("D", tf_sym_dnw18)]),
    ]:
        st, corr = combine_folios(pairs)
        print(f"  {name:<48}: {st['ops']:3d} ops | PF {st['pf']:4.2f} | Net {st['net']:+7.0f} | "
              f"DD {st['dd']:4.0f} | R/DD {st['rdd']:5.2f} | {st['meses']} | corr={corr:+.3f}")

    print("\n--- C. COMPARAÇÃO NO PORTFÓLIO COM E22_WIN (1ct e 2ct) E V1a_WDO ---")
    folios = [
        ("1. E22_WIN (1ct) sozinho",                         [("E22", tf_e22_1)]),
        ("2. E22_WIN (1ct) + SYM_TOP1_WIN (1ct)",            [("E22", tf_e22_1), ("SW", tf_sym_w240)]),
        ("3. E22_WIN (1ct) + SYM_TOP1_WIN Manhã <10h",       [("E22", tf_e22_1), ("SWM", tf_sym_wm)]),
        ("4. E22_WIN (1ct) + SYM_TOP1_WDO (TP11 t24)",       [("E22", tf_e22_1), ("SD11", tf_sym_d11)]),
        ("5. E22_WIN (1ct) + SYM_TOP1_WDO (ProxWall t18)",   [("E22", tf_e22_1), ("SDNW", tf_sym_dnw18)]),
        ("6. E22_WIN (1ct) + V1a_WDO (1ct)",                 [("E22", tf_e22_1), ("V1a", tf_v1a)]),
        ("7. E22_WIN (2ct) + SYM_TOP1_WDO (ProxWall t18)",   [("E22_2", tf_e22_2), ("SDNW", tf_sym_dnw18)]),
        ("8. E22_WIN (2ct) + SYM_TOP1_WDO (ProxWall t24)",   [("E22_2", tf_e22_2), ("SDNW24", tf_sym_dnw24)]),
        ("9. E22_WIN (2ct) + V1a_WDO (1ct)",                 [("E22_2", tf_e22_2), ("V1a", tf_v1a)]),
        ("10. E22_WIN (2ct) + V1a_WDO + SYM_TOP1_WIN <10h",  [("E22_2", tf_e22_2), ("V1a", tf_v1a), ("SWM", tf_sym_wm)]),
    ]
    for name, pairs in folios:
        st, corr = combine_folios(pairs)
        print(f"  {name:<48}: {st['ops']:3d} ops | PF {st['pf']:4.2f} | Net {st['net']:+7.0f} | "
              f"DD {st['dd']:4.0f} | R/DD {st['rdd']:5.2f} | {st['meses']} | corr={corr:+.3f}")


if __name__ == "__main__":
    t0 = time.time()
    analyze_pivot_distance()
    audit_sym_top1_variants()
    portfolio_analysis()
    print(f"\nConcluído em {time.time()-t0:.1f}s")
