# External Integrations

## 1. MetaTrader 5 (MT5) — Primary Data Source

**Type**: Shared memory IPC (Windows-only)  
**Library**: `MetaTrader5` Python package  
**Connection Manager**: `core/mt5_client.py`

### Data Flow
```
MT5 Terminal (running) → shared memory → mt5.copy_rates_from_pos() → numpy arrays
```

### Operations
| Function | Symbol | Timeframe | Bars | Usage |
|---|---|---|---|---|
| `fetch_bars(WIN$N)` | WIN$N | M5 | 250-2250 | Z-score, Beta OLS |
| `fetch_bars(WDO$N)` | WDO$N | M5 | 250-2250 | Spread computation |
| `copy_rates_from_pos(WIN$N)` | WIN$N | M30 | 1500 | HMM regime detection |

### Configuration
- **Terminal path**: `C:/Program Files/MetaTrader 5 Terminal/terminal64.exe`
- **Auto-reconnect**: Yes (checks `mt5.terminal_info()` before each request)
- **Failover**: Returns error JSON; frontend switches to simulated mode

### Gotchas
- MT5 must be running and logged into a B3 broker account
- Symbol names change on rollover dates (`WIN$N` → continuous contract)
- MT5 timestamps are UTC; server applies `TIME_OFFSET = 3 * 3600` for BRT

---

## 2. SQLite3 — Trade Persistence

**Type**: Embedded database  
**File**: `trades.db` (project root)  
**Tables**: `operations` (legacy), `matador_ops` (current)

### Schema: `matador_ops`
```sql
CREATE TABLE matador_ops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_in DATETIME,
    status TEXT,           -- 'OPEN' | 'CLOSED'
    direction TEXT,        -- 'BUY' | 'SELL'
    z_in REAL,
    z_source TEXT,         -- 'V2_KALMAN' | 'V1_OLS'
    rho_in REAL,
    beta_in REAL,
    qty_win INTEGER,
    price_win_in REAL,
    price_wdo_in REAL,
    timestamp_out DATETIME,
    exit_reason TEXT,       -- 'TARGET' | 'STOP_LOSS' | 'BE_STOP' | 'FORCE_CLOSE'
    price_win_out REAL,
    price_wdo_out REAL,
    pnl_brl REAL,
    max_pts_favor REAL DEFAULT 0.0,
    be_active INTEGER DEFAULT 0,
    hmm_state TEXT
);
```

### Access Pattern
- **Read**: `_get_open_trade()` — called every 2-5 seconds (bar cycle)
- **Write**: On trade open/close (maybe 0-5 times per session)
- **No connection pooling**: Opens/closes connection per call (adequate for single-user)

---

## 3. Beta State File — `beta_ultimo.json`

**Type**: JSON file persistence  
**Purpose**: Persists the last OLS beta across server restarts

```json
{"beta": -22.4987, "ts": "2026-04-08T17:30:00"}
```

Loaded at server startup via `load_beta_ultimo()`, saved at 17:00 each day.

---

## 4. Browser (Frontend ↔ Backend)

**Type**: HTTP REST (JSON), CORS enabled  
**Polling**: Every 2.5 seconds from frontend  
**Cache**: 2-second TTL on `/api/regime` response

### API Contract
| Endpoint | Method | Response Key Fields |
|---|---|---|
| `/api/regime` | GET | `current_z`, `signal`, `regime_health`, `history[]`, `trade_engine` |
| `/api/v2/regime` | GET | Same as above + `z_v1` dual z-score |
| `/api/performance` | GET | `total_closed_trades`, `win_rate_pct`, `accumulated_pnl`, `trades[]` |
| `/health` | GET | `mt5_connected`, `terminal_name`, `symbol_a/b` |

### Fallback Behavior
When backend is unreachable, the frontend generates synthetic Gaussian z-score data for layout testing (status → "SIMULADO").

---

## 5. Historical CSV Files (Offline Research)

**Type**: CSV files exported from MT5  
**Location**: `data/historical/`  
**Size**: ~400 MB total

| File | Size | Content |
|---|---|---|
| `WIN$N_M1_*.csv` | ~43 MB | Mini Índice 1-minute bars (2021-2026) |
| `WDO$N_M1_*.csv` | ~49 MB | Mini Dólar 1-minute bars |
| `VIX_M1_*.csv` | ~34 MB | VIX 1-minute (international MT5) |
| `DXY_M1_*.csv` | ~92 MB | Dollar Index 1-minute |
| `XAUUSD_M1_*.csv` | ~105 MB | Gold 1-minute |
| `XTIUSD_M1_*.csv` | ~90 MB | Oil 1-minute |

Used by `research/data_prep.py` to resample M1 → M30 and create the unified `dataset_m30.parquet`.
