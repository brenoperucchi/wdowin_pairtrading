---
id: TASK-17.8
title: >-
  Slice A.8 — Tests end-to-end de fidelidade
  (tests/test_replay_simulation_fidelity.py)
status: Done
assignee: []
created_date: '2026-05-13 01:21'
updated_date: '2026-05-13 04:14'
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
- [x] #1 7 cenários cobertos com fixtures determinísticas
- [x] #2 Cada cenário asserts: action, exit_reason, entry_price, exit_price, pnl_brl
- [x] #3 Cenário 6 (no-op) compara matador_ops bit-a-bit com baseline gravado
- [x] #4 Tests passam em CI sem MT5 (mock como em test_replay_execution_timeline.py)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resultado

Criado `tests/test_replay_simulation_fidelity.py` com **9 testes** (todos passing) cobrindo os 7 cenários de fidelidade MT5 em nível end-to-end através de `run_replay()` + `TradeEngine.evaluate()`.

### Testes implementados

| # | Teste | Cenário |
|---|-------|---------|
| 1 | `test_buy_entry_and_exit_slippage_lands_in_matador_ops` | Entry + exit slippage 5pt cada, cost=0 → entry=130005, exit=130800, pnl=318.0 |
| 2 | `test_intra_bar_sl_exits_at_level_not_at_close` | low=129700 (wick) hits SL=300 mas close=130000 recovers → exit em 129700, pnl=-120 |
| 3 | `test_intra_bar_tp_from_wick_when_close_below_tp` | high=130850 (wick) > TP=800 mas close=130100 → TARGET em 130800 |
| 4 | `test_conflict_rule_sl_first_resolves_to_be_stop_when_tp_and_bestop_collide` | TP+BE_STOP no mesmo candle → BE_STOP (pnl=0) |
| 4b | `test_conflict_rule_tp_first_resolves_to_target_when_tp_and_bestop_collide` | Mesmo setup, `tp_first` → TARGET |
| 4c | `test_conflict_rule_sl_first_resolves_to_stop_loss_when_tp_and_raw_sl_collide` | TP+stop original no mesmo candle → STOP_LOSS no SL level |
| 5 | `test_cost_per_contract_rt_deducted_from_persisted_pnl` | cost_rt=1.0, WIN_CONTRACTS=2 → pnl = 320 - 2 = 318; payload.cost_brl=2.0 |
| 6 | `test_simulation_disabled_matches_baseline_trade_row_bit_exact` | Bit-exact matador_ops em 8 colunas: direction, strategy, exit_reason, prices, pnl_brl, max_pts_favor, be_active |
| 7 | `test_intra_bar_without_ohlc_emits_warning_event_and_continues` | OHLC ausente + intra_bar=True → emite `INTRA_BAR_DEGRADED` warning event, trade fecha via close-only fallback |

### Insight de calibração

Como `BUY_BE_ACT=300 < BUY_TP=800`, quando o wick atinge TP intra-bar também ativa BE no mesmo bar. Testes 4/4b cobrem o conflito TP vs BE_STOP. O teste 4c cobre explicitamente o caso mais adverso TP vs stop original, garantindo que `sl_first` não mascara `STOP_LOSS` como `BE_STOP`.

### Helpers reutilizados

- `_seed_bar(...)` aceita `win_high/win_low/win_open` opcionais (alinhado com `tests/test_replay_simulation_wiring.py`)
- `_seed_buy_entry` / `_seed_exit_bar` montam setup determinístico de BUY trigger
- `_sim_overrides(**kw)` constrói o dict de simulation explícito (default: enabled=True, slip/cost zero)

### Acceptance criteria

- ✅ AC1: 7 cenários cobertos (9 testes; conflito splittado em BE_STOP, tp_first e raw SL)
- ✅ AC2: cada teste asserta `direction/exit_reason/price_win_in/price_win_out/pnl_brl`
- ✅ AC3: cenário 6 compara matador_ops bit-a-bit em 8 colunas críticas
- ✅ AC4: sem MT5 (puramente bar_history SQLite + engine in-process)

### Regressão

Full suite: **473 passed, 19 skipped** (sem regressões).
<!-- SECTION:FINAL_SUMMARY:END -->
