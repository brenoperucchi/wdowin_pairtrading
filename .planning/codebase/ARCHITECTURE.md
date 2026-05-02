# Architecture

## System Overview

WIN×WDO is a **statistical arbitrage (pairs trading) system** for the Brazilian B3 exchange. It monitors the price relationship between Mini Índice (WIN) and Mini Dólar (WDO), detects mean-reversion opportunities via z-score, and manages trades with asymmetric risk parameters.

```
┌───────────────────────────────────────────────────────────────┐
│                       MT5 Terminal                            │
│                  (WIN$N + WDO$N live data)                    │
└──────────────┬──────────────────────┬─────────────────────────┘
               │ M5 bars              │ M30 bars
               ▼                      ▼
┌──────────────────────────┐  ┌──────────────────────┐
│   FastAPI Server (:8080) │  │   HMM Background     │
│                          │  │   Thread (15-min)     │
│  ┌──────────────────┐    │  │                       │
│  │ mt5_client.py    │◄───┤  │  GaussianHMM 3-state  │
│  │ (fetch_bars)     │    │  │  → BULL/BEAR/CHOP     │
│  └────────┬─────────┘    │  └───────────┬───────────┘
│           │              │              │
│  ┌────────▼─────────┐    │   hmm_regime │
│  │ signals.py       │    │◄─────────────┘
│  │ (zscore, rho, β) │    │
│  └────────┬─────────┘    │
│           │              │
│  ┌────────▼─────────┐    │
│  │ kalman_filter.py  │    │
│  │ (V2 Kalman β/z)   │    │
│  └────────┬─────────┘    │
│           │              │
│  ┌────────▼─────────┐    │
│  │ trade_engine.py   │    │
│  │ (entry/exit/BE)   │    │     ┌─────────────┐
│  └────────┬─────────┘    │     │  trades.db   │
│           │              │◄───►│  (SQLite)    │
│           ▼              │     └─────────────┘
│     JSON Response        │
└──────────┬───────────────┘
           │ HTTP (CORS)
           ▼
┌──────────────────────────┐
│  React Dashboard (:5174) │
│                          │
│  App.jsx (orchestrator)  │
│  ├── SetupMatadorPanel   │
│  ├── ZScoreChart         │
│  ├── IndexChart (NWE)    │
│  ├── SignalHistogram     │
│  ├── RegimeHealthPanel   │
│  ├── PerformancePanel    │
│  └── TradingGuide        │
└──────────────────────────┘
```

## System Execution (PM2)
The backend and frontend are orchestrated by **PM2** via `ecosystem.config.js`. This guarantees that both services are automatically revived on failure or machine reboot.

## Computation Pipeline (per request cycle)

1. **Data Acquisition**: `mt5_client.fetch_bars()` pulls M5 closes for WIN$N and WDO$N
2. **Beta Estimation**:
   - V1: OLS regression (`signals.calc_beta_ols()`) — hourly state machine
   - V2: Kalman filter (`kalman_filter.KalmanBetaFilter.update()`) — per-bar
3. **Z-Score Computation**:
   - V1 OLS z-score: `signals.calc_zscore()` (rolling mean/std of spread)
   - V2 Kalman z-score: `KalmanBetaFilter.rolling_zscore()` (residual-based)
4. **Regime Health**: Pearson ρ rolling, β delta vs 20-day ref, cointegration p-value
5. **HMM Regime**: Background thread every 15 min → `BULL`/`BEAR`/`CHOP`
6. **Signal Generation**: `signals.get_signal()` maps z-score → action (HMM can block)
7. **Trade Engine**: `trade_engine.evaluate()` manages SL/TP/BE per direction
8. **Response Assembly**: `_build_response()` → JSON to frontend

## Dual Z-Score Routing (Key Design Decision)

The system uses **different z-score sources for BUY vs SELL**:
- **BUY** (long WIN): V2 Kalman z-score ≤ -1.8 → faster mean-reversion detection
- **SELL** (short WIN): V1 OLS z-score ≥ +1.8 → more conservative, fewer false positives

This asymmetry is based on market behavior: Brazilian index BULL moves are gradual, BEAR drops are abrupt.

## Research Pipeline (Offline)

```
data/historical/*.csv (M1 bars)
        │
        ▼
research/data_prep.py → resample M1→M30, merge VIX/DXY
        │
        ▼
data/processed/dataset_m30.parquet (~1MB)
        │
        ▼
research/models/features.py → 17+ technical/macro features
        │
        ├── research/models/hmm_direction.py  (GaussianHMM 3-state)
        ├── research/models/lstm_direction.py  (LSTM seq→class, PyTorch)
        └── research/models/xgb_direction.py   (XGBoost tabular)
        │
        ▼
research/wfa_runner.py → Walk-Forward Analysis (12mo train / 3mo test)
        │
        ▼
data/processed/wfa_results/{hmm,lstm,xgb}/predictions_oos.parquet
        │
        ▼
research/backtest_ml_zscore.py → Combined ML+ZScore backtest on M5
        │
        ▼
research/compare_models.py → Comparative report + equity plots
```

## Threading & Process Model

| Thread / Process | Purpose | Cycle / Manager |
|---|---|---|
| Backend (uvicorn) | HTTP request handling | Managed by PM2 / Per-request (~2.5s) |
| Frontend (vite) | Serve React Dashboard | Managed by PM2 |
| HMM background | M30 regime detection | Thread in uvicorn / Every 15 min |

The HMM thread shares state via a single module-level variable: `core.hmm_background.current_hmm_regime` (string). No locks needed—write is atomic for Python strings.

## State Management

| State | Location | Scope | Update Frequency |
|---|---|---|---|
| Beta OLS current/previous | `core.mt5_client.beta_state` (dict) | Module-level | ~Hourly (state machine) |
| Beta last known | `beta_ultimo.json` (file) | Persistent | Daily at 17:00 |
| HMM regime | `core.hmm_background.current_hmm_regime` | Module-level | Every 15 min |
| Cointegration cache | `core.signals._coint_cache` | Module-level | Per beta recalc |
| Trade state | `trades.db` SQLite | Persistent | On trade open/close |
| API response cache | `server._cache` dict | Module-level | TTL 2 seconds |
