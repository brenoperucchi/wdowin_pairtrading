# Parameter Profile — live vs. research

Single source of truth for trading parameters: **`core/config.py`**. The
live engine and `server.py` consume it directly. Research scripts under
`research/` were written across multiple phases and **most hardcode their
own values**, so backtest P&L will not match live P&L unless the script
was explicitly aligned to the live profile.

This file is the manifest required by TASK-3 AC #5. It compares the
canonical live constants against every research script that defines its
own copy. Update it when `core/config.py` changes or when a research
script's hardcoded values shift.

## 1. Canonical live profile

Pulled from `core/config.py` (TIMEFRAME = M5, account = XP DEMO 52033102).
Each row maps a single attribute on `core/config.py` to its current value.
`tests/test_param_profile.py` parses these tables and asserts each value
equals `getattr(cfg, NAME)` — if `core/config.py` changes, the test fails
and forces an update here.

### Bar / data window

These define the *shape* of the data the engine sees. A change here
silently invalidates any backtest that loads its own number of bars or
a different timeframe.

| Constant     | Value | Notes |
|--------------|-------|-------|
| `TIMEFRAME`  | 5     | `mt5.TIMEFRAME_M5` enum (5 == M5; M15 == 15, etc.) |
| `WINDOW`     | 90    | OLS rolling window (bars) |
| `BARS`       | 250   | bars fetched per MT5 poll (WIN×WDO) |
| `DI_BARS`    | 250   | bars fetched per MT5 poll (DI) |

### Kalman tuning

WDO and DI run independent Kalman filters with their own Q/R/W. A
backtest that recomputes Z with a different W or Q/R is not comparing
the same signal as live.

| Constant       | Value  | Notes |
|----------------|--------|-------|
| `WDO_KALMAN_Q` | 0.0001 | trans_cov (1e-4) |
| `WDO_KALMAN_R` | 100.0  | obs_cov (1e2) |
| `WDO_KALMAN_W` | 40     | Z-score rolling window |
| `DI_KALMAN_Q`  | 0.001  | trans_cov (1e-3) — fast adaptation |
| `DI_KALMAN_R`  | 10.0   | obs_cov (1e1) — low smoothing |
| `DI_KALMAN_W`  | 60     | Z-score rolling window |

### Johansen test

| Constant           | Value | Notes |
|--------------------|-------|-------|
| `JOH_WINDOW`       | 150   | rolling window (bars) for Johansen test |
| `JOH_RECHECK_BARS` | 12    | recompute every N bars (~1h on M5) |

### Entry / signal

| Constant         | Value | Notes |
|------------------|-------|-------|
| `Z_ENTRY`        | 1.4   | Z-score entry threshold (WDO) |
| `Z_ANOMALY`      | 4.0   | Block trade above this (anomaly) |
| `Z_ATTENTION`    | 1.2   | Display-only attention zone |
| `DI_Z_ENTRY`     | 1.4   | Z-score entry threshold (DI) |
| `DI_Z_ANOMALY`   | 4.0   | Block (DI) |
| `DI_Z_ATTENTION` | 1.2   | Display-only (DI) |

### SL / TP / BE (WIN points)

| Constant       | Value | Notes |
|----------------|-------|-------|
| `BUY_SL`       | 300   | BUY stop-loss (pts) |
| `BUY_TP`       | 800   | BUY take-profit (pts) |
| `BUY_BE_ACT`   | 300   | BUY break-even activation (pts) |
| `BUY_BE_LOCK`  | 0     | BUY break-even lock-in offset (pts) |
| `SELL_SL`      | 300   | SELL stop-loss (pts) |
| `SELL_TP`      | 800   | SELL take-profit (pts) |
| `SELL_BE_ACT`  | 300   | SELL break-even activation (pts) |
| `SELL_BE_LOCK` | 0     | SELL break-even lock-in offset (pts) |

### Sizing

