# research/

Exploratory backtests, optimizers and plotting utilities. **None of these scripts are the production engine** — they read CSV snapshots and operate offline. The live engine is `core/trade_engine.py`, fed by `server.py`.

## Nomenclature: DOL ≡ WDO

In conversation we sometimes say "DOL" or "dólar" — in this codebase that **always** refers to `WDO$N` (Mini Dólar, B3 ticker, 10 R$/ponto, tick 0.5). There is **no** `DOL$F` (full dollar contract) anywhere in the project: not in `core/config.py`, not in `server.py`, not in any research script. If a backtest filename or comment mentions "DOL", it means WDO.

If we ever introduce the full dollar contract, do it explicitly with a new constant (`DOL_SYMBOL = "DOL$F"`) and update this section.

## Production scope (what the live engine actually does)

The live trade engine opens **only WIN** contracts (`WIN_CONTRACTS=2` in `core/config.py`) — it is a directional WIN strategy with WDO/DI used as filter/consensus vectors. There is no hedge leg, no spread P&L, no WDO order. See `CLAUDE.md` → "Trading Scope" for the full statement.

## Script classification

The scripts in this folder were written across multiple research phases and **do not all model the production engine**. Before drawing conclusions from any P&L number, check what the script actually trades:

### Single-leg WDO (WDO-only — does NOT match production)
These open only WDO positions. The live engine never trades WDO, so the P&L here is not comparable to live paper trading.

- `optimize_wdo.py`
- `optimize_wdo_sltp.py`

If the gestor reports "the DOL backtest doesn't work", it is almost certainly one of these — and the explanation is structural: the live system never executes that strategy.

### 4-leg speculative (long/short WIN + long/short WDO independently — does NOT match production)
Tests four independent legs (`wdo_buy`, `wdo_sell`, `win_buy`, `win_sell`) without coordinated entry/exit. Useful as research, not as validation of the engine.

- `backtest.py`
- `backtest_pa.py`
- `backtest_johansen_gate.py`

### Directional WIN (closer to production scope)
Opens only WIN. Closer to the live engine, but still differs in details (filter logic, gate ordering).

- `backtest_win.py`
- `run_matador_v5_johansen.py` — closest to the live engine; consensus across CONS_BASE / WDO_NWE / DI_NWE

### Optimizers / plotting (do not trade)
Grid searches and visualizations. They consume the outputs of the above and compute metrics; do not by themselves represent a strategy.

- `optimize_*.py` (except the WDO-only ones flagged above)
- `plot_*.py`
- `compare_*.py`
- `tune_*.py`
- `equity_*.py`

## Known gaps (apply to ALL scripts here)

These are **not modeled** in any script and will systematically bias backtest P&L upward vs. live paper trading:

1. **B3 fees** (emolumentos + corretagem) — order of ~R$ 1.50 per contract per side. Adds up over hundreds of trades.
2. **Slippage** — assumed zero; live entries/exits cross the spread.
3. **Rollover gaps** — continuous-series CSVs splice contract months. Trades crossing the rollover absorb a 3-5 point gap that does not exist in the live market.
4. **Divergent params** — most scripts hardcode their own `Z_ENTRY`, `BUY_SL`, `BUY_TP` values rather than importing `core/config.py`. A "good" research P&L may rest on params the live engine does not use.

These will be addressed by the AC #14/#15/#16 reconciliation work in TASK-3.

## Running a script

All scripts assume CSVs live under `research/` (or wherever the script's `pd.read_csv(...)` path points). Run from repo root:

```bash
python research/<script>.py
```

Outputs (CSVs, PNGs, equity curves) are written next to the script. Inspect each script's `__main__` block before running — many take command-line args or have hardcoded date ranges.
