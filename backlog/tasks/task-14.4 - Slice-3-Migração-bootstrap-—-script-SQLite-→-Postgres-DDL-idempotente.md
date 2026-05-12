---
id: TASK-14.4
title: '[Slice 3] Migração/bootstrap — script SQLite → Postgres + DDL idempotente'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 04:16'
labels:
  - migration
  - timescaledb
  - bootstrap
dependencies: []
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Script `scripts/migrate_bar_history_to_pg.py` que: (a) cria schema/hypertable/políticas se não existem, (b) copia `bar_history` do SQLite para Postgres em transação única, (c) confere `count(*)` e checksum por dia.

## Entregáveis
- DDL idempotente (`CREATE TABLE IF NOT EXISTS`, `create_hypertable(..., if_not_exists=>TRUE)`).
- Importação em batch (COPY ou batched INSERT), single transaction.
- Relatório final: linhas migradas, dias cobertos, primeiro/último timestamp, diff vs SQLite.

## Aceitação
- Rodar o script em DB vazio importa 100% das linhas do SQLite atual.
- Rodar segunda vez é no-op (idempotente).
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resultado

`scripts/migrate_bar_history_to_pg.py` migra `bar_history` SQLite → TimescaleDB com bootstrap idempotente. Validado contra `trades.db` (54.293 linhas, 482 dias).

- **Run 1 (DB vazio):** 54.293 linhas importadas em 3.8s. 25 chunks de 30 dias criados. Política de compressão `compress_after = 7776000s` (90 dias) ativa.
- **Run 2 (idempotência):** mesmo input → 0 mudanças, checksum por dia continua batendo. `ON CONFLICT(timestamp) DO NOTHING`.
- **Suite de testes:** 351 passed com `PG_TEST_URI` setado. Zero regressões.

## Descoberta blocante (e fix)

A Debian trixie distribui `postgresql-17-timescaledb 2.19.3+dfsg-1` — **Apache edition, sem compressão**. Compressão é parte do contrato do Slice 0.

Solução: novo script `scripts/setup_timescale_tsl.sh` instala o `timescaledb-2-postgresql-17` (Community/TSL, 2.26.4) do `packagecloud.io/timescale`. Recovery destrutivo guardado por `ALLOW_DESTRUCTIVE_UPGRADE=1` (chicken-and-egg: o loader falha no connect quando o `.so` da versão antiga sumiu, então `DROP EXTENSION` não funciona — única saída é `DROP DATABASE` + recreate).

Também ajustado: `add_compression_policy('bar_history', BIGINT '7776000', if_not_exists => TRUE)` em vez de `INTERVAL '90 days'` (coluna time é BIGINT/epoch, exige integer-seconds).

## Entregáveis

- `scripts/migrate_bar_history_to_pg.py` — DDL bootstrap (hypertable+índice via wrapper) + compressão (TSL) + import em batches 5k com `ON CONFLICT DO NOTHING` + verify por totais e checksum por dia (`SUM(timestamp)` por `date_str`).
- `scripts/setup_timescale_tsl.sh` — Apache→TSL switch idempotente, com auto-detecção do estado bricked + guarda destrutivo.
- `docs/migration_bar_history_timescale.md` §3.4 atualizada (BIGINT compress_after) + nova §13 (TSL edition, procedimento, caveats).
- Memória `project_timescaledb_tsl.md` registrando o gotcha para futuros setups.

## Aceitação

- ✅ DB vazio importa 100% das linhas (54.293/54.293, 482/482 dias).
- ✅ Segunda execução é no-op (mesmos totais + checksums).
- ✅ DDL idempotente (`CREATE TABLE IF NOT EXISTS`, `if_not_exists => TRUE`).
- ✅ Relatório final imprime linhas, dias, primeiro/último timestamp, tempo.
<!-- SECTION:FINAL_SUMMARY:END -->
