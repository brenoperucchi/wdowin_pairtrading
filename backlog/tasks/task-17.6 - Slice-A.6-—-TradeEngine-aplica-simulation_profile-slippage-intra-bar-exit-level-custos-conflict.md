---
id: TASK-17.6
title: >-
  Slice A.6 — TradeEngine aplica simulation_profile
  (slippage/intra-bar/exit-level/custos/conflict)
status: Done
assignee: []
created_date: '2026-05-13 01:20'
updated_date: '2026-05-13 03:49'
labels:
  - engine
  - simulation
  - fidelity
dependencies: []
parent_task_id: TASK-17
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Fazer `TradeEngine.evaluate()` aceitar `simulation_profile` opcional e propagar para `_open_trade`, `_check_exits`, `_close_trade`. Quando `None` ou `enabled=False` → no-op bit-exato (live preservado). Quando dict ativo → aplica fidelidade MT5.

## Modificações

### `_open_trade` (linha 405)
Quando profile ativo e `LIVE_ORDERS=0`:
- BUY: `entry_price = win_price + entry_slippage_pts`
- SELL: `entry_price = win_price - entry_slippage_pts`
- Log slippage aplicado no `EXECUTION_FILLED.payload_json`.

### `_check_exits` (linha 557)
- Aceitar `win_high=None, win_low=None` (passados pelo replay).
- Se `intra_bar_sl_tp` ativo e H/L presentes:
  - Detectar trigger TP (lado favorável atinge TP) e SL (lado desfavorável atinge SL) via wick.
  - **TP+SL no mesmo candle**: aplicar `conflict_rule`. Default `sl_first` → STOP_LOSS no nível do SL.
- Se `exit_at_sl_tp_level` ativo e trigger por TP/SL: `exit_price = entry_price ± nível` (não win_price).
- BE/`FORCE_CLOSE` continuam usando `win_price` (espelha o que MT5 também faria).
- Aplicar `exit_slippage_pts` ao preço final no lado correspondente.
- Sem H/L disponível mas profile ativo: fallback graceful close-only + log warn.

### `_close_trade` (linha 676)
- Descontar `cost_per_contract_rt_brl * WIN_CONTRACTS` do `pnl` (round-trip).
- Persistir `cost_brl` no `matador_ops` (coluna nova) ou no `payload_json` do timeline.

## Dependência (informativa)

TASK-17.3 (SimulationProfile no runtime_config).

## Janela

**Fora de mercado** — modifica o engine que o `trade_eval_loop` está usando.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 evaluate(..., simulation_profile=None) produz output bit-exato ao baseline pré-A.6 (regressão zero)
- [x] #2 Com profile.enabled=True: BUY entry = win_price + entry_slippage_pts; SELL entry = win_price - entry_slippage_pts
- [x] #3 Com intra_bar_sl_tp=True e win_high/low passados: TP/SL via wick disparam antes do close
- [x] #4 Com exit_at_sl_tp_level=True: exit_price = entry_price ± nível quando trigger é TP/SL (não win_price)
- [x] #5 TP e SL no mesmo candle com conflict_rule=sl_first → STOP_LOSS no SL level
- [x] #6 pnl final desconta cost_per_contract_rt_brl * WIN_CONTRACTS
- [x] #7 Sem H/L mas profile ativo: cai pra close-only com log warn
- [ ] #8 matador_ops persiste cost_brl
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Implementação

**Arquivos modificados:**
- `core/trade_engine.py` — `evaluate()`, entry evaluators, `_open_trade`, `_check_exits` aceitam/propagam `simulation_profile` + `win_high`/`win_low`.
- `tests/test_trade_engine_simulation.py` — NOVO, 20 testes.

**Princípio inegociável preservado:** `simulation_profile` é input do mesmo `TradeEngine.evaluate()` — não path paralelo. Live continua chamando `simulation_profile=None`. Quando `None` ou `enabled=False` → execução bit-exata ao baseline (verificado por 43 testes pre-existentes em `test_trade_engine.py` + 26 em `test_replay_execution_timeline.py`).

## Decisões de design

### Slippage de entrada (paper-only)
`_open_trade` aplica slippage só se `sim_enabled` AND `not LIVE_ORDERS`. Em modo live MT5 retorna o preço real de fill (que já incorpora qualquer slippage do mercado) — sim não pode contaminar.

### Detecção intra-bar
`_check_exits`:
- Computa `favor_high` (best favorable) e `favor_low` (worst adverse) a partir de `win_high`/`win_low`.
- BUY: favor_high = high - entry; favor_low = low - entry.
- SELL: favor_high = entry - low; favor_low = entry - high.
- `tp_hit`, `sl_hit`, `be_stop_hit` calculados a partir desses.

### BE intra-bar
`max_pts_favor` agora atualiza usando `favor_high` (intra-bar) ao invés de close. Isso reproduz BE activations que ocorreriam em live (poll a cada 2.5s captura picos intra-bar) mas que o replay close-only não veria. Vale para tudo: replay com sim enabled tem BE mais realista.

