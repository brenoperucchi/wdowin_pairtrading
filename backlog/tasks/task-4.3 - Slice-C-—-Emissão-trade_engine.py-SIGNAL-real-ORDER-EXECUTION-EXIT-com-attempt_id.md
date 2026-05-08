---
id: TASK-4.3
title: >-
  Slice C — Emissão trade_engine.py (SIGNAL real, ORDER, EXECUTION, EXIT) com
  attempt_id
status: To Do
assignee: []
created_date: '2026-05-08 18:54'
labels:
  - timeline
  - slice-c
dependencies:
  - TASK-4.2
references:
  - /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md
  - 'core/trade_engine.py:339,394,456'
  - core/mt5_client.py
parent_task_id: TASK-4
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wirear emissão de SIGNAL efetivo (BUY_WIN/SELL_WIN), ORDER_REQUEST, EXECUTION_FILLED/REJECTED e EXIT (TARGET/STOP_LOSS/BE_STOP/FORCE_CLOSE/CLOSE_FAILED) dentro do `TradeEngine`. `core/mt5_client.py` permanece puro — todos os 19 testes mockados continuam verdes.

**Arquivos**
- Modificado: `core/trade_engine.py` (`_open_trade`, `_close_trade`, `_check_exits`, `evaluate`)
- Modificado: `tests/test_trade_engine.py` (novos testes)

**Pontos de inserção**
- `_open_trade` (linha ~339): gerar `attempt_id = uuid4().hex` antes da tentativa.
  - Se entry confirmada, emitir SIGNAL `BUY_WIN`/`SELL_WIN` com `correlation_id=f"attempt:{attempt_id}"`.
  - Se `LIVE_ORDERS`: emitir ORDER_REQUEST (payload `{symbol, side, volume, magic, deviation, comment}`); chamar `send_market_order`; emitir EXECUTION_FILLED (`{ticket, price, retcode, message}`) ou EXECUTION_REJECTED (`{retcode, message}`) conforme `result["ok"]`.
  - Após persist em `matador_ops`, atualizar `correlation_id` para `f"trade:{trade_id}"` nos próximos eventos do mesmo trade (entries/exits subsequentes).
- `_check_exits` (linha ~432): emitir EXIT correspondente (TARGET/STOP_LOSS/BE_STOP/FORCE_CLOSE) com `correlation_id=f"trade:{trade_id}"`. Em LIVE_ORDERS, em caso de close_result `ok=False`, emitir CLOSE_FAILED com payload `{retcode, message}`.
- `evaluate()`: NÃO emitir SIGNAL=SKIPPED a cada poll — server.py faz isso na barra fechada (Slice B).

**Testes**:
- Paper mode: SIGNAL=BUY_WIN gravado mesmo sem ORDER (LIVE_ORDERS=False)
- Live mode (monkeypatched send_market_order ok): SIGNAL → ORDER_REQUEST → EXECUTION_FILLED gravados, mesmo `correlation_id=attempt:<uuid>` antes do trade_id, depois `trade:<id>`
- Live mode reject: SIGNAL → ORDER_REQUEST → EXECUTION_REJECTED, sem trade aberto, sem EXIT
- Exit por TARGET/STOP_LOSS/BE/FORCE_CLOSE em paper grava EXIT com `correlation_id=trade:<id>`
- Exit em live com close failure grava EXIT principal + CLOSE_FAILED
- `evaluate()` em loop NÃO grava SIGNAL=SKIPPED por poll
- 19 testes existentes de `test_mt5_client.py` continuam verdes (cliente puro)
- caplog tests existentes continuam verdes
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `_open_trade` gera `attempt_id` (uuid) e emite SIGNAL/ORDER/EXECUTION com `correlation_id=attempt:<uuid>` até existir trade_id, depois passa a `trade:<id>`
- [ ] #2 Em paper mode, SIGNAL real é gravado sem ORDER/EXECUTION
- [ ] #3 Em live mode, sequência SIGNAL→ORDER_REQUEST→EXECUTION_FILLED/REJECTED é gravada com payloads normalizados
- [ ] #4 EXIT (TARGET/STOP_LOSS/BE_STOP/FORCE_CLOSE) gravado em `_check_exits` com `correlation_id=trade:<id>`
- [ ] #5 CLOSE_FAILED emitido quando `close_position_by_ticket` retorna `ok=False` em live
- [ ] #6 `evaluate()` não emite SIGNAL=SKIPPED a cada poll (responsabilidade do server.py)
- [ ] #7 `mt5_client.py` continua puro (sem import/uso de `execution_timeline`)
- [ ] #8 Todos os testes de `test_mt5_client.py` continuam passando; novos testes de timeline em `test_trade_engine.py` verdes
<!-- AC:END -->
