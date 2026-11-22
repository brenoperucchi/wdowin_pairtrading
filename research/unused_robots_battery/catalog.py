"""Catálogo dos 24 robôs não utilizados (vs Top 8 ao vivo na 2004051) e interface unificada de simulação."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

import research.discover_gex_nwe_setups as disc
from research.discover_m15_deep_dive import load_tf_bars, run_experiment
from research.mt5_loader import load_win_and_wdo_aligned
from research.optimizers import optimize_existing_16_setups as o16
from research.optimizers import sg_sim
from research.optimizers import wdo_mt5_sim as wsim

FULL_START = "2026-01-02"
FULL_END = "2026-11-06"

# Split cronológico principal (anti-overfitting: seleção 100% no IS, validação cega no OOS)
IS_END = "2026-07-31"       # 02/01 a 31/07/2026 (~145 pregões)
OOS_START = "2026-08-01"    # 01/08 a 06/11/2026 (~67 pregões)

# Cross-check nos 2 semestres canônicos do projeto
H1_END = "2026-05-06"       # Jan–Mai (84 pregões)
H2_START = "2026-05-07"     # Mai–Nov (128 pregões)

WIN_COST_PTS = 10.0   # R$ 2,00 / contrato
WDO_COST_PTS = 0.5    # R$ 5,00 / contrato

ACTIVE_8_ROBOTS = [
    "EST-04", "EST-07", "EST-13", "EST-14", "EST-15",
    "WDO-01", "WDO-05", "WDO-07",
]

PROPOSTA_B_EXTRA = {"EST-01", "EST-03", "EST-05"}


@dataclass(frozen=True)
class CandidateSpec:
    code: str
    asset: str          # "WIN" | "WDO"
    engine: str         # "win_o16" | "win_m15" | "win_sg" | "wdo_core"
    slot_id: int
    tf: str             # "M5" | "M15"
    name: str
    in_proposta_b: bool
    baseline_cfg: dict[str, Any]


def _win_cfg(
    order_type: str = "CURRENT",
    be_mode: str = "BE_ZERO",
    wall_buf: float = 20.0,
    tp_mode: str = "TP_CURRENT",
    max_trades_day: int = 0,
    max_losses_day: int = 0,
    window: str = "CURRENT",
) -> dict[str, Any]:
    return {
        "order_type": order_type,
        "be_mode": be_mode,
        "wall_buf": float(wall_buf),
        "tp_mode": tp_mode,
        "max_trades_day": int(max_trades_day),
        "max_losses_day": int(max_losses_day),
        "window": window,
    }


def _wdo_cfg(
    order_type: str = "CURRENT",
    be_mode: str = "CURRENT",       # "CURRENT" | "BE_ZERO" | "BE_WALL_SHIELD" | "BE_WALL_2STAGE"
    wall_buf: float = -1.0,         # -1.0 = CURRENT | 1.0 | 1.5
    tp_mode: str = "CURRENT",       # "CURRENT" | "TP_MIDWALL" | "TP_MAIN_WALL"
    max_trades_day: int = 0,
    max_losses_day: int = 0,
    window: str = "CURRENT",
) -> dict[str, Any]:
    return {
        "order_type": order_type,
        "be_mode": be_mode,
        "wall_buf": float(wall_buf),
        "tp_mode": tp_mode,
        "max_trades_day": int(max_trades_day),
        "max_losses_day": int(max_losses_day),
        "window": window,
    }


UNUSED_24_SPECS: list[CandidateSpec] = [
    # --- 11 WIN não ativos na 2004051 (Jumba_8) ---
    CandidateSpec("EST-01", "WIN", "win_o16", 1, "M5", "WIN_PA_PINBAR_WALL (Scalper NY)", True,
                  _win_cfg("CURRENT", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL")),
    CandidateSpec("EST-02", "WIN", "win_o16", 2, "M5", "WIN_Scalper DiaTodo Lim50%B1", False,
                  _win_cfg("LIMIT_B1_MID", "BE_ZERO", 20.0, "TP_MAIN_WALL")),
    CandidateSpec("EST-03", "WIN", "win_m15", 3, "M15", "WIN_M15_FAKEOUT_TRAP", True,
                  _win_cfg("MARKET", "BE_ZERO", 30.0, "TP_MIDWALL")),
    CandidateSpec("EST-05", "WIN", "win_m15", 5, "M15", "WIN_M15_MIDWALL_PULLBACK", True,
                  _win_cfg("MARKET", "BE_ZERO", 35.0, "TP_MIDWALL")),
    CandidateSpec("EST-06", "WIN", "win_o16", 6, "M5", "WIN_Pullback StopB1 Slope", False,
                  _win_cfg("STOP_B1_EXT", "BE_WALL_SHIELD", 15.0, "TP_MAIN_WALL")),
    CandidateSpec("EST-08", "WIN", "win_o16", 8, "M5", "WIN_Breakout Rapido Core", False,
                  _win_cfg("CURRENT", "BE_ZERO", 20.0, "TP_MAIN_WALL")),
    CandidateSpec("EST-09", "WIN", "win_o16", 9, "M5", "WIN_Breakout Stop/Lim Wall NY", False,
                  _win_cfg("CURRENT", "BE_ZERO", 20.0, "TP_CURRENT")),
    CandidateSpec("EST-10", "WIN", "win_o16", 10, "M5", "WIN_MainWalls Only GammaFlip", False,
                  _win_cfg("CURRENT", "BE_ZERO", 20.0, "TP_CURRENT")),
    CandidateSpec("EST-11", "WIN", "win_o16", 11, "M5", "WIN_Grid Pullback 1+2L", False,
                  _win_cfg("STOP_B1_EXT", "BE_WALL_SHIELD", 25.0, "TP_MIDWALL")),
    CandidateSpec("EST-12", "WIN", "win_o16", 12, "M5", "WIN_Piramidacao Lucro 1+1L", False,
                  _win_cfg("CURRENT", "BE_ZERO", 20.0, "TP_MAIN_WALL")),
    CandidateSpec("EST-16", "WIN", "win_sg", 16, "M5", "WIN_SG_SPRING_Z30_WALL (1+2L)", False,
                  _win_cfg("CURRENT", "BE_WALL_SHIELD", 20.0, "TP_MIDWALL")),

    # --- 13 WDO não ativos na 2004051 (Jumba_8) ---
    CandidateSpec("WDO-02", "WDO", "wdo_core", 2, "M5", "WDO_Scalper CORE LimB1+2St", False, _wdo_cfg()),
    CandidateSpec("WDO-03", "WDO", "wdo_core", 3, "M5", "WDO_Arb WIN+WDO MainWall", False, _wdo_cfg()),
    CandidateSpec("WDO-04", "WDO", "wdo_core", 4, "M5", "WDO_MainWall GammaFlip Lim50%", False, _wdo_cfg()),
    CandidateSpec("WDO-06", "WDO", "wdo_core", 6, "M5", "WDO_BrenoWick MainWall Lim50%", False, _wdo_cfg()),
    CandidateSpec("WDO-08", "WDO", "wdo_core", 8, "M5", "WDO_Absorcao MainWall+Gamma", False, _wdo_cfg()),
    CandidateSpec("WDO-09", "WDO", "wdo_core", 9, "M5", "WDO_Cluster NWE30+50 LimWall", False, _wdo_cfg()),
    CandidateSpec("WDO-10", "WDO", "wdo_core", 10, "M5", "WDO_S2 Reversao NWE 12-14h30", False, _wdo_cfg()),
    CandidateSpec("WDO-11", "WDO", "wdo_core", 11, "M5", "WDO_SmartGrid GF+NextWall 1+2L", False, _wdo_cfg()),
    CandidateSpec("WDO-12", "WDO", "wdo_core", 12, "M5", "WDO_Piramidacao 1+1L NY", False, _wdo_cfg()),
    CandidateSpec("WDO-13", "WDO", "wdo_core", 13, "M5", "WDO_SmartGrid 1+2L GF", False, _wdo_cfg()),
    CandidateSpec("WDO-14", "WDO", "wdo_core", 14, "M5", "WDO_Grid Institucional 1+2+3L", False, _wdo_cfg()),
    CandidateSpec("WDO-15", "WDO", "wdo_core", 15, "M5", "WDO_MainWall Z30_Rev+Shield", False, _wdo_cfg()),
    CandidateSpec("WDO-16", "WDO", "wdo_core", 16, "M5", "WDO_Posicional EOD MainWall", False, _wdo_cfg()),
]

SPEC_BY_CODE: dict[str, CandidateSpec] = {s.code: s for s in UNUSED_24_SPECS}

WDO_BE_MAP = {
    "CURRENT": -1,
    "BE_ZERO": 0,
    "BE_WALL_SHIELD": 1,
    "BE_WALL_2STAGE": 2,
}

WDO_TP_MAP = {
    "CURRENT": 0,
    "TP_MIDWALL": 1,
    "TP_MAIN_WALL": 2,
}

M15_WINDOWS = {
    "CURRENT": (555, 1005),
    "NO_LUNCH": (555, 1005),  # tratado via filtro de janela abaixo se necessário
    "NY_1000_1630": (600, 990),
    "MORNING_09_12": (555, 720),
}


def load_shared_market_data(load_win: bool = True, load_wdo: bool = True) -> dict[str, Any]:
    """Carrega dados de mercado M5/M15 + indicadores NWE/RSI uma única vez por processo."""
    market: dict[str, Any] = {}
    if load_win:
        df_win, gex_win = load_win_and_wdo_aligned()
        c = df_win["close"].values
        n50 = disc.compute_nwe_series(c, lookback=50, bw=5.0, mult=2.0)
        n30 = disc.compute_nwe_series(c, lookback=30, bw=3.0, mult=1.6)
        dp = pd.Series(c).diff()
        rsi7 = (
            100.0 - (100.0 / (1.0 + (
                dp.clip(lower=0).rolling(7).mean()
                / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6)
            )))
        ).fillna(50.0).values
        market["win_m5_args"] = (
            df_win, gex_win,
            n50[0], n50[1], n50[2], n50[4],
            n30[0], n30[1], n30[2], n30[4],
            rsi7,
        )
        market["gex_win"] = gex_win

        df_m15 = load_tf_bars("WIN", "M15", start_date="2025-12-15", end_date=FULL_END)
        c15 = df_m15["close"].values
        c15_c, u15, l15, _, s15 = disc.compute_nwe_series(c15, lookback=30, bw=4.0, mult=1.8)
        market["win_m15_df"] = df_m15
        market["win_m15_nwe"] = {"center": c15_c, "upper": u15, "lower": l15, "slope": s15}

    if load_wdo:
        df_wdo, gex_wdo = wsim.load_wdo_mt5_raw()
        cd = df_wdo["close"].values
        w50 = disc.compute_nwe_series(cd, lookback=50, bw=5.0, mult=2.0)
        w30 = disc.compute_nwe_series(cd, lookback=30, bw=3.0, mult=1.6)
        wrsi = wsim.compute_rsi7_series(cd)
        market["wdo_m5_args"] = (
            df_wdo, gex_wdo,
            w50[0], w50[1], w50[2], w50[4],
            w30[0], w30[1], w30[2], w30[4],
            wrsi,
        )
        market["gex_wdo"] = gex_wdo

    return market


def _to_min_sec(ts: Any) -> tuple[int, int]:
    if ts is None or pd.isna(ts):
        return 540, 540 * 60
    t = pd.Timestamp(ts)
    m = t.hour * 60 + t.minute
    return int(m), int(m * 60 + t.second)


def simulate_candidate(
    spec: CandidateSpec,
    cfg: dict[str, Any],
    market: dict[str, Any],
    cost_mult: float = 1.0,
) -> list[dict[str, Any]]:
    """Executa uma configuração para o robô `spec` e devolve trades padronizados no formato do stop_diario."""
    rows: list[dict[str, Any]] = []

    if spec.engine == "win_o16":
        cost_pts = WIN_COST_PTS * cost_mult
        tr_list, _ = o16.simulate_single_est_slot(
            spec.slot_id,
            *market["win_m5_args"],
            entry_override=cfg["order_type"],
            be_mode=cfg["be_mode"],
            wall_shield_buf=float(cfg["wall_buf"]),
            tp_mode=cfg["tp_mode"],
            cost_pts=cost_pts,
            start_date=FULL_START,
            end_date=FULL_END,
            max_trades_day=int(cfg["max_trades_day"]),
            max_losses_day=int(cfg["max_losses_day"]),
            window_override=cfg["window"],
        )
        for t in tr_list:
            d = str(t["date"])
            if not (FULL_START <= d <= FULL_END):
                continue
            min_in, sec_in = _to_min_sec(t.get("entry_time"))
            min_out, sec_out = _to_min_sec(t.get("exit_time"))
            lots = float(t.get("contracts", 1))
            pnl = float(t["pnl_brl"])
            cost_brl = 2.0 * cost_mult * lots
            rows.append({
                "date": d,
                "strat": spec.code,
                "asset": "WIN",
                "side": int(t["side"]),
                "lots": lots,
                "px_in": float(t["avg_px"]),
                "px_out": float(t["exit_px"]),
                "min_in": min_in,
                "min_out": max(min_in, min_out),
                "sec_in": sec_in,
                "sec_out": max(sec_in, sec_out),
                "pnl": round(pnl, 2),
                "pnl_gross": round(pnl + cost_brl, 2),
                "cost_extra": round(cost_brl, 2),
                "pt_val": 0.20,
            })

    elif spec.engine == "win_m15":
        cost_pts = WIN_COST_PTS * cost_mult
        setup_name = "M15_FAKEOUT_TRAP" if spec.slot_id == 3 else "M15_MIDWALL_PULLBACK"
        min_tp = 220.0 if spec.slot_id == 3 else 250.0
        use_slope = spec.slot_id == 5
        slope_th = 4.0 if spec.slot_id == 5 else 0.0
        min_bw = 300.0 if spec.slot_id == 5 else 0.0
        tw = M15_WINDOWS.get(cfg["window"], (555, 1005))

        tr_list = run_experiment(
            market["win_m15_df"],
            market["gex_win"],
            "WIN",
            "M15",
            setup_name,
            cfg["order_type"],
            market["win_m15_nwe"],
            wall_buf=float(cfg["wall_buf"]),
            min_tp_dist=min_tp,
            front_run=20.0,
            be_ratio=0.50,
            be_lock_pts=25.0,
            time_window=tw,
            use_nwe_slope=use_slope,
            nwe_slope_thresh=slope_th,
            min_nwe_bw=min_bw,
            be_mode=cfg["be_mode"],
            tp_mode=cfg["tp_mode"],
            max_trades_day=int(cfg["max_trades_day"]),
            max_losses_day=int(cfg["max_losses_day"]),
            cost_pts_override=cost_pts,
            strict_causal=True,
        )
        for t in tr_list:
            d = str(t["date"])
            if not (FULL_START <= d <= FULL_END):
                continue
            if cfg["window"] == "NO_LUNCH" and (720 < int(t["time"]) < 810):
                continue
            min_in, sec_in = _to_min_sec(t.get("entry_time"))
            min_out, sec_out = _to_min_sec(t.get("exit_time"))
            pnl = float(t["brl"])
            cost_brl = 2.0 * cost_mult
            rows.append({
                "date": d,
                "strat": spec.code,
                "asset": "WIN",
                "side": int(t["side"]),
                "lots": 1.0,
                "px_in": float(t["ep"]),
                "px_out": float(t["xp"]),
                "min_in": min_in,
                "min_out": max(min_in, min_out),
                "sec_in": sec_in,
                "sec_out": max(sec_in, sec_out),
                "pnl": round(pnl, 2),
                "pnl_gross": round(pnl + cost_brl, 2),
                "cost_extra": round(cost_brl, 2),
                "pt_val": 0.20,
            })

    elif spec.engine == "win_sg":
        cost_pts = WIN_COST_PTS * cost_mult
        be_ov = 0 if cfg["be_mode"] == "BE_ZERO" else (1 if cfg["be_mode"] == "BE_WALL_SHIELD" else -1)
        df_sg = sg_sim.run(
            slots=(spec.slot_id,),
            start=FULL_START,
            end=FULL_END,
            cost_pts=cost_pts,
            entry_override=cfg["order_type"],
            be_mode_override=be_ov,
            wall_buf_override=float(cfg["wall_buf"]),
            max_trades_day=int(cfg["max_trades_day"]),
            max_losses_day=int(cfg["max_losses_day"]),
            window_override=cfg["window"],
        )
        for _, t in df_sg.iterrows():
            d = pd.Timestamp(t["t_in"]).strftime("%Y-%m-%d")
            if not (FULL_START <= d <= FULL_END):
                continue
            min_in, sec_in = _to_min_sec(t["t_in"])
            min_out, sec_out = _to_min_sec(t["t_out"])
            lots = float(t["lots"])
            pnl = float(t["brl"])
            cost_brl = 2.0 * cost_mult * lots
            rows.append({
                "date": d,
                "strat": spec.code,
                "asset": "WIN",
                "side": int(t["side"]),
                "lots": lots,
                "px_in": float(t["avg_px"]),
                "px_out": float(t["px_out"]),
                "min_in": min_in,
                "min_out": max(min_in, min_out),
                "sec_in": sec_in,
                "sec_out": max(sec_in, sec_out),
                "pnl": round(pnl, 2),
                "pnl_gross": round(pnl + cost_brl, 2),
                "cost_extra": round(cost_brl, 2),
                "pt_val": 0.20,
            })

    elif spec.engine == "wdo_core":
        cost_pts = WDO_COST_PTS * cost_mult
        tr_list = wsim.simulate_wdo_core_slot(
            spec.slot_id,
            *market["wdo_m5_args"],
            start_date=FULL_START,
            end_date=FULL_END,
            cost_pts=cost_pts,
            entry_override=cfg["order_type"],
            be_mode_override=WDO_BE_MAP.get(cfg["be_mode"], -1),
            wall_buf_override=float(cfg["wall_buf"]),
            tp_mode_override=WDO_TP_MAP.get(cfg["tp_mode"], 0),
            max_trades_day=int(cfg["max_trades_day"]),
            max_losses_day=int(cfg["max_losses_day"]),
            window_override=cfg["window"],
        )
        for t in tr_list:
            d = str(t["date"])
            if not (FULL_START <= d <= FULL_END):
                continue
            min_in, sec_in = _to_min_sec(t.get("entry_time"))
            min_out, sec_out = _to_min_sec(t.get("exit_time"))
            lots = float(t.get("contracts", 1))
            pnl = float(t["pnl_brl"])
            cost_brl = 5.0 * cost_mult * lots
            rows.append({
                "date": d,
                "strat": spec.code,
                "asset": "WDO",
                "side": int(t["side"]),
                "lots": lots,
                "px_in": float(t["avg_px"]),
                "px_out": float(t["exit_px"]),
                "min_in": min_in,
                "min_out": max(min_in, min_out),
                "sec_in": sec_in,
                "sec_out": max(sec_in, sec_out),
                "pnl": round(pnl, 2),
                "pnl_gross": round(pnl + cost_brl, 2),
                "cost_extra": round(cost_brl, 2),
                "pt_val": 10.0,
            })

    rows.sort(key=lambda r: (r["date"], r["sec_in"], r["sec_out"]))
    return rows


def format_cfg_label(spec: CandidateSpec, cfg: dict[str, Any]) -> str:
    """Resumo legível apenas das alavancas alteradas em relação ao baseline do EA."""
    base = spec.baseline_cfg
    diffs = []
    if cfg["order_type"] != base["order_type"]:
        diffs.append(f"Ordem={cfg['order_type']}")
    if cfg["be_mode"] != base["be_mode"] or abs(float(cfg["wall_buf"]) - float(base["wall_buf"])) > 1e-6:
        if cfg["be_mode"] in ("BE_WALL_SHIELD", "BE_WALL_2STAGE") and float(cfg["wall_buf"]) >= 0:
            diffs.append(f"WallBE={cfg['be_mode']}({cfg['wall_buf']:g})")
        else:
            diffs.append(f"WallBE={cfg['be_mode']}")
    if cfg["tp_mode"] != base["tp_mode"]:
        diffs.append(f"TP={cfg['tp_mode']}")
    if int(cfg["max_trades_day"]) != int(base["max_trades_day"]):
        diffs.append(f"MaxTr={cfg['max_trades_day']}/d")
    if int(cfg["max_losses_day"]) != int(base["max_losses_day"]):
        diffs.append(f"MaxLoss={cfg['max_losses_day']}/d")
    if cfg["window"] != base["window"]:
        diffs.append(f"Janela={cfg['window']}")
    return "ORIGINAL (sem ajuste)" if not diffs else " + ".join(diffs)


def count_changed_knobs(spec: CandidateSpec, cfg: dict[str, Any]) -> int:
    base = spec.baseline_cfg
    c = 0
    if cfg["order_type"] != base["order_type"]:
        c += 1
    if cfg["be_mode"] != base["be_mode"] or abs(float(cfg["wall_buf"]) - float(base["wall_buf"])) > 1e-6:
        c += 1
    if cfg["tp_mode"] != base["tp_mode"]:
        c += 1
    if int(cfg["max_trades_day"]) != int(base["max_trades_day"]):
        c += 1
    if int(cfg["max_losses_day"]) != int(base["max_losses_day"]):
        c += 1
    if cfg["window"] != base["window"]:
        c += 1
    return c
