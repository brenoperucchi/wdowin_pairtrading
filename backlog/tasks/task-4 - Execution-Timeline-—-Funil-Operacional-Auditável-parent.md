---
id: TASK-4
title: Execution Timeline — Funil Operacional Auditável (parent)
status: In Progress
assignee: []
created_date: '2026-05-08 18:52'
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
- [ ] #4 Trade real registra SIGNAL→ORDER_REQUEST→EXECUTION_FILLED/REJECTED→EXIT(target/SL/BE/force/CLOSE_FAILED) com `attempt_id` e/ou `trade_id`
- [ ] #5 Painel `ExecutionTimelinePanel` aparece entre `RegimeHealthPanel` e `PerformancePanel`, mostra gargalo atual + lista filtrável
- [x] #6 `pytest tests/ -q` verde com testes de schema, dedupe, distance/ratio, bottleneck e live issue
- [ ] #7 `npm run lint && npm run build` em `regime-dashboard/` verde
<!-- AC:END -->
