# Configuration

This document outlines the environment variables and configuration files required to run the WIN×WDO Pair Trading system.

## Required Software

1. **MetaTrader 5**: Must be installed and running on Windows.
2. **Python 3.10+**: Used for the backend engine.
3. **Node.js 18+**: Used for the Vite frontend.
4. **PM2**: Node process manager for production execution.

## System Configuration Files

### `server.py` Configuration

The core backend configuration is defined within the `server.py` script constants:

- `MT5_PATH`: The absolute path to your `terminal64.exe` installation. **VERIFY**: You must update this path if your MT5 is not installed in the default broker directory.
- `TIME_OFFSET`: Default is `3 * 3600` (+3 hours). Used to synchronize international MT5 servers with the official B3 (Brazil) timezone.
- `SYMBOLS`: `WIN$N` and `WDO$N` (for generic continuous contracts) or specific month tickers like `WINM25`. **VERIFY**: Ensure the correct contract month is being used to prevent "No data" errors.

### `.env` Files (Frontend)

The `regime-dashboard` uses Vite environment variables:
- `VITE_API_URL`: Points to the FastAPI backend (e.g., `http://localhost:8080/api/v2/regime`).

### PM2 Ecosystem File

The `ecosystem.config.js` in the root or `regime-dashboard` directory dictates the port numbers and start scripts:
- Backend Port: `8080`
- Frontend Port: `5174`

## Setup Matador Parameters

The internal risk and trade trigger thresholds for the **Setup Matador** strategy are defined inside the `SetupMatador` class in `trade_engine.py`:

- `z_ent` (Entry Z-Score): Default `1.4`
- `z_att` (Attention Z-Score): Default `1.2`
- `nwe_h` (Kernel bandwidth): Default `8`

For extensive technical configuration details, please see `.planning/docs/SETUP_MATADOR.md`.
