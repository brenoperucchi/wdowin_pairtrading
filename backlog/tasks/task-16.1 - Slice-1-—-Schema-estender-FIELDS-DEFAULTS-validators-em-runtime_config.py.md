---
id: TASK-16.1
title: 'Slice 1 — Schema: estender FIELDS/DEFAULTS/validators em runtime_config.py'
status: To Do
assignee: []
created_date: '2026-05-12 19:37'
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

## Acceptance criteria

- AC1: `load_runtime_config()` com `runtime.json` atual (7 campos) retorna 23 campos por profile.
- AC2: Validator rejeita cada novo campo fora de bounds.
- AC3: `pytest tests/test_runtime_config.py -v` passa.
<!-- SECTION:DESCRIPTION:END -->
