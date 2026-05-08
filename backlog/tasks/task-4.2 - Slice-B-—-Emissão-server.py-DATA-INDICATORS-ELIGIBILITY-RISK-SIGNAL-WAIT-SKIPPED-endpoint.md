---
id: TASK-4.2
title: >-
  Slice B — Emissão server.py (DATA/INDICATORS/ELIGIBILITY/RISK/SIGNAL
  WAIT-SKIPPED) + endpoint
status: Done
assignee: []
created_date: '2026-05-08 18:53'
updated_date: '2026-05-08 19:38'
labels:
  - timeline
  - slice-b
dependencies:
  - TASK-4.1
references:
  - /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md
  - 'server.py:606-790'
  - core/risk_gate.py
parent_task_id: TASK-4
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Conectar a Execution Timeline ao `regime_v2`: emitir eventos do funil somente quando há nova barra fechada, expor o endpoint `/api/execution-timeline`. Não toca `trade_engine.py` (Slice C cuida disso).

**Arquivos**
- Modificado: `server.py:606-790` (`regime_v2` + helpers + startup)
- Modificado: `tests/test_server_*.py` (ou novo `tests/test_execution_timeline_emit.py`)

**Pontos de inserção**
- Startup: chamar `init_timeline_table(DB_PATH)` perto do `TradeEngine(DB_PATH)` em server.py
- `regime_v2`: manter `_last_emitted_bar_ts` em closure/módulo. Só emitir funil quando `bar_close_confirmed` for True E `closed_bar_ts != _last_emitted_bar_ts`.
- DATA failures (MT5 desconectado, fetch_bars falhou) com dedupe por janela curta (minuto) ou por transição de estado — não usar uuid em loop.
- INDICATORS_OK com payload `{closed_bar_ts, z_wdo, z_di, rho, beta_delta_pct, eg_pvalue, joh_open, live_orders_enabled, mt5_connected}`.
- ELIGIBILITY: um evento por reason do gate (`risk_gate.reasons`), exceto `BAR_NOT_CLOSED` (que fica no `/api/v2/regime`). Reusar `core.risk_gate.WITHIN_POLL_OP_REASONS` para classificar severity.
- RISK: um evento por reason operacional (`MAX_TRADES_REACHED`, `DAILY_LOSS_LIMIT`, `LOSS_COOLDOWN`).
- SIGNAL WAIT/SKIPPED: por estratégia, somente nesse contexto de barra fechada, usando o resultado do `TradeEngine.evaluate()` retornado.

**Endpoint** `GET /api/execution-timeline`:
- Query params: `limit=200, phase=, status=, strategy=, event=, since=` (passados ao `load_timeline`)
- Resposta: `{events: [...], summary: {current_bottleneck, current_live_issue}}`

**Testes**:
- Cache hit não duplica funil (mesma `closed_bar_ts` chamada 2x → 1 conjunto de eventos)
- ELIGIBILITY emite uma row por reason (ex.: `EG_NOT_COINTEGRATED` com `value=eg_pvalue`, `threshold=0.10`, `operator="<"`, distance positiva quando acima do limite)
- Endpoint retorna 200 com summary, filtros funcionam
- `BAR_NOT_CLOSED` não aparece como evento ELIGIBILITY
- DATA failure repetido em polls consecutivos não vira N rows
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `init_timeline_table(DB_PATH)` chamado no startup do server
- [x] #2 `regime_v2` mantém `_last_emitted_bar_ts` e só emite funil em barra fechada nova
- [x] #3 DATA failure usa dedupe por janela ou transição de estado (sem uuid em loop)
- [x] #4 INDICATORS_OK emitido com payload completo conforme plano
- [x] #5 ELIGIBILITY emite uma row por reason exceto `BAR_NOT_CLOSED`; severity classificado via `WITHIN_POLL_OP_REASONS`
- [x] #6 RISK emite uma row por reason operacional
- [x] #7 SIGNAL WAIT/SKIPPED emitido por estratégia somente quando barra fecha
- [x] #8 Endpoint `GET /api/execution-timeline` aceita filtros e retorna `{events, summary}`
- [x] #9 Testes integrados via TestClient verdes; total continua passando
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Slice B entregue:

- `server.py` agora define `DB_PATH`, inicializa `execution_timeline` no startup/import e expõe `GET /api/execution-timeline`.
- `regime_v2` registra DATA failures (`MT5_DISCONNECTED`, `BARS_FETCH_FAILED`) com dedupe por minuto e registra recuperação DATA quando o processo volta de uma falha conhecida.
- A timeline de barra fechada é emitida apenas quando `bar_close_confirmed=True` e `closed_bar_ts` ainda não foi emitido. `BAR_NOT_CLOSED` fica fora da timeline persistente.
- `INDICATORS_OK` carrega payload rico (`z_wdo`, `z_di`, `rho`, `rho_level`, `beta_delta_pct`, `eg_pvalue`, `joh_open`, `live_orders_enabled`, `mt5_connected`).
- ELIGIBILITY/RISK geram uma linha por reason, com metric/threshold/operator quando conhecido. EG usa `operator="<"` e distance positiva quando `eg_pvalue` está acima de `0.10`.
- SIGNAL `WAIT`/`SKIPPED` é emitido por estratégia somente no contexto de barra fechada. `TradeEngine` ainda não emite SIGNAL real/ORDER/EXECUTION/EXIT; isso fica para TASK-4.3.
- `tests/test_execution_timeline_server.py` adiciona 4 testes cobrindo DATA dedupe, emissão de reasons sem `BAR_NOT_CLOSED`, dedupe por closed bar e endpoint com filtros/summary.

`PYTHONPATH=/tmp/codex-pytest python3 -m pytest tests/ -q` → 169 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice B fechado em commit `372b20d` (feat(task-4): emit execution timeline from server). Codex confirmou veredito "good to close". 169 testes passando. Funil por barra fechada emite DATA failures (com dedupe minute-key + transição), INDICATORS_OK com payload completo, ELIGIBILITY/RISK por reason (operator=requisito de pass, distance>0=blocked) e SIGNAL WAIT/SKIPPED por estratégia. Endpoint `/api/execution-timeline` retorna events + summary {current_bottleneck, current_live_issue}. Verificado em runtime LIVE_ORDERS=1 com gate bloqueado por BAR_NOT_CLOSED + OUT_OF_SESSION + EG_NOT_COINTEGRATED.
<!-- SECTION:FINAL_SUMMARY:END -->
