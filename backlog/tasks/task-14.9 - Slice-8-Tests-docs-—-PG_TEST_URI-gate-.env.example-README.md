---
id: TASK-14.9
title: '[Slice 8] Tests + docs — PG_TEST_URI gate, .env.example, README'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 07:45'
labels:
  - migration
  - timescaledb
  - tests
  - docs
dependencies: []
parent_task_id: TASK-14
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Suite final: testes de integração opt-in com `PG_TEST_URI`, `pytest.skip()` quando ausente; `.env.example` consolidado; README/`CLAUDE.md` atualizado com setup do Postgres opcional, comando de migração, e instruções de rollback.

## Entregáveis
- `tests/test_bar_history_db.py` cobrindo SQLite (sempre roda) e Postgres (skipa).
- `.env.example` com `PG_URI`, `PG_TEST_URI`, `BAR_HISTORY_BACKEND`.
- `CLAUDE.md` ou `docs/migration_bar_history_timescale.md` com seção "Backend de bar_history" explicando defaults, ativação, rollback.
<!-- SECTION:DESCRIPTION:END -->
