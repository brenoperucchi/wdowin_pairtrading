---
id: TASK-8.2
title: Slice B — Script replay_execution_timeline.py (motor offline)
status: In Progress
assignee: []
created_date: '2026-05-09 17:13'
updated_date: '2026-05-10 07:06'
labels:
  - execution-timeline
  - replay
  - backend
  - scripts
dependencies: []
references:
  - scripts/replay_execution_timeline.py
  - core/execution_timeline.py
  - core/risk_gate.py
  - core/trade_engine.py
  - server.py
parent_task_id: TASK-8
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implementar o motor de replay como script CLI standalone que reconstrói o funil DATA→EXIT a partir de `bar_history`, gravando eventos em `replays/execution_timeline_<date>.db` (DB isolado).

Depende do Slice A para ter os indicadores persistidos. Para barras pré-Slice-A (sem `eg_pvalue/rho/beta`), emite `MISSING_*` em vez de quebrar.

Escopo:
- `scripts/replay_execution_timeline.py --date YYYY-MM-DD [--source trades.db] [--out replays/]`
- Loop bar-a-bar: carrega `bar_history` da data, ordena por timestamp, e para cada barra:
  - Emite DATA/INDICATORS conforme presença/ausência de campos
  - Constrói chamada a `risk_gate(...)` com valores persistidos (Slice A) ou MISSING_* se NULL
  - Constrói chamada a `TradeEngine.evaluate(...)` em modo paper (sem MT5)
  - Grava todos os eventos via `record_event(db_path=replay_db, ...)` reusando o mesmo módulo do live
- Garantia: `LIVE_ORDERS=False` no scope do replay, e nenhum import que dispare `mt5.initialize()`.
- DB de saída fica em `replays/execution_timeline_<date>.db`, criado idempotentemente via `init_timeline_table()`.
- Resumo final no stdout e como evento META no DB: total bars, processed, missing, blockers por (phase, reason), trades simulados, PnL paper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Script `scripts/replay_execution_timeline.py` aceita `--date YYYY-MM-DD` (obrigatório), `--source` (default `trades.db`), `--out` (default `replays/`).
- [ ] #2 Cria `replays/execution_timeline_<date>.db` se não existir, usando `init_timeline_table()`.
- [ ] #3 Para cada barra de `bar_history` na data: emite eventos DATA, INDICATORS, ELIGIBILITY, RISK, SIGNAL, ORDER, EXECUTION, EXIT respeitando o funil (não emite ORDER se ELIGIBILITY bloqueou, etc).
- [ ] #4 Reusa `risk_gate()`, `TradeEngine.evaluate()` (em modo paper), `record_event()` do código do live; não reimplementa lógica.
- [ ] #5 Quando `eg_pvalue/rho/rho_level/beta_value/beta_delta_pct/wdo_price/di_price/win_price` estão NULL na barra, emite evento DATA com `MISSING_<FIELD>` e segue para a próxima barra (não quebra).
- [ ] #6 Replay nunca importa `MetaTrader5` nem chama `mt5.order_send`; teste assegura isso (mock/import guard).
- [ ] #7 Janela operacional vem de `core.config.ENTRY_START_H/M, ENTRY_END_H/M`; sem hardcode no script.
- [ ] #8 Stdout exibe summary final: bars total, processed, missing-by-field, blockers por (phase, reason), trades simulados, PnL paper, current_bottleneck, current_live_issue.
- [ ] #9 Testes: replay de fixture com 1 dia válido produz N eventos esperados; replay de fixture com `di_price` faltante emite `MISSING_DI_PRICE`; replay de fixture com `eg_pvalue` faltante emite `MISSING_EG_PVALUE`; nenhum import MT5 é disparado.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Files added:**
- `core/timeline_emit.py` — extracted `emit_closed_bar_timeline`, `severity_for_reason`, `reason_fields`, `timeline_ts`, `timeline_minute_key`, `TIMELINE_RISK_REASONS`, `TIMELINE_TRANSIENT_REASONS` from `server.py`. Pure module, no MT5/firebase deps. Both server.py and the replay import from here so phase-routing/severity logic doesn't drift.
- `scripts/replay_execution_timeline.py` — CLI driver. Opens `--source` with `mode=ro` URI for guaranteed read-only source-DB access. Iterates `bar_history` rows for the date, validates AC #5 fields, emits `MISSING_<FIELD>` DATA events when NULL (one per missing field), otherwise builds `risk_gate(...)` + `engine.evaluate(...)` + `emit_closed_bar_timeline(...)` against `replays/execution_timeline_<date>.db`. Refuses to run when `LIVE_ORDERS=True`. Stdout summary + META event (`phase=EXIT, event=REPLAY_SUMMARY`).
- `tests/test_replay_execution_timeline.py` — 6 tests: happy 2-bar funnel, MISSING_DI_PRICE, MISSING_EG_PVALUE, REQUIRED_BAR_FIELDS matches AC #5, MetaTrader5 module identity unchanged after replay (sentinel attribute), source-DB mtime/size unchanged.

