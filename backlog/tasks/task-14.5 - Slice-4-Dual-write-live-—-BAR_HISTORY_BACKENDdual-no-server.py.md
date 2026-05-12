---
id: TASK-14.5
title: '[Slice 4] Dual-write live — BAR_HISTORY_BACKEND=dual no server.py'
status: To Do
assignee: []
created_date: '2026-05-12 03:26'
labels:
  - migration
  - timescaledb
  - live
dependencies: []
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Substituir os call sites de escrita em `server.py` (e trade engine se aplicável) pelo wrapper do Slice 2. Default permanece `sqlite`; ativar `BAR_HISTORY_BACKEND=dual` em dev/staging para acumular paridade.

## Entregáveis
- Server e poller usam `bar_history_db.upsert_bar(...)` em vez de SQL inline para escrita.
- Modo `dual` validado por janela (ex.: 1 dia em produção dev) sem divergência.

## Aceitação
- `BAR_HISTORY_BACKEND=sqlite` → comportamento idêntico ao baseline.
- `BAR_HISTORY_BACKEND=dual` → ambos os DBs recebem as mesmas barras, leitura continua do SQLite.
<!-- SECTION:DESCRIPTION:END -->
