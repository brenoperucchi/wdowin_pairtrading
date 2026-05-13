---
id: TASK-2.1.5
title: Slice 5 — Campo scope no timeline_emit (reasons operacionais)
status: To Do
assignee: []
created_date: '2026-05-13 20:25'
labels:
  - backend
  - timeline
  - observability
  - tests
dependencies: []
references:
  - docs/plans/separar-risco-linear-umbrella.md
  - 'core/timeline_emit.py:74'
  - 'core/timeline_emit.py:212'
  - tests/test_execution_timeline.py
parent_task_id: TASK-2.1
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Último slice. Adiciona campo `scope` nos eventos de timeline que distinguem live de paper, para auditoria/debug.

Depende dos Slices 1-3 (precisa do flag `live_only` chegando do server).

## Mudança

### `core/timeline_emit.py`

1. `reason_fields(reason, ..., live_only: bool = False)` (linha 74-115): em cada um dos três blocos abaixo, adicionar `"scope": "live" if live_only else "all"`:
   - `MAX_TRADES_REACHED` (l.94-100)
   - `DAILY_LOSS_LIMIT` (l.101-107)
   - `LOSS_COOLDOWN` (l.108-114)
   
   Demais reasons (BAR_NOT_CLOSED, RHO_BREAKDOWN, BETA_DRIFT, Z_ANOMALY, etc.) **não** recebem `scope` — o conceito não se aplica.

2. `emit_closed_bar_timeline(..., live_only: bool = False)` (linha 212): aceitar e repassar para `reason_fields`.

### `server.py`

Na chamada de `emit_closed_bar_timeline` (≈l.1475 ou onde estiver após o slice 4), passar `live_only=bool(LIVE_ORDERS)`.

## Testes

Novo em `tests/test_execution_timeline.py`:
- `test_emit_closed_bar_timeline_includes_scope_for_operational_reasons` — com `live_only=True`, eventos de MAX_TRADES_REACHED/DAILY_LOSS_LIMIT/LOSS_COOLDOWN têm `scope=live`; eventos de outras reasons (RHO_BREAKDOWN, BAR_NOT_CLOSED) não têm o campo.
- `test_reason_fields_default_omits_scope` — default `live_only=False` deixa `scope=all`.

## Compatibilidade

Consumidores existentes (dashboard, replay) toleram campos extras em `payload_json` — não há schema strict. Confirmar lendo `tests/test_execution_timeline*` (já valida dicts permissivos).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 reason_fields injeta 'scope' apenas em MAX_TRADES_REACHED, DAILY_LOSS_LIMIT, LOSS_COOLDOWN
- [ ] #2 Demais reasons (BAR_NOT_CLOSED, RHO_BREAKDOWN, BETA_DRIFT, Z_ANOMALY, etc.) inalteradas - sem campo scope
- [ ] #3 emit_closed_bar_timeline aceita e propaga live_only kwarg-only (default False)
- [ ] #4 server.py passa live_only=bool(LIVE_ORDERS) na chamada de emit_closed_bar_timeline
- [ ] #5 Testes novos em test_execution_timeline.py passam
- [ ] #6 Suite pytest completa verde
<!-- AC:END -->
