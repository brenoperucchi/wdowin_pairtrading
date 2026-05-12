---
id: TASK-14.6
title: '[Slice 5] Cutover read — BAR_HISTORY_BACKEND=postgres lê de Postgres'
status: To Do
assignee: []
created_date: '2026-05-12 03:26'
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
