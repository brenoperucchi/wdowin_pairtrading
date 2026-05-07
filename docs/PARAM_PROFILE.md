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

### Entry / signal

| Constant       | Value | Notes |
|----------------|-------|-------|
| `Z_ENTRY`      | 1.4   | Z-score entry threshold (WDO) |
| `Z_ANOMALY`    | 4.0   | Block trade above this (anomaly) |
| `Z_ATTENTION`  | 1.2   | Display-only attention zone |
| `DI_Z_ENTRY`   | 1.4   | Z-score entry threshold (DI) |
| `DI_Z_ANOMALY` | 4.0   | Block (DI) |
| `DI_Z_ATTENTION` | 1.2 | Display-only (DI) |

### SL / TP / BE (WIN points)

| Constant      | BUY | SELL |
|---------------|-----|------|
| `*_SL`        | 300 | 300  |
| `*_TP`        | 800 | 800  |
| `*_BE_ACT`    | 300 | 300  |
| `*_BE_LOCK`   | 0   | 0    |

### Sizing

| Constant         | Value | Notes |
|------------------|-------|-------|
| `WIN_CONTRACTS`  | 2     | WIN-only — no WDO leg |
| `WIN_PV`         | 0.20  | R$/point/contract |

### Regime / hedge ratio

| Constant            | Value  | Notes |
|---------------------|--------|-------|
| `BETA_INITIAL`      | -22.5  | OLS reference beta WIN×WDO |
| `RHO_MIN`           | -0.40  | rho breakdown threshold |
| `BETA_DELTA_MAX`    | 25.0   | %, beta drift block |
| `KALMAN_BURN_IN`    | 15000  | bars |

### Session (BRT)

| Constant          | Value         |
|-------------------|---------------|
| Entry start       | 09:00 BRT     |
| Entry end         | 15:00 BRT     |
| Force close       | 17:40 BRT     |

### Operational risk (TASK-3 AC #11)

| Constant                   | Value | Notes |
|----------------------------|-------|-------|
| `MAX_TRADES_PER_DAY`       | 4     | floor — production should tighten |
| `DAILY_LOSS_LIMIT_BRL`     | 240.0 | ~2× a single losing trade |
| `LOSS_COOLDOWN_MIN`        | 30    | global, all slots |
| `BLOCK_ON_MT5_DISCONNECT`  | True  | only safe default for live |

### NWE filter

| Constant         | Value | Notes |
|------------------|-------|-------|
| `NWE_BANDWIDTH`  | 8     | kernel bandwidth |
| `NWE_LOOKBACK`   | 95    | bars |
| `NWE_BAND_MULT`  | 0.10  | adaptive band fraction |
| `NWE_MULT_MAE`   | 3.0   | MAE multiplier |

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

| Script                       | Param swept              | Range                |
|------------------------------|--------------------------|----------------------|
| `research/backtest.py`       | `Z_ENTRY`                | `[2.0, 4.0]`         |
| `research/backtest_pa.py`    | `Z_ENTRY`                | `[2.0, 4.0]`         |
| `research/backtest_win.py`   | `Z_ENTRY`                | `[2.0, 4.0]`         |
| `research/optimize_breakeven.py` | `BUY_BE_ACT`         | `[200..500]`         |

### ⚠️ Divergent hardcoded values

These scripts pin a single value that differs from the live profile.
Backtest P&L from these is structurally not comparable to live P&L.

| Script                              | Constant   | Script value          | Live value  | Delta |
|-------------------------------------|------------|-----------------------|-------------|-------|
| `research/compare_hedge_methods.py` | `Z_ENTRY`  | 1.8                   | 1.4         | +0.4  |
| `research/optimize_consensus.py`    | `Z_ENTRY`  | 1.8                   | 1.4         | +0.4  |
| `research/optimize_core_models.py`  | `Z_ENTRY`  | 1.6                   | 1.4         | +0.2  |
| `research/hmm_zscore_optimizer.py`  | `BUY_SL/TP`  | 350 / 500           | 300 / 800   | tighter SL, smaller TP |
| `research/hmm_zscore_optimizer.py`  | `SELL_SL/TP` | 300 / 1400          | 300 / 800   | larger SELL TP        |
| `research/hmm_zscore_optimizer.py`  | `BUY_BE_ACT/LOCK` | 400 / 50      | 300 / 0     | later BE, locks +50 pts |
| `research/plot_final_vs_hmm.py`     | (same as hmm_zscore_optimizer) | (same)  | (same)      | (same) |
| `research/plot_hmm_comparison.py`   | (same as hmm_zscore_optimizer) | (same)  | (same)      | (same) |
| `research/plot_isolated_new.py`     | `Z_ENTRY`  | 1.4                   | 1.4         | matches |

### Categorized but no hardcoded entry/exit override

Optimizers and plotters that define their own ranges/grids but don't
pin a single live-equivalent constant: `optimize_nwe*.py`,
`optimize_zscore*.py`, `optimize_sltp.py`, `optimize_di_*.py`,
`plot_*.py` (excluding the three flagged above), `equity_*.py`,
`compare_models.py`, `tune_*.py`. Treat as research-only.

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

## 4. How to keep this manifest honest

`tests/test_param_profile.py` asserts:
- `core/config.py` exposes every canonical name listed above with the
  expected type and a sane range. If a constant is renamed or its
  type changes, the test fails — forcing a manifest update.
- This file (`docs/PARAM_PROFILE.md`) exists. Keeps the doc in the
  loop.

When you change a constant in `core/config.py`, update Section 1 here.
When you change a research script's hardcoded value, update Section 2.
