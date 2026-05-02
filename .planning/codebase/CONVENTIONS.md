# Code Conventions

## Language & Naming

### Python (Backend + Research)
- **Language**: Code comments, docstrings, and variable names mix Portuguese and English
  - Module docstrings: Portuguese (`"""Calcula o hedge ratio β via OLS"""`)
  - Function names: English (`calc_beta_ols`, `get_signal`, `fetch_bars`)
  - Config constants: English UPPER_SNAKE (`Z_ENTRY`, `BUY_SL`, `SELL_TP`)
  - Print/log messages: Portuguese (`"[MT5] Conectando ao terminal"`)
  - UI labels: Portuguese (`"COMPRA WIN"`, `"AGUARDAR"`, `"ANOMALIA"`)
- **Type hints**: Used on function signatures (`def calc_beta_ols(closes_a: np.ndarray, ...) -> float`)
- **Private helpers**: Prefixed with underscore (`_build_history`, `_update_beta_state`, `_rolling_zscore`)
- **Classes**: PascalCase (`KalmanBetaFilter`, `TradeEngine`, `HMMDirection`, `LSTMDirection`)
- **Modules**: snake_case (`trade_engine.py`, `kalman_filter.py`, `hmm_background.py`)

### JavaScript/JSX (Frontend)
- **Components**: PascalCase functions (`SetupMatadorPanel`, `ZScoreChart`, `RegimeHealthPanel`)
- **State hooks**: camelCase (`currentZ`, `lastUpdate`, `safeToTrade`)
- **Constants**: UPPER_SNAKE for config (`API_URL`, `POLL_MS`, `SESSION_START`)
- **CSS**: Inline styles (objects), no CSS-in-JS libraries, no Tailwind
- **No TypeScript** — plain JSX with no type checking

## File Organization

### Production vs Research Separation
```
core/        → Runs in production (server.py imports these)
research/    → Offline analysis only (never imported by server.py)
data/        → Input/output data (never committed to git for large files)
docs/        → Documentation and specs
tests/       → Unit tests for core/ modules
```

### Research File Prefixes
- `_*.py` → Internal helper scripts, not meant to be run standalone
- `optimize_*.py` → Parameter grid search scripts
- `plot_*.py` → Visualization-only scripts
- `tune_*.py` → Hyperparameter tuning scripts
- `backtest_*.py` → Backtesting variants

## Architecture Patterns

### Server Pattern: Thin Controller
`server.py` is deliberately thin — it orchestrates `core/` modules but contains no computation logic itself. All math lives in `core/signals.py`, `core/kalman_filter.py`, etc.

### State Machine Pattern (Beta)
Beta is not recalculated every bar. A state machine in `mt5_client.beta_state` dict tracks:
- When beta was last calculated
- Whether it's a new hour/day
- If beta is "unstable" (>15% change intra-day)

Recalculation happens only at :30 of each hour during trading session (09:30, 10:30, ..., 17:30).

### Module-Level Shared State
Several modules use module-level variables as shared state (no class instances):
- `core.hmm_background.current_hmm_regime` (str) — written by daemon thread
- `core.mt5_client.beta_state` (dict) — written by server on beta recalc
- `core.signals._coint_cache` (dict) — written by server on cointegration test
- `server._cache` / `server._cache_ts` — response-level cache

### Signal → Action Mapping
`get_signal()` returns a dict with standardized fields:
```python
{"id": "compraWin", "label": "COMPRA WIN (KALMAN)", "sub": "...",
 "wdo": "IGNORAR", "win": "COMPRAR", "qty_wdo": 0, "qty_win": 2, "color": "#00e87a"}
```
The `id` field is the stable machine-readable key; `label` is Portuguese display text.

### ML Model Interface
All three direction models in `research/models/` follow a consistent interface:
```python
class ModelDirection:
    def fit(self, X_train, y_train) -> self
    def predict(self, X_test) -> np.ndarray  # Returns ['BUY', 'SELL', 'FLAT']
    def predict_proba(self, X_test) -> np.ndarray  # Optional
```

## Configuration

### All Config in One File
`core/config.py` centralizes **all** trading parameters — no magic numbers scattered in code. Categories:
- Infrastructure (MT5 path)
- Symbols (WIN$N, WDO$N)
- Timeframe & windows (M5, 40-bar window, 250 bars)
- Entry parameters (Z_ENTRY=1.8, Z_ANOMALY=4.0)
- Risk parameters (SL/TP/BE per direction)
- Session hours (10:00-16:00 entry, 17:40 force close)
- Server settings (cache TTL, time offset)

### Asymmetric Parameters
BUY and SELL have **different** SL/TP/BE parameters, reflecting market asymmetry:
- BUY: SL=350, TP=500, BE_ACT=400, BE_LOCK=50
- SELL: SL=300, TP=1400, BE_ACT=800, BE_LOCK=200

## Code Style

### Python
- No formatter enforced (no black/ruff config files found)
- Docstrings present on all public functions and classes
- Section headers with Unicode box-drawing characters: `# ─── Section ───`
- Imports grouped: stdlib → third-party → local (`from core.config import ...`)

### JavaScript
- ESLint configured (`eslint.config.js`)
- No Prettier — formatting is informal
- Components are function-based (no class components)
- All state managed via `useState` / `useEffect` hooks (no Redux/Context)

## Error Handling
- **MT5 failures**: Return error JSON, frontend switches to "SIMULADO" mode
- **DB failures**: Silent catch with pass (beta persistence)
- **HMM failures**: Caught in background thread, printed, retried in 15 min
- **Frontend fetch errors**: Caught, status set to "fallback", simulated data shown
