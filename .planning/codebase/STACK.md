# Technology Stack

## Backend (Python)
- **Runtime**: Python 3.10+
- **Web Framework**: FastAPI + Uvicorn (port 8080)
- **Market Data**: MetaTrader5 (MT5 shared-memory bridge, Windows-only)
- **Database**: SQLite3 (`trades.db`) — zero-config, single-user

### Core Dependencies
| Package | Version | Purpose |
|---|---|---|
| `fastapi` | latest | REST API server |
| `uvicorn` | latest | ASGI server |
| `MetaTrader5` | latest | B3 market data via shared memory |
| `numpy` | latest | Vectorized computation (OLS, z-score, Kalman) |
| `pandas` | latest | DataFrame processing (HMM, research) |
| `statsmodels` | latest | Cointegration test (Engle-Granger) |
| `hmmlearn` | latest | GaussianHMM regime detection (3-state) |
| `ta` | latest | Technical indicators (ATR, ADX, WMA, RSI) |
| `firebase-admin` | latest | RTDB state synchronization to cloud |

### ML / Research Dependencies
| Package | Version | Purpose |
|---|---|---|
| `torch` | ≥2.0 | LSTM directional model (PyTorch) |
| `xgboost` | ≥2.0 | XGBoost directional classifier |
| `pyarrow` | ≥15.0 | Parquet I/O for processed datasets |
| `dateutil` | latest | WFA window date arithmetic |
| `scikit-learn` | latest | (implicit via xgboost/hmmlearn) |

## Frontend (React + Vite)
- **Runtime**: Node.js 18+ (tested on v22)
- **Framework**: React 19 (function components, hooks only)
- **Bundler**: Vite 8.0
- **Charting**: Recharts 3.8
- **Styling**: Inline CSS (dark theme, financial UI aesthetic)
- **Port**: 5174 (Vite dev server)
- **Hosting**: Firebase Hosting (`wdo-win-dashboard.web.app`)

### Frontend Dependencies
| Package | Version | Purpose |
|---|---|---|
| `react` | ^19.2.4 | UI framework |
| `react-dom` | ^19.2.4 | DOM renderer |
| `recharts` | ^3.8.1 | Z-Score area chart |
| `vite` | ^8.0.1 | Dev server + bundler |
| `eslint` | ^9.39.4 | Linting |

## Infrastructure
| Component | Technology | Notes |
|---|---|---|
| OS | Windows (required) | MT5 uses Windows shared memory |
| Process Manager | **PM2** | Manages FastAPI and Vite via `ecosystem.config.js` |
| Cloud State | Firebase RTDB | Syncs live data for public dashboard (`dashboard`, `history_30d`) |
| Data Persistence | SQLite3 (trades.db) | Single-file DB, local only |
| Data Serialization | JSON (API), Parquet (research) | JSON for live data, Parquet for offline analysis |
| Beta State | File-based (beta_ultimo.json) | Persists last daily beta across restarts |
| Historical Data | CSV files (data/historical/) | M1 bars exported from MT5 (~50MB each) |

## Language Distribution
- **Python**: ~85% (backend, core logic, research, ML models)
- **JavaScript/JSX**: ~15% (frontend dashboard)
- No TypeScript, no CSS preprocessors, no Docker

## Ports & Endpoints
| Service | Port | Key Endpoints |
|---|---|---|
| Backend (FastAPI) | 8080 | `/api/regime`, `/api/v2/regime`, `/api/performance`, `/health` |
| Frontend (Vite) | 5174 | Dashboard UI |
| MT5 | N/A | Shared memory (no TCP) |
