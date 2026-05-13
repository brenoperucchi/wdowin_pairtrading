---
id: TASK-2.1.3
title: 'Slice 3 — Cutover server.py: passa live_only=bool(LIVE_ORDERS)'
status: To Do
assignee: []
created_date: '2026-05-13 20:25'
labels:
  - backend
  - server
  - live-orders
  - risk
  - tests
dependencies: []
references:
  - docs/plans/separar-risco-linear-umbrella.md
  - 'server.py:1411'
  - 'server.py:1440'
  - 'server.py:1464'
  - core/trade_engine.py
parent_task_id: TASK-2.1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Slice de cutover. Antes deste slice, defaults `False` preservam comportamento legado. Aqui o `server.py` passa a propagar `live_only=bool(LIVE_ORDERS)` e o bug real é corrigido.

Depende dos Slices 1 e 2.

## Mudança

Em `server.py`, nas três chamadas relevantes (linhas aproximadas — confirmar no diff):
- l.1411: pré-evaluate `risk_gate(...)` — risk_gate em si não muda, mas as stats que alimentam ele precisam ter sido calculadas com `live_only`
- l.1440: `_trade_engine.evaluate(..., live_only=bool(LIVE_ORDERS))`
- l.1464: pós-evaluate `risk_gate(...)`

Como `risk_gate()` é scope-agnostic, a mudança concreta é:
1. Calcular `trades_today_count`, `daily_pnl_brl`, `minutes_since_last_loss` (passados a `risk_gate`) com `live_only=bool(LIVE_ORDERS)`.
2. Passar `live_only=bool(LIVE_ORDERS)` na chamada de `evaluate`.

## Testes

Novo em `tests/test_trade_engine_live.py`:
- `test_evaluate_live_only_still_blocks_on_live_daily_loss` — seed live `pnl_brl = -DAILY_LOSS_LIMIT_BRL` CLOSED hoje (`live=1`); `evaluate(..., live_only=True)` retorna `WAIT` com gate_reasons contendo `DAILY_LOSS_LIMIT`.

Integração no FastAPI TestClient (se viável neste slice, senão adiar para Slice 4):
- Subir app, seedar paper loss + live profit, polar `/api/v2/regime`, verificar que `risk_gate.allowed=True` (ou pelo menos que `DAILY_LOSS_LIMIT` saiu de `reasons`).

## Validação manual pós-merge

1. Confirmar trade paper R$-494 no DB.
2. Subir server com `LIVE_ORDERS=1`.
3. Aguardar próxima janela de sinal — entrada não bloqueada por `DAILY_LOSS_LIMIT` do paper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 server.py propaga live_only=bool(LIVE_ORDERS) para evaluate e nas stats que alimentam risk_gate
- [ ] #2 Teste test_evaluate_live_only_still_blocks_on_live_daily_loss passa (perda live real ainda bloqueia)
- [ ] #3 Quando LIVE_ORDERS=0, comportamento legado preservado (live_only=False)
- [ ] #4 Suite pytest completa verde
- [ ] #5 Validação manual: paper R$-494 deixa de bloquear entrada live
<!-- AC:END -->
