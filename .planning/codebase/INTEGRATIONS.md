# Integrations

## MetaTrader 5 (MT5)
- **Method**: IPC / Windows shared memory via `MetaTrader5` pip package
- **Connection**: `core/mt5_client.py` → `mt5.initialize(path=MT5_PATH)` with 10s timeout
- **Terminal**: `C:/Program Files/MetaTrader 5/terminal64.exe` (XP Demo account)
- **Data fetched**: `mt5.copy_rates_from_pos(symbol, TIMEFRAME_M5, 0, count)` — returns OHLCV numpy arrays
- **Symbols**: `WIN$N` (Mini Índice), `WDO$N` (Mini Dólar), `DI1$N` (DI Futuro)
- **Auto-select**: On connection, all 3 symbols are activated in Market Watch via `mt5.symbol_select()`
- **Limitation**: Windows-only. Terminal must be logged in. No Linux/Docker support.
- **Known issue**: "MetaTrader 5 Terminal" path causes IPC timeout due to RegimeSupervisor holding PID in Session 0; use "MetaTrader 5" (XP Demo) which runs in user Session 1.

## Firebase Realtime Database (RTDB)
- **Method**: `firebase-admin` SDK with Service Account (`serviceAccountKey.json`)
- **Database URL**: `https://wdo-win-dashboard-default-rtdb.firebaseio.com`
- **Push loop** (`server.py` → `firebase_push_loop()`):
  - `/dashboard` — full regime state pushed every 15s (or immediately on trade signal)
  - `/history_30d` — bar history pushed every 5min (300s)
- **Data structure**:
  ```
  /dashboard
    /regime      → full /api/v2/regime response
    /di_regime   → full /api/di-regime response
    /performance → full /api/performance response
  /history_30d   → array of {z, z_di, spread, bar_time, date, win_price}
  ```
- **Plan**: Spark (free tier) — bandwidth-conscious push intervals

## Firebase Hosting
- **Project**: `wdo-win-dashboard`
- **URL**: `wdo-win-dashboard.web.app`
- **Deploy**: `firebase deploy --only hosting` from project root
- **Source**: `regime-dashboard/dist/` (Vite production build)
- **Config**: `firebase.json` + `.firebaserc`

## SQLite3 (`trades.db`)
- **Tables**:
  - `operations` — legacy V1 trade log
  - `matador_ops` — V4/V5 multi-strategy paper trades (CONS_BASE, WDO_NWE, DI_NWE)
  - `bar_history` — persisted M5 bars with z-scores for historical replay
- **Access pattern**: Direct `sqlite3.connect()` per operation (no connection pool)
- **Known issue**: Disk thrashing from ~5 connect/disconnect cycles per 2.5s poll

## Beta Persistence (`beta_ultimo.json`)
- Legacy artifact from the V1 OLS endpoint. `core/mt5_client.py` still defines `save_beta_ultimo()` / `load_beta_ultimo()` and seeds a `beta_state` dict, but no live code reads or updates it after the V1 removal.
- V2 (`/api/v2/regime`) and `/api/history` recompute OLS beta inline on each call from the current window; there is no daily persistence step today.
- File and helpers will be deleted (or replaced with a real cache) when the `risk_gate` slice lands.