| Constant        | Value | Notes |
|-----------------|-------|-------|
| `WIN_CONTRACTS` | 2     | WIN-only — no WDO leg |
| `WIN_PV`        | 0.20  | R$/point/contract |

### Regime / hedge ratio

| Constant         | Value  | Notes |
|------------------|--------|-------|
| `BETA_INITIAL`   | -22.5  | OLS reference beta WIN×WDO |
| `RHO_MIN`        | -0.40  | rho breakdown threshold |
| `BETA_DELTA_MAX` | 25.0   | %, beta drift block |
| `KALMAN_BURN_IN` | 15000  | bars |

### Session (BRT)

| Constant        | Value | Notes |
|-----------------|-------|-------|
| `ENTRY_START_H` | 9     | entry window start hour |
| `ENTRY_START_M` | 0     | entry window start minute |
| `ENTRY_END_H`   | 15    | entry window end hour |
| `ENTRY_END_M`   | 0     | entry window end minute |
| `FORCE_CLOSE_H` | 17    | force-close hour |
| `FORCE_CLOSE_M` | 40    | force-close minute |

### Operational risk (TASK-3 AC #11)

| Constant                  | Value | Notes |
|---------------------------|-------|-------|
| `MAX_TRADES_PER_DAY`      | 4     | floor — production should tighten |
| `DAILY_LOSS_LIMIT_BRL`    | 240.0 | ~2× a single losing trade |
| `LOSS_COOLDOWN_MIN`       | 30    | global, all slots |
| `BLOCK_ON_MT5_DISCONNECT` | True  | only safe default for live |

### NWE filter

| Constant        | Value | Notes |
|-----------------|-------|-------|
| `NWE_BANDWIDTH` | 8     | kernel bandwidth |
| `NWE_LOOKBACK`  | 95    | bars |
| `NWE_BAND_MULT` | 0.10  | adaptive band fraction |
| `NWE_MULT_MAE`  | 3.0   | MAE multiplier |

### Symbols & infra

| Constant    | Value    | Notes |
|-------------|----------|-------|
| `SYMBOL_A`  | `WIN$N`  | mini índice (only leg actually traded) |
| `SYMBOL_B`  | `WDO$N`  | mini dólar — used only as filter, not traded |
| `DI_SYMBOL` | `DI1$N`  | DI1 front-month, filter-only |

## 2. Research script status

Three categories. Status badge appears next to each script.

### ✅ Imports `core.config` (live-aligned where applicable)

These scripts pull from the canonical module. They may still redefine
*some* constants — flagged below.

| Script                                | Imports                                    | Local overrides                              |
|---------------------------------------|--------------------------------------------|----------------------------------------------|
| `research/backtest_johansen_gate.py`  | `MT5_PATH, SYMBOL_A, SYMBOL_B, BETA_INITIAL` | **`Z_ENTRY=1.8`** (vs live 1.4)            |
| `research/run_matador_v5_johansen.py` | `SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH, ...` | redefines `WIN_PV=0.20` (matches) |

### 🔍 Sweep ranges (intentional grid search)

These scripts iterate over parameter ranges. The "divergence" is the
purpose of the script — they are calibration tools, not validation runs.

| Script                           | Param swept       | Range / values        |
|----------------------------------|-------------------|-----------------------|
| `research/backtest.py`           | `Z_ENTRY`         | `[2.0, 4.0]`          |
| `research/backtest_pa.py`        | `Z_ENTRY`         | `[2.0, 4.0]`          |
| `research/backtest_win.py`       | `Z_ENTRY`         | `[2.0, 4.0]`          |
| `research/optimize_breakeven.py` | `BUY_BE_ACT`      | `[200..500]` (over a divergent SL/TP base — see below) |
| `research/optimize_time.py`      | `ENTRY_START/END` | sweeps session window |

### ⚠️ Divergent hardcoded values

These scripts pin a single value (or set) that differs from the live
profile. Backtest P&L from these is structurally not comparable to live
P&L until they are aligned.

