---
id: TASK-2.1.1
title: Slice 1 — live_only kwarg nas 3 stats agregadas do TradeEngine
status: Done
assignee: []
created_date: '2026-05-13 20:25'
labels:
  - backend
  - trade-engine
  - risk
  - tests
dependencies: []
references:
  - docs/plans/separar-risco-linear-umbrella.md
  - 'core/trade_engine.py:1037'
  - tests/test_trade_engine.py
parent_task_id: TASK-2.1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Primeiro slice da TASK-2.1. Apenas leitura — zero impacto em runtime (defaults `False` em todos os kwargs). Ver `docs/plans/separar-risco-linear-umbrella.md` para visão completa.

## Mudança

Em `core/trade_engine.py`, adicionar kwarg-only `live_only: bool = False` em:
- `count_trades_today(date_str, *, live_only=False)` (linha 1037)
- `pnl_today(date_str, *, live_only=False)` (linha 1047)
- `minutes_since_last_loss(now=None, *, live_only=False)` (linha 1063)

Quando `live_only=True`, anexar `AND live = 1` ao WHERE de cada query.

## Testes

Novos em `tests/test_trade_engine.py`, com helper `_seed_trade` que faz INSERT direto em `matador_ops` via SQL para controlar `live`, `status`, `timestamp_in/out`, `pnl_brl`, `exit_reason`:

- `test_count_trades_today_default_includes_paper_and_live` — seed 1 paper + 1 live; resultado = 2.
- `test_count_trades_today_live_only_filters_paper` — mesmo seed; com `live_only=True` resultado = 1.
- `test_pnl_today_live_only_excludes_paper_losses` — replica o cenário R$-494: paper loss + live profit; `pnl_today(today, live_only=True)` ignora o paper.
- `test_minutes_since_last_loss_live_only_ignores_paper_stop` — paper STOP_LOSS 5min atrás + live STOP_LOSS 90min atrás; `live_only=True` retorna ~90.
- `test_minutes_since_last_loss_live_only_returns_none_when_no_live_stop` — só paper STOP_LOSS; retorna None.

## Fora de escopo

- Nada em `_get_open_trades`, `evaluate`, `server.py`, `timeline_emit` — vai nos próximos slices.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 count_trades_today, pnl_today, minutes_since_last_loss aceitam live_only: bool=False (kwarg-only)
- [x] #2 Quando live_only=True, queries anexam AND live = 1 ao WHERE
- [x] #3 Default (live_only=False) preserva comportamento atual: nenhuma chamada existente quebra
- [x] #4 Os 5 testes novos passam: count default + live_only, pnl exclui paper losses, cooldown ignora paper stop, cooldown=None sem live stop
- [x] #5 Suite pytest tests/test_trade_engine.py verde
<!-- AC:END -->
