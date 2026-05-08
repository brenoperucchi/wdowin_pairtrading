---
id: TASK-4.4
title: Slice D — Frontend ExecutionTimelinePanel + integração no App.jsx
status: To Do
assignee: []
created_date: '2026-05-08 18:54'
labels:
  - timeline
  - slice-d
  - frontend
dependencies:
  - TASK-4.3
references:
  - /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md
  - regime-dashboard/src/components/PerformancePanel.jsx
  - 'regime-dashboard/src/App.jsx:678-693'
parent_task_id: TASK-4
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Painel React para consumir `/api/execution-timeline`, mostrar `current_bottleneck` (ou `current_live_issue` se sem barra) com value/threshold/distance/ratio, e listar eventos cronologicamente com filtros.

**Arquivos**
- Novo: `regime-dashboard/src/components/ExecutionTimelinePanel.jsx`
- Modificado: `regime-dashboard/src/App.jsx:678-693` (inserir o painel entre `RegimeHealthPanel` e `PerformancePanel`)

**Comportamento**
- Polling próprio a `POLL_MS=2500` (mesmo padrão do App)
- Summary section (topo): "Gargalo atual" com phase, event, strategy, value vs threshold, distance, ratio. Se `current_bottleneck` é null, mostrar "Funil OK na última barra fechada"; se houver `current_live_issue`, mostrar destacado em vermelho.
- Tabela: timestamp, phase, event, status, strategy, symbol, value/threshold (ou message), correlation_id curto (8 chars). Linhas BLOCKED/FAILED em vermelho, OK em verde, INFO/SKIPPED neutras.
- Filtros: phase (dropdown 8 fases + "all"), status (OK/BLOCKED/SKIPPED/FAILED/INFO/all), strategy (CONS_BASE/WDO_NWE/DI_NWE/all), event (texto livre).
- Estilo: inline `style={{}}` + dark theme, padrão de `PerformancePanel.jsx`.

**Verificação**
- `npm run lint` verde
- `npm run build` verde
- Manual: rodar `npm run dev` em :5174, conferir polling no console, filtrar por `phase=ELIGIBILITY status=BLOCKED` e ver `EG_NOT_COINTEGRATED` listado quando o gate bloqueia
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `ExecutionTimelinePanel.jsx` faz polling em `POLL_MS=2500` no `/api/execution-timeline`
- [ ] #2 Summary mostra `current_bottleneck` com value/threshold/distance/ratio, ou `current_live_issue`, ou "Funil OK"
- [ ] #3 Tabela cronológica colorida por status; filtros funcionais (phase, status, strategy, event)
- [ ] #4 Painel inserido entre `RegimeHealthPanel` e `PerformancePanel` no `App.jsx`
- [ ] #5 `npm run lint` verde no `regime-dashboard/`
- [ ] #6 `npm run build` verde no `regime-dashboard/`
<!-- AC:END -->
