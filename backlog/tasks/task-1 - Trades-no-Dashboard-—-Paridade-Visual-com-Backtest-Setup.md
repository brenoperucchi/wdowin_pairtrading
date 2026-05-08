---
id: TASK-1
title: Trades no Dashboard — Paridade Visual com Backtest/Setup
status: In Progress
assignee: []
created_date: '2026-05-06 17:57'
updated_date: '2026-05-06 22:38'
labels:
  - feature
  - dashboard
  - backend
  - frontend
milestone: Trades no Dashboard
dependencies: []
references:
  - docs/plans/o-gestor-me-passou-purrfect-platypus.md
  - core/trade_engine.py
  - server.py
  - regime-dashboard/src/App.jsx
  - regime-dashboard/src/components/SignalHistogram.jsx
  - regime-dashboard/src/components/ZScoreChart.jsx
  - regime-dashboard/src/components/IndexChart.jsx
  - tests/test_trade_engine.py
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

O gestor solicitou "equalizar o setup/backtest com histograma com trades mostrados no dashboard". Hoje os trades (entradas e saídas) existem no SQLite (tabela `matador_ops`) mas aparecem **apenas** na tabela do `PerformancePanel`. Os scripts de backtest (`equity_curve.py`, `backtest.py`) mostram trades sobrepostos nos gráficos — o dashboard ao vivo deve replicar essa experiência.

## Objetivo

Plotar marcadores de entrada e saída dos trades diretamente nos gráficos do dashboard:
- **SignalHistogram** (prioridade 1 — pedido principal)
- **ZScoreChart** (prioridade 2)
- **IndexChart** (prioridade 3)

## Decisões Arquiteturais

- Fonte oficial dos trades para plotagem: `matador_ops` via novo endpoint `trades_today` no `/api/v2/regime`
- `/api/performance` continua exclusivo do `PerformancePanel` (não misturar responsabilidades)
- Sem dependência nova no frontend — usar Recharts (`ReferenceDot`) já instalado
- Schema SQLite sem alterações
- Marcadores históricos (dias anteriores) fora da v1
- Trades OPEN (posição em aberto) mostram entrada mas sem saída

## Estrutura das Subtasks

1. Fase 0 — Corrigir testes existentes da TradeEngine (pré-requisito)
2. Fase 1 — Backend: `get_trades_for_date()` + `trades_today` na API + testes
3. Fase 2 — Frontend: state `todayTrades` + helper de alinhamento M5
4. Fase 3a — Frontend: marcadores no SignalHistogram
5. Fase 3b — Frontend: marcadores no ZScoreChart e IndexChart

## Verificação Final

- `pytest tests/ -v` — zero falhas
- `npm run lint && npm run build` — zero erros
- Dashboard localhost:5174 com marcadores visíveis nos 3 gráficos
- Trade aberto mostra entrada sem saída; trade fechado mostra ambos
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 GET /api/v2/regime retorna campo trades_today (array, vazio fora do pregão)
- [ ] #2 Marcadores de entrada (▲ BUY / ▼ SELL) aparecem no SignalHistogram na barra M5 correta
- [ ] #3 Marcadores de saída (■) aparecem no SignalHistogram com cor da estratégia correspondente
- [ ] #4 Dots de entrada visíveis no ZScoreChart na posição (bar_time, z_in)
- [ ] #5 Marcadores de entrada/saída visíveis no IndexChart nas posições de preço corretas
- [ ] #6 Hover nos marcadores exibe tooltip: estratégia, direção, z_in, exit_reason, pnl_brl
- [ ] #7 Trade OPEN mostra entrada mas não saída
- [ ] #8 Todos os testes existentes continuam passando (nenhuma regressão)
- [ ] #9 npm run lint e npm run build sem erros
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-05-06 — Evidência de atendimento parcial/majoritário ao pedido do gestor: backend já expõe `trades_today` a partir de `matador_ops` via `core/trade_engine.py:get_trades_for_date()` e `/api/v2/regime`; `App.jsx` já mantém `todayTrades`, alinha trades ao `paddedSignals`/M5 e passa `trades` para `SignalHistogram`, `ZScoreChart` e `IndexChart`; `SignalHistogram` renderiza entrada `▲/▼`, saída `■`, cor por estratégia e tooltip nativo; `ZScoreChart` e `IndexChart` renderizam dots de entrada/saída. Ajustes recentes limparam `todayTrades` em fallback/erro e empilharam marcadores no histograma para evitar sobreposição no mesmo candle. Status mantido como não concluído porque ainda falta validação visual ponta a ponta com dashboard/trades reais, `npm run lint` geral permanece falhando por débitos existentes, e testes Python não foram executados neste ambiente por ausência de `pytest`. `npm run build` passou e `npx eslint src/components/SignalHistogram.jsx` passou.
<!-- SECTION:NOTES:END -->
