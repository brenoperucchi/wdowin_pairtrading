# Concerns & Technical Debt

## 🔴 High Priority

### C001 — No Thread Safety on Shared State
**Risk**: Data corruption  
Multiple module-level dictionaries (`beta_state`, `_coint_cache`, `_cache`) are read/written from both the main request thread and the HMM background thread without locks.

- `beta_state` is mutated in `_update_beta_state()` (main thread) while `hmm_background` reads symbols
- `_cache` dict is reassigned atomically (Python GIL protects reference swap), but dict mutation during read isn't guaranteed safe

**Impact**: Low in practice (single-server, single-user, GIL protects most access), but architecturally fragile.

**Mitigation**: Consider `threading.Lock` on shared dicts, or use a thread-safe queue pattern.

---

### C002 — SQLite Connection-per-Call Pattern
**Risk**: Performance degradation under load  
`TradeEngine` opens and closes a new SQLite connection for every method call (`_get_open_trade`, `_update_field`, `_close_trade`). Each `evaluate()` call may trigger 3+ connection cycles.

**Impact**: Acceptable at current load (~1 call per 2.5s), but would not scale to multi-user or higher frequency.

**Mitigation**: Use a connection pool or keep a persistent connection per TradeEngine instance.

---

### C003 — No API Authentication
**Risk**: Security  
FastAPI server has `allow_origins=["*"]` and no authentication. Anyone on the network can read live trading signals and trade state.

**Impact**: Low if running on localhost only. High if exposed on LAN or VPS.

**Mitigation**: Add API key middleware or restrict CORS origins.

---

## 🟡 Medium Priority

### C004 — Hardcoded MT5 Path
**Risk**: Portability  
`MT5_PATH = "C:/Program Files/MetaTrader 5 Terminal/terminal64.exe"` is hardcoded in `core/config.py`. Won't work on different installations or broker-specific paths.

**Mitigation**: Use environment variable with fallback (`os.environ.get("MT5_PATH", ...)`).

---

### C005 — Research Code Quality
**Risk**: Maintainability  
The `research/` directory has 37+ Python files, many with similar boilerplate (backtest loops, plot generation). Several files are 9000-23000+ lines with duplicated logic.

- `tune_all_models.py` is 23,665 lines — likely contains massive grid search output or auto-generated code
- Multiple `optimize_*.py` files share near-identical backtest logic
- Utility scripts prefixed with `_` have unclear entry points

**Mitigation**: Extract shared backtest engine into a reusable module. Archive obsolete scripts.

---

### C006 — Frontend Inline Styles
**Risk**: Maintainability  
`App.jsx` (464 lines) uses exclusively inline CSS styles. No CSS classes, no design tokens, no theming system. Color values like `#00e87a`, `#ff3860`, `#c8a444` are duplicated dozens of times.

**Impact**: Hard to maintain consistent design changes. No dark/light mode toggle possible.

**Mitigation**: Extract color palette and spacing to CSS variables or a theme object.

---

### C007 — No Error Boundaries in Frontend
**Risk**: User experience  
React app has no `ErrorBoundary` component. A crash in any component (e.g., null `data.signal`) takes down the entire dashboard.

**Mitigation**: Add React error boundaries + error fallback UI at component level.

---

### C008 — Backtest ≠ Production Parity
**Risk**: Strategy integrity  
The backtest engine (`research/backtest_ml_zscore.py`) and the production engine (`core/trade_engine.py`) are **separate implementations**. There's no guarantee they use identical entry/exit logic.

**Impact**: Backtest results may not accurately predict live performance. Changes to one engine may not be reflected in the other.

**Mitigation**: Share a common `evaluate()` function between backtest and production, parameterized by data source.

---

### C009 — Missing Logging Framework
**Risk**: Observability  
All logging uses bare `print()` statements. No log levels, no log rotation, no structured logging.

**Impact**: Difficult to troubleshoot production issues. HMM thread errors are printed but may be lost.

**Mitigation**: Replace with `logging` module. Set levels per module (DEBUG for research, INFO for production).

---

## 🟢 Low Priority

### C010 — Dead Code in server.py
Lines 300-304 compute `z_kalman` using a temporary Kalman filter, then immediately overwrite it with a second proper computation (lines 307-312). The first block is dead code.

---

### C011 — No .env File Support
Configuration is all in `core/config.py` as Python constants. No `.env` file, no `pydantic-settings`, no runtime overrides.

---

### C012 — Large Historical Data in Repo
`data/historical/` contains ~400MB of CSV files. `.gitignore` exists but its coverage should be verified to ensure large data isn't accidentally committed.

---

### C013 — Frontend Fallback Data Quality
The simulated Gaussian fallback in `App.jsx` doesn't replicate realistic market behavior (no session boundaries, no gaps, no regime changes). Could mislead during offline testing.

---

### C014 — No Dependency Pinning
No `requirements.txt` or `pyproject.toml` for Python dependencies. No `package-lock.json` guarantee for exact versions. Reproducibility risk.

---

## Summary Matrix

| ID | Concern | Risk | Effort to Fix |
|---|---|---|---|
| C001 | Thread safety | 🔴 High | Low |
| C002 | SQLite conn-per-call | 🔴 High | Low |
| C003 | No API auth | 🔴 High | Low |
| C004 | Hardcoded MT5 path | 🟡 Medium | Trivial |
| C005 | Research code quality | 🟡 Medium | High |
| C006 | Inline frontend styles | 🟡 Medium | Medium |
| C007 | No error boundaries | 🟡 Medium | Low |
| C008 | Backtest ≠ production | 🟡 Medium | High |
| C009 | No logging framework | 🟡 Medium | Low |
| C010 | Dead code | 🟢 Low | Trivial |
| C011 | No .env support | 🟢 Low | Low |
| C012 | Large data in repo | 🟢 Low | Low |
| C013 | Fallback data quality | 🟢 Low | Low |
| C014 | No dep pinning | 🟢 Low | Low |
