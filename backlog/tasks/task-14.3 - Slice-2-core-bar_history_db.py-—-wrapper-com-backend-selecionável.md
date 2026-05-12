---
id: TASK-14.3
title: '[Slice 2] core/bar_history_db.py — wrapper com backend selecionável'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 04:01'
labels:
  - migration
  - timescaledb
  - wrapper
dependencies: []
references:
  - core/bar_history_db.py
  - tests/test_bar_history_db.py
  - requirements.txt
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implementar `core/bar_history_db.py` expondo as mesmas funções usadas hoje (insert/upsert, fetch_range, fetch_latest, etc.) com despacho para SQLite ou Postgres conforme `BAR_HISTORY_BACKEND`. Sem alterar call sites ainda.

## Entregáveis
- `core/bar_history_db.py` com API estável (assinaturas idênticas aos helpers atuais).
- Backends: `sqlite` (atual), `postgres` (psycopg ou asyncpg — decidir no Slice 0), `dual` (escreve em ambos, lê do SQLite).
- Logging de divergência em modo `dual` (warn quando POs leituras divergem em conferência opcional).

## Aceitação
- Testes unitários do wrapper passam para os 3 modos (postgres skipa se `PG_TEST_URI` ausente).
- Nenhum call site da app foi tocado — só wrapper novo.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Wrapper entregue em `core/bar_history_db.py` + suite `tests/test_bar_history_db.py` (26 testes).

**API estável (mapeada a partir dos call sites atuais de bar_history):**
- `init_schema(backend=None)` — DDL idempotente (SQLite + Postgres hypertable + índice em date_str).
- `upsert_bar(row, backend=None)` — INSERT/UPSERT preservando assimetria do z_di.
- `update_columns(timestamp, **cols, backend=None)` — partial UPDATE por PK.
- `select_window(*, days|since_ts, backend=None)` — janela ts >= cutoff.
- `select_by_date(date_str, backend=None)` — WHERE date_str=?
- `select_eg_warmup(date_str, backend=None)` — WHERE date_str<=? (replay EG).
- `count_rows(date_str=None, backend=None)`, `bar_time_range(date_str, backend=None)`.

**Backends:**
- `sqlite` (default): trades.db via env BAR_HISTORY_SQLITE_PATH.
- `postgres`: PG_URI obrigatório; psycopg3 importado lazily.
- `dual`: escreve em ambos; **lê de SQLite** para preservar baseline durante cutover (Slice 4→5).

**UPSERT replicado byte-equivalente:** todos os campos COALESCE-preservam o valor existente, exceto `z_di` que sobrescreve se EXCLUDED não for NULL (asymmetria do server.py:save_bar_history mantida).

**Testes:**
- 17 sempre rodam (SQLite + backend resolution).
- 9 opt-in via PG_TEST_URI (Postgres + dual mode + verificação de hypertable registrado em timescaledb_information.hypertables).
- Suite completa: 323 passed, 9 skipped — zero regressão.

**Dependências:** `psycopg[binary]>=3.1` adicionado ao requirements.txt. Não é hard-fail: o `import psycopg` é lazy no wrapper; ambientes só-SQLite continuam funcionando sem ele (apenas o `pip install -r` baixa o pacote).

**Nenhum call site foi tocado** — server.py, scripts/* permanecem usando o SQL inline em SQLite. Slice 4+ faz a troca.
<!-- SECTION:FINAL_SUMMARY:END -->
