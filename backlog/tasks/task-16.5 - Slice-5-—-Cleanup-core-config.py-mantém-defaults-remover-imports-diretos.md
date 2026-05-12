---
id: TASK-16.5
title: 'Slice 5 — Cleanup: core/config.py mantém defaults, remover imports diretos'
status: To Do
assignee: []
created_date: '2026-05-12 19:38'
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
