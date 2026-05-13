---
id: TASK-17.8
title: >-
  Slice A.8 — Tests end-to-end de fidelidade
  (tests/test_replay_simulation_fidelity.py)
status: To Do
assignee: []
created_date: '2026-05-13 01:21'
labels:
  - tests
  - fidelity
dependencies: []
parent_task_id: TASK-17
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Novo arquivo de teste end-to-end cobrindo todos os cenários de fidelidade MT5 introduzidos por A.5 + A.6 + A.7.

## Casos

1. **Slippage entrada/saída**: BUY com `entry_slippage_pts=5, exit_slippage_pts=5` → entrada em `close+5`, saída em `nivel-5`.
2. **Exit at SL level**: BUY com SL=60, bar com low ≤ entry-60 e close > entry-60 → exit em `entry-60`, não no close.
3. **Intra-bar TP via wick**: BUY com TP=80, bar.high ≥ entry+80, close < entry+80 → exit em `entry+80` no mesmo bar.
4. **TP+SL no mesmo candle (sl_first)**: bar onde high e low cruzam ambos → STOP_LOSS no SL level. Caso simétrico para `tp_first`.
5. **Custo round-trip**: `pnl_brl` desconta `cost_per_contract_rt_brl * WIN_CONTRACTS`.
6. **No-op com enabled=False**: bit-exato à baseline (regressão zero).
7. **OHLC ausente + intra_bar_sl_tp=True**: graceful degradation + log warn no timeline.

## Reusos

Estender `_seed_bar` / `_seed_bar_sequence` em `tests/test_replay_execution_timeline.py` para aceitar `win_high`/`win_low` opcionais.

## Dependência (informativa)

A.7. Safe durante mercado.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 7 cenários cobertos com fixtures determinísticas
- [ ] #2 Cada cenário asserts: action, exit_reason, entry_price, exit_price, pnl_brl
- [ ] #3 Cenário 6 (no-op) compara summary dict bit-a-bit com baseline gravado
- [ ] #4 Tests passam em CI sem MT5 (mock como em test_replay_execution_timeline.py)
<!-- AC:END -->
