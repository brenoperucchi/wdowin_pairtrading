# Runbook — Symbol Rollover (WIN / WDO / DI)

WIN$N, WDO$N and DI1$N are **continuous** front-month symbols on B3. MT5
maps them to whichever physical contract is current. There is no automatic
adjustment for the price gap when one contract retires and the next one
takes over — that gap will appear as a single-bar discontinuity in the
historical series.

This runbook covers the manual checks performed each rollover.

## Calendar

B3 contract expiries:

| Symbol | Expiry day                    | Codes used per year                    |
|--------|-------------------------------|----------------------------------------|
| WIN    | Wed nearest the 15th, even months | G,J,M,Q,V,Z (Feb, Apr, Jun, Aug, Oct, Dec) |
| WDO    | First business day of every month | F,G,H,J,K,M,N,Q,U,V,X,Z                  |
| DI1    | First business day of every month | F,G,H,J,K,M,N,Q,U,V,X,Z (each maturity)  |

WDO and DI1 roll **monthly**; WIN rolls **bi-monthly**. The combined cadence
is: there is at least one rollover almost every month, and a "double" event
when both WDO/DI1 roll on the same day a WIN expiry month begins.

## Pre-rollover checklist (T-1)

The day before any expiry:

1. `pm2 stop all` — stop the live engine before market close to avoid
   straddling a rollover with an open position.
2. Close any open positions in the dashboard or directly via XP.
3. Confirm the gap size in MT5 (Market Watch → right-click symbol → Specs):
   the front-month price vs. the next-month's settle. Gaps of 5+ pts in WDO
   or 0.05+ % in DI1 are common and will dominate single-bar P&L if the
   engine restarts mid-rollover.

## Rollover day (T)

1. Wait for B3 to publish the new front-month (typically before 09:00 BRT).
2. In MT5 Market Watch, verify `WIN$N`, `WDO$N`, `DI1$N` are all enabled
   and pointing at the new front-month (the symbol's "Spec" tab shows the
   underlying physical contract).
3. **Backfill check**: `python scripts/probe_mt5.py --bars 200` and inspect
   the last bar before/after the rollover ts. If a > 5σ jump appears in the
   spread, note the rollover ts in your trade journal so post-mortem
   reviews can flag the discontinuity (the `bar_history` table currently
   has no per-bar status column; future improvement could add one).
4. **Restart the engine fresh** so the Kalman filter re-burns its 15k bars
   on the post-rollover series:
   ```
   pm2 start ecosystem.config.js
   ```
5. Watch the first 10 polls in the dashboard:
   - `regime_health.beta_unstable` should NOT be true (Kalman has
     re-converged).
   - `risk_gate.allowed` may legitimately be False for the first ~hour
     while EG cointegration re-establishes — this is expected.

## Post-rollover validation (T+1)

1. Pull the day's `matador_ops` rows and verify no trades were opened
   within ±60 minutes of the rollover ts. If they were, flag for review —
   the SL/TP points-based logic does not adjust for inter-contract gaps.
2. Compare daily P&L from `matador_ops` against XP DEMO 52033102 broker
   statement. Mismatches > R$ 50 likely come from rollover gaps appearing
   in continuous-series prices but not in your actual fills.
3. Update `docs/MOTOR_E_FLUXO_DE_DADOS.md` only if the rollover surfaced
   a new edge case in the engine.

## Open questions / known gaps

- **Backtest scripts** under `research/` use the continuous CSV without
  rollover gap adjustment — see `research/README.md`. P&L from those
  scripts will diverge from production's per-contract P&L by the
  cumulative gap size. Documented; not yet fixed.
- **Automated detection**: a future improvement is to detect rollover
  via symbol-spec changes from MT5 and either pause the engine or apply
  a programmatic gap correction. Not in scope for the pre-live hardening
  milestone.
