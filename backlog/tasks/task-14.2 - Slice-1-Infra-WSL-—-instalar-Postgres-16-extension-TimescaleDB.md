---
id: TASK-14.2
title: '[Slice 1] Infra WSL — instalar Postgres 16 + extension TimescaleDB'
status: To Do
assignee: []
created_date: '2026-05-12 03:26'
labels:
  - migration
  - timescaledb
  - infra
dependencies: []
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Provisionar Postgres 16 + TimescaleDB no WSL Linux (dev local), criar DB `pairtrading`, role + permissões, e validar `CREATE EXTENSION timescaledb`. Sem tocar no código da app.

## Entregáveis
- Script `scripts/setup_timescale_wsl.sh` (idempotente) ou doc em `docs/migration_bar_history_timescale.md#install`.
- Confirmação que `psql -c "SELECT extversion FROM pg_extension WHERE extname='timescaledb';"` retorna versão.
- `.pgpass` orientado no doc; nenhum segredo em git.

## Aceitação
- `psql $PG_URI -c '\dx'` mostra timescaledb instalado.
- Falha graciosa: se Postgres não estiver instalado, `BAR_HISTORY_BACKEND=sqlite` (default) ainda funciona — só Slice 2+ depende.
<!-- SECTION:DESCRIPTION:END -->
