# -*- coding: utf-8 -*-
"""
Simulação combinatória completa das 4 estratégias:
  1. E22_WIN     : ESP_DIV_V22_WIN Produção (M.V32_PROD, all, OPC, !super, seq<=1, 10h-16h, ext50>-0.5&sl>-0.5, SL200 BE180->20 t12)
  2. C1a_WIN     : BRK_F1F2 Rompimento c/ Convergência (conv_k1w2, near&crs, hh!=11, ext50_trend<0.5, SL280 TP280 t24)
  3. V1a_WDO     : Campeã WDO v3.2 (V32_OPEN, wall, CONF, d_wall<=3.5, hh!=11, ext30>0, SL14 ProxWall t24)
  4. SYM_TOP1    : Simétrica WIN+WDO (V32_OPEN, wall, CONF, seq<=1, hh!=11, ext50>-0.5&sl>-0.5; WIN SL280 TP240 t24 + WDO SL14 ProxWall t18)

Avalia todas as combinações de 1, 2, 3 e 4 estratégias:
  - Parte A: 1 ct por estratégia (E22_WIN 1ct, C1a_WIN 1ct, V1a_WDO 1ct, SYM_TOP1 Par WIN+WDO 1ct cada)
  - Parte B: Mesma grade com peso de produção E22_WIN = 2 ct
  - Parte C: Decomposição de SYM_TOP1_WIN vs SYM_TOP1_WDO + impacto de usar uma única trava UM_POR_VEZ por ativo (WIN / WDO)
  - Parte D: Matriz de correlação diária, pior dia, pior mês e máximo drawdown em R$.
"""
from __future__ import annotations

import itertools
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
    win_cache, XW, get_e22_signals, eval_e22
)
from research.div_master.wdo_especialista.robustez_final import make_P as make_P_wdo
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo, OPT_OPEN
from research.div_master.flow_breakout.busca_convergencia_v32 import collect_asset_conv
from research.div_master.flow_breakout.audit_convergencia_v32 import sim_win_df
from research.div_master.test_sym_top1 import collect_sym_top1, sim_asset


