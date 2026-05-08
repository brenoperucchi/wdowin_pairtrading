---
id: TASK-4
title: Execution Timeline — Funil Operacional Auditável (parent)
status: Done
assignee: []
created_date: '2026-05-08 18:52'
updated_date: '2026-05-08 21:21'
labels:
  - timeline
  - observability
dependencies: []
references:
  - /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md
  - core/risk_gate.py
  - core/trade_engine.py
  - server.py
  - regime-dashboard/src/components/PerformancePanel.jsx
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Hoje, com `LIVE_ORDERS=1`, o gate retorna `BAR_NOT_CLOSED + EG_NOT_COINTEGRATED` (eg_pvalue=0.64) e o diagnóstico só é possível chamando `/api/v2/regime` direto. Não há histórico do que travou em cada barra/poll, nem auditoria sobre se a ordem MT5 foi tentada/falhou/preenchida.

A Execution Timeline é um funil persistente em `trades.db` com 8 fases (DATA, INDICATORS, ELIGIBILITY, RISK, SIGNAL, ORDER, EXECUTION, EXIT) registrando valor/threshold/distance por evento, expondo `/api/execution-timeline` e um painel `ExecutionTimelinePanel.jsx` que mostra o gargalo atual.

Plano completo em `/home/brenoperucchi/.claude/plans/stateful-toasting-pony.md`.

**Decisões-chave**
- Granularidade híbrida: funil por barra M5 fechada + eventos críticos a qualquer hora
- Emit owner: `server.py` emite funil/SIGNAL WAIT-SKIPPED na barra fechada; `trade_engine.py` emite tentativa/execução/saída
- `correlation_id` agrupa, `dedupe_key` (UNIQUE INDEX + INSERT OR IGNORE) é a única chave de idempotência
- ORDER/EXECUTION antes do insert em matador_ops usam `attempt_id`; depois usam `trade_id`
- Eventos críticos DATA usam dedupe por janela/transição de estado (não uuid em loop)
- WAL mode em `trades.db` para eliminar contenção
- `current_bottleneck` (última barra fechada) + `current_live_issue` (falhas críticas sem barra) separados no summary

**Ritual de revisão**: cada slice termina com pytest verde, commit isolado, e revisão antes de iniciar o próximo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Tabela `execution_timeline` no `trades.db` com índices, UNIQUE INDEX em `dedupe_key`, e WAL ligado
- [x] #2 Endpoint `GET /api/execution-timeline?limit=&phase=&status=&strategy=&event=&since=` retorna eventos + `summary.current_bottleneck` + `summary.current_live_issue`
- [x] #3 Funil por barra fechada cobre DATA failures, INDICATORS_OK (com payload rico), ELIGIBILITY/RISK reasons (sem `BAR_NOT_CLOSED`), SIGNAL WAIT-SKIPPED por estratégia
- [x] #4 Trade real registra SIGNAL→ORDER_REQUEST→EXECUTION_FILLED/REJECTED→EXIT(target/SL/BE/force/CLOSE_FAILED) com `attempt_id` e/ou `trade_id`
- [x] #5 Painel `ExecutionTimelinePanel` aparece entre `RegimeHealthPanel` e `PerformancePanel`, mostra gargalo atual + lista filtrável
- [x] #6 `pytest tests/ -q` verde com testes de schema, dedupe, distance/ratio, bottleneck e live issue
- [x] #7 `npm run lint && npm run build` em `regime-dashboard/` verde
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Execution Timeline entregue end-to-end em 5 slices.

**Slice A** (TASK-4.1) — `core/execution_timeline.py`: schema com UNIQUE INDEX em `dedupe_key`, `record_event` (INSERT OR IGNORE) calculando `distance`/`ratio_to_threshold` a partir de `value/threshold/operator`, `bulk_record_events`, `current_bottleneck` (última barra fechada, ordem de fase), `current_live_issue` (falhas críticas sem barra, com expiração). WAL ligado em `TradeEngine._init_db`.

**Slice B** (TASK-4.2) — `server.py`: `init_timeline_table` no startup, `_emit_closed_bar_timeline` emite DATA failures (rate-limit por minuto), INDICATORS_OK com payload rico, ELIGIBILITY/RISK por reason (sem `BAR_NOT_CLOSED`), SIGNAL WAIT/SKIPPED por estratégia. Endpoint `GET /api/execution-timeline?limit=&phase=&status=&strategy=&event=&since=` retorna eventos + summary.

**Slice C** (TASK-4.3) — `core/trade_engine.py`: `_open_trade` gera `attempt_id`, emite SIGNAL real (BUY_WIN/SELL_WIN), depois ORDER_REQUEST → EXECUTION_FILLED/REJECTED, transicionando `correlation_id` de `attempt:{uuid}` → `trade:{id}` após insert em `matador_ops`. `_check_exits`/close emitem TARGET/STOP_LOSS/BE_STOP/FORCE_CLOSE; CLOSE_FAILED com dedupe por minuto. Trigger event marca FAILED quando o close falha (ressalva pós-review fechada em `d61c1b0`).

**Slice D** (TASK-4.4) — `regime-dashboard/src/components/ExecutionTimelinePanel.jsx` com summary 3-estado (live_issue > bottleneck > FUNIL OK), filtros phase/status/strategy/event/limit, polling 2.5s, distance color-coded conforme contrato (`>0` = bloqueado, `<0` = margem). Inserido entre RegimeHealthPanel e PerformancePanel.

**Slice E** (TASK-4.5) — `templates/execution_timeline.html` + rota `GET /execution-timeline` (Jinja2) servindo página standalone com meta-refresh, para diagnóstico sem precisar do dashboard React. Adicionado `jinja2==3.1.4` ao `requirements.txt`.

**Verificação:**
- `pytest tests/ -q` verde com testes de schema, dedupe, distance/ratio, bottleneck, live issue, emissão server.py, emissão trade_engine.py, e renderização HTML.
- `npm run lint && npm run build` em `regime-dashboard/` verde.
- Backend deployado via `systemctl --user restart pairtrading-server`; `/api/execution-timeline` retorna estado real da sessão (gargalo atual: OUT_OF_SESSION/RHO_BREAKDOWN/EG_NOT_COINTEGRATED).

**Observabilidade ganha:** pela primeira vez é possível auditar barra-a-barra por que uma oportunidade não virou trade — qual fase travou, qual valor vs threshold, qual estratégia foi pulada, e (em LIVE) se a ordem MT5 saiu, foi rejeitada ou nem foi tentada.
<!-- SECTION:FINAL_SUMMARY:END -->
