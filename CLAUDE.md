# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**WIN×WDO Advanced Regime Monitor** — statistical arbitrage system for Brazilian futures (Mini Índice WIN$N × Mini Dólar WDO$N) on B3. Operates intraday on M5 bars, detecting cointegration breakdowns via Z-score and generating mean-reversion signals. Currently paper trading only — no real MT5 orders.

## Trading Scope (read this before touching the trade engine)

This is **directional WIN trading with a WDO/DI consensus filter** — not a market-neutral pair trade.

- The trade engine (`core/trade_engine.py:_open_trade`) opens **only WIN contracts** (`WIN_CONTRACTS=2`). No simultaneous WDO leg, no hedge, no spread P&L. Action is always `BUY_WIN` or `SELL_WIN`.
- WDO and DI are used **as filters / signal vectors**: cointegration health (`WIN×WDO`), Z-score on the spread, and `DI_NWE`/`WDO_NWE` envelope confirmations gate the WIN entry. They do not produce orders.
- The WIN×WDO Engle-Granger / OLS / Kalman machinery exists to *qualify* the WIN entry (regime sanity check), not to generate a paired position.
- "DOL" in conversation == `WDO$N` mini dólar. There is no full-size dollar contract (`DOL$F`) anywhere in this codebase.
- Backtest scripts under `research/` test other configurations (single-leg WDO, 4-leg specs) and **do not match the production engine** — see `research/README.md` for which scripts are validation vs. exploratory.

If a future change introduces a real WDO leg or hedge, update this section first.


## Commands

### Backend
```bash
# Run dev server
python server.py
# OR with auto-reload
uvicorn server:app --host 0.0.0.0 --port 8080 --reload

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_signals.py -v
```

### Frontend
```bash
cd regime-dashboard
npm install
npm run dev        # Dev server on port 5174
npm run build      # Production build
npm run lint       # ESLint
```

### Production (systemd --user)
```bash
systemctl --user start pairtrading-server pairtrading-frontend
systemctl --user status pairtrading-server
journalctl --user -u pairtrading-server -f
```

## Architecture

```
MT5 Terminal (Windows)
    │ shared memory / copy_rates_from_pos()
    ▼
core/mt5_client.py  ←── fetches M5 bars (beta_ultimo.json is a legacy V1 artifact, not updated)
    │
    ▼
server.py (FastAPI, port 8080)
    │ internal trade_eval_loop polls every 2.5s, CACHE_TTL=2.0s
    │
    ├─ /api/v2/regime  ──► core/kalman_filter.py → core/signals.py → core/trade_engine.py
    ├─ /api/di-regime  ──► OLS beta on DI1$N pair
    ├─ /api/performance ─► SQLite matador_ops query
    ├─ /api/history    ──► last 5min of bar_history
    └─ optional Firebase RTDB mirror (15s cadence for live state, 5min for history)
                │
                ▼
    regime-dashboard/ (React 19 + Vite, port 5174)
        └─ App.jsx polls API every 2500ms (falls back to Gaussian simulator)
```

### Core Modules

- **`core/config.py`** — module-level constants used as **defaults** by `core/runtime_config.DEFAULTS`. Operational params (window, z_entry, z_attention, BUY/SELL SL/TP/BE, ENTRY/FORCE_CLOSE windows, eg_threshold, rho_breakdown_level, beta_delta_max, z_anomaly) are tuned at runtime via `POST /api/runtime-config` — the engine reads them from the live profile, not the globals. Globals only kick in as fallback when callers omit the runtime params (legacy/test paths).
- **`core/kalman_filter.py`** — `KalmanBetaFilter` class; re-instantiated fresh on each API call (no persistent state between calls) with 15,000-bar burn-in to avoid state corruption from duplicate updates.
- **`core/signals.py`** — pure functions: `calc_beta_ols()`, `calc_zscore()`, `get_signal()`, `calc_nwe_with_bands()`, `get_rho_status()`, `get_beta_status()`. No side effects.
- **`core/trade_engine.py`** — `TradeEngine` with three independent slots: `CONS_BASE`, `WDO_NWE`, `DI_NWE`. Each slot tracks its own position, SL/TP/BE state, and logs to SQLite `matador_ops`.
- **`core/mt5_client.py`** — MT5 connection with retry; `get_bars()` returns numpy array; Windows-only.
- **`core/hmm_background.py`** — background thread; `GaussianHMM` (3-state) on WIN M30 bars; classifies regime as BULL/BEAR/CHOP every 30 min using ATR + ADX + WMA features.

### Frontend Components (`regime-dashboard/src/components/`)

All use inline `style={{}}` objects and Recharts for visualization. Dark financial theme. No state management library.

- `ZScoreChart.jsx` — dual Z-score lines (Kalman + OLS)
- `IndexChart.jsx` — WIN price with NWE bands
- `RegimeHealthPanel.jsx` — Rho / Beta-drift / Johansen status pills
- `SignalHistogram.jsx` — per-bar consensus histogram
- `PerformancePanel.jsx` — PnL table and trade history

## Key Design Decisions

