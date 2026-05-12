---
id: TASK-14.3
title: '[Slice 2] core/bar_history_db.py — wrapper com backend selecionável'
status: To Do
assignee: []
created_date: '2026-05-12 03:26'
labels:
  - migration
  - timescaledb
  - wrapper
dependencies: []
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implementar `core/bar_history_db.py` expondo as mesmas funções usadas hoje (insert/upsert, fetch_range, fetch_latest, etc.) com despacho para SQLite ou Postgres conforme `BAR_HISTORY_BACKEND`. Sem alterar call sites ainda.

## Entregáveis
- `core/bar_history_db.py` com API estável (assinaturas idênticas aos helpers atuais).
- Backends: `sqlite` (atual), `postgres` (psycopg ou asyncpg — decidir no Slice 0), `dual` (escreve em ambos, lê do SQLite).
- Logging de divergência em modo `dual` (warn quando POs leituras divergem em conferência opcional).

## Aceitação
- Testes unitários do wrapper passam para os 3 modos (postgres skipa se `PG_TEST_URI` ausente).
- Nenhum call site da app foi tocado — só wrapper novo.
<!-- SECTION:DESCRIPTION:END -->