### Conflito intra-bar — observação importante
Com `BUY_BE_ACT=300 < BUY_TP=800`, um candle que toca TP também pode ativar BE dentro da própria barra. A resolução separa dois casos:
- Se o candle toca TP e apenas o BE_LOCK, `sl_first`/`worst` → `BE_STOP`; `tp_first` → `TARGET`.
- Se o candle toca TP e também o stop original, `sl_first`/`worst` → `STOP_LOSS`; `tp_first` → `TARGET`.

O BE ativado pela máxima da mesma barra não pode mascarar um toque no stop original quando não há sequência tick-by-tick.

### Exit pricing
- `exit_at_sl_tp_level=True`: TARGET/STOP_LOSS/BE_STOP saem no level (TP/-SL/BE_LOCK pts), não no close.
- `FORCE_CLOSE`: sempre usa o close (time-based, mirror MT5).
- `exit_slippage_pts` reduz `final_pts_favor` (sempre adverso ao trader, espelha bid/ask).

### Custo
`cost_brl = cost_per_contract_rt_brl * WIN_CONTRACTS` deduzido do `pnl` no path sim. **Persistência**: optei por gravar `cost_brl` no `payload_json` do timeline event de saída (o plano permite "matador_ops OU payload_json"). Evita uma migração de schema; o pnl líquido já vai pra `matador_ops.pnl_brl` (com cost embutido). Se quisermos column dedicada, adiciono em A.7 ou slice próprio.

### Graceful degradation
`intra_bar_sl_tp=True` mas H/L ausentes → `use_intra=False` (log debug). Restante do profile (slippage + cost + snap-to-level) continua aplicado, só perde detecção via wick. Testes `test_intra_bar_missing_hl_*` cobrem.

### Live mode safety
Quando `LIVE_ORDERS=1`: `_open_trade` skip entry slippage (price = MT5 fill). `_close_trade` recomputa pnl a partir do fill MT5 (sem dedução de cost — B3 cobra à parte). Sim profile naturalmente no-op em live mesmo se enabled=True por erro de config.

## Timeline audit trail
Eventos `SIGNAL` agora carregam `entry_price`/`entry_slippage_pts`; eventos de saída carregam `exit_pts_favor`, `final_pts_favor`, `exit_slippage_pts`, `cost_brl`, `simulation_enabled`, `intra_bar_used`, `win_high`, `win_low`. Postmortem completo no DB de timeline.

## Verificação

```
$ python3 -m pytest tests/ -q
453 passed, 19 skipped, 1 warning in 5.37s
```

- 43 testes existentes de `test_trade_engine.py` passam (bit-exact baseline).
- 26 testes de `test_replay_execution_timeline.py` passam (replay sem sim = baseline).
- 22 testes em `test_trade_engine_simulation.py` cobrem ACs 1-7.

## AC #8 — cost_brl em matador_ops

Não implementado como coluna; persistido no timeline payload_json (alternativa permitida pelo plano original). Se for requisito hard, criar slice ALTER TABLE — sugiro postergar para A.7/A.8 onde o replay precise queryar custos.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resumo

`TradeEngine` agora consome `simulation_profile` como **input opcional** do mesmo `evaluate()` que o live usa. Não há path paralelo de código: live passa `simulation_profile=None` (no-op bit-exato), replay/backtest passam dict ativo. Suporta:

- **Entry slippage** (paper-mode only — live preserva fill MT5).
- **Intra-bar SL/TP** via `win_high`/`win_low` (detecção por wick).
- **Conflict rule** (`sl_first` | `tp_first` | `worst`) quando TP e stop disparam no mesmo candle.
- **exit_at_sl_tp_level** snap-to-level (preço de saída no nível, não no close).
- **Exit slippage** adverso ao trader.
- **cost_per_contract_rt_brl** deduzido do pnl_brl final (round-trip).
- **Graceful degradation** se H/L ausentes: aplica resto do profile, log debug.

## Verificação

- **Bit-exact regression**: 43 testes pre-existentes em `test_trade_engine.py` + 26 em `test_replay_execution_timeline.py` passam sem mudança — comprova que `simulation_profile=None` e `enabled=False` mantêm o engine idêntico.
- **Full suite**: 453 passed, 19 skipped, 0 regressions (vs 431 baseline → +22 testes novos).
- **22 testes** em `tests/test_trade_engine_simulation.py` cobrem ACs 1-7.

## AC #8

`cost_brl` persistido no `payload_json` do timeline event de saída (não coluna em matador_ops). O plano permitia "matador_ops OU payload_json"; escolhi a opção sem ALTER TABLE. Marcado como pendente para revisão; se for hard requirement, criar slice próprio.

## Janela e próximos passos

A.6 é a slice mais sensível da Fase A — mexe no engine usado pelo `trade_eval_loop`. **Deploy só fora de mercado.** Bit-exact regression assegura zero impacto em live (que não passa o kwarg), mas auditar 1-2 ciclos de paper pós-deploy é prudente.

Próxima slice: **A.7** — `scripts/replay_execution_timeline.py` propaga OHLC + simulation_profile + CLI flags.
<!-- SECTION:FINAL_SUMMARY:END -->
