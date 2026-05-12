---
id: TASK-16.4
title: >-
  Slice 4 — Consumer trade_engine.py: BUY/SELL SL/TP/BE_* via profile (snapshot
  no open)
status: To Do
assignee: []
created_date: '2026-05-12 19:37'
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