| Script                              | Constant     | Script value      | Live value | Delta |
|-------------------------------------|--------------|-------------------|------------|-------|
| `research/compare_hedge_methods.py` | `Z_ENTRY`    | 1.8               | 1.4        | +0.4 |
| `research/optimize_consensus.py`    | `Z_ENTRY`    | 1.8               | 1.4        | +0.4 |
| `research/optimize_core_models.py`  | `Z_ENTRY`    | 1.6               | 1.4        | +0.2 |
| `research/hmm_zscore_optimizer.py`  | `BUY_SL/TP`  | 350 / 500         | 300 / 800  | tighter SL, smaller TP |
| `research/hmm_zscore_optimizer.py`  | `SELL_SL/TP` | 300 / 1400        | 300 / 800  | larger SELL TP |
| `research/hmm_zscore_optimizer.py`  | `BUY_BE_ACT/LOCK`  | 400 / 50    | 300 / 0    | later BE, locks +50 pts |
| `research/hmm_zscore_optimizer.py`  | `SELL_BE_ACT/LOCK` | 800 / 200   | 300 / 0    | much later BE, locks +200 pts |
| `research/plot_final_vs_hmm.py`     | (same as hmm_zscore_optimizer) | (same) | (same) | (same) |
| `research/plot_hmm_comparison.py`   | (same as hmm_zscore_optimizer) | (same) | (same) | (same) |
| `research/plot_isolated_new.py`     | `Z_ENTRY`    | 1.4               | 1.4        | matches |
| `research/optimize_daily_limits.py` | `BUY_SL/TP`  | 350 / 500         | 300 / 800  | tighter SL, smaller TP |
| `research/optimize_daily_limits.py` | `SELL_SL/TP` | 300 / 1400        | 300 / 800  | larger SELL TP |
| `research/optimize_daily_limits.py` | session      | 09:15–16:00       | 09:00–15:00 | shifted/extended window |
| `research/optimize_time.py`         | `BUY_SL/TP`  | 350 / 500         | 300 / 800  | tighter SL, smaller TP |
| `research/optimize_time.py`         | `SELL_SL/TP` | 300 / 1400        | 300 / 800  | larger SELL TP |
| `research/optimize_breakeven.py`    | `BUY_SL/TP`  | 350 / 500         | 300 / 800  | tighter SL, smaller TP |
| `research/optimize_breakeven.py`    | `SELL_SL/TP` | 300 / 1400        | 300 / 800  | larger SELL TP |
| `research/plot_final_equity.py`     | `BUY_SL/TP`  | 350 / 500         | 300 / 800  | tighter SL, smaller TP |
| `research/plot_final_equity.py`     | `SELL_SL/TP` | 300 / 1400        | 300 / 800  | larger SELL TP |
| `research/plot_final_equity.py`     | `BUY_BE_ACT/LOCK`  | 400 / 50    | 300 / 0    | later BE, locks +50 |
| `research/plot_final_equity.py`     | `SELL_BE_ACT/LOCK` | 800 / 200   | 300 / 0    | much later BE, locks +200 |
| `research/plot_final_equity.py`     | session      | 10:00–16:00       | 09:00–15:00 | shifted/extended window |
| `research/equity_curve.py`          | `BUY_ZMIN/MAX`     | 2.0 / 3.0   | live uses single `Z_ENTRY=1.4` (no upper) | bounded entry zone |
| `research/equity_curve.py`          | `SELL_ZMIN/MAX`    | 2.1 / 3.0   | live uses single `Z_ENTRY=1.4`            | bounded entry zone |
| `research/equity_curve.py`          | session      | 09:15–16:00       | 09:00–15:00 | shifted window |
| `research/equity_split.py`          | `BUY_ZMIN/MAX`     | 2.0 / 3.0   | live uses single `Z_ENTRY=1.4`            | bounded entry zone |
| `research/equity_split.py`          | `SELL_ZMIN/MAX`    | 2.1 / 3.0   | live uses single `Z_ENTRY=1.4`            | bounded entry zone |
| `research/equity_split.py`          | session      | 09:15–16:00       | 09:00–15:00 | shifted window |
| `research/optimize_wdo_sltp.py`     | `BUY_ZMIN`   | 3.00              | 1.4 (`Z_ENTRY`) | +1.6, much harder entry |
| `research/optimize_wdo_sltp.py`     | `SELL_ZMIN`  | 2.75              | 1.4 (`Z_ENTRY`) | +1.35 |
| `research/optimize_wdo_sltp.py`     | session      | 10:00–16:00       | 09:00–15:00 | shifted/extended window |
| `research/optimize_wdo.py`          | leg traded   | WDO only (1 ct, PV=10) | WIN only (2 ct, PV=0.20) | **structural mismatch** — different instrument |
| `research/optimize_wdo.py`          | `SL_PTS/TP_PTS`    | 15 / 15 (WDO pts)  | 300 / 800 (WIN pts) | scales differ — WDO tick=0.5pt vs WIN tick=5pt; not directly comparable |
| `research/optimize_wdo.py`          | Z range            | sweeps `Z_MIN ∈ [1.5, 3.5]`, `Z_MAX ∈ [3.0, 6.5]` | single `Z_ENTRY=1.4` | bounded entry zones, much harder than live |
| `research/optimize_wdo.py`          | session      | 10:00–16:00       | 09:00–15:00 | shifted/extended window |

