---
id: TASK-16.3
title: 'Slice 3 — Consumer risk_gate.py: ENTRY_*/FORCE_CLOSE_* via profile'
status: Done
assignee: []
created_date: '2026-05-12 19:37'
updated_date: '2026-05-13 12:58'
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

Migrar `core/risk_gate.py` para receber `entry_start_h/m`, `entry_end_h/m`, `force_close_h/m` via parâmetros.

## Mudanças

### `core/risk_gate.py`
- `_in_session(hour, minute, entry_start_h=..., entry_start_m=..., entry_end_h=..., entry_end_m=...)`.
- `risk_gate(...)` aceita os mesmos kwargs e propaga.

### `core/trade_engine.py`
- `force_close_h/m` consumido em `force_close_if_open(...)`.
- Idealmente lido do profile a cada poll (hot-reload).

### `server.py`, `replay_execution_timeline.py`
- Passar profile values em todos os call sites.

## Constraints

- Restart fora do mercado.
- `tests/test_risk_gate.py` cobre cada combinação de janela.

## Acceptance criteria

- AC1: `_in_session(10, 0)` com profile `entry_end_h=15` retorna True; com `entry_end_h=10` retorna False.
- AC2: Mudança via POST muda comportamento sem restart na próxima poll.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resumo

Liftei `ENTRY_START_*`/`ENTRY_END_*` e `FORCE_CLOSE_*` dos globais de `core.config` para o perfil runtime — live e replay agora compartilham o mesmo knob hot-reloadable de janela de entrada e force-close de EOD.

## Mudanças

- **`core/risk_gate.py`**:
  - `_in_session(hour, minute, *, entry_start_h=None, entry_start_m=None, entry_end_h=None, entry_end_m=None)` — `None` cai no global do módulo (backward-compat para callers legados).
  - `risk_gate()` ganhou 4 kwargs novos (`entry_start_h/m`, `entry_end_h/m`) que propagam para `_in_session`.
- **`core/trade_engine.py`**:
  - `_is_force_close(hour, minute, *, force_close_h=None, force_close_m=None)` — mesmo padrão.
  - `evaluate(...)` e `_check_exits(...)` aceitam `force_close_h/m` e threadam pra `_is_force_close`.
- **`server.py`**:
  - `_build_gate` injeta `entry_start_h/m`, `entry_end_h/m` do `live_profile` na chamada de `risk_gate`.
  - `_trade_engine.evaluate(...)` recebe `force_close_h/m` do `live_profile`.
- **`scripts/replay_execution_timeline.py`**:
  - `ReplayRuntimeProfile` ganhou 6 campos (`entry_start_h/m`, `entry_end_h/m`, `force_close_h/m`) via `from_mapping`.
  - `run_replay()` propaga os 6 valores para `risk_gate(...)` e `engine.evaluate(...)`.
- **Tests**:
  - `tests/test_risk_gate.py`: 4 casos novos — widen window, shrink window, boundary inclusivo, None-fallback.
  - `tests/test_trade_engine.py`: 3 casos novos — advance force_close, delay force_close, None-fallback.

## ACs

- **AC1** (engine + risk_gate aceitam params como kwargs) — feito. Defaults preservados via `None`.
- **AC2** (mudança via POST sem restart) — `live_profile` re-lido a cada `regime_v2()` (já era padrão TASK-16.2). Próxima poll após POST reflete a nova janela.
- **AC3** (replay parity) — `ReplayRuntimeProfile.from_mapping` lê do `replay` profile; pega `entry_*`/`force_close_*` do perfil ao invés do global. Suíte de replay (`test_replay_execution_timeline.py`) continua verde.

## Suíte

`python3 -m pytest tests/ -q` → **557 passed, 19 skipped, 1 warning** (+9 vs baseline 548 da TASK-16.2). Sem regressão.

## Limites de escopo

- `core/trade_engine.py` ainda lê `BUY_SL/TP/BE_*` e `SELL_SL/TP/BE_*` direto dos globais — escopo de TASK-16.4.
- `MAX_TRADES_PER_DAY`/`DAILY_LOSS_LIMIT_BRL`/`LOSS_COOLDOWN_MIN` ainda em `operational_checks` — fora desta task (limites operacionais, não janela de entrada).

## Commits

- `43ded29 fix(task-16.2): cache history by window + extract OLS tail helper` (follow-up TASK-16.2 que vinha solto no worktree)
- `cf5ee57 feat(task-16.3): risk_gate + force_close consume runtime profile`
<!-- SECTION:FINAL_SUMMARY:END -->
