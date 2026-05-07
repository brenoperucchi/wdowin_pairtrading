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

### Production (PM2)
```bash
pm2 start ecosystem.config.js
pm2 logs
pm2 save
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
    │ polls every 2.5s, CACHE_TTL=2.0s
    │
    ├─ /api/v2/regime  ──► core/kalman_filter.py → core/signals.py → core/trade_engine.py
    ├─ /api/di-regime  ──► OLS beta on DI1$N pair
    ├─ /api/performance ─► SQLite matador_ops query
    ├─ /api/history    ──► last 5min of bar_history
    └─ Firebase RTDB push (15s cadence for live state, 5min for history)
                │
                ▼
    regime-dashboard/ (React 19 + Vite, port 5174)
        └─ App.jsx polls API every 2500ms (falls back to Gaussian simulator)
```

### Core Modules

- **`core/config.py`** — single source of truth for all parameters: Kalman Q/R, Z-score thresholds, SL/TP, session hours, NWE tuning. Always touch this first before hardcoding any constant.
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

**Regime health gates** (checked before any entry):
- `ρ > -0.40` → block (correlation breakdown)
- `Δβ > 25%` vs 20d moving average → block (hedge ratio drift)
- Engle-Granger p-value ≥ 0.10 → zero contracts
- `|z| ≥ 4.0` → block (anomaly)

## Critical Constraints

- **Windows-only:** MT5 API (`MetaTrader5` package) requires Windows. The frontend and SQLite layer are portable, but `core/mt5_client.py` is not.
- **Paper trading only:** `mt5.order_send()` is not called anywhere. `TradeEngine` simulates trades via SQLite only.
- **No position persistence across crashes:** In-memory trade state in `TradeEngine` is lost on server restart. On-disk state is only in `matador_ops` (closed trades). `beta_ultimo.json` exists on disk but is no longer read or written by V2 — beta is recomputed inline each poll.
- **Symbol rollover:** `WIN$N`, `WDO$N`, `DI1$N` are continuous symbols requiring manual update each contract expiry.

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