**Z-score asymmetry:** Kalman (fast) for buy signals, OLS (slow) for sell signals. This reflects the Brazilian market pattern: WIN crashes are abrupt, rises are gradual.

**Stateless Kalman per request:** The filter re-runs from scratch on every API poll. Do not introduce a module-level `KalmanBetaFilter` singleton — this was explicitly reverted due to state corruption from bar deduplication.

**DI as macro filter:** `DI1$N` (Selic futures) is used as a third vector for regime confirmation in `DI_NWE` and `CONS_BASE` strategies, which is non-obvious and unique to B3.

**Regime health gates** (checked before any entry — aligned with Miqueias upstream `server.py:608` `safe_to_trade`):
- `rho_status.level ≥ 2` → block. Equivalent to `ρ > -0.55`. Level table in `core/signals.py:get_rho_status`: 0=`ρ≤-0.70`, 1=`ρ≤-0.55`, 2=`ρ≤-0.40`, 3=`ρ>-0.40`. Tunable via `runtime_config.rho_breakdown_level` (default 2).
- `|Δβ| ≥ 15%` vs 20d moving average → block. Comes from upstream `beta_status.level < 2`. Tunable via `runtime_config.beta_delta_max` (default 15.0 on both live and replay profiles).
- Engle-Granger p-value ≥ `runtime_config.eg_threshold` (default 0.10) → block. Per-strategy via `eg_strategies`.
- `|z| ≥ runtime_config.z_anomaly` (default 4.0, falls back to `core.config.Z_ANOMALY`) → block (anomaly). Enforced inside `risk_gate` and `TradeEngine.evaluate`.
- `beta_unstable=True` → block. Bar-over-bar Kalman beta state machine (`server.py:_win_beta_state`, threshold `WIN_BETA_UNSTABLE_PCT=15.0`); replay mirrors it across `_process_bar` iterations. Mirrors upstream `safe_to_trade and not beta_unstable`.

**Operational params (per-profile in `runtime_config`, snapshot at `_open_trade` so mid-position POSTs don't move the goalposts):**
- `z_entry` / `z_attention` — signal thresholds consumed by `_eval_consensus/_eval_wdo_nwe/_eval_di_nwe`.
- `buy_sl/tp/be_act/be_lock` and `sell_*` — burned into `matador_ops.sl_pts/tp_pts/be_act_pts/be_lock_pts` at open; `_check_exits` reads from the row, not the globals.
- `entry_start_h/m`, `entry_end_h/m`, `force_close_h/m` — session window passed to `risk_gate` and `TradeEngine._is_force_close` as kwargs.
- `window` — sliding window for `calc_zscore` (signals.py argument, not global state).

All of the above fall back to `core/config.py` globals only when the kwarg is `None` (legacy paths). Live: `live_profile = runtime_config.get_profile("live")` is fetched per-poll for hot-reload. Replay: `ReplayRuntimeProfile.as_engine_params()` builds the same dict from the `replay` profile.

If you tighten/loosen any of these in code or runtime config, mirror the change here.

## Critical Constraints

- **Windows-only:** MT5 API (`MetaTrader5` package) requires Windows. The frontend and SQLite layer are portable, but `core/mt5_client.py` is not.
- **Paper trading only:** `mt5.order_send()` is not called anywhere. `TradeEngine` simulates trades via SQLite only.
- **No position persistence across crashes:** In-memory trade state in `TradeEngine` is lost on server restart. On-disk state is only in `matador_ops` (closed trades). `beta_ultimo.json` exists on disk but is no longer read or written by V2 — beta is recomputed inline each poll.
- **Symbol rollover:** `WIN$N`, `WDO$N`, `DI1$N` are continuous symbols requiring manual update each contract expiry.
- **Paper OPEN orphans:** When live risk uses `live_only=True`, paper rows with `status='OPEN'` are deliberately ignored by `_get_open_trades`; they remain OPEN in `matador_ops` for audit/history and are not auto-closed by the live motor.

<!-- BACKLOG.MD MCP GUIDELINES START -->

<CRITICAL_INSTRUCTION>

## BACKLOG WORKFLOW INSTRUCTIONS

This project uses Backlog.md MCP for all task and project management activities.

**CRITICAL GUIDANCE**

- If your client supports MCP resources, read `backlog://workflow/overview` to understand when and how to use Backlog for this project.
- If your client only supports tools or the above request fails, call `backlog.get_workflow_overview()` tool to load the tool-oriented overview (it lists the matching guide tools).

- **First time working here?** Read the overview resource IMMEDIATELY to learn the workflow
- **Already familiar?** You should have the overview cached ("## Backlog.md Overview (MCP)")
- **When to read it**: BEFORE creating tasks, or when you're unsure whether to track work

These guides cover:
- Decision framework for when to create tasks
- Search-first workflow to avoid duplicates
- Links to detailed guides for task creation, execution, and finalization
- MCP tools reference

You MUST read the overview resource to understand the complete workflow. The information is NOT summarized here.

</CRITICAL_INSTRUCTION>

<!-- BACKLOG.MD MCP GUIDELINES END -->
