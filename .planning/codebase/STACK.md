# Technology Stack

## Backend (Python)
- **Runtime**: Python 3.10+ (Windows, required for MT5 IPC)
- **Web Framework**: FastAPI + Uvicorn (port 8080)
- **Market Data**: MetaTrader5 pip package (shared-memory bridge, Windows-only)
- **Database**: SQLite3 (`trades.db`) — zero-config, single-user

### Core Dependencies
| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | REST API server (ASGI) |
| `MetaTrader5` | B3 market data via IPC shared memory |
| `numpy` | Vectorized computation (OLS, Kalman, Z-score, NWE) |
| `pandas` | DataFrame processing (HMM features) |
| `statsmodels` | Cointegration tests (Engle-Granger + Johansen) |
| `hmmlearn` | GaussianHMM regime detection (3-state, M30 cycle) |
| `ta` | Technical indicators (ATR, ADX, WMA for HMM features) |
| `firebase-admin` | Realtime Database sync to cloud |
| `scipy`, `scikit-learn` | Implicit via hmmlearn |

### Quantitative Engine Modules
| Module | Role |
|---|---|
| `core/kalman_filter.py` | `KalmanBetaFilter` — online hedge-ratio estimation via Kalman Filter |
| `core/signals.py` | Z-score, OLS beta, half-life, NWE envelope, signal generation |
| `core/trade_engine.py` | Multi-strategy evaluator (CONS_BASE, WDO_NWE, DI_NWE), paper trading |
| `core/hmm_background.py` | Background thread — 3-state GaussianHMM regime classifier (M30) |
| `core/mt5_client.py` | MT5 connection, bar fetching, beta persistence |
| `core/config.py` | All constants: Kalman params, thresholds, session times, ports |

## Frontend (React + Vite)
- **Framework**: React 19 (function components, hooks only)
- **Bundler**: Vite 8.0
- **Charting**: Recharts 3.8
- **Styling**: Inline CSS objects (dark financial theme)
- **Port**: 5174 (Vite dev server)
- **Hosting**: Firebase Hosting (`wdo-win-dashboard.web.app`)

### Frontend Key Files
| File | Role |
|---|---|
| `App.jsx` | Main loop: Firebase/polling, signal merge, NWE client-side, layout |
| `firebase.js` | Firebase Web SDK init |
| `components/ZScoreChart.jsx` | Z-Score dual-line chart (WDO + DI) |
| `components/IndexChart.jsx` | WIN price line + NWE envelope bands |
| `components/SignalHistogram.jsx` | Per-bar consensus signal histogram |
| `components/RegimeHealthPanel.jsx` | Beta/Rho/Johansen status cards |
| `components/PerformancePanel.jsx` | Paper trading PnL and trade list |

## Infrastructure
| Component | Technology |
|---|---|
| OS | Windows (required for MT5 shared memory) |
| Process Manager | PM2 or `start.bat` (launches Backend + Vite) |
| Cloud State | Firebase RTDB (push every 15s live, 5min history) |
| Data Persistence | SQLite3 (`trades.db`) |
| Beta State | Recomputed inline per V2 poll (`calc_beta_ols`); legacy `beta_ultimo.json` kept on disk but unused |

## Ports & Endpoints
| Service | Port | Key Endpoints |
|---|---|---|
| Backend (FastAPI) | 8080 | `/api/v2/regime`, `/api/di-regime`, `/api/performance`, `/api/history`, `/health` |
| Frontend (Vite) | 5174 | Dashboard UI |
| MT5 | N/A | Shared memory (no TCP) |
