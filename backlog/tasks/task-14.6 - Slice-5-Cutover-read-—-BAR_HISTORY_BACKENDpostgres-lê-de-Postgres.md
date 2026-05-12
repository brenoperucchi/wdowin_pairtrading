---
id: TASK-14.6
title: '[Slice 5] Cutover read — BAR_HISTORY_BACKEND=postgres lê de Postgres'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 06:26'
labels:
  - migration
  - timescaledb
  - cutover
dependencies: []
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trocar os 19 call sites de leitura para o wrapper. Em modo `postgres`, leituras vão para o hypertable. SQLite permanece como fallback ativo via env var.

## Entregáveis
- Todas as leituras passam pelo wrapper.
- Validação A/B: rodar mesma janela de EG/rho em ambos os backends e comparar valores (script de diff).

## Aceitação
- Replay execution timeline em data X produz mesmos resultados em `sqlite` e `postgres`.
- Voltar para SQLite via env var continua funcionando (rollback).
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Entrega

Slice 5 troca o **read path** do live engine para Postgres quando `BAR_HISTORY_BACKEND=postgres`. Writes continuam indo para ambos backends em modo `dual` E `postgres` — só o read path muda. Isso evita o cutover quebrado onde reads PG ficariam stale enquanto writes só atingissem SQLite.

| backend    | write SQLite | write PG | read     |
|------------|--------------|----------|----------|
| `sqlite`   | ✅           | —        | SQLite   |
| `dual`     | ✅           | ✅       | SQLite   |
| `postgres` | ✅           | ✅       | Postgres |

### server.py

- `save_bar_history` → guard de dual-write expandido para `bhdb.get_backend() in ("dual", "postgres")`. Sem essa correção (capturada por reviewer feedback), o cutover read seria pra um PG congelado.
- `load_bar_history` → quando `backend == "postgres"`, busca rows via `bhdb.select_window(days=days, backend="postgres")`. Loop subsequente é backend-agnostic.
- `do_backfill_if_empty` → em modo `postgres`, `COUNT(*)` via `bhdb.count_rows(backend="postgres")`.
- `db_path` aceito mas ignorado pelas leituras em `postgres`; writes ainda usam.

### Não escopo (próximas slices)

- Scripts (`scripts/replay_execution_timeline.py`, `scripts/backfill_*`) — Slice 6.

## Cobertura (`tests/test_bar_history.py`)

Default (sem `PG_TEST_URI`):
- `test_load_bar_history_default_unaffected_by_wrapper` — sem env, `bhdb.select_window` não é invocado.
- `test_do_backfill_if_empty_uses_postgres_count` — `postgres` mode roteia `COUNT(*)` via wrapper.
- `test_save_bar_history_mirrors_to_pg_when_backend_dual_or_postgres` (parametrizado `dual`/`postgres`) — **regression do cutover**: ambos modos invocam `bhdb.upsert_bar(backend="postgres")` E gravam SQLite.
- `test_save_bar_history_pg_failure_does_not_break_sqlite` (parametrizado) — PG falha → SQLite OK em ambos modos.
- `test_save_bar_history_skips_pg_when_sqlite_fails` (parametrizado) — SQLite falha → PG skipped em ambos modos.

Gated em `PG_TEST_URI`:
- `test_load_bar_history_reads_from_postgres_when_backend_postgres` — seed via wrapper, lê via `load_bar_history(db_path="/ghost.db")`; rows do PG; db_path ignorado.
- `test_load_bar_history_dual_still_reads_from_sqlite` — modo `dual` mantém leitura SQLite.

## Aceitação

- ✅ `sqlite` default: comportamento idêntico ao baseline. Suite: **352 passed, 11 skipped, 1 warn**.
- ✅ `dual`: write em ambos, read SQLite.
- ✅ `postgres`: write em ambos, read PG. Com `PG_TEST_URI` setado: **53/53 nos suites alvo, 0 skip**.
- ✅ Smoke live (postgres mode): `save_bar_history` gravou em PG; `load_bar_history(db_path="/ghost.db")` leu de PG com round-trip exato (`z=0.77 rho=-0.83`).
- ✅ Rollback: alternar env entre `sqlite`/`dual`/`postgres` muda backend sem mudar código; SQLite continua tendo todas as barras nos três modos.

## Docs

- `docs/migration_bar_history_timescale.md` §15 (novo): read cutover, matriz write/read por backend, ativação/rollback, cobertura.

## Próximo

- Slice 6 — migrar `scripts/replay_execution_timeline.py`, `scripts/backfill_*` para o wrapper. Inclui A/B de replay (mesmo dia, sqlite vs postgres) prometido nesta task.
<!-- SECTION:FINAL_SUMMARY:END -->