### Categorized but no hardcoded entry/exit override

Optimizers and plotters that define their own ranges/grids but don't
pin a single live-equivalent constant: `optimize_nwe*.py`,
`optimize_zscore*.py`, `optimize_sltp.py`, `optimize_di_*.py`,
`plot_*.py` (excluding the three flagged above), `compare_models.py`,
`tune_*.py`. Treat as research-only.

Note: `equity_*.py` were previously listed here. Codex round-7 audit
moved them into the divergent table above — `equity_curve.py` and
`equity_split.py` pin `BUY_ZMIN/SELL_ZMIN` plus a shifted session, and
`optimize_wdo_sltp.py` pins entry thresholds far above live.

## 3. Implications for backtest reconciliation (AC #14/#15/#16)

- A script that diverges in Z_ENTRY/SL/TP and **does not import
  core.config** cannot be used as a paridade benchmark for live P&L.
  AC #14 forces an explicit choice per script: rewrite to the live
  profile, or stamp a "research exploratory" header.
- The closest existing match to the live engine is
  `research/run_matador_v5_johansen.py` (already imports the canonical
  module set). Reconciliation work should start there.
- `backtest_johansen_gate.py` partially imports core.config but
  overrides `Z_ENTRY=1.8`; if elevated to production validation it
  must drop the override and import `Z_ENTRY` from `core.config`.
- The "HMM family" (`hmm_zscore_optimizer.py`, `plot_final_vs_hmm.py`,
  `plot_hmm_comparison.py`, `plot_final_equity.py`) shares one
  divergent SL/TP/BE profile (350/500 BUY, 300/1400 SELL, BE shifted)
  — aligning them is one decision, not four.
- `optimize_daily_limits.py` / `optimize_time.py` / `optimize_breakeven.py`
  share the 350/500 + 300/1400 SL/TP base. If the gestor cites these
  for live calibration, the SL/TP base must be reconciled with live
  values first.

## 4. How to keep this manifest honest

`tests/test_param_profile.py` asserts:
- `core/config.py` exposes every canonical name listed above with the
  expected type and a sane range.
- **Each value in Section 1 above equals `getattr(cfg, NAME)`** — the
  test parses this file and compares row-by-row. If a constant is
  renamed, removed, or its value changes in `core/config.py`, the test
  fails and forces an update here.
- This file (`docs/PARAM_PROFILE.md`) exists with the three required
  sections (canonical / research / config).

When you change a constant in `core/config.py`, update Section 1 here.
When you change a research script's hardcoded value, update Section 2.
