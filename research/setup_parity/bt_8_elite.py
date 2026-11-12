"""
BT dos 8 EAs "Elite" do MT5 (perfis Jumba_8_COM_FILTRO / Jumba_8_SEM_FILTRO, `mt5/build_xp_profiles_11_8.py`):
EST-04, EST-07, EST-13, EST-14, EST-15 (WIN) e WDO-01, WDO-05, WDO-07.

Cada EA individual roda UM slot do Core (`PRESET_SINGLE_ROBOT`) com a configuração do Core MQL, que difere da
versão registrada no painel em dois pontos:
  1. EST-07 no Core: BE_WALL_SHIELD(15) + TP_Original (650) — o registrado usa TP_MIDWALL.
  2. Filtro de fluxo nativo (`InpUseFlowFilter`): WIN = 4_FLUXO_ABSORCAO, WDO = 3_FLUXO_INST
     (as mesmas condições de `flow_filters.py`), em vez dos filtros NR_* dos registrados.
Simuladores: os mesmos do runner (EST-04 alinhado WDO, EST-07 o16, EST-13..15 sg_sim, WDO wdo_mt5_sim).
Diferença conhecida: o MT5 calcula o fluxo nativo dos ticks da corretora (lote inst. >= 50); aqui vem do `.min`.
Saída: results/bt_8_elite_summary.csv, results/bt_8_elite_trades.csv
Uso: python -m research.setup_parity.bt_8_elite
"""
from __future__ import annotations

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.setups_runner import _load_market, _window  # noqa: E402
from research.flow_window_asg import generate_portfolio_6_json as gp  # noqa: E402
from research.flow_window_asg.flow_filters import MISSING_FLOW_LOOKUPS, load_flow_tables, make_sig_filter  # noqa: E402
from research.optimizers import sg_sim  # noqa: E402
from research.setup_parity.bt_32_slots import END, SPLIT, START, stats  # noqa: E402

OUT = os.path.join(ROOT, "research", "setup_parity", "results")
ELITE = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"]
NATIVE = {"WIN": "4_FLUXO_ABSORCAO", "WDO": "3_FLUXO_INST"}


def run_elite(sid, mk, ft, fname):
    df_win, gex_win, n50w, n30w, rsi7w, df_wdo, gex_wdo, n50d, n30d, rsi7d = mk
    asset = "WDO" if sid.startswith("WDO") else "WIN"
    sf = make_sig_filter(ft, asset, fname)
    k = int(sid[-2:])
    A = (df_win, gex_win, n50w[0], n50w[1], n50w[2], n50w[4], n30w[0], n30w[1], n30w[2], n30w[4], rsi7w)
    if sid == "EST_04":
        tr, _ = gp.simulate_aligned_win_wdo_slot(4, *A, be_mode="BE_WALL_2STAGE_177K", wall_shield_buf=15.0,
                                                 tp_mode="TP_MIDWALL", entry_override="ALIGNED",
                                                 cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START)
        out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)
    elif sid == "EST_07":
        tr, _ = gp.o16.simulate_single_est_slot(7, *A, entry_override="CURRENT", be_mode="BE_WALL_SHIELD",
                                                wall_shield_buf=15.0, tp_mode="TP_CURRENT",
                                                cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START)
        out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)
    elif asset == "WIN":
        out = gp.format_sg_trades(sg_sim.run(slots=(k,), start=START, cost_pts=gp.COST_WIN_PTS, sig_filter=sf))
    else:
        out = gp.format_wdo_trades(gp.wsim.simulate_wdo_core_slot(
            k, df_wdo, gex_wdo, n50d[0], n50d[1], n50d[2], n50d[4], n30d[0], n30d[1], n30d[2], n30d[4], rsi7d,
            start_date=START, end_date=END, cost_pts=gp.COST_WDO_PTS, sig_filter=sf), sid)
    return [t for t in out if START <= t["date"] <= END]


def main():
    os.makedirs(OUT, exist_ok=True)
    ft, _ = load_flow_tables("min")
    rows, all_tr = [], []
    with _window(START, END, None, None):
        mk = _load_market()
        for sid in ELITE:
            asset = "WDO" if sid.startswith("WDO") else "WIN"
            for mode, fname in (("sem_filtro", "0_BASE_MT5"), ("com_filtro", NATIVE[asset])):
                trs = run_elite(sid, mk, ft, fname)
                s, s_is, s_oos = stats(trs), stats(trs, hi=SPLIT), stats(trs, lo=SPLIT)
                rows.append({"sid": sid, "mode": mode, "filter": fname, **s, "is_net": s_is["net"],
                             "oos_ops": s_oos["ops"], "oos_net": s_oos["net"], "oos_pf": s_oos["pf"],
                             "oos_ret_dd": s_oos["ret_dd"]})
                all_tr += [dict(t, sid=sid, mode=mode) for t in trs]
                print(sid, mode, s, "OOS", s_oos["net"], flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "bt_8_elite_summary.csv"), index=False)
    T = pd.DataFrame(all_tr)
    T.to_csv(os.path.join(OUT, "bt_8_elite_trades.csv"), index=False)
    for mode in ("sem_filtro", "com_filtro"):
        for name, mask in (("WIN 5", ~T["sid"].str.startswith("WDO")), ("WDO 3", T["sid"].str.startswith("WDO")),
                           ("TOTAL 8", T["sid"].notna())):
            d = T[(T["mode"] == mode) & mask].to_dict("records")
            print(f"{mode} {name}: {stats(d)} | IS {stats(d, hi=SPLIT)} | OOS {stats(d, lo=SPLIT)}")
    print("consultas de fluxo sem dado (bloqueadas):", dict(MISSING_FLOW_LOOKUPS))


if __name__ == "__main__":
    main()
