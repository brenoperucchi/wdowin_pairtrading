---
id: TASK-4.1
title: Slice A — Schema + módulo execution_timeline + WAL
status: Done
assignee: []
created_date: '2026-05-08 18:53'
updated_date: '2026-05-08 18:57'
labels:
  - timeline
  - slice-a
dependencies: []
references:
  - /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md
  - 'core/trade_engine.py:_init_db'
parent_task_id: TASK-4
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implementar `core/execution_timeline.py` com schema idempotente, helpers de escrita/leitura, e ligar WAL no `TradeEngine._init_db`. Sem tocar `server.py` nem `trade_engine.py` (além do WAL).

**Arquivos**
- Novo: `core/execution_timeline.py`
- Novo: `tests/test_execution_timeline.py`
- Modificado: `core/trade_engine.py` (somente `_init_db` ganha `PRAGMA journal_mode=WAL`)

**API do módulo**
- `init_timeline_table(db_path)` — `CREATE TABLE IF NOT EXISTS execution_timeline` + índices `(timestamp)` e `(closed_bar_ts, phase, strategy)` + `UNIQUE INDEX` em `dedupe_key`. Idempotente.
- `record_event(db_path, **fields)` — calcula `distance` e `ratio_to_threshold` a partir de `value/threshold/operator`. Usa `INSERT OR IGNORE` keyed em `dedupe_key`. Retorna a row id (ou None se ignorado).
- `bulk_record_events(db_path, events: list[dict])` — uma transação só, mesmo cálculo.
- `load_timeline(db_path, *, limit=200, phase=None, status=None, strategy=None, event=None, since=None)` — lista filtrável.
- `current_bottleneck(db_path)` — `MAX(closed_bar_ts)` → primeiro BLOCKED/FAILED pela ordem do funil DATA>INDICATORS>ELIGIBILITY>RISK>SIGNAL>ORDER>EXECUTION>EXIT. None se a última barra fechada passou limpa.
- `current_live_issue(db_path)` — última falha crítica recente com `closed_bar_ts IS NULL` (ex.: `MT5_DISCONNECTED`).

**Schema de evento** (referência: plano):
campos `id, timestamp, closed_bar_ts, correlation_id, attempt_id, dedupe_key, trade_id, phase, event, status, severity, strategy, symbol, metric, value, threshold, operator, distance, ratio_to_threshold, message, payload_json`.

**Testes** (8-10):
- schema é idempotente (chamar `init_timeline_table` 2x não falha)
- `record_event` com `value=0.64, threshold=0.10, operator=">"` calcula `distance=0.54, ratio=6.4`
- `record_event` com `dedupe_key` repetido só grava 1 vez
- `bulk_record_events` em uma transação
- `load_timeline` filtra por phase/status/strategy/event/since/limit
- `current_bottleneck` retorna primeiro BLOCKED por ordem do funil em uma barra
- `current_bottleneck` retorna None se última barra passou limpa
- `current_live_issue` retorna evento crítico recente sem barra
- WAL: após `_init_db`, `PRAGMA journal_mode` retorna `wal`
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `init_timeline_table` cria tabela + 3 índices idempotentemente (índice de timestamp, composto closed_bar_ts/phase/strategy, UNIQUE em dedupe_key)
- [x] #2 `record_event` calcula `distance` e `ratio_to_threshold` corretamente conforme operator; usa INSERT OR IGNORE em `dedupe_key`
- [x] #3 `bulk_record_events` insere em uma transação; rollback em erro
- [x] #4 `load_timeline` aceita filtros phase/status/strategy/event/since/limit e retorna mais recentes primeiro
- [x] #5 `current_bottleneck` segue ordem fixa do funil dentro da MAX(closed_bar_ts); retorna None quando barra passa limpa
- [x] #6 `current_live_issue` retorna falha crítica recente com closed_bar_ts NULL
- [x] #7 `PRAGMA journal_mode=WAL` ativo após `TradeEngine._init_db`
- [x] #8 `pytest tests/test_execution_timeline.py -q` verde, todos os testes existentes continuam passando
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Slice A entregue: 

- `core/execution_timeline.py` com `init_timeline_table`, `record_event`, `bulk_record_events`, `load_timeline`, `current_bottleneck`, `current_live_issue`. PHASE_ORDER constante (DATA→...→EXIT) usada pelo bottleneck. Schema tem UNIQUE INDEX em `dedupe_key` + 2 índices secundários (timestamp e composto closed_bar_ts/phase/strategy). `INSERT OR IGNORE` faz dedupe; row id retornado em insert real, None quando ignorado.
- `core/trade_engine.py:_init_db` ganhou `PRAGMA journal_mode=WAL` (também ligado em `init_timeline_table`).
- `tests/test_execution_timeline.py` com 15 testes cobrindo: idempotência do schema, WAL pragma após `_init_db`, distance/ratio para operadores `>` e `<`, dedupe por collision, bulk transação + payload_json dict serializado, filtros `phase/status/strategy/event/since/limit`, ordem do funil em `current_bottleneck`, MAX(closed_bar_ts) usado, None quando barra passa limpa, `current_live_issue` retorna FAILED mais recente sem barra e ignora eventos com barra, validação de campos obrigatórios.

`PYTHONPATH=. pytest tests/ -q --ignore=tests/test_bar_history.py --ignore=tests/test_build_history.py` → 146 passed (15 novos + 131 existentes).
<!-- SECTION:NOTES:END -->
