---
id: TASK-11.4
title: >-
  [Slice D] Live engine hot-reload of runtime profile (eg_threshold/bars/recalc,
  rho, beta)
status: Done
assignee: []
created_date: '2026-05-11 01:26'
updated_date: '2026-05-11 01:41'
labels:
  - live
  - config
  - risk-gate
dependencies: []
references:
  - 'server.py:1067-1100'
  - 'core/risk_gate.py:168'
  - core/runtime_config.py
  - 'scripts/replay_execution_timeline.py:213-232'
parent_task_id: TASK-11
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Plumb os 5 campos do perfil **live** (`runtime_config.get_profile("live")`) no live engine de `server.py` para que um POST em `/api/runtime-config` aplique no próximo poll, sem restart.

## Estado atual (após Slice C)

- Slice A: load/save + endpoints prontos.
- Slice B: replay já consome todos os 5 campos via CLI/config.
- Slice C: live já lê `eg_strategies` por poll (`server.py:1097-1100`) — os outros 4 campos ainda usam constantes de `core/risk_gate.py` e `core/config.py`.

Faltam:
- `eg_threshold` → passar para `risk_gate(eg_threshold=...)` (já é kwarg opcional).
- `rho_breakdown_level` → idem.
- `beta_delta_max` → idem.
- `eg_bars` → fatiar `eg_input_a/eg_input_b` antes de chamar `compute_engle_granger_pvalue`.
- `eg_recalc` → quando `daily`, reusar pvalue para o resto do dia (cache por `date_str`).

## Risco

Sem isso, qualquer mudança no slideover do operador é silenciosamente ignorada para os parâmetros mais importantes (threshold do EG, profundidade da janela). O Slice C apenas movia o gate "rodar EG sim/não", não os limites em si.

## Não-escopo

- Frontend (slideover continua em TASK-11 AC #3/#4).
- Mudar `core/risk_gate.py` (já aceita os kwargs).
- Tocar replay (já completo no Slice B).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 live_profile (todos os 5 campos) é lido a cada poll antes de _build_gate em server.py
- [x] #2 _build_gate passa eg_threshold/rho_breakdown_level/beta_delta_max para risk_gate()
- [x] #3 eg_input_a/eg_input_b são fatiados para os últimos eg_bars antes de compute_engle_granger_pvalue
- [x] #4 Quando eg_recalc=='daily', pvalue é calculado uma vez por date_str e reusado nos polls seguintes
- [x] #5 Quando runtime_config está inválido (ValueError), live cai em DEFAULTS sem 500 — fallback já existente é estendido para incluir todos os campos
- [x] #6 Test: alterar eg_threshold via runtime_config muda gate.allowed no próximo poll (sem restart)
- [x] #7 Test: eg_recalc='daily' não recomputa coint() em bars subsequentes do mesmo dia
- [x] #8 Smoke: pytest verde + replay histórico continua funcionando
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resumo

Live engine agora consome todos os 5 campos de `runtime_config.get_profile("live")` por poll. Operador pode ajustar via POST `/api/runtime-config` e o próximo poll já reflete (sem restart).

## Mudanças

**`server.py`**
- Importa `copy` para fallback profundo em DEFAULTS.
- Novo módulo-level: `_live_eg_daily_cache` + `_live_eg_daily_lock` para cache pvalue por `date_str` quando `eg_recalc='daily'`.
- Novo helper `_compute_live_eg_pvalue(...)`: fatia `eg_input_a/eg_input_b` para os últimos `eg_bars` antes de chamar `compute_engle_granger_pvalue`; quando `eg_recalc=='daily'`, computa uma vez por dia. Resultados `None` (curta janela) não são cacheados — retentam no próximo bar.
- Helper `reset_live_eg_daily_cache()` para isolamento de testes.
- `regime_v2`: load de `live_profile` foi hoisted para **antes** do EG, com fallback `copy.deepcopy(DEFAULTS["live"])` quando o JSON está malformado (não 500).
- `_build_gate(...)`: passa `eg_threshold`, `rho_breakdown_level`, `beta_delta_max` do `live_profile` em todas as chamadas (pre + post evaluate). `risk_gate` já aceitava esses kwargs (Slice anterior).

**`tests/test_execution_timeline_server.py`** (+4 testes, 29 → 33)
- `test_compute_live_eg_pvalue_bar_mode_calls_through` — confirma que `eg_bars` fatia a entrada antes do coint.
- `test_compute_live_eg_pvalue_daily_caches_first_pvalue` — `daily` calcula uma vez por `date_str` e reusa nos polls seguintes; nova data dispara recompute.
- `test_compute_live_eg_pvalue_daily_does_not_cache_none` — pvalue None não é cacheado; um histórico curto consegue se "auto-curar" no próximo bar.
- `test_live_engine_falls_back_to_defaults_when_runtime_config_invalid` — runtime.json malformado não derruba o engine; fallback contém todos os FIELDS.

## Verificação

- `pytest tests/` → 295 passed (291 → 295).
- `python3 scripts/replay_execution_timeline.py --date 2026-05-08` → mesmo trade que pré-Slice D (SELL DI_NWE 10:15 → BE_STOP 10:35, pnl -34.0). Sem regressão.

## Não-escopo (continua aberto na TASK-11)

- AC #3/#4 do parent: slideover na UI (frontend).
- TASK-12: revalidar `beta_di` quando `bar_history` tiver >= 2240 bars de WIN+DI.

## Patch follow-up (review)

**Medium**: o cache diário agora usa chave `(date_str, eg_bars)` em vez de só `date_str`. Sem isso, mudar `eg_bars` via runtime durante o pregão não invalidava o pvalue cacheado — quebrava AC #7. Novo teste `test_compute_live_eg_pvalue_daily_invalidates_when_eg_bars_changes` cobre o caso.

**Verificação**: 296 passed (295 → 296 com o teste novo).

**Obs.**: outros 4 campos (`eg_threshold`, `rho_breakdown_level`, `beta_delta_max`, `eg_strategies`) já invalidam naturalmente porque são lidos diretamente do `live_profile` por poll (não passam pelo cache do EG).
<!-- SECTION:FINAL_SUMMARY:END -->
