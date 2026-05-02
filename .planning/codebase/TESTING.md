# Testing

## Test Framework
- **Runner**: pytest
- **Location**: `tests/` directory
- **Coverage tool**: None configured
- **CI/CD**: None — tests run locally

## Test Files

| File | Lines | Tests | Module Under Test |
|---|---|---|---|
| `test_config.py` | 635 | Config parameter validation | `core/config.py` |
| `test_kalman_filter.py` | 670 | Kalman beta estimation | `core/kalman_filter.py` |
| `test_signals.py` | 1985 | Z-score, signals, health | `core/signals.py` |
| `test_trade_engine.py` | 5085 | Trade lifecycle, SL/TP/BE | `core/trade_engine.py` |

## Test Characteristics

### What's Tested
- **Pure computation functions** (`calc_beta_ols`, `calc_zscore`, `calc_half_life`)
- **Signal classification** (`get_signal`, `get_rho_status`, `get_beta_status`)
- **Kalman filter** convergence and z-score normalization
- **Trade engine** entry/exit logic, SL/TP thresholds, break-even mechanics
- **Config boundaries** (parameter validation)

### What's NOT Tested
- **MT5 integration** — requires live MT5 terminal, impossible in CI
- **HMM background thread** — daemon thread with live data dependency
- **Frontend (React)** — no Jest/Vitest/Playwright configured
- **API endpoints** — no TestClient/httpx fixtures
- **Research pipeline** — ML models, WFA, backtests (no test harness)
- **SQLite integration** — test_trade_engine likely uses a test DB

### Test Strategy
The architecture was specifically refactored (see DECISIONS.md E003) to separate **pure computation** (`core/signals.py`) from **I/O** (`core/mt5_client.py`), enabling tests to run **without MT5 connected**.

```
core/signals.py = pure functions (testable with synthetic data)
core/mt5_client.py = I/O (not tested, requires MT5)
core/hmm_background.py = I/O + threading (not tested)
server.py = orchestration (not tested directly)
```

## Running Tests

```bash
# From project root
python -m pytest tests/ -v

# Expected: ~24 tests passing in ~0.3s
```

## Test Data Approach
- Tests use **synthetic numpy arrays** as input (no fixtures from real market data)
- Trade engine tests likely use an **in-memory SQLite** or a temp file
- No shared test data across test files

## Test Gaps & Recommendations

### Critical Gaps
1. **No API integration tests** — should test `/api/regime` with mocked MT5
2. **No frontend tests** — dashboard could have visual regression tests
3. **No ML model tests** — `research/models/` has no test coverage
4. **No cointegration test validation** — `coint()` call in server untested

### Risk Areas Without Tests
- Beta state machine hourly transitions
- HMM regime → signal blocking logic
- Trade engine with concurrent requests
- Frontend polling + error recovery
- Backtest fidelity vs production engine