def extra_metrics(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return dict(worst_day=0, worst_mo=0, max_seq_loss=0)
    d_sum = df.groupby("date")["pnl"].sum()
    m_sum = df.assign(mo=df["date"].str[:7]).groupby("mo")["pnl"].sum()
    # Sequência máxima de losses no portfólio ordenado
    T = df.sort_values(["date", "xt", "tm"])
    cur, mx = 0, 0
    for p in T["pnl"].values:
        if p < 0:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return dict(
        worst_day=round(float(d_sum.min())),
        worst_mo=round(float(m_sum.min())),
        max_seq_loss=int(mx),
    )


def eval_combo(dfs: list[tuple[str, pd.DataFrame, float]], dedup_asset: bool = False) -> dict:
    parts = []
    for name, df, mult in dfs:
        c = df[["date", "tm", "xt", "pnl", "asset"]].copy()
        c["pnl"] = c["pnl"] * mult
        c["strat"] = name
        parts.append(c)
    comb = pd.concat(parts, ignore_index=True).sort_values(["date", "tm", "xt"]).reset_index(drop=True)

    if dedup_asset:
        # Se 2 estratégias no mesmo ativo quiserem operar ao mesmo tempo, aplica UM_POR_VEZ compartilhado por ativo
        out_assets = []
        for asset in comb["asset"].unique():
            sub = comb[comb["asset"] == asset].sort_values(["date", "tm", "xt"]).copy()
            out_assets.append(bt.mgmt(sub, "pnl", "xt", "UM"))
        comb = pd.concat(out_assets, ignore_index=True).sort_values(["date", "tm", "xt"]).reset_index(drop=True)

    st = bt.stats(comb, "pnl", "xt")
    ex = extra_metrics(comb)
    return {**st, **ex}


def build_strategies():
    # 1. E22_WIN (1 ct base)
    r_e22 = get_e22_signals("all", M.V32_PROD)
    _, tf_e22 = eval_e22(r_e22, mult=1.0)
    tf_e22["asset"] = "WIN"

    # 2. C1a_WIN (BRK_F1F2: conv_k1w2 | near&crs | hh!=11 | ext50_trend<0.5 | SL280 TP280 t24)
    df_conv_win = collect_asset_conv("WIN", "wall", True)
    m_c1a = (
        (df_conv_win["family"] == "BRK_F1F2")
        & df_conv_win["conv_k1_ok"]
        & df_conv_win["w2_fav"]
        & df_conv_win["near_wall"]
        & df_conv_win["crossed_wall"]
        & (df_conv_win["hh"] != 11)
        & (df_conv_win["ext50_trend"] < 0.5)
    )
    tf_c1a = bt.mgmt(sim_win_df(df_conv_win[m_c1a], 280.0, 280.0, 24, "padrao"), "pnl", "xt", "UM")
    tf_c1a["asset"] = "WIN"

    # 3. V1a_WDO (V32_OPEN wall | CONF | d_wall<=3.5 | hh!=11 | ext30>0 | SL14 ProxWall t24)
    P_wdo = make_P_wdo(zone=3.5, pierce_max=6.0)
    r_v1a = run_v32_wdo(P_wdo, "wall", "common", OPT_OPEN, "CONF",
                        lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
    _, tf_v1a = eval_wdo(r_v1a, 14.0, "nw", 0.0, 24, "UM")
    tf_v1a["asset"] = "WDO"

    # 4. SYM_TOP1_WIN (SL280 TP240 t24) + SYM_TOP1_WDO (SL14 ProxWall t18)
    df_sw = collect_sym_top1("WIN", nodiv=False, strict_no_super=False)
    _, tf_sym_w = sim_asset(df_sw, "WIN", 280.0, "fix", 240.0, 0.0, 0.0, 24)
    tf_sym_w["asset"] = "WIN"

    df_sd = collect_sym_top1("WDO", nodiv=False, strict_no_super=False)
    _, tf_sym_d = sim_asset(df_sd, "WDO", 14.0, "nw_all", 0.0, 0.0, 0.0, 18)
    tf_sym_d["asset"] = "WDO"

    tf_sym_par = pd.concat([tf_sym_w, tf_sym_d], ignore_index=True).sort_values(["date", "tm", "xt"]).reset_index(drop=True)

    return {
        "E22_WIN": tf_e22,
        "C1a_WIN": tf_c1a,
        "V1a_WDO": tf_v1a,
        "SYM_PAR": tf_sym_par,
        "SYM_WIN": tf_sym_w,
        "SYM_WDO": tf_sym_d,
    }


def print_block(title: str, items: list[tuple[str, pd.DataFrame, float]], dedup: bool = False):
    print("\n" + "=" * 124)
    print(title)
    print("=" * 124)
    print(f"{'k':>1} | {'Combinação':<44} | {'ops':>4} | {'WR':>5} | {'PF':>4} | {'Net (R$)':>8} | {'DD':>5} | "
          f"{'R/DD':>6} | {'Meses':>5} | {'H1 / H2 / OOS':<22} | {'PiorDia':>7} | {'PiorMês':>7}")
    print("-" * 124)
    rows = []
    for k in range(1, len(items) + 1):
        for comb in itertools.combinations(items, k):
            lbl = " + ".join(f"{n}" + (f"({int(m)}ct)" if m != 1.0 else "") for n, _, m in comb)
            st = eval_combo(list(comb), dedup_asset=dedup)
            rows.append((k, st["rdd"], lbl, st))
    # Ordena por k crescente, e dentro de cada k por Ret/DD decrescente
    rows.sort(key=lambda x: (x[0], -x[1]))
    for k, _, lbl, st in rows:
        subp = f"{st['h1']:+6d}/{st['h2']:+6d}/{st['oos']:+6d}"
        print(f"{k:>1} | {lbl:<44} | {st['ops']:4d} | {st['wr']:4.1f}% | {st['pf']:4.2f} | {st['net']:+8d} | "
              f"{st['dd']:5d} | {st['rdd']:6.2f} | {st['meses']:>5} | {subp:<22} | {st['worst_day']:+7d} | {st['worst_mo']:+7d}")


def print_corr_and_overlap(strats: dict[str, pd.DataFrame]):
    print("\n" + "=" * 124)
    print("MATRIZ DE CORRELAÇÃO DIÁRIA DE PNL (213 PREGÕES) E SOBREPOSIÇÃO DE HORÁRIO NO MESMO ATIVO")
    print("=" * 124)
    keys = ["E22_WIN", "C1a_WIN", "V1a_WDO", "SYM_WIN", "SYM_WDO", "SYM_PAR"]
    all_dates = sorted(win_cache.keys())
    daily = pd.DataFrame({
        k: strats[k].groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)
        for k in keys
    })
    print(daily.corr().round(3).to_string())

    print("\nSobreposição temporal simultânea (quando uma nova entrada ocorre enquanto outra estratégia do mesmo ativo está posicionada):")
    for a, b, asset in [
        ("E22_WIN", "C1a_WIN", "WIN"),
        ("E22_WIN", "SYM_WIN", "WIN"),
        ("C1a_WIN", "SYM_WIN", "WIN"),
        ("V1a_WDO", "SYM_WDO", "WDO"),
    ]:
        da = strats[a]
        db = strats[b]
        # Conta quantos trades de b abrem dentro do intervalo [tm, xt] de um trade de a
        ov = 0
        by_day = {d: list(zip(g["tm"], g["xt"])) for d, g in da.groupby("date")}
        for r in db.itertuples():
            for t0, t1 in by_day.get(r.date, []):
                if t0 <= r.tm <= t1:
                    ov += 1
                    break
        # Também conta quantos trades têm exatamente o mesmo minuto de entrada
        same_tm = len(set(zip(da["date"], da["tm"])) & set(zip(db["date"], db["tm"])))
        print(f"  {asset}: {a} ({len(da)} ops) vs {b} ({len(db)} ops) -> {ov} sobreposições de horário ({same_tm} no mesmo candle M5)")


def main():
    t0 = time.time()
    strats = build_strategies()

    # Bloco 1: As 4 estratégias com peso 1 ct cada (SYM_PAR = SYM_TOP1 operando WIN + WDO)
    items_1ct = [
        ("E22_WIN", strats["E22_WIN"], 1.0),
        ("C1a_WIN", strats["C1a_WIN"], 1.0),
        ("V1a_WDO", strats["V1a_WDO"], 1.0),
        ("SYM_PAR", strats["SYM_PAR"], 1.0),
    ]
    print_block("1. COMBINAÇÕES 1 A 4 ESTRATÉGIAS (PESO 1:1:1:1 | CONTAS / SUBESTRATÉGIAS INDEPENDENTES)", items_1ct, dedup=False)

    # Bloco 2: Mesmas 4 estratégias, mas aplicando trava UM_POR_VEZ compartilhada por ativo (se quiser impedir posição simultânea no mesmo ativo)
    print_block("2. MESMAS COMBINAÇÕES COM TRAVA ÚNICA UM_POR_VEZ POR ATIVO (SEM POSIÇÃO SIMULTÂNEA NO MESMO ATIVO)", items_1ct, dedup=True)

    # Bloco 3: Com peso de produção E22_WIN = 2 ct (2 ct E22 + 1 ct nas demais)
    items_prod = [
        ("E22_WIN", strats["E22_WIN"], 2.0),
        ("C1a_WIN", strats["C1a_WIN"], 1.0),
        ("V1a_WDO", strats["V1a_WDO"], 1.0),
        ("SYM_PAR", strats["SYM_PAR"], 1.0),
    ]
    print_block("3. COMBINAÇÕES COM PESO DE PRODUÇÃO (E22_WIN = 2 ct | DEMAIS = 1 ct | INDEPENDENTES)", items_prod, dedup=False)

    # Bloco 4: Comparação separando SYM_WIN e SYM_WDO dentro da carteira com E22 + C1a + V1a
    print("\n" + "=" * 124)
    print("4. DECOMPOSIÇÃO: ADICIONANDO APENAS SYM_WIN OU APENAS SYM_WDO AO NÚCLEO (E22 + C1a + V1a)")
    print("=" * 124)
    for mult_e22 in (1.0, 2.0):
        print(f"  [Peso E22_WIN = {int(mult_e22)} ct]")
        base = [("E22_WIN", strats["E22_WIN"], mult_e22), ("C1a_WIN", strats["C1a_WIN"], 1.0), ("V1a_WDO", strats["V1a_WDO"], 1.0)]
        for lbl, extra in [
            ("Núcleo (E22 + C1a + V1a)",                base),
            ("Núcleo + apenas SYM_WIN (1 ct)",          base + [("SYM_WIN", strats["SYM_WIN"], 1.0)]),
            ("Núcleo + apenas SYM_WDO (1 ct)",          base + [("SYM_WDO", strats["SYM_WDO"], 1.0)]),
            ("Núcleo + SYM_PAR (SYM_WIN + SYM_WDO)",    base + [("SYM_PAR", strats["SYM_PAR"], 1.0)]),
            ("Substituindo V1a por SYM_WDO (E22+C1a+SYM_WDO)", [("E22_WIN", strats["E22_WIN"], mult_e22), ("C1a_WIN", strats["C1a_WIN"], 1.0), ("SYM_WDO", strats["SYM_WDO"], 1.0)]),
        ]:
            st = eval_combo(extra, dedup_asset=False)
            print(f"    {lbl:<50}: {st['ops']:4d} ops | PF {st['pf']:4.2f} | Net {st['net']:+7d} | DD {st['dd']:4d} | "
                  f"R/DD {st['rdd']:5.2f} | {st['meses']} | H1 {st['h1']:+5d} H2 {st['h2']:+5d} OOS {st['oos']:+5d} | PiorDia {st['worst_day']:+5d}")

    print_corr_and_overlap(strats)
    print(f"\nConcluído em {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
