---
id: TASK-16.6
title: 'Slice 6 — Frontend: novos campos no slideover /config'
status: To Do
assignee: []
created_date: '2026-05-12 19:38'
labels:
  - frontend
  - ui
  - runtime-config
dependencies: []
parent_task_id: TASK-16
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Adicionar inputs no slideover Runtime Config (`regime-dashboard/`) para os 16 novos campos. UX consistente com os campos existentes.

## Tarefas

1. Identificar o componente que renderiza `/api/runtime-config` no React.
2. Adicionar grupos visuais:
   - **Janela & thresholds**: `window`, `z_entry`
   - **Janela de sessão**: `entry_start_h/m`, `entry_end_h/m`, `force_close_h/m`
   - **Risk (BUY)**: `buy_sl`, `buy_tp`, `buy_be_act`, `buy_be_lock`
   - **Risk (SELL)**: `sell_sl`, `sell_tp`, `sell_be_act`, `sell_be_lock`
3. Inputs com validation client-side (bounds idênticos ao backend).
4. Submit chama POST `/api/runtime-config` (já existe).

## Acceptance criteria

- AC1: Slideover mostra os 16 novos campos com defaults atuais.
- AC2: Edit + Save persiste em runtime.json e reflete em `/api/runtime-config` GET.
- AC3: Validation rejeita valores fora de bounds sem chamar API.
<!-- SECTION:DESCRIPTION:END -->
