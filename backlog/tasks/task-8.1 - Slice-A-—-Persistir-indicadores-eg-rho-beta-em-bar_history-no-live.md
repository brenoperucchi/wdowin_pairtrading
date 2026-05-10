---
id: TASK-8.1
title: Slice A — Persistir indicadores (eg/rho/beta) em bar_history no live
status: In Progress
assignee: []
created_date: '2026-05-09 17:13'
updated_date: '2026-05-09 17:14'
labels:
  - execution-timeline
  - replay
  - schema-migration
  - backend
dependencies: []
references:
  - server.py
  - core/signals.py
  - core/risk_gate.py
parent_task_id: TASK-8
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Pré-requisito de paridade live↔replay. Hoje `bar_history` só tem `z_wdo, z_di, win/wdo/di_price, NWE`. Para que o replay rode `risk_gate()` com os mesmos valores que o live decidiu naquela barra, precisamos persistir também: `eg_pvalue`, `rho`, `rho_level`, `beta_value`, `beta_delta_pct`.

Sem este slice, AC #9 e #10 da TASK-8 não fecham.

Escopo:
- Migration idempotente (`ALTER TABLE bar_history ADD COLUMN ... DEFAULT NULL`) executada no boot do `server.py`, igual padrão atual.
- `save_bar_history(...)` aceita os 5 novos kwargs (todos opcionais, default None) e grava com COALESCE para preservar valores não-None vindos de upserts.
- Em `_persist_closed_bars(history, ...)` e em `regime_v2()`, propagar os valores computados naquela poll (rho, beta_value, beta_delta_pct, eg_pvalue, rho_level) para dentro dos entries de history antes da persistência.
- Não-objetivo: backfill histórico. Barras anteriores ficam NULL e o replay desses dias gera `MISSING_*` (Slice B).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Migration idempotente adiciona colunas `eg_pvalue REAL`, `rho REAL`, `rho_level INTEGER`, `beta_value REAL`, `beta_delta_pct REAL` em `bar_history` no boot do servidor; rodar 2x sem erro.
- [ ] #2 `save_bar_history()` aceita os 5 novos kwargs opcionais e grava com COALESCE (não sobrescreve valor não-NULL existente com NULL).
- [ ] #3 `_persist_closed_bars()` propaga os valores computados na poll para os 5 novos campos quando disponíveis; mantém comportamento atual quando ausentes.
- [ ] #4 `regime_v2()` (ou helper de persistência chamado por ele) anexa `eg_pvalue/rho/rho_level/beta_value/beta_delta_pct` aos entries de history antes da chamada a `_persist_closed_bars`.
- [ ] #5 Teste pytest novo em `tests/test_bar_history.py` cobre: schema possui as 5 colunas novas; salvar com valores e recuperar via `load_bar_history` preserva os valores; salvar com kwargs ausentes mantém o valor antigo (COALESCE).
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `py.exe -3.12 -m pytest tests/test_bar_history.py -q` passa.
- [ ] #2 `py.exe -3.12 -m pytest tests/ -q` não regride.
- [ ] #3 Inspecionar manualmente: subir o servidor, deixar uma barra fechar, conferir via SQL que pelo menos 1 linha em `bar_history` tem `eg_pvalue/rho/beta_value` não-NULL.
<!-- DOD:END -->
