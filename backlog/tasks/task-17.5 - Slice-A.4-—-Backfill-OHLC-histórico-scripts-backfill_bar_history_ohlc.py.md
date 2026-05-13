---
id: TASK-17.5
title: Slice A.4 — Backfill OHLC histórico (scripts/backfill_bar_history_ohlc.py)
status: Done
assignee: []
created_date: '2026-05-13 01:20'
updated_date: '2026-05-13 03:03'
labels:
  - backfill
  - ohlc
  - scripts
dependencies: []
parent_task_id: TASK-17
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Script CLI para popular OHLC em barras históricas do `bar_history` que foram gravadas antes de A.3 (close-only).

## Escopo

`scripts/backfill_bar_history_ohlc.py`:
- CLI: `--start YYYY-MM-DD --end YYYY-MM-DD --symbols WIN,WDO,DI [--commit] [--force-refresh]`.
- Para cada barra no range com OHLC NULL: fetch via `fetch_rates_range` (A.1), UPSERT só nos 9 campos novos.
- Idempotente (cell-level checksum padrão da memória feedback_migration_cell_checksum).
- `--commit` faz writes; sem ele = dry-run (mostra count que seria atualizado).
- `--force-refresh` reescreve mesmo se OHLC já existe (recovery).

## Dependência (informativa)

TASK-17.1 (fetch_rates) + TASK-17.2 (schema OHLC).

## Janela / host

Windows-only (`py.exe -3.12`) — MT5 API requer Windows. Safe durante mercado (UPDATE só em colunas novas).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dry-run reporta count de barras que seriam atualizadas, sem escrever
- [x] #2 --commit popula OHLC em todas as barras do range que estavam NULL
- [x] #3 Idempotente: rodar 2x com --commit não muda nada na 2ª rodada
- [x] #4 --force-refresh reescreve OHLC mesmo se já existe
- [x] #5 Cell-level checksum confirma que close/win_price antigos não foram alterados
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Implementação

**Arquivos criados:**
- `scripts/backfill_bar_history_ohlc.py` — CLI runner
- `tests/test_backfill_bar_history_ohlc.py` — 8 testes (5 ACs + 3 edge cases)

### Script (`scripts/backfill_bar_history_ohlc.py`)

- CLI: `--start YYYY-MM-DD --end YYYY-MM-DD [--symbols WIN,WDO,DI] [--commit] [--force-refresh]`
- `SYMBOL_ALIASES`: `WIN → (SYMBOL_A, win_{open,high,low})`, idem `WDO`/`DI`. Cada alias atualiza 3 colunas → 9 cells por bar no caso default.
- `_default_mt5_fetcher` lazy-importa `core.mt5_client.{connect_mt5, fetch_rates_range}` para manter CI offline-safe (lado WSL).
- `Mt5RatesFetcher = Callable[[str, datetime, datetime], np.ndarray | None]` permite injeção em testes.
- `_mt5_bounds_for_date` devolve `(date_00:00, date+1_00:00)` — datetimes diretos pra `copy_rates_range` (mesma técnica do `fetch_bars` driven backfill).
- `_build_ohlc_map`: indexa rates por `local_ts = int(r["time"]) + TIME_OFFSET` → `{col_open, col_high, col_low}`.
- `_plan_updates_for_row`: cells_to_set se `force_refresh OR existing is None` E valor difere.
- `run_backfill`: loop por data → `bhdb.select_by_date` → fetcher por alias → merge em `ohlc_by_ts` → `bhdb.update_columns(ts, **cells)` quando commit. Conta `rows_scanned/rows_updated/cells_updated/rows_missing_mt5_data`.

### Integridade (AC#5)

SHA-256 sobre `INTEGRITY_COLUMNS` (`win_price, wdo_price, di_price, z_wdo, z_di, spread_wdo, spread_di, eg_pvalue, rho, rho_level, beta_value, beta_delta_pct`):
- Computa **before** sobre `all_existing_rows` (snapshot pré-commit).
- Pós-commit re-lê todas as datas processadas e recalcula → se drift → `RuntimeError` (aborta).
- Padrão da memória `feedback_migration_cell_checksum` (COUNT+SUM falham sob DO NOTHING; SHA-256 sobre cells é o detector real).

### Testes (8/8 passando)

- `test_dry_run_reports_plan_without_writing` — AC#1
- `test_commit_populates_null_ohlc` — AC#2 (+ asserts em valores específicos de bar0)
- `test_idempotent_second_commit_is_noop` — AC#3 (segunda rodada: rows_updated=0, cells_updated=0)
- `test_force_refresh_rewrites_existing_ohlc` — AC#4 (fetcher shifted +100 → win_high muda)
- `test_integrity_checksum_aborts_on_non_ohlc_drift` — AC#5 (monkeypatch hostile que clobbera `win_price` → `RuntimeError` levantada)
- `test_integrity_checksum_stable_when_only_ohlc_written` — sanity: clean run → checksum bit-exato
- `test_symbols_subset_only_updates_requested_columns` — `--symbols WIN` só popula 3 colunas
- `test_rows_with_no_mt5_data_are_counted_not_updated` — gap no fetcher → contado em `rows_missing_mt5_data`

### Verificação

Full suite: **403 passed, 19 skipped, 1 warning** (zero regressões; +8 testes vs baseline A.3).

### Windows-only execution

Runtime real precisa MT5 ⇒ `py.exe -3.12 scripts/backfill_bar_history_ohlc.py --start ... --end ... --commit`. Smoke test fora do escopo do slice (sem janela de execução com mercado fechado neste momento).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice A.4 entregue: script `scripts/backfill_bar_history_ohlc.py` + 8 testes cobrindo os 5 ACs.

**O que funciona:**
- Dry-run mostra plano (rows/cells que seriam atualizadas) sem escrever
- `--commit` popula OHLC apenas em cells NULL (default merge mode)
- Idempotente em 2ª execução (skip por `existing is not None`)
- `--force-refresh` reescreve mesmo cells já populadas
- SHA-256 cell-level checksum aborta se algum UPDATE escapar do conjunto de 9 colunas OHLC

**O que ainda falta no slice:** smoke-test real contra MT5 no host Windows (`py.exe -3.12 scripts/backfill_bar_history_ohlc.py --start 2026-04-01 --end 2026-05-09 --commit`) — adiado para próxima janela fora de mercado.

**Próximo slice (A.5):** `SimulationProfile` dentro de cada perfil em `core/runtime_config.py` (slippage/intra-bar/costs/conflict_rule), conforme acordado: `simulation` block aninhado em live/replay, default `enabled=false` em ambos.
<!-- SECTION:FINAL_SUMMARY:END -->
