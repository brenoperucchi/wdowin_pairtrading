---
id: TASK-13.1
title: '[Slice 1] beta_delta_max default 25 → 15'
status: Done
assignee: []
created_date: '2026-05-11 18:55'
updated_date: '2026-05-11 19:06'
labels:
  - gate
  - config
dependencies: []
parent_task_id: TASK-13
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Trocar o default de `beta_delta_max` em ambos os perfis de `runtime_config.DEFAULTS` de **25.0 → 15.0** para alinhar com `beta_status.level < 2` do upstream (`|Δβ| < 15%`).

## Mudanças

- `core/runtime_config.py:62,72` — DEFAULTS.live.beta_delta_max e DEFAULTS.replay.beta_delta_max
- Teste em `tests/` cobrindo: (a) DEFAULTS efetivamente expõe 15.0, (b) gate bloqueia em 15.0 ≤ |Δβ| < 25.0 (caso intermediário onde antes passava)
- CLAUDE.md `Regime health gates` — atualizar a linha "current default 25.0, divergent" → "default 15.0, aligned"

## Compatibilidade

- Arquivo `data/runtime_config.json` existente continua válido (apenas o DEFAULTS muda). Operador que personalizou seu profile mantém o valor antigo até resetar/editar via /CONFIG.
- Slideover `RuntimeConfigSlideover.jsx` não precisa mudar — campo já existe; só o pré-preenchimento numa instalação limpa altera.

## Não-escopo

- Migrar o `data/runtime_config.json` em disco do usuário.
- Mudar a tabela de classificação em `get_beta_status` (5/15/25%) — permanece hardcoded.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `core/runtime_config.py` DEFAULTS.live.beta_delta_max == 15.0
- [x] #2 `core/runtime_config.py` DEFAULTS.replay.beta_delta_max == 15.0
- [x] #3 Novo teste cobre cenário |Δβ|=20% bloqueado por BETA_DRIFT
- [x] #4 `CLAUDE.md` não contém mais a nota 'divergent — upstream effective threshold is 15.0'
- [x] #5 Todos os testes existentes continuam passando (pytest tests/)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resumo

`DEFAULTS.live.beta_delta_max` migrado de 25.0 → 15.0 em `core/runtime_config.py:61`. Replay já estava em 15.0, então a mudança removeu a divergência que existia apenas no perfil live. Comment block do DEFAULTS reescrito pra refletir o alinhamento total com upstream (não mais explicação de split entre profiles).

## Mudanças

- `core/runtime_config.py:50-74` — DEFAULTS.live.beta_delta_max 25.0→15.0, comment block atualizado.
- `tests/test_runtime_config.py:223-226` — novo `test_defaults_beta_delta_max_aligned_with_upstream`.
- `tests/test_risk_gate.py:95-108` — novo `test_beta_drift_blocks_at_runtime_config_15_default` cobrindo o caso |Δβ|=20% que antes passava silenciosamente e agora bloqueia.
- `CLAUDE.md:106` — nota "current default 25.0, divergent" removida.

## Não-mudado deliberadamente

- `core/config.py:61 BETA_DELTA_MAX = 25.0` continua 25.0. É o fallback estático do `risk_gate.py:219` quando ninguém passa o kwarg — i.e., só usado por callers legacy/externos. O fluxo live/replay sempre passa `live_profile["beta_delta_max"]=15.0` agora. Mexer no fallback é fora do escopo desta slice e exigiria revisar callers externos do `risk_gate`.
- `data/runtime_config.json` em disco (se existir) mantém o valor antigo até operador resetar/editar pelo /CONFIG — comportamento backward-compat documentado na task.

## Verificação

- `PYTHONPATH=. pytest tests/ -q` → **307 passed, 1 warning** (warning não-relacionado, vem de httpx). 
- Comparativamente, `pytest tests/test_runtime_config.py tests/test_risk_gate.py -q` → 78 passed.
- Hot-reload do live profile já está validado por TASK-11.4; mesma cadeia leva o novo default ao `risk_gate` no próximo poll.

## Riscos / observação para o operador

- No próximo restart do server (ou primeira mudança via /CONFIG após reset), o perfil live vai bloquear trades em `|Δβ| ≥ 15%` em vez de `≥ 25%`. Esse é o objetivo da slice (alinhar upstream), mas pode aumentar a frequência de `BETA_DRIFT` no timeline em dias de drift moderado. Se isso causar barulho excessivo, o operador pode subir manualmente via /CONFIG.
<!-- SECTION:FINAL_SUMMARY:END -->
