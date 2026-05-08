---
id: TASK-4.3
title: >-
  Slice C — Emissão trade_engine.py (SIGNAL real, ORDER, EXECUTION, EXIT) com
  attempt_id
status: Done
assignee: []
created_date: '2026-05-08 18:54'
updated_date: '2026-05-08 19:38'
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
- [x] #1 `_open_trade` gera `attempt_id` (uuid) e emite SIGNAL/ORDER/EXECUTION com `correlation_id=attempt:<uuid>` até existir trade_id, depois passa a `trade:<id>`
- [x] #2 Em paper mode, SIGNAL real é gravado sem ORDER/EXECUTION
- [x] #3 Em live mode, sequência SIGNAL→ORDER_REQUEST→EXECUTION_FILLED/REJECTED é gravada com payloads normalizados
- [x] #4 EXIT (TARGET/STOP_LOSS/BE_STOP/FORCE_CLOSE) gravado em `_check_exits` com `correlation_id=trade:<id>`
- [x] #5 CLOSE_FAILED emitido quando `close_position_by_ticket` retorna `ok=False` em live
- [x] #6 `evaluate()` não emite SIGNAL=SKIPPED a cada poll (responsabilidade do server.py)
- [x] #7 `mt5_client.py` continua puro (sem import/uso de `execution_timeline`)
- [x] #8 Todos os testes de `test_mt5_client.py` continuam passando; novos testes de timeline em `test_trade_engine.py` verdes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Guardrails do codex (review pós-Slice B):
1. `attempt_id` (uuid4) deve nascer ANTES de qualquer `mt5.order_send`, inclusive antes do insert em `matador_ops` (antes de existir `trade_id`). correlation_id usa `attempt:{attempt_id}` até o insert; depois muda para `trade:{trade_id}`.
2. Payloads MT5 devem ser suficientes para debug, sem dados sensíveis:
   - `ORDER_REQUEST.payload`: {symbol, side, volume, magic, deviation, comment} — SEM credenciais, login, server.
   - `EXECUTION_FILLED.payload`: {ticket, price, retcode, message}
   - `EXECUTION_REJECTED.payload`: {retcode, message}
   - `CLOSE_FAILED.payload`: {ticket, retcode, message}
3. SIGNAL=BUY_WIN/SELL_WIN emitido UMA vez por tentativa real de entrada (no caminho que executa abertura). NÃO a cada poll.
4. SKIPPED/WAIT continua exclusivo do Slice B (server.py). Slice C foca apenas no caminho real de execução.
5. EXIT events distinguem claramente: TARGET, STOP_LOSS, BE_STOP, FORCE_CLOSE (sucesso) e CLOSE_FAILED (falha de envio MT5).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- `TradeEngine` agora inicializa `execution_timeline` para uso isolado em teste/worker e emite eventos com escrita tolerante a falha.
- Entradas reais emitem `SIGNAL` (`BUY_WIN`/`SELL_WIN`) em paper e live; live também emite `ORDER_REQUEST` e `EXECUTION_FILLED`/`EXECUTION_REJECTED`.
- Saídas emitem `EXIT` para `TARGET`, `STOP_LOSS`, `BE_STOP`, `FORCE_CLOSE`; falha de fechamento live emite também `CLOSE_FAILED`.
- `server.py` passa `closed_bar_ts` para `evaluate()`, mantendo eventos de entrada/saída ligados à barra M5 quando aplicável.
- Verificação focada: `PYTHONPATH=/tmp/codex-pytest python3 -m pytest tests/test_trade_engine.py tests/test_trade_engine_live.py tests/test_mt5_client.py -q` → 65 passed.
<!-- SECTION:NOTES:END -->
