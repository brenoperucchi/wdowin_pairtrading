---
id: TASK-16.5
title: 'Slice 5 — Cleanup: core/config.py mantém defaults, remover imports diretos'
status: Done
assignee: []
created_date: '2026-05-12 19:38'
updated_date: '2026-05-13 13:56'
labels:
  - refactor
  - cleanup
  - docs
dependencies: []
parent_task_id: TASK-16
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Após slices 16.2-16.4, `core/config.py` ainda exporta as constantes (usadas como defaults em `runtime_config.DEFAULTS`). Limpar imports diretos restantes em código de produção (não tests).

## Tarefas

1. Grep imports de `WINDOW`, `Z_ENTRY`, `ENTRY_*`, `FORCE_CLOSE_*`, `BUY_*`, `SELL_*` em production code.
2. Substituir pelo profile param onde já há profile no escopo.
3. Manter constantes em `core/config.py` como defaults para `DEFAULTS` em `runtime_config.py`.
4. Atualizar CLAUDE.md (seção "Regime health gates") para mencionar que valores agora vêm de runtime config.
5. Docstring em `core/config.py` esclarece: "Defaults consumed by `runtime_config.DEFAULTS`. Operators tune via /api/runtime-config".

## Acceptance criteria

- AC1: `grep -rn 'from core.config import .*WINDOW\|Z_ENTRY\|BUY_SL...' core/ server.py scripts/` em production code retorna apenas `runtime_config.py`.
- AC2: CLAUDE.md atualizado.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## TASK-16.5 — Cleanup imports diretos + runtime-config docstring

### Mudanças

**`core/trade_engine.py`**
- `_eval_consensus/_eval_wdo_nwe/_eval_di_nwe` agora leem `z_entry`/`z_attention` de `engine_params` (fallback para `Z_ENTRY`/`Z_ATTENTION` quando `None`).
- `_open_trade` resolve `z_threshold` do `engine_params` para gravar no timeline `SIGNAL` event (era global `Z_ENTRY` hard-coded).
- Removido `_in_session()` (dead code após TASK-16.3 mover gating para `risk_gate`).
- Limpos imports `Z_ANOMALY`, `ENTRY_START_H/M`, `ENTRY_END_H/M` que ficaram sem uso.
- De-tagueados comentários internos que referenciavam "TASK-16.4" (sigaling/code rot).

**`scripts/replay_execution_timeline.py`**
- `ReplayRuntimeProfile` recebe `z_entry` e `z_attention`; `as_engine_params()` inclui ambos para que replay passe os mesmos thresholds que o live passa ao engine.

**`server.py`**
- Removido import unused `WINDOW`.

**`core/config.py`**
- Docstring esclarece o papel como **defaults** consumidos por `runtime_config.DEFAULTS`; operadores afinam via `POST /api/runtime-config`, não editando o arquivo.

**`CLAUDE.md`**
- `core/config.py` bullet reescrito (defaults, não single source of truth).
- Nova subseção "Operational params (per-profile in `runtime_config`)" lista z_entry/z_attention, BUY/SELL SL/TP/BE, ENTRY/FORCE_CLOSE_*, window — apontando snapshot at `_open_trade` (CAR4) e hot-reload via `get_profile("live")` por poll.

**`tests/test_trade_engine.py`** (+4 tests)
- `test_engine_params_z_entry_gates_consensus_buy` — z_entry alto bloqueia BUY consensus; relaxar abre.
- `test_engine_params_z_entry_gates_wdo_nwe` — WDO_NWE também usa z_entry do engine_params.
- `test_engine_params_z_entry_recorded_on_timeline_threshold` — timeline `SIGNAL.threshold` reflete engine_params, não global.
- `test_engine_params_z_entry_none_falls_back_to_global` — fallback para `Z_ENTRY` quando engine_params ausente.
- Helper `_engine_params` ganhou kwargs `z_entry`/`z_attention` (default `Z_ENTRY`/`Z_ATTENTION`).

### Verificação

**AC1** — production-code grep para imports dos globais migrados:
```
$ grep -rnE "from core\.config import.*\b(WINDOW|Z_ENTRY|Z_ATTENTION|BUY_SL|...|FORCE_CLOSE_M)\b" core/ server.py scripts/
core/signals.py:9:from core.config import WINDOW, BARS, Z_ENTRY, Z_ATTENTION
```
Único hit: `signals.py` — kept as kwarg-with-None-fallback (`window`/`z_entry`/`z_attention` aceitos como args desde TASK-16.2). Outros consumers (trade_engine, risk_gate) seguem o mesmo padrão; o import existe apenas para servir de fallback quando o kwarg vem `None`.

**AC2** — CLAUDE.md atualizado: bullet `core/config.py` reescrito + nova subseção "Operational params (per-profile in `runtime_config`)" detalhando snapshot, hot-reload e fallback.

**Tests** — 568 passed, 19 skipped (env workaround `BAR_HISTORY_SQLITE_PATH=/tmp/...` para o disk I/O na trades.db real em /mnt/c/, pendência de slice separada).

### Gaps deixados para slices futuros

- `core/timeline_emit.py` ainda lê `MAX_TRADES_PER_DAY`, `DAILY_LOSS_LIMIT_BRL`, `LOSS_COOLDOWN_MIN` como global — mesmo padrão de fallback, mas esses três continuam não tendo override por kwarg (também não estão no runtime profile). Levar para slice operacional separado quando decidirmos parametrizar limites diários.
- `RHO_MIN` em `core/trade_engine.py` continua importado mas não tem usuário — limpeza pequena que pode ser feita oportunisticamente.
<!-- SECTION:FINAL_SUMMARY:END -->
