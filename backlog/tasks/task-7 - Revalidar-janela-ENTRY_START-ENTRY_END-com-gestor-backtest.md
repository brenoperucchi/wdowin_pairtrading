---
id: TASK-7
title: Revalidar janela ENTRY_START/ENTRY_END com gestor + backtest
status: To Do
assignee: []
created_date: '2026-05-09 06:55'
labels:
  - product
  - config
dependencies: []
references:
  - 'core/config.py:114-119'
  - 'core/risk_gate.py:96-102'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A janela atual de entradas é `09:00 – 15:00 BRT` (`ENTRY_START_H/M`, `ENTRY_END_H/M`), com `FORCE_CLOSE 17:40`.

Pregão WIN B3 vai até **17:55 BRT (regular)** ou **17:25 BRT (DST)**. Cortar entradas em 15:00 deixa **2h25min–2h55min** sem novas posições — buffer prudente para mean-reversion antes do force-close, mas pode estar deixando setups bons em cima da mesa entre 15:00–16:30.

**Decisão a tomar (com gestor + backtest):**
1. Manter 15:00 (status quo, conservador)
2. Estender para 16:00 ou 16:30 (mais setups, menor margem para reverter antes do force-close)
3. Janela dinâmica baseada em DST/horário de pregão atual

**Pré-requisito:** rodar backtest comparando PnL/sharpe/drawdown nas 3 hipóteses sobre histórico recente (≥3 meses). Não mexer em produção sem essa validação.

**Why:** parâmetro de produto/risk com impacto direto em frequência de trades. Documentar a decisão (incluindo o "por que 15:00" original, se conhecido) para evitar reincidência da pergunta.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Backtest comparativo das janelas 15:00 / 16:00 / 16:30 sobre histórico ≥3 meses (PnL, sharpe, drawdown, número de trades)
- [ ] #2 Decisão registrada em CLAUDE.md ou doc dedicada — incluindo motivo da janela escolhida
- [ ] #3 Se mudar: ajuste em `core/config.py` + atualização de testes que usem ENTRY_END_H
<!-- AC:END -->
