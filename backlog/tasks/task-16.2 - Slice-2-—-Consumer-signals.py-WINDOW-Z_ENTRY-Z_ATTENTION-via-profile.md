---
id: TASK-16.2
title: 'Slice 2 — Consumer signals.py: WINDOW/Z_ENTRY/Z_ATTENTION via profile'
status: In Progress
assignee: []
created_date: '2026-05-12 19:37'
updated_date: '2026-05-13 04:51'
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

Migrar `core/signals.py` para receber `window`, `z_entry`, `z_attention` como parâmetros, lidos do `RuntimeProfile` pelo caller. Tornar `core/config.py` constantes em defaults.

## Mudanças

### `core/signals.py`
- Remover `from core.config import WINDOW, BARS, Z_ENTRY, Z_ATTENTION`.
- Funções que usam essas constantes recebem como kwargs (com default = constante do `core.config`).
- Identificar todos os call sites (server.py, replay_execution_timeline.py).

### `server.py`
- Carregar profile via `load_runtime_config()["live"]` (já existe).
- Passar `window=profile["window"]`, `z_entry=profile["z_entry"]` etc. nos consumidores.

### `scripts/replay_execution_timeline.py`
- Mesmo, mas usando `profile["replay"]`.

## Constraints

- **Restart obrigatório** — fora do horário de mercado (após 17:40 BRT).
- Validar com `tests/test_signals.py` + replay parity (20 dias abril, deve bater byte-identical com baseline).

## Acceptance criteria

- AC1: `calc_zscore(...)` aceita `window` kwarg; default == `core.config.WINDOW` (backward compat).
- AC2: Mudança de `window` via POST `/api/runtime-config` reflete na próxima poll sem restart.
- AC3: Replay com `WINDOW=240` no profile produz mesmo resultado que `WINDOW=240` hardcoded em `core/config.py` (parity check).
<!-- SECTION:DESCRIPTION:END -->
