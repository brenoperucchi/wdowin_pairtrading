---
id: TASK-11.2
title: '[Slice B] Replay runtime profile and EG recompute'
status: Done
assignee: []
created_date: '2026-05-10 22:30'
updated_date: '2026-05-10 22:30'
labels:
  - config
  - replay
  - risk-gate
dependencies:
  - TASK-11.1
parent_task_id: TASK-11
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wire `scripts/replay_execution_timeline.py` to the `replay` runtime profile.

Scope:
- Load `runtime_config["replay"]`.
- Add CLI overrides: `--eg-threshold`, `--eg-bars`, `--eg-recalc`, `--rho-breakdown-level`, `--beta-delta-max`.
- Recompute Engle-Granger p-value from `bar_history.win_price/wdo_price` during replay instead of trusting persisted `bar_history.eg_pvalue`.
- Support `eg_recalc=bar` and `eg_recalc=daily`.
- Pass replay thresholds into `risk_gate`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Replay loads `runtime_config["replay"]` by default.
- [x] #2 CLI overrides replace the JSON values without writing `config/runtime.json`.
- [x] #3 Replay EG uses a rolling `eg_bars` window over `bar_history` prices, including previous-day warmup rows.
- [x] #4 `eg_recalc=bar` recomputes each bar; `eg_recalc=daily` reuses one p-value per date.
- [x] #5 `risk_gate` accepts per-call `eg_threshold`, `rho_breakdown_level`, and `beta_delta_max` while preserving live defaults.
- [x] #6 Tests cover window length, daily cache, CLI parse, risk-gate override, and no-MT5 replay guarantees.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice B landed.

**Files**
- `scripts/replay_execution_timeline.py` — added `ReplayRuntimeProfile`, profile resolution from `runtime_config`, CLI overrides, EG source warmup query, `ReplayEgComputer`, runtime profile summary, and threshold forwarding into `risk_gate`.
- `core/risk_gate.py` — `risk_gate()` now accepts optional per-call thresholds for EG, rho breakdown, and beta drift. Defaults still come from the existing module constants when not provided.
- `core/runtime_config.py` — public `validate_runtime_config()` helper for normalising overrides without writing a file.
- `tests/test_replay_execution_timeline.py` — tests for EG window recompute, daily cache, CLI overrides, updated missing-EG semantics, and preserved no-MT5/source-readonly contracts.
- `tests/test_risk_gate.py` and `tests/test_runtime_config.py` — override and validation coverage.

**Behavioral change**
- `bar_history.eg_pvalue` is no longer a required replay input. Missing persisted EG does not skip the bar; replay recomputes EG from prices. If there is not enough warmup price history, the bar is processed with `eg_pvalue=None`, producing `EG_UNAVAILABLE`.

**Validation**
- `python3 -m py_compile scripts/replay_execution_timeline.py core/risk_gate.py core/runtime_config.py`
- `python3 -m pytest tests/test_replay_execution_timeline.py tests/test_runtime_config.py tests/test_risk_gate.py -q` → 83 passed.
- `python3 -m pytest tests/ -q` → 274 passed.
- Manual CLI smoke: `python3 scripts/replay_execution_timeline.py --date 2026-05-07 --source trades.db --out /tmp/wdowin-slice-b-replay --eg-bars 60 --eg-recalc daily --eg-threshold 0.30` completed and wrote a replay DB under `/tmp`.
<!-- SECTION:FINAL_SUMMARY:END -->
