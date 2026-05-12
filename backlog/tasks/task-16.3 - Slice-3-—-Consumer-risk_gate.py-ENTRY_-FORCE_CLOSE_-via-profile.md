---
id: TASK-16.3
title: 'Slice 3 — Consumer risk_gate.py: ENTRY_*/FORCE_CLOSE_* via profile'
status: To Do
assignee: []
created_date: '2026-05-12 19:37'
labels:
  - refactor
  - runtime-config
dependencies: []
parent_task_id: TASK-16
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Migrar `core/risk_gate.py` para receber `entry_start_h/m`, `entry_end_h/m`, `force_close_h/m` via parâmetros.

## Mudanças

### `core/risk_gate.py`
- `_in_session(hour, minute, entry_start_h=..., entry_start_m=..., entry_end_h=..., entry_end_m=...)`.
- `risk_gate(...)` aceita os mesmos kwargs e propaga.

### `core/trade_engine.py`
- `force_close_h/m` consumido em `force_close_if_open(...)`.
- Idealmente lido do profile a cada poll (hot-reload).

### `server.py`, `replay_execution_timeline.py`
- Passar profile values em todos os call sites.

## Constraints

- Restart fora do mercado.
- `tests/test_risk_gate.py` cobre cada combinação de janela.

## Acceptance criteria

- AC1: `_in_session(10, 0)` com profile `entry_end_h=15` retorna True; com `entry_end_h=10` retorna False.
- AC2: Mudança via POST muda comportamento sem restart na próxima poll.
<!-- SECTION:DESCRIPTION:END -->
