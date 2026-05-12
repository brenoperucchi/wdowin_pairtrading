---
id: TASK-14
title: Migração bar_history SQLite → TimescaleDB (parent)
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 11:15'
labels:
  - migration
  - timescaledb
  - bar_history
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

`bar_history` (atualmente em `trades.db` SQLite) cresceu para 54k+ barras e é a fonte de verdade para Engle-Granger rolling, rho, beta_di e replay execution timeline. As janelas de leitura (2240 barras EG, 240 barras rho) ficam custosas para consultas multi-mês.

## Objetivo

Mover apenas a tabela `bar_history` para TimescaleDB (Postgres extension), preservando a semântica de UPSERT do SQLite e habilitando hypertable + `compress_chunks` para janelas históricas.

Resto da app (`matador_ops`, runtime_config, replays/, audits/) permanece em SQLite. Sem mudança de comportamento de trading.

## Princípios (acordados com usuário)

1. **Contract-first**: Slice 0 entrega doc de design antes de qualquer linha de código.
2. **Dual-write antes de cutover**: nada de hard switch. Backend selecionável via env var `BAR_HISTORY_BACKEND=sqlite|postgres|dual`.
3. **Rollback por env**: voltar a SQLite sem deploy.
4. **Credenciais via env, não em `core/config.py`**: `.env.example` + `.pgpass`.
5. **Testes de integração opt-in**: skip via `pytest.skip()` quando `PG_TEST_URI` ausente; suite unit continua portátil.
6. **Hypertable chunk de 30 dias** (não 7), `compress_chunks` >= 90 dias.
7. **PK/índice único inclui a coluna de tempo** (requisito do TimescaleDB).

## Escopo de aceitação

- `BAR_HISTORY_BACKEND=sqlite` (default) continua igual ao comportamento atual.
- `BAR_HISTORY_BACKEND=dual` grava em ambos, lê do SQLite (paridade observável).
- `BAR_HISTORY_BACKEND=postgres` grava e lê só do Postgres; replay/EG produzem o mesmo resultado do baseline SQLite na mesma data.
- Fresh clone consegue subir o stack em SQLite sem instalar Postgres; doc explica como ativar Postgres.

## Slices

- Slice 0 — Design contract (este TASK)
- Slice 1 — Infra WSL (instalar Postgres + extension TimescaleDB)
- Slice 2 — `core/bar_history_db.py` wrapper (dual backend)
- Slice 3 — Script de migração/bootstrap (cria schema, importa SQLite → PG)
- Slice 4 — Dual-write live (`BAR_HISTORY_BACKEND=dual`)
- Slice 5 — Cutover read (`BAR_HISTORY_BACKEND=postgres`)
- Slice 6 — Migrar scripts principais (replay, backfill)
- Slice 7 — Migrar scripts secundários (probes, comparativo)
- Slice 8 — Tests + docs (`PG_TEST_URI`, `.env.example`, README)
<!-- SECTION:DESCRIPTION:END -->
