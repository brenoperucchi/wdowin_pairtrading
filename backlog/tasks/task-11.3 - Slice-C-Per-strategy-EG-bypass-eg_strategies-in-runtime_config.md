---
id: TASK-11.3
title: '[Slice C] Per-strategy EG bypass (eg_strategies in runtime_config)'
status: Done
assignee: []
created_date: '2026-05-11 00:08'
updated_date: '2026-05-11 00:08'
labels:
  - risk-gate
  - trade-engine
  - config
  - replay
dependencies: []
parent_task_id: TASK-11
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replicar a divisão de Miqueias (server.py:608 vs :715): WIN/WDO endpoint checa Engle-Granger; DI endpoint **não checa** EG. Adicionar `eg_strategies` ao `runtime_config` e fazer `TradeEngine.evaluate()` filtrar `EG_NOT_COINTEGRATED`/`EG_UNAVAILABLE` por slot.

Default: `["CONS_BASE", "WDO_NWE"]` em ambos os perfis.

Inclui CLI `--eg-strategies "CONS_BASE,WDO_NWE"` (ou `none` pra bypass total) no replay.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 #1 runtime_config tem campo eg_strategies (lista, validada contra VALID_STRATEGIES, sem dup)
- [x] #2 #2 DEFAULTS dos dois perfis = ['CONS_BASE','WDO_NWE'] espelhando Miqueias
- [x] #3 #3 risk_gate.EG_REASONS expõe o conjunto {EG_NOT_COINTEGRATED, EG_UNAVAILABLE}
- [x] #4 #4 TradeEngine.evaluate(eg_strategies=...) filtra EG por slot; None = backward compatible
- [x] #5 #5 server.py passa runtime_config.get_profile('live')['eg_strategies'] em cada poll
- [x] #6 #6 replay_execution_timeline.py aceita --eg-strategies CSV ou 'none'; ReplayRuntimeProfile inclui o campo
- [x] #7 #7 emit_closed_bar_timeline usa per-strategy gate_reasons (slot que bypassou EG não mostra EG_* no SIGNAL)
- [x] #8 #8 Tests: validação eg_strategies, bypass por slot no engine, CLI/profile no replay, emissão per-strategy do timeline
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implementado: campo `eg_strategies` no `runtime_config`, filtro per-slot em `TradeEngine.evaluate(eg_strategies=...)`, CLI `--eg-strategies` no replay, e correção do `emit_closed_bar_timeline` pra usar per-strategy `gate_reasons` (slot que bypassou EG agora aparece como WAIT/INFO em vez de SKIPPED com EG falso).

**Arquivos tocados:**
- `core/runtime_config.py` — VALID_STRATEGIES, validação, DEFAULTS
- `config/runtime.json` — eg_strategies em ambos perfis
- `core/risk_gate.py` — `EG_REASONS = frozenset({"EG_NOT_COINTEGRATED","EG_UNAVAILABLE"})`
- `core/trade_engine.py` — parâmetro `eg_strategies` + filtro per-slot
- `core/timeline_emit.py` — usa `strat_result["gate_reasons"]` em vez do gate global
- `server.py` — `runtime_config.get_profile("live")["eg_strategies"]` por poll
- `scripts/replay_execution_timeline.py` — `ReplayRuntimeProfile.eg_strategies`, CLI `--eg-strategies`
- Tests: `test_runtime_config.py`, `test_trade_engine.py`, `test_replay_execution_timeline.py`, `test_execution_timeline_server.py`

**Smoke 2026-05-08:** confirmação visual no replay DB — em 10:00, CONS_BASE/WDO_NWE emitem `SIGNAL SKIPPED gate_reasons=["EG_NOT_COINTEGRATED"]`, DI_NWE emite `SIGNAL WAIT gate_reasons=[]` (bypass funcional). Trade não dispara porque z_di=-1.127 (negativo) — divergência de cálculo de Z entre nós e Miqueias é problema separado, fora do escopo desta slice.

**Suite:** 289 tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
