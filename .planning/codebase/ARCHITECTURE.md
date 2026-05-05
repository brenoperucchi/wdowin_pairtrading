# Architecture

## Padrão Arquitetural
Hybrid Extended Architecture — quantitative engine (Python) + reactive thin-client (React).

```
 ┌──────────────┐     IPC      ┌────────────────────┐     Firebase RTDB      ┌─────────────┐
 │  MetaTrader5  │────────────▶│   server.py (8080)  │──────────────────────▶│ Web Dashboard│
 │  (WIN/WDO/DI) │  shared mem │   FastAPI + Engine  │  push every 2.5-15s   │ React (5174) │
 └──────────────┘              └─────────┬──────────┘                        └──────┬──────┘
                                         │                                          │
                              ┌──────────▼──────────┐                    ┌──────────▼──────────┐
                              │   core/ modules     │                    │ Firebase Hosting     │
                              │ kalman, signals,    │                    │ wdo-win-dashboard    │
                              │ trade_engine, hmm   │                    │ .web.app             │
                              └─────────┬──────────┘                    └─────────────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │   trades.db (SQLite) │
                              └────────────────────┘
```

## Data Flow (tick-to-dashboard)
1. **MT5 IPC** — `mt5_client.fetch_bars()` pulls M5 OHLCV via shared memory for WIN$N, WDO$N, DI1$N
2. **Kalman Filter** — `KalmanBetaFilter.update()` iteratively estimates beta (hedge ratio) for each pair
3. **Z-Score** — `KalmanBetaFilter.rolling_zscore()` normalizes Kalman spread residuals over a rolling window
4. **Johansen Gate** — `_compute_johansen_gate()` runs periodic cointegration test (every 12 bars ~1h)
5. **NWE Envelope** — `calc_nwe_with_bands()` computes Nadaraya-Watson trend bands for contra-trend filtering
6. **HMM Regime** — Background thread (M30 cycle) classifies WIN into BULL/BEAR/CHOP
7. **Trade Engine** — `TradeEngine.evaluate()` runs 3 strategies (CONS_BASE, WDO_NWE, DI_NWE) independently
8. **API Response** — FastAPI endpoint `/api/v2/regime` assembles full payload
9. **Firebase Sync** — `firebase_push_loop()` pushes dashboard state every 2.5s, history every 5min
10. **React Dashboard** — Subscribes to Firebase RTDB (prod) or polls localhost (dev)

## Strategy Architecture (Matador v4/v5)
The trade engine manages 3 independent strategy slots in parallel:

| Strategy | Entry Signal | Filter |
|---|---|---|
| **CONS_BASE** | WDO z ≤ -1.4 AND DI z ≤ -1.2 (or vice versa) | None (pure consensus) |
| **WDO_NWE** | WDO z ≤ -1.4 | NWE contra-trend + band proximity |
| **DI_NWE** | DI z ≤ -1.4 | NWE contra-trend + band proximity |

Each slot manages its own position lifecycle: Entry → SL/TP/BE monitoring → Force Close at 17:40.

## Key Design Decisions
- **Stateless Kalman per request**: The V2 endpoint re-runs the Kalman from scratch each poll to avoid state corruption from duplicate bar updates. Burn-in = 15,000 bars.
- **Bar-close gate**: Entries only fire on confirmed M5 bar close (backtest parity). Exits check every tick.
- **Dual-pair consensus**: WDO and DI z-scores must align before CONS_BASE triggers.
- **Paper trading only**: No MT5 order dispatch. Signal-only + SQLite logging.
