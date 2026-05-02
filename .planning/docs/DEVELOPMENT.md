# Development Guide

This guide provides instructions on how to modify and extend the WIN×WDO Pair Trading system.

## Codebase Layout

- `server.py`: The main FastAPI application. Handles HTTP requests, polling `mt5_client`, and running the simulation fallback.
- `core/`: Contains the mathematical models and business logic.
  - `mt5_client.py`: Bridge to MetaTrader 5. Fetches historical and live data.
  - `signals.py`: Computes Z-Score, Cointegration tests, and Beta OLS.
  - `kalman_filter.py`: The V2 Kalman Filter implementation for dynamic Beta.
  - `trade_engine.py`: The Setup Matador execution logic, tracking open trades, PnL, and Stop Losses.
- `regime-dashboard/`: The React + Vite frontend application.
  - `src/App.jsx`: Main UI orchestrator, polling the API and managing state.
  - `src/components/`: Reusable Recharts components (`SignalHistogram.jsx`, `IndexChart.jsx`, `ZScoreChart.jsx`).

## Development Workflow

1. **Frontend Hot-Reload**: Running `npm run dev` in the `regime-dashboard` folder will start a Vite dev server. Any changes saved to `.jsx` files will instantly reflect in the browser.
2. **Backend Hot-Reload**: Running `uvicorn server:app --reload` will automatically restart the Python API whenever a `.py` file is modified.
3. **Simulation Mode**: If the market is closed or MT5 is unavailable, the backend automatically switches to returning simulated Gaussian random walk data, allowing UI development to continue seamlessly.

## Modifying the Trade Engine

The `trade_engine.py` script is strictly decoupled from the UI. If you want to modify how the "Setup Matador" triggers entries or exits:

1. Locate the `SetupMatador` class in `core/trade_engine.py`.
2. The method `evaluate(wdo_nwe, di_nwe, cons_wdo, cons_di, data)` is called every 2.5 seconds.
3. Ensure you follow the Causal-Only rules: Do not use future data (Lookahead Bias) when altering mathematical smoothing techniques.

## Adding New Features to the Dashboard

When adding new panels or metrics to the React dashboard:
- Ensure they are hooked into the `pollData()` cycle inside `App.jsx`.
- Avoid adding heavy computational loads (like rolling regressions) on the Frontend. Perform all heavy lifting in Python and transmit the results via the JSON API payload.
- Be extremely careful with Recharts `syncId` and X-Axis alignments (`CHART_MARGIN`) to ensure cross-chart tooltips remain perfectly synchronized.
