---
id: TASK-16.4
title: >-
  Slice 4 — Consumer trade_engine.py: BUY/SELL SL/TP/BE_* via profile (snapshot
  no open)
status: Done
assignee: []
created_date: '2026-05-12 19:37'
updated_date: '2026-05-13 13:25'
labels:
  - refactor
  - runtime-config
  - trade-engine
dependencies: []
parent_task_id: TASK-16
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Migrar SL/TP/BE de `core/config.py` para o profile, **com snapshot no momento do `_open_trade`**. Posições já abertas NÃO devem ser afetadas por mudanças subsequentes no profile.

## Razão do snapshot

Trade já aberto tem expectativa fixa de SL/TP. Hot-reload do BUY_SL não pode mover stops de posições em curso — operador veria SL/TP mudar magicamente. Solução: gravar valores no `position` dict ao abrir.

## Mudanças

### `core/trade_engine.py`
- `_open_trade(...)` recebe profile, copia `BUY_SL/TP/BE_ACT/BE_LOCK` ou `SELL_*` no `position` dict.
- Lógica de SL/TP/BE em `_update_position(...)` lê do `position` dict (não mais dos constants).
- Persistência (matador_ops) também armazena esses valores para auditoria.

### `server.py`
- Trade engine eval loop passa `profile=load_runtime_config()["live"]` no `evaluate()`.

## Acceptance criteria

- AC1: `BUY_SL` alterado via POST após `_open_trade` NÃO altera SL da posição aberta.
- AC2: Próximo `_open_trade` usa novo `BUY_SL`.
- AC3: `position` dict serializável + persistido em SQLite com os valores capturados.
- AC4: `tests/test_trade_engine.py` cobre snapshot behavior.

## Constraints

- Restart obrigatório fora do mercado.
- Migration path: leitura de matador_ops antigo (sem colunas extras) deve continuar funcionando.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resumo

Liftei `BUY_SL/TP/BE_*` e `SELL_SL/TP/BE_*` dos globais de `core.config` para o perfil runtime e, crucial, **gravei o snapshot no momento do `_open_trade`**. Hot-reload via POST `/api/runtime-config` afeta apenas trades futuros — posições já abertas mantêm os SL/TP/BE com que foram abertas (CAR4 imutabilidade de posição).

## Mudanças

### `core/trade_engine.py`

- **Schema**: 4 novas colunas em `matador_ops` via ADD COLUMN idempotente — `sl_pts`, `tp_pts`, `be_act_pts`, `be_lock_pts` (INTEGER nullable).
- **`evaluate(...)`**: novo kwarg `engine_params: dict | None = None`; propagado para `_eval_consensus`, `_eval_wdo_nwe`, `_eval_di_nwe` e daí para `_open_trade`.
- **`_open_trade(...)`**: resolve direção-específica via prefix (`buy` ou `sell`) e grava 4 valores na linha matador_ops + no dict retornado. `None` cai nos globais `core.config` (backward-compat para callers que não migraram).
- **`_get_open_trades`**: SELECT carrega as 4 colunas no dict.
- **`_check_exits`**: lê `trade.get("sl_pts")` etc. Trades pré-migração (NULL) caem no global direção-resolvido — backward compat completo.

### `server.py`

- `_trade_engine.evaluate(..., engine_params=live_profile)` — o `live_profile` (já um dict com as 8 chaves de TASK-16.1) é passado direto.

### `scripts/replay_execution_timeline.py`

- `ReplayRuntimeProfile` ganhou 8 campos (`buy_sl/tp/be_act/be_lock` + `sell_*`) via `from_mapping`.
- Novo método `as_engine_params()` devolve o subset que o engine quer.
- `engine.evaluate(..., engine_params=runtime_profile.as_engine_params())`.

### Tests (`tests/test_trade_engine.py`)

6 testes novos:
1. `test_engine_params_burned_into_matador_ops_on_open` — AC3 persistência
2. `test_engine_params_sell_direction_picks_sell_keys` — resolução BUY vs SELL
3. `test_engine_params_none_falls_back_to_core_config` — backward-compat
4. `test_snapshot_is_immutable_to_mid_position_param_changes` — **AC1**: SL=100 burned, depois POST relaxa para 400, mas o trade ainda dispara STOP_LOSS no nível original
5. `test_next_open_after_hot_reload_uses_new_params` — **AC2**: próximo trade pega o novo valor
6. `test_legacy_open_trade_without_snapshot_falls_back_to_globals` — OPEN row sem `sl_pts` (pre-migração) continua fechando corretamente

## ACs

- **AC1** (snapshot imutável a mid-position) — coberto pelo teste 4. Posição aberta com SL=100 fecha em STOP_LOSS depois que o POST relaxa para 400, comprovando que o profile novo não move o stop existente.
- **AC2** (próximo `_open_trade` usa novo valor) — coberto pelo teste 5.
- **AC3** (dict serializável + persistido em SQLite) — coberto pelos testes 1, 2. Persistido nas 4 novas colunas.
- **AC4** (`test_trade_engine.py` cobre snapshot) — 6 casos novos.

## Suíte

`BAR_HISTORY_SQLITE_PATH=/tmp/trades.test2.db python3 -m pytest tests/ -q` → **564 passed, 19 skipped, 1 warning** (+6 vs 558 baseline). Sem regressão.

> `BAR_HISTORY_SQLITE_PATH` é gambiarra do dev: o `trades.db` no `/mnt/c/` dá `disk I/O error` no WSL ao tentar habilitar WAL. Não é regressão da task — fora dela o arquivo já estava em estado problemático. Reportar separadamente se quiser que esse path use tmp por default em testes.

## Limites de escopo (out)

- `core/trade_engine.py` ainda usa `Z_ENTRY`/`Z_ATTENTION` globais em `_eval_consensus`/`_eval_wdo_nwe`/`_eval_di_nwe` (linhas 310, 317, 330, 369). TASK-16.2 cobriu `core/signals.get_signal`, mas as decisões de entrada do engine ainda são via global. Não vi essa lacuna no checklist do plano original — sinalizar antes de seguir 16.5/16.6 (ou criar slice extra).
- `MAX_TRADES_PER_DAY` / `DAILY_LOSS_LIMIT_BRL` / `LOSS_COOLDOWN_MIN` em `operational_checks` ainda lidos via global — escopo de TASK-16.5 (cleanup) ou slice separado.
<!-- SECTION:FINAL_SUMMARY:END -->
