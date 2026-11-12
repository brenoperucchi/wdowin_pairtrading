"""
As 31 versões de entrada do teste do gate (research/div_gate/PLANO.md, seção 2) e como simular cada uma
pelos mesmos simuladores do runner único. `run_version(vid, mk, ft, sig_filter, flow_on, start, end)`.
`flow_on` só importa para o WIN_E2, que tem condições de fluxo embutidas no próprio simulador.
"""
from __future__ import annotations

from research.flow_window_asg import generate_portfolio_6_json as gp
from research.optimizers import sg_sim

# vid: (ativo, família, simulador, slot, kwargs de saída, filtro de fluxo atual)
VERSIONS = {
    "EST_01": ("WIN", "W01", "o16", 1, dict(entry_override="CURRENT", be_mode="BE_WALL_SHIELD", wall_shield_buf=25.0, tp_mode="TP_MAIN_WALL"), "14_NR_BREAKOUT_SQUEEZE"),
    "WIN_S02": ("WIN", "W02", "o16", 2, {}, "16_NR_DIV_ABS_OR_AGGR"),
    "EST_16": ("WIN", "W03", "o16", 3, dict(entry_override="CURRENT", be_mode="BE_WALL_SHIELD", wall_shield_buf=20.0, tp_mode="TP_MIDWALL"), "16_NR_DIV_ABS_OR_AGGR"),
    "WIN_S04": ("WIN", "W04", "o16", 4, {}, "15_NR_IGNITION_DIV"),
    "EST_04": ("WIN", "W04A", "aligned", 4, dict(be_mode="BE_WALL_2STAGE_177K", wall_shield_buf=15.0, tp_mode="TP_MIDWALL", entry_override="ALIGNED"), "15_NR_IGNITION_DIV"),
    "WIN_S05": ("WIN", "W05", "o16", 5, {}, "17_NR_SQUEEZE_CLEAN"),
    "WIN_S06": ("WIN", "W06", "o16", 6, {}, "14_NR_BREAKOUT_SQUEEZE"),
    "EST_07_EA": ("WIN", "W07", "o16", 7, dict(entry_override="CURRENT", be_mode="BE_WALL_SHIELD", wall_shield_buf=15.0, tp_mode="TP_CURRENT"), "16_NR_DIV_ABS_OR_AGGR"),
    "EST_07": ("WIN", "W07", "o16", 7, dict(entry_override="CURRENT", be_mode="BE_WALL_SHIELD", wall_shield_buf=15.0, tp_mode="TP_MIDWALL"), "16_NR_DIV_ABS_OR_AGGR"),
    "WIN_S09": ("WIN", "W09", "o16", 9, {}, "17_NR_SQUEEZE_CLEAN"),
    "WIN_S10": ("WIN", "W10", "o16", 10, {}, "16_NR_DIV_ABS_OR_AGGR"),
    "WIN_S11": ("WIN", "W11", "o16", 11, {}, "17_NR_SQUEEZE_CLEAN"),
    "EST_13": ("WIN", "W13", "sg", 13, {}, "11_PROFIT_WALL_SHIELD"),
    "EST_14": ("WIN", "W14", "sg", 14, {}, "12_NR_WALL_TRAP_DIV"),
    "EST_15": ("WIN", "W15", "sg", 15, {}, "14_NR_BREAKOUT_SQUEEZE"),
    "WIN_S16": ("WIN", "W16", "sg", 16, {}, "17_NR_SQUEEZE_CLEAN"),
    "WIN_E2": ("WIN", "WE2", "e2", 0, {}, "13_NR_PRICE_ABS_DIV"),
    "WDO_01": ("WDO", "D01", "wdo", 1, {}, "13_NR_PRICE_ABS_DIV"),
    "WDO_02": ("WDO", "D02", "wdo", 2, {}, "17_NR_SQUEEZE_CLEAN"),
    "WDO_09": ("WDO", "D03", "wdo", 3, {}, "18_NR_ASG_PLUS_DIV"),
    "WDO_S04": ("WDO", "D04", "wdo", 4, {}, None),
    "WDO_05": ("WDO", "D05", "wdo", 5, {}, "13_NR_PRICE_ABS_DIV"),
    "WDO_S06": ("WDO", "D06", "wdo", 6, {}, "10_PROFIT_SMART_WALL"),
    "WDO_07": ("WDO", "D07", "wdo", 7, {}, "12_NR_WALL_TRAP_DIV"),
    "WDO_S08": ("WDO", "D08", "wdo", 8, {}, "13_NR_PRICE_ABS_DIV"),
    "WDO_S09": ("WDO", "D09", "wdo", 9, {}, "7_PROFIT_DEFENSE"),
    "WDO_10": ("WDO", "D10", "wdo", 10, {}, "6_COMBO_SMART"),
    "WDO_S11": ("WDO", "D11", "wdo", 11, {}, "8_PROFIT_SWEEP"),
    "WDO_S13": ("WDO", "D13", "wdo", 13, {}, "2_JANELA_S_EXPLOSAO"),
    "WDO_S15": ("WDO", "D15", "wdo", 15, {}, "14_NR_BREAKOUT_SQUEEZE"),
}
ELITE_8 = ("EST_04", "EST_07_EA", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07")


def run_version(vid, mk, ft, sig_filter, flow_on, start, end):
    asset, _fam, sim, k, kw, _flt = VERSIONS[vid]
    df_win, gex_win, n50w, n30w, rsi7w, df_wdo, gex_wdo, n50d, n30d, rsi7d = mk
    A = (df_win, gex_win, n50w[0], n50w[1], n50w[2], n50w[4], n30w[0], n30w[1], n30w[2], n30w[4], rsi7w)
    if sim == "o16":
        tr, _ = gp.o16.simulate_single_est_slot(k, *A, cost_pts=gp.COST_WIN_PTS, sig_filter=sig_filter,
                                                start_date=start, **kw)
        out = gp.format_win_o16_trades([t for t in tr if start <= str(t["date"]) <= end], df_win, vid)
    elif sim == "aligned":
        tr, _ = gp.simulate_aligned_win_wdo_slot(k, *A, cost_pts=gp.COST_WIN_PTS, sig_filter=sig_filter,
                                                 start_date=start, **kw)
        out = gp.format_win_o16_trades([t for t in tr if start <= str(t["date"]) <= end], df_win, vid)
    elif sim == "sg":
        out = gp.format_sg_trades(sg_sim.run(slots=(k,), start=start, cost_pts=gp.COST_WIN_PTS, sig_filter=sig_filter))
    elif sim == "e2":
        out = gp.simulate_win_e2_wall_gasta(df_win, gex_win, n50w, n30w, ft, use_flow=flow_on, sig_filter=sig_filter)
    else:
        out = gp.format_wdo_trades(gp.wsim.simulate_wdo_core_slot(
            k, df_wdo, gex_wdo, n50d[0], n50d[1], n50d[2], n50d[4], n30d[0], n30d[1], n30d[2], n30d[4], rsi7d,
            start_date=start, end_date=end, cost_pts=gp.COST_WDO_PTS, sig_filter=sig_filter), vid)
    return [t for t in out if start <= t["date"] <= end]
