"""
Backtest comparativo IS / OOS das variantes GEX WIN e WDO contra o baseline de produção.
Não altera nenhum arquivo de produção.

Uso: python -m research.gex_audit_bt.run_bt_compare
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import setups_runner  # noqa: E402
from research import mt5_loader  # noqa: E402
from research.flow_window_asg.flow_filters import load_flow_tables  # noqa: E402
from research.optimizers import sg_sim, wdo_mt5_sim  # noqa: E402
from research.setup_parity.bt_8_elite import ELITE, NATIVE, run_elite  # noqa: E402
from research.setup_parity.bt_32_slots import END, SPLIT, START, stats  # noqa: E402

CSV_DIR = os.path.join(ROOT, "research", "gex_audit_bt", "gex_csvs")
RES_DIR = os.path.join(ROOT, "research", "gex_audit_bt", "results")

PROD_WIN = os.path.join(ROOT, "mt5", "Files", "jumba_gex_win_history.csv")
PROD_WDO = os.path.join(ROOT, "mt5", "Files", "jumba_gex_wdo_history.csv")

_ORIG_LOAD_GEX_CSV = mt5_loader.load_gex_csv


def set_gex_paths(win_csv: str, wdo_csv: str):
    """Atualiza todas as referências e caches de GEX antes de carregar mercado."""
    mt5_loader.HIST_WIN = win_csv
    mt5_loader.HIST_WDO = wdo_csv
    wdo_mt5_sim.HIST_WDO = wdo_csv
    mt5_loader.load_gex_csv = lambda path=None: _ORIG_LOAD_GEX_CSV(win_csv if path is None else path)
    if hasattr(sg_sim.load_m5_m1_wdo_gex, "cache_clear"):
        sg_sim.load_m5_m1_wdo_gex.cache_clear()


def verify_gex_loaded(variant_name: str, win_csv: str, wdo_csv: str, baseline_sig: dict | None = None):
    g_win = mt5_loader.load_gex_csv()
    _, g_wdo = wdo_mt5_sim.load_wdo_mt5_raw()
    _, _, _, g_sg = sg_sim.load_m5_m1_wdo_gex()
    sample_d = "2026-10-01"
    sig = {
        "win_walls": tuple(round(float(x), 2) for x in g_win[sample_d]["walls"][:5]),
        "win_flip": round(float(g_win[sample_d]["gamma_flip"] or 0.0), 2),
        "sg_walls": tuple(round(float(x), 2) for x in g_sg[sample_d]["walls"][:5]),
        "wdo_walls": tuple(round(float(x), 2) for x in g_wdo[sample_d]["walls"][:5]),
        "wdo_flip": round(float(g_wdo[sample_d]["gamma_flip"] or 0.0), 2),
    }
    assert sig["win_walls"] == sig["sg_walls"], "sg_sim nao pegou o mesmo WIN GEX!"
    if baseline_sig is not None and not variant_name.startswith("BASE_"):
        if win_csv != PROD_WIN:
            all_same = all(
                round(float(g_win[d]["gamma_flip"] or 0.0), 2) == baseline_sig["win_flips_all"].get(d)
                and tuple(round(float(x), 2) for x in g_win[d]["walls"][:5]) == baseline_sig["win_walls_all"].get(d)
                for d in ("2026-06-01", "2026-09-01", "2026-10-01", "2026-11-04")
                if d in g_win
            )
            assert not all_same, f"WIN GEX nao mudou para {win_csv}!"
        if wdo_csv != PROD_WDO:
            all_same = all(
                round(float(g_wdo[d]["gamma_flip"] or 0.0), 2) == baseline_sig["wdo_flips_all"].get(d)
                and tuple(round(float(x), 2) for x in g_wdo[d]["walls"][:5]) == baseline_sig["wdo_walls_all"].get(d)
                for d in ("2026-06-01", "2026-09-01", "2026-10-01", "2026-11-04")
                if d in g_wdo
            )
            assert not all_same, f"WDO GEX nao mudou para {wdo_csv}!"
    if baseline_sig is None:
        sig["win_flips_all"] = {d: round(float(g_win[d]["gamma_flip"] or 0.0), 2) for d in ("2026-06-01", "2026-09-01", "2026-10-01", "2026-11-04") if d in g_win}
        sig["win_walls_all"] = {d: tuple(round(float(x), 2) for x in g_win[d]["walls"][:5]) for d in ("2026-06-01", "2026-09-01", "2026-10-01", "2026-11-04") if d in g_win}
        sig["wdo_flips_all"] = {d: round(float(g_wdo[d]["gamma_flip"] or 0.0), 2) for d in ("2026-06-01", "2026-09-01", "2026-10-01", "2026-11-04") if d in g_wdo}
        sig["wdo_walls_all"] = {d: tuple(round(float(x), 2) for x in g_wdo[d]["walls"][:5]) for d in ("2026-06-01", "2026-09-01", "2026-10-01", "2026-11-04") if d in g_wdo}
    return sig


def eval_variant(asset_group: str, variant_name: str, win_csv: str, wdo_csv: str,
                 ft, baseline_sig: dict | None = None):
    set_gex_paths(win_csv, wdo_csv)
    sig = verify_gex_loaded(variant_name, win_csv, wdo_csv, baseline_sig=baseline_sig)

    summary_rows = []
    setup_rows = []

    with setups_runner._window(START, END, None, None):
        mk = setups_runner._load_market()

        # 1) Elite 8 (somente os EAs do ativo testado)
        elite_sids = [s for s in ELITE if (s.startswith("WDO") if asset_group == "WDO" else not s.startswith("WDO"))]
        for mode_lbl, use_native in (("elite_sem_filtro", False), ("elite_com_filtro", True)):
            all_trs = []
            for sid in elite_sids:
                fname = NATIVE[asset_group] if use_native else "0_BASE_MT5"
                trs = run_elite(sid, mk, ft, fname)
                all_trs.extend(trs)
                s_all = stats(trs)
                s_is = stats(trs, hi=SPLIT)
                s_oos = stats(trs, lo=SPLIT)
                setup_rows.append({
                    "asset": asset_group, "variant": variant_name, "suite": mode_lbl, "sid": sid,
                    **s_all, "is_net": s_is["net"], "oos_ops": s_oos["ops"], "oos_net": s_oos["net"],
                    "oos_pf": s_oos["pf"], "oos_ret_dd": s_oos["ret_dd"],
                })
            s_all = stats(all_trs)
            s_is = stats(all_trs, hi=SPLIT)
            s_oos = stats(all_trs, lo=SPLIT)
            summary_rows.append({
                "asset": asset_group, "variant": variant_name, "suite": mode_lbl,
                **s_all, "is_net": s_is["net"], "oos_ops": s_oos["ops"], "oos_net": s_oos["net"],
                "oos_pf": s_oos["pf"], "oos_ret_dd": s_oos["ret_dd"],
            })

        # 2) Setups Registrados do Painel (com fluxo oficial)
        panel_res = setups_runner.gp.run_all_strategies_for_mode(*mk, ft, use_flow=True)
        panel_sids = setups_runner.WDO_SIDS if asset_group == "WDO" else setups_runner.WIN_SIDS
        panel_trs = []
        for sid in panel_sids:
            trs = [t for t in panel_res[sid] if START <= t["date"] <= END]
            panel_trs.extend(trs)
            s_all = stats(trs)
            s_is = stats(trs, hi=SPLIT)
            s_oos = stats(trs, lo=SPLIT)
            setup_rows.append({
                "asset": asset_group, "variant": variant_name, "suite": "panel_registrados", "sid": sid,
                **s_all, "is_net": s_is["net"], "oos_ops": s_oos["ops"], "oos_net": s_oos["net"],
                "oos_pf": s_oos["pf"], "oos_ret_dd": s_oos["ret_dd"],
            })
        s_all = stats(panel_trs)
        s_is = stats(panel_trs, hi=SPLIT)
        s_oos = stats(panel_trs, lo=SPLIT)
        summary_rows.append({
            "asset": asset_group, "variant": variant_name, "suite": "panel_registrados",
            **s_all, "is_net": s_is["net"], "oos_ops": s_oos["ops"], "oos_net": s_oos["net"],
            "oos_pf": s_oos["pf"], "oos_ret_dd": s_oos["ret_dd"],
        })

    return summary_rows, setup_rows, sig


def main():
    os.makedirs(RES_DIR, exist_ok=True)
    ft, _ = load_flow_tables("min")

    all_summary = []
    all_setups = []

    win_configs = [
        ("BASE_PROD", PROD_WIN),
        ("BASE_RECALC", os.path.join(CSV_DIR, "win_base_recalc.csv")),
        ("V1_OI_FLIP", os.path.join(CSV_DIR, "win_v1_oi_flip.csv")),
        ("V2_B3_STRIKES", os.path.join(CSV_DIR, "win_v2_b3_strikes.csv")),
    ]
    wdo_configs = [
        ("BASE_PROD", PROD_WDO),
        ("BASE_RECALC", os.path.join(CSV_DIR, "wdo_base_recalc.csv")),
        ("V1_FIXES123", os.path.join(CSV_DIR, "wdo_v1_fixes123.csv")),
        ("V2A_MULTI_ALWAYS", os.path.join(CSV_DIR, "wdo_v2a_multiexp_always.csv")),
        ("V2B_MULTI_ROLL5D", os.path.join(CSV_DIR, "wdo_v2b_multiexp_roll5d.csv")),
    ]

    print("=== RODANDO VARIANTES WIN (WDO FIXO EM BASE_PROD) ===", flush=True)
    base_sig = None
    for vname, wcsv in win_configs:
        sr, st, sig = eval_variant("WIN", vname, wcsv, PROD_WDO, ft, baseline_sig=base_sig)
        if base_sig is None:
            base_sig = sig
        all_summary.extend(sr)
        all_setups.extend(st)
        print(f"  [WIN {vname}] concluido", flush=True)

    print("\n=== RODANDO VARIANTES WDO (WIN FIXO EM BASE_PROD) ===", flush=True)
    for vname, dcsv in wdo_configs:
        sr, st, _ = eval_variant("WDO", vname, PROD_WIN, dcsv, ft, baseline_sig=base_sig)
        all_summary.extend(sr)
        all_setups.extend(st)
        print(f"  [WDO {vname}] concluido", flush=True)

    df_sum = pd.DataFrame(all_summary)
    df_set = pd.DataFrame(all_setups)
    df_sum.to_csv(os.path.join(RES_DIR, "bt_compare_summary.csv"), index=False)
    df_set.to_csv(os.path.join(RES_DIR, "bt_compare_by_setup.csv"), index=False)

    print("\n" + "=" * 115)
    print("  RESUMO COMPARATIVO GEX AUDIT BT (IS: 02/01-31/07 | OOS: 01/08-06/11)")
    print("=" * 115)
    for asset in ("WDO", "WIN"):
        for suite in ("panel_registrados", "elite_com_filtro", "elite_sem_filtro"):
            sub = df_sum[(df_sum["asset"] == asset) & (df_sum["suite"] == suite)].copy()
            b_prod = sub.loc[sub["variant"] == "BASE_PROD", "net"].iloc[0]
            b_rec = sub.loc[sub["variant"] == "BASE_RECALC", "net"].iloc[0]
            sub["d_prod"] = sub["net"] - b_prod
            sub["d_rec"] = sub["net"] - b_rec
            print(f"\n--- {asset} | {suite} ---")
            cols = ["variant", "ops", "wr_pct" if "wr_pct" in sub else "wr", "pf", "net", "mdd", "ret_dd", "pos_m", "is_net", "oos_ops", "oos_net", "oos_pf", "oos_ret_dd", "d_prod", "d_rec"]
            cols = [c for c in cols if c in sub.columns]
            print(sub[cols].to_string(index=False))


if __name__ == "__main__":
    main()