**Files modified:**
- `server.py` — replaced inline `_emit_closed_bar_timeline` and friends with imports from `core.timeline_emit`. Updated single call site in `regime_v2()` to pass `db_path=DB_PATH`. Removed now-dead imports (`WITHIN_POLL_OP_REASONS`, `EG_PVALUE_THRESHOLD`, `BETA_DELTA_MAX`, `Z_ANOMALY`, `MAX_TRADES_PER_DAY`, `DAILY_LOSS_LIMIT_BRL`, `LOSS_COOLDOWN_MIN`). Behavior unchanged — call site signature is identical except for the new `db_path=DB_PATH` keyword.

**AC mapping:**
- #1 ✅ argparse with `--date` required, `--source` default `trades.db`, `--out` default `replays`
- #2 ✅ `Path(out_dir).mkdir(parents=True, exist_ok=True)` + `init_timeline_table(replay_db)` + `TradeEngine(db_path=replay_db)` (engine init also calls `init_timeline_table`)
- #3 ✅ `emit_closed_bar_timeline` builds INDICATORS/RISK/ELIGIBILITY/SIGNAL; `TradeEngine.evaluate` builds SIGNAL/ORDER/EXECUTION/EXIT internally. Phase routing identical to live.
- #4 ✅ Reuses `risk_gate()`, `TradeEngine.evaluate()`, `record_event()`, `emit_closed_bar_timeline()` (now shared). Zero duplicated logic.
- #5 ✅ `_missing_required_fields` against `REQUIRED_BAR_FIELDS = (win_price, wdo_price, di_price, eg_pvalue, rho, rho_level, beta_value, beta_delta_pct)` — emits one MISSING_<FIELD> per NULL, then `continue`.
- #6 ✅ Test `test_replay_does_not_import_metatrader5` tags the conftest stub with a sentinel and asserts identity unchanged after `run_replay`. Replay refuses when `LIVE_ORDERS=True` (paper-only by config default).
- #7 ✅ Session window enforced via `risk_gate(... hour, minute, ...)` which reads `core.config.ENTRY_START_H/M, ENTRY_END_H/M` — no hardcode in script.
- #8 ✅ `_print_summary` covers all required fields + bottleneck + live_issue.
- #9 ✅ Tests cover all four scenarios (valid day, missing DI, missing EG, no MT5).

**Known fidelity gaps (not blocking AC):**
- Timeline event `timestamp` falls back to `datetime.now()` inside `TradeEngine` SIGNAL/ORDER/EXECUTION emissions (engine doesn't accept a `now` override). The bar's actual moment is still encoded via `closed_bar_ts`. INDICATORS/RISK/ELIGIBILITY/SIGNAL events from `emit_closed_bar_timeline` carry the bar timestamp via `now_dt`.
- `matador_ops.timestamp_in/out` carry replay execution wall-clock, not the bar's wall-clock. Audit happens against `execution_timeline.closed_bar_ts`, so this doesn't affect funnel correctness — only the matador_ops view.

Both gaps are candidates for a follow-up TASK-8.x if needed; punted from this slice to keep blast minimal.

**Validation handoff (Windows):**
- `py.exe -3.12 -m pytest tests/test_replay_execution_timeline.py -q`
- `py.exe -3.12 -m pytest tests/test_bar_history.py tests/test_execution_timeline.py tests/test_execution_timeline_server.py tests/test_trade_engine.py -q` — regression check after server.py refactor
- `sha256sum trades.db` before; `py.exe -3.12 scripts/replay_execution_timeline.py --date 2026-05-08`; `sha256sum trades.db` after — must be identical (DoD #3)
<!-- SECTION:NOTES:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `py.exe -3.12 -m pytest tests/test_replay_execution_timeline.py -q` passa.
- [ ] #2 `py.exe -3.12 scripts/replay_execution_timeline.py --date 2026-05-08` roda sem erro e produz `replays/execution_timeline_2026-05-08.db`.
- [ ] #3 Confirmar que `trades.db` não foi alterado pela execução do script (compara mtime/sha256 antes/depois).
<!-- DOD:END -->
