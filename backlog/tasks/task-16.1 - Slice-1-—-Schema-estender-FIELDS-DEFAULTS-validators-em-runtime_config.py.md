---
id: TASK-16.1
title: 'Slice 1 — Schema: estender FIELDS/DEFAULTS/validators em runtime_config.py'
status: Done
assignee: []
created_date: '2026-05-12 19:37'
updated_date: '2026-05-13 04:29'
labels:
  - refactor
  - runtime-config
dependencies: []
parent_task_id: TASK-16
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Apenas `core/runtime_config.py` + `tests/test_runtime_config.py`. Não toca consumers. Safe durante mercado aberto (additive change, backfill em `_backfill_missing_fields` mantém configs legados funcionais).

## Novos campos por profile

| Campo | Tipo | Bounds | Default (live) |
|---|---|---|---|
| `window` | int | [30, 1000] | 240 |
| `z_entry` | float | (0.1, 5.0] | 1.4 |
| `entry_start_h` | int | [0, 23] | 9 |
| `entry_start_m` | int | [0, 59] | 0 |
| `entry_end_h` | int | [0, 23] | 17 |
| `entry_end_m` | int | [0, 59] | 0 |
| `force_close_h` | int | [0, 23] | 17 |
| `force_close_m` | int | [0, 59] | 40 |
| `buy_sl` | int | [10, 5000] | 300 |
| `buy_tp` | int | [10, 5000] | 800 |
| `buy_be_act` | int | [0, 5000] | 300 |
| `buy_be_lock` | int | [0, 5000] | 0 |
| `sell_sl` | int | [10, 5000] | 300 |
| `sell_tp` | int | [10, 5000] | 800 |
| `sell_be_act` | int | [0, 5000] | 300 |
| `sell_be_lock` | int | [0, 5000] | 0 |

Defaults espelhados em `replay` profile.

## Tarefas

1. Adicionar campos em `FIELDS` tuple.
2. Adicionar valores em `DEFAULTS["live"]` e `DEFAULTS["replay"]` (idênticos por enquanto).
3. Adicionar validators em `_validate_profile` com bounds + tipo.
4. Confirmar `_backfill_missing_fields` cobre os novos campos automaticamente (já faz pelo loop `for field in FIELDS`).
5. Atualizar docstring do módulo.
6. Testes em `tests/test_runtime_config.py`:
   - Backfill carrega config legado sem os novos campos e retorna com defaults.
   - POST inválido (ex: `window=10`, `entry_end_h=24`) levanta `ValueError` com mensagem.
   - Roundtrip save→load preserva os novos campos.

## Acceptance Criteria
<!-- AC:BEGIN -->
- AC1: `load_runtime_config()` com `runtime.json` atual (7 campos) retorna 23 campos por profile.
- AC2: Validator rejeita cada novo campo fora de bounds.
- AC3: `pytest tests/test_runtime_config.py -v` passa.
<!-- SECTION:DESCRIPTION:END -->

- [x] #1 Legacy on-disk config (7 risk-gate fields) loads with engine defaults backfilled (24 keys in FIELDS, 23 leaf fields excluding simulation)
- [x] #2 Validators reject each new engine param outside bounds (window, z_entry, entry_*, force_close_*, buy/sell SL/TP/BE_*)
- [x] #3 DEFAULTS engine params mirror core.config legacy constants (behaviour no-op)
- [x] #4 pytest tests/test_runtime_config.py + tests/test_execution_timeline_server.py pass
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resultado

Schema additive em `core/runtime_config.py`: 16 novos campos por profile.

### Mudanças

**`core/runtime_config.py`**
- `FIELDS`: +16 entries agrupados em sessões (risk-gate / signals / hours / trade-side / simulation)
- `DEFAULTS`: extraído `_ENGINE_DEFAULTS` (dict compartilhado) e espalhado via `**copy.deepcopy(...)` em live/replay. Valores mirror exatos de `core/config.py` (incluindo `entry_end_m=25`, diferente da tabela do plano que listava 0 — produção venceu)
- `_validate_profile`: helper interno `_int_in(field, lo, hi)` + 16 chamadas inline + 1 float (`z_entry`)
- Return dict do validator inclui os 16 campos normalizados
- Docstring reescrita com seções "Risk-gate / Engine / Simulation"

**`config/runtime.json`**
- Adicionados os 16 campos em ambos perfis (preservou `rho_breakdown_level=3` no live, override operacional pré-existente)

**`tests/test_runtime_config.py`**: +52 testes
- 36 cases novos no `test_validation_rejects_bad_values` parametrize (bounds + tipo)
- `test_engine_params_present_in_fields_tuple`
- `test_engine_param_defaults_match_legacy_core_config` (no-op check vs core.config)
- `test_load_backfills_missing_engine_params` (AC1: legacy → 24 keys + 23 leaf)
- `test_engine_params_roundtrip_save_load`
- `test_engine_params_z_entry_normalises_int_to_float`
- `test_engine_params_accept_boundary_values`
- `test_committed_runtime_json_has_engine_params`

**`tests/test_execution_timeline_server.py`**: refactor de 2 fixtures POST para partir de `copy.deepcopy(DEFAULTS)` em vez de inline literal — futuras extensões de schema não exigem mais editar esses testes.

### Bounds aplicados

| Campo | Type | Bounds |
|---|---|---|
| window | int | [30, 1000] |
| z_entry | float | (0.1, 5.0] |
| entry_start_h, entry_end_h, force_close_h | int | [0, 23] |
| entry_start_m, entry_end_m, force_close_m | int | [0, 59] |
| buy_sl, buy_tp, sell_sl, sell_tp | int | [10, 5000] |
| buy_be_act, buy_be_lock, sell_be_act, sell_be_lock | int | [0, 5000] |

### Regressão

Full suite: **521 passed, 19 skipped** (+48 vs baseline 473). Consumers (signals.py, risk_gate.py, trade_engine.py) ainda não tocados — schema-only, hot-reload safe durante mercado.

### Próximas slices (A'.2, A'.3, A'.4)

- TASK-16.2: signals.py consome `window` / `z_entry` via profile
- TASK-16.3: risk_gate.py consome `entry_*` / `force_close_*` via profile
- TASK-16.4: trade_engine.py consome `buy/sell SL/TP/BE_*` snapshot no `_open_trade`
<!-- SECTION:FINAL_SUMMARY:END -->
