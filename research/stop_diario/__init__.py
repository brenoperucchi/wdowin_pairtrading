"""Sistema de simulação e otimização de Stop Diário Máximo — 11 Robôs Jumba."""

from research.stop_diario.data_loader import (
    DEFAULT_HTM_DIR,
    PORTFOLIO_PRESETS,
    ROBOT_METADATA,
    enrich_trades_with_m1_mae_mfe,
    load_m1_bars,
    load_portfolio_trades,
    parse_mt5_htm_trades,
)
from research.stop_diario.engine import (
    IS_START,
    OOS_END,
    analyze_robots,
    build_intraday_days,
    compute_recovery_bands,
    run_combined_grid,
    run_full_analysis,
    run_monte_carlo,
    run_param_sweep,
    run_walk_forward,
    simulate_combined_stops,
    simulate_single_scope,
)

__all__ = [
    "DEFAULT_HTM_DIR",
    "IS_START",
    "OOS_END",
    "PORTFOLIO_PRESETS",
    "ROBOT_METADATA",
    "analyze_robots",
    "build_intraday_days",
    "compute_recovery_bands",
    "enrich_trades_with_m1_mae_mfe",
    "load_m1_bars",
    "load_portfolio_trades",
    "parse_mt5_htm_trades",
    "run_combined_grid",
    "run_full_analysis",
    "run_monte_carlo",
    "run_param_sweep",
    "run_walk_forward",
    "simulate_combined_stops",
    "simulate_single_scope",
]
