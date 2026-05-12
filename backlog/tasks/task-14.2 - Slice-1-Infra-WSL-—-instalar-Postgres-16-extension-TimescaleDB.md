---
id: TASK-14.2
title: '[Slice 1] Infra WSL — instalar Postgres 16 + extension TimescaleDB'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 03:44'
labels:
  - migration
  - timescaledb
  - infra
dependencies: []
references:
  - scripts/setup_timescale_wsl.sh
  - docs/migration_bar_history_timescale.md
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Postgres 17 + TimescaleDB provisionados no WSL via script idempotente.

**Entregue:**
- `scripts/setup_timescale_wsl.sh` — instala `postgresql-17-timescaledb` (Debian trixie main, 2.19.3), patch `shared_preload_libraries` com backup automático, start/restart do cluster 17/main, cria role `pairtrading` + DBs `pairtrading` e `pairtrading_test`, habilita extension. Cada passo checa estado antes — re-rodar é no-op.
- `docs/migration_bar_history_timescale.md` §12 — seção de install com pré-requisitos, comandos de validação, override por env vars, política de senha (dev default `pairtrading_dev`, override via `DB_PASSWORD`), instruções de rollback.

**Mudança vs Slice 0:** alvo passou de PG 16 para **PG 17.5** porque o WSL já tem o cluster `17/main` instalado e o `postgresql-17-timescaledb 2.19.3` está nos repos padrão do Debian trixie — não precisou adicionar o apt repo do Timescale. Schema e contratos da §3-§4 do design contract permanecem idênticos.

**Validação:**
- `pg_lsclusters` → `17/main online port=5432`
- `SELECT extname, extversion FROM pg_extension` → `timescaledb 2.19.3` em ambas as DBs
- `psql -h 127.0.0.1 -U pairtrading -d pairtrading` → login OK via TCP
- `CREATE TEMP TABLE` → permissões do owner OK
- App **não foi tocada** — `BAR_HISTORY_BACKEND` default segue `sqlite`
<!-- SECTION:FINAL_SUMMARY:END -->
