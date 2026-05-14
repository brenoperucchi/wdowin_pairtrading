---
id: TASK-2.1
title: Separar risco live de paper e auditoria por scope
status: To Do
assignee: []
created_date: '2026-05-13 20:24'
labels:
  - backend
  - trade-engine
  - live-orders
  - risk
dependencies: []
references:
  - docs/plans/separar-risco-linear-umbrella.md
  - core/trade_engine.py
  - core/risk_gate.py
  - core/timeline_emit.py
  - server.py
parent_task_id: TASK-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Hoje, com `LIVE_ORDERS=1`, os gates operacionais (`MAX_TRADES_REACHED`, `DAILY_LOSS_LIMIT`, `LOSS_COOLDOWN`, posição aberta por slot) consideram TODAS as linhas de `matador_ops`, sem distinguir trade real (`live=1`) de simulado (`live=0`). Consequência: um trade paper de hoje com `pnl_brl=-494` está bloqueando entradas live via `DAILY_LOSS_LIMIT`.

## Objetivo

Em modo live:
- Gates operacionais consideram somente `matador_ops.live=1`.
- Trades paper continuam no DB para auditoria mas não bloqueiam o motor.
- SL/TP/BE/FORCE_CLOSE continuam decididos pelo motor (sem SL/TP pendurado no MT5).
- Interface (`/api/v2/regime`, `/health`) e timeline indicam o escopo (live vs all).

## Abordagem

Kwarg `live_only: bool` nas funções de leitura agregada do `TradeEngine`; `server.py` decide via `bool(LIVE_ORDERS)` e propaga. `risk_gate()` permanece scope-agnostic.

Plano completo em `docs/plans/separar-risco-linear-umbrella.md`. Cinco slices independentes (cada um vira subtask abaixo). Defaults `False` em tudo: o efeito real só acontece no Slice 3 (cutover server.py).

## Escopo dessa umbrella

Coordenação dos 5 slices. Cada slice tem seus próprios testes e commit independente. Reportar ao usuário entre cada slice antes de iniciar o seguinte.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Plano em docs/plans/separar-risco-linear-umbrella.md aprovado e referenciado nos slices
- [x] #2 Slice 1: count_trades_today, pnl_today, minutes_since_last_loss aceitam live_only kwarg e filtram por live=1 quando True; testes verdes
- [x] #3 Slice 2: _get_open_trades e evaluate aceitam live_only e propagam internamente; testes verdes incluindo o caso do paper R$-494 NÃO bloqueando
- [x] #4 Slice 3: server.py passa live_only=bool(LIVE_ORDERS) nas chamadas de evaluate; gate live ainda bloqueia em perda live real
- [x] #5 Slice 4: /api/v2/regime expõe risk_stats_scope, risk_trades_today, risk_daily_pnl_brl, risk_minutes_since_last_loss; /health expõe risk_stats_scope
- [ ] #6 Slice 5: timeline_emit.reason_fields injeta scope nos eventos MAX_TRADES_REACHED, DAILY_LOSS_LIMIT, LOSS_COOLDOWN; demais reasons inalteradas
- [ ] #7 Trades paper-OPEN antigos NÃO são modificados; comportamento documentado em docstring de _get_open_trades e em CLAUDE.md
- [ ] #8 Suite pytest completa verde após o último slice
<!-- AC:END -->
