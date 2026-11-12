"""
Runner ÚNICO dos setups registrados (WIN: EST_01/04/07/13/14/15/16, WIN_E2 · WDO: 01/02/05/07/09/10).

BT e ao vivo chamam a mesma função, `run_setups`, que executa os simuladores alinhados ao MT5
(`optimize_existing_16_setups`, `test_win_aligned_wdo_matrix`, `sg_sim`, `wdo_mt5_sim`, `simulate_win_e2_wall_gasta`)
via `generate_portfolio_6_json.run_all_strategies_for_mode`. A única diferença entre BT e ao vivo é o corte de dados:
  - BT: `cutoff=None` (todo o histórico em cache).
  - Ao vivo / teste de paridade: `cutoff=T` → só barras M5/M1 FECHADAS até T entram (`mt5_loader.set_bar_cutoff`).
Fluxo: 18 filtros do `.min` do Profit (`flow_filters.load_flow_tables("min")`); ao vivo, as máscaras do dia corrente
são recalculadas do `.min` com `research.setup_parity.build_flow_min.session_masks`.

Trades cuja saída cai na última barra disponível antes do fim do pregão são marcados `status="ABERTA"`.
"""
from __future__ import annotations

import contextlib
from typing import Dict, List, Optional

import pandas as pd

from research import mt5_loader
from research.flow_window_asg import generate_portfolio_6_json as gp
from research.flow_window_asg.flow_filters import load_flow_tables
from research.optimizers import sg_sim

SESSION_END_MIN = {"WIN": 17 * 60 + 55, "WDO": 17 * 60 + 55}
WIN_SIDS = ("EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "EST_16", "WIN_E2")
WDO_SIDS = ("WDO_01", "WDO_02", "WDO_05", "WDO_07", "WDO_09", "WDO_10")


@contextlib.contextmanager
def _window(start: str, end: str, cutoff, warmup_days):
    old = (gp.START_DATE, gp.END_DATE)
    gp.START_DATE, gp.END_DATE = start, end
    mt5_loader.set_bar_floor(None if warmup_days is None else pd.Timestamp(start) - pd.Timedelta(days=warmup_days))
    mt5_loader.set_bar_cutoff(cutoff)
    sg_sim.EMIT_OPEN_AT_END = gp.wsim.EMIT_OPEN_AT_END = cutoff is not None
    if hasattr(sg_sim.load_m5_m1_wdo_gex, "cache_clear"):
        sg_sim.load_m5_m1_wdo_gex.cache_clear()
    try:
        yield
    finally:
        gp.START_DATE, gp.END_DATE = old
        mt5_loader.set_bar_floor(None)
        mt5_loader.set_bar_cutoff(None)
        sg_sim.EMIT_OPEN_AT_END = gp.wsim.EMIT_OPEN_AT_END = False
        if hasattr(sg_sim.load_m5_m1_wdo_gex, "cache_clear"):
            sg_sim.load_m5_m1_wdo_gex.cache_clear()


def _load_market():
    """Mesmos dados e indicadores do gerador oficial (`generate_portfolio_6_json.main`)."""
    df_win, gex_win = gp.o16.load_win_and_wdo_aligned()
    cw = df_win["close"].values
    n50w = gp.o16.compute_nwe_series(cw, lookback=50, bw=5.0, mult=2.0)
    n30w = gp.o16.compute_nwe_series(cw, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(cw).diff()
    rsi7w = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean()
                                      / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values
    df_wdo, gex_wdo = gp.wsim.load_wdo_mt5_raw()
    cd = df_wdo["close"].values
    n50d = gp.wsim.compute_nwe_series(cd, lookback=50, bw=5.0, mult=2.0)
    n30d = gp.wsim.compute_nwe_series(cd, lookback=30, bw=3.0, mult=1.6)
    rsi7d = gp.wsim.compute_rsi7_series(cd)
    return df_win, gex_win, n50w, n30w, rsi7w, df_wdo, gex_wdo, n50d, n30d, rsi7d


def _mark_open(trades_by_sid: Dict[str, List[dict]], df_win, df_wdo, cutoff) -> None:
    if cutoff is None:
        return
    last = {}
    for asset, df in (("WIN", df_win), ("WDO", df_wdo)):
        if len(df):
            t_last = pd.Timestamp(df["t"].iloc[-1])
            last[asset] = (t_last.strftime("%Y-%m-%d"), t_last.strftime("%H:%M"), t_last.hour * 60 + t_last.minute)
    for sid, trs in trades_by_sid.items():
        for t in trs:
            lk = last.get(t["asset"])
            if lk and t["date"] == lk[0] and t["exit_time"] >= lk[1] and lk[2] < SESSION_END_MIN[t["asset"]]:
                t["status"] = "ABERTA"


def run_setups(start: str, end: str, use_flow: bool = True, flow_tables=None, cutoff=None,
               warmup_days: Optional[int] = None) -> Dict[str, List[dict]]:
    """
    Trades de todos os setups entre `start` e `end` (datas ISO), com dados fechados até `cutoff`.
    `warmup_days`: dias corridos de histórico antes de `start` (None = histórico inteiro). O teste
    `research/setup_parity/test_runner_causal.py` prova que o valor usado ao vivo não muda nenhum trade.
    """
    if flow_tables is None:
        flow_tables, _ = load_flow_tables("min")
    with _window(start, end, cutoff, warmup_days):
        mk = _load_market()
        out = gp.run_all_strategies_for_mode(*mk, flow_tables, use_flow=use_flow)
        _mark_open(out, mk[0], mk[5], cutoff)
    for sid in out:
        out[sid] = [t for t in out[sid] if start <= t["date"] <= end]
    return out
