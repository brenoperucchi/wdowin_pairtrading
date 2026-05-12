---
id: TASK-14.4
title: '[Slice 3] Migração/bootstrap — script SQLite → Postgres + DDL idempotente'
status: To Do
assignee: []
created_date: '2026-05-12 03:26'
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
