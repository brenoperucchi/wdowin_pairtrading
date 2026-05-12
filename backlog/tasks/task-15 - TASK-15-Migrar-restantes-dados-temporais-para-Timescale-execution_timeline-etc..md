---
id: TASK-15
title: >-
  TASK-15 - Migrar restantes dados temporais para Timescale (execution_timeline,
  etc.)
status: To Do
assignee: []
created_date: '2026-05-12 06:35'
labels:
  - migration
  - timescaledb
  - followup
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Depois que TASK-14 fechar com `bar_history` 100% no Timescale e SQLite stop-write + DROP TABLE, identificar e migrar os demais blocos temporais para o mesmo storage. Mantém SQLite apenas para journal/KV (operations, matador_ops, runtime_config).

## Candidatos a avaliar
- `execution_timeline` (TASK-4) — log de eventos por bar, hot path do replay/painel.
- Outras tabelas com `timestamp BIGINT` ou densidade alta por dia.

## Não-candidatos (ficam em SQLite)
- `operations`, `matador_ops` — trade journal, escrita esporádica.
- `runtime_config` — chave/valor, snapshot.
- Quaisquer tabelas operacionais < 1k linhas/dia.

## Entregáveis
- Para cada tabela: schema PG (hypertable se justificar), contrato de UPSERT idêntico, wrapper análogo a `core/bar_history_db`, slice dual-write → read cutover → stop-write + DROP TABLE.
- Atualização da regra geral em CLAUDE.md: "dados temporais ficam no Timescale, journal/KV ficam em SQLite".

## Aceitação
- Nenhuma tabela com mais de N rows/dia em SQLite (definir N na avaliação).
- README/CLAUDE.md refletem a separação storage.

Aberta intencionalmente como follow-up de TASK-14. Sem deadline.
<!-- SECTION:DESCRIPTION:END -->
