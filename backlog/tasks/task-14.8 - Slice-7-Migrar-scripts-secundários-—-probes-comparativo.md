---
id: TASK-14.8
title: '[Slice 7] Migrar scripts secundários — probes + comparativo'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 07:28'
labels:
  - migration
  - timescaledb
  - scripts
dependencies: []
parent_task_id: TASK-14
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Atualizar `scripts/probe_mt5_history.py`, comparativo Miqueias, scripts de seed e qualquer outro que abra `trades.db` diretamente para `bar_history`.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Refactored 3 scripts to route bar_history I/O through core.bar_history_db wrapper:
- scripts/seed_dashboard_demo_trades.py: uses bhdb.count_rows + bhdb.bar_time_range; matador_ops still SQLite (TASK-15 scope).
- scripts/replay_bar_history_to_matador_ops.py: bar reads via bhdb.select_by_date; --db SQLite conn deferred to --commit branch.
- scripts/backfill_bar_history_indicators.py: ensure_indicator_columns no-op under PG; apply_price_rows/apply_updates route through bhdb.upsert_bars_batch + bhdb.update_columns; create_backup returns None under PG; BAR_HISTORY_SQLITE_PATH overridden via context manager during sqlite/dual runs.

Validation:
- 11 SQLite legacy tests still green.
- +4 backend-aware unit tests + 2 PG-gated integration tests (test_backfill_*_postgres).
- Full suite: 381 passed.
- A/B parity 2026-05-08: byte-equivalent stats sqlite vs postgres on both replay_bar_history_to_matador_ops.py and backfill_bar_history_indicators.py dry-runs.

Docs: docs/migration_bar_history_timescale.md §17 (Slice 7) added with table, validation, tests.
<!-- SECTION:PLAN:END -->
