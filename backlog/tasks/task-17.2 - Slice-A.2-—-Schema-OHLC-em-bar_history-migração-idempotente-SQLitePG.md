---
id: TASK-17.2
title: Slice A.2 — Schema OHLC em bar_history (migração idempotente SQLite+PG)
status: Done
assignee: []
created_date: '2026-05-13 01:19'
updated_date: '2026-05-13 01:49'
labels:
  - schema
  - migration
  - bar-history
dependencies: []
parent_task_id: TASK-17
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Estender `bar_history` com colunas OHLC para WIN/WDO/DI: `win_open, win_high, win_low, wdo_open, wdo_high, wdo_low, di_open, di_high, di_low`. Migração idempotente para SQLite e Postgres.

## Escopo

- `core/bar_history_db.py`:
  - `BAR_COLUMNS` (linha 32): adicionar 9 colunas novas.
  - `_SQLITE_SCHEMA` (linha 43) e `_POSTGRES_SCHEMA` (linha 67): declarar nullable.
  - Função `_ensure_ohlc_columns(conn, backend)`: lê `PRAGMA table_info` (SQLite) ou `information_schema.columns` (PG) e emite `ALTER TABLE ADD COLUMN` para cada coluna nova ausente.
  - Chamar `_ensure_ohlc_columns` ao abrir conexão (mesmo padrão de `_backfill_missing_columns` se existir).
- `tests/test_bar_history_db.py`: cobrir migração em SQLite vazio, SQLite legado (sem colunas novas), e Postgres (gate em PG_TEST_URI).

## Why explícito (codex)

`CREATE TABLE IF NOT EXISTS` **não altera** tabela já existente. Em prod, a tabela existe há semanas — precisamos de ALTER explícito.

## Safe durante mercado

Sim — colunas nullable, sem mudar inserts existentes. Migração roda no boot do módulo, idempotente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 SQLite vazio: bar_history criada com 9 colunas OHLC nullable
- [x] #2 SQLite legado (sem colunas OHLC): migração adiciona as 9 colunas via ALTER TABLE ADD COLUMN
- [x] #3 Postgres: idem via ALTER TABLE ADD COLUMN IF NOT EXISTS
- [x] #4 Idempotente: rodar 2x não erra (informação do schema consultada antes de cada ALTER)
- [x] #5 Inserts existentes (sem OHLC) continuam funcionando — colunas são nullable
- [x] #6 tests/test_bar_history_db.py cobre os 3 cenários (gate PG em PG_TEST_URI)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Mudanças

### `core/bar_history_db.py`
- `BAR_COLUMNS` estendido com 9 colunas OHLC posicionadas ao lado dos respectivos `*_price` (`win_open/high/low`, `wdo_open/high/low`, `di_open/high/low`).
- Constante `_OHLC_COLUMNS` extraída para uso na migração.
- `_SQLITE_SCHEMA`: 9 colunas `REAL` (nullable).
- `_POSTGRES_SCHEMA`: 9 colunas `DOUBLE PRECISION` (nullable).
- `_CONFLICT_SQLITE` e `_CONFLICT_POSTGRES`: cláusulas COALESCE-preserve para todas as OHLC (mesmo padrão dos indicadores — preserva valor existente, preenche NULLs).
- `_values_tuple()` lê as 9 chaves OHLC do dict posicionalmente.
- Migração idempotente:
  - `_ensure_ohlc_columns_sqlite(conn)`: `PRAGMA table_info(bar_history)` → diff → `ALTER TABLE ADD COLUMN <col> REAL` para cada faltante.
  - `_ensure_ohlc_columns_postgres(conn)`: `ALTER TABLE ADD COLUMN IF NOT EXISTS <col> DOUBLE PRECISION` (nativo PG).
- `init_schema` chama o helper apropriado após o `CREATE TABLE IF NOT EXISTS`.

### `server.py` (regressão descoberta + fix)
- `init_bar_history()` tinha DDL SQLite duplicada com seu próprio loop idempotente de `ALTER TABLE ADD COLUMN` para indicadores. Estendi esse loop com 9 sentenças OHLC para manter os dois pontos de criação sincronizados.

### `tests/test_bar_history_db.py`
- Helper `_bar_with_ohlc(ts, **overrides)` factory.
- Helpers `_sqlite_columns(db_path)` e `_postgres_columns(pg_uri)` p/ inspeção de schema.
- Cobertura SQLite (8 testes): fresh init com 9 colunas, migração de tabela legada (DDL antiga criada manualmente, ALTER preserva linha existente), idempotência em re-runs, upsert roundtrip com OHLC, merge preserva OHLC, merge preenche NULL quando fornecido, replace sobrescreve, `update_columns` aceita OHLC.
- Cobertura Postgres (5 testes, gated em `PG_TEST_URI`): fresh, migração legada, idempotência, upsert, merge-preserve.

## Verificação

- Suite completa: **386 passed, 19 skipped** (14 skips = PG_TEST_URI ausente no WSL).
- Regressão `test_backfill_fetch_mt5_fills_prices_and_computes_indicators` capturada no primeiro run e corrigida sincronizando `server.py:init_bar_history` com o schema novo.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice A.2 fechado. `bar_history` agora carrega OHLC para WIN/WDO/DI com migração idempotente em SQLite (PRAGMA table_info + ALTER TABLE) e Postgres (ALTER TABLE ADD COLUMN IF NOT EXISTS). UPSERT preserva OHLC existente via COALESCE (mesmo padrão dos indicadores).

Descoberta lateral: `server.py:init_bar_history()` tem DDL SQLite paralela com seu próprio loop de ALTER idempotente; sincronizei lá também — esse foi o ponto que causou regressão no primeiro run (`test_backfill_fetch_mt5_fills_prices_and_computes_indicators` quebrou com "no column named win_open"). Anotação mental para futuras adições de coluna: alterar os dois lugares.

Tudo aditivo + nullable → safe durante mercado. 386 passed / 19 skipped.

Próximo: A.3 (live captura OHLC via `fetch_rates()` no `server.py`). Não-safe durante mercado — mexe no caminho usado por `trade_eval_loop`.
<!-- SECTION:FINAL_SUMMARY:END -->
