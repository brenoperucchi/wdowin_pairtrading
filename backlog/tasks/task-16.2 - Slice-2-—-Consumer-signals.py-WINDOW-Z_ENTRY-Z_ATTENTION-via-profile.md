---
id: TASK-16.2
title: 'Slice 2 — Consumer signals.py: WINDOW/Z_ENTRY/Z_ATTENTION via profile'
status: Done
assignee: []
created_date: '2026-05-12 19:37'
updated_date: '2026-05-13 05:00'
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resumo

Liftei `WINDOW`, `Z_ENTRY` e `Z_ATTENTION` dos globais de `core.config` para o perfil runtime — live e replay/sweep passam a compartilhar o mesmo knob hot-reloadable.

## Mudanças

- **`core/runtime_config.py`** — `z_attention=1.2` adicionado ao `_ENGINE_DEFAULTS`; validator próprio (`(0.1, 5.0]`); regra cross-field `z_attention < z_entry` (estrita) — `FIELDS` agora tem 25 chaves (24 + sub-block `simulation`).
- **`core/signals.py`** — `get_signal(... z_entry=None, z_attention=None, ...)`; `None` cai no global do módulo (backward-compat preservada para callers legados).
- **`server.py`**:
  - `regime_v2`: load do `live_profile` movido para logo após o data-fetch guard, antes do `calc_zscore`. Esse mesmo profile injeta `window` em `calc_beta_ols`/`calc_zscore` e `z_entry`/`z_attention` em `get_signal`. O bloco duplicado abaixo (linhas ~1336) foi reduzido a só rebind de `live_eg_strategies`.
  - `history_endpoint`: carrega `live` profile e injeta `window` no `calc_beta_ols`/`calc_zscore` da pista OLS — a visualização da história agora bate com o engine ao vivo.
- **`config/runtime.json`** — `z_attention: 1.2` adicionado a `live` e `replay`.
- **Tests**:
  - `tests/test_runtime_config.py`: `_ENGINE_PARAM_FIELDS` ganhou `z_attention`; 5 parametrize cases de rejeição; leaf-count bump (23 → 24); novo `test_validation_rejects_z_attention_not_below_entry` (3 cases); defaults committed agora exigem `z_attention < z_entry`.
  - `tests/test_signals.py`: 4 testes novos cobrindo `z_entry`/`z_attention` injetados via kwargs + fallback quando `None`.

## ACs

- **AC1** (calc_zscore `window` kwarg backward-compat) — já existia; verificado.
- **AC2** (hot-reload sem restart) — `live_profile` re-lido a cada `regime_v2()` (poll). `window`/`z_entry`/`z_attention` mudam na próxima poll após POST.
- **AC3** (replay parity) — `replay_execution_timeline.py` não usa `core/signals.py:get_signal` diretamente (ele computa via Kalman + cached z), então sem regressão. Para o caso hipotético em que use, o default kwarg=None faz o engine cair no `Z_ENTRY/Z_ATTENTION` legado, garantindo paridade bit-exata.

## Suíte

`python3 -m pytest tests/ -q` → **548 passed, 19 skipped, 1 warning** (+12 vs baseline 536). Sem nenhum teste pré-existente quebrado.

## Limites de escopo

- `core/trade_engine.py` ainda lê `Z_ENTRY`/`Z_ATTENTION` direto do global — escopo de TASK-16.4.
- `di_regime` continua usando `DI_KALMAN_W` (família independente — fora desta task).
- `core/config.py` continua existindo como fonte de defaults (não removido nada).

## Commit

`5a8b363 feat(task-16.2): signals.py reads window/z_entry/z_attention from profile`
<!-- SECTION:FINAL_SUMMARY:END -->
