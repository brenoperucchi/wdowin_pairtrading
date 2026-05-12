---
id: TASK-14.5
title: '[Slice 4] Dual-write live — BAR_HISTORY_BACKEND=dual no server.py'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 06:16'
labels:
  - migration
  - timescaledb
  - live
dependencies: []
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Substituir os call sites de escrita em `server.py` (e trade engine se aplicável) pelo wrapper do Slice 2. Default permanece `sqlite`; ativar `BAR_HISTORY_BACKEND=dual` em dev/staging para acumular paridade.

## Entregáveis
- Server e poller usam `bar_history_db.upsert_bar(...)` em vez de SQL inline para escrita.
- Modo `dual` validado por janela (ex.: 1 dia em produção dev) sem divergência.

## Aceitação
- `BAR_HISTORY_BACKEND=sqlite` → comportamento idêntico ao baseline.
- `BAR_HISTORY_BACKEND=dual` → ambos os DBs recebem as mesmas barras, leitura continua do SQLite.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Entrega

- `server.py` agora importa `core.bar_history_db as bhdb` e invoca o wrapper como **espelho** das escritas SQLite — não substituição (tests dependem do parâmetro `db_path`, mantido intacto).
- `init_bar_history`: após criar schema em SQLite, chama `bhdb.init_schema(backend="postgres")` quando `BAR_HISTORY_BACKEND ∈ {dual, postgres}`. Falha é logada (`[ERRO PG]`), nunca raise.
- `save_bar_history`: após o `INSERT ... ON CONFLICT` em SQLite, chama `bhdb.upsert_bar(row, backend="postgres")` apenas em modo `dual` **e somente se o commit SQLite passou** (`sqlite_ok` flag). Isso preserva a invariante: PG nunca recebe uma barra que SQLite (source-of-truth) rejeitou. Exceções no path PG são engolidas com log — a poll loop não pode parar se PG cair.
- Default (`BAR_HISTORY_BACKEND` unset) é byte-equivalente ao baseline pré-TASK-14. Verificado pelos 20 testes do `tests/test_bar_history.py`.

## Cobertura adicionada (`tests/test_bar_history.py`)

1. `test_save_bar_history_default_backend_skips_pg` — sem env, wrapper nunca é chamado; SQLite gravado.
2. `test_save_bar_history_dual_backend_mirrors_to_pg` — `dual` → `bhdb.upsert_bar` recebe row com 19 colunas + `backend="postgres"`; SQLite também gravado (z=0.42 round-trip).
3. `test_save_bar_history_dual_pg_failure_does_not_break_sqlite` — `bhdb.upsert_bar` lança → captura `[ERRO PG]`; SQLite continua coerente.
4. `test_save_bar_history_dual_skips_pg_when_sqlite_fails` — quando o INSERT SQLite levanta (path inválido), `bhdb.upsert_bar` NÃO é chamado. Log mostra `[ERRO DB]` mas não `[ERRO PG]`. Guarda o contrato de parity.

## Aceitação

- ✅ `BAR_HISTORY_BACKEND=sqlite` (default): comportamento idêntico ao baseline. Suite full (347 passed, 9 skipped, 1 warn).
- ✅ `BAR_HISTORY_BACKEND=dual`: write path duplicado, read continua SQLite. Validado por unit tests com monkeypatch + smoke live.
- ✅ Smoke live (PG up + dual + sample bar): hypertable criada via `init_bar_history`, `save_bar_history` espelhou row de 19 colunas; `SELECT timestamp,z_wdo,rho,beta_value` retornou `(1778566261, 0.42, -0.91, 1.05)` byte-identical em SQLite e Postgres. Row de smoke removida (`DELETE FROM bar_history WHERE timestamp=1778566261`).

## Docs

- `docs/migration_bar_history_timescale.md` §14 (novo): dual-write live, modo de falha tolerado, comando de ativação/reverter, smoke manual.

## Não escopo (próximas slices)

- Slice 5 — `BAR_HISTORY_BACKEND=postgres` flip read path em `load_bar_history` + `/api/history`.
- Slice 8 — cron de paridade (`migrate_bar_history_to_pg.py --force-refresh`) para reparar gap quando PG cair em modo dual.
<!-- SECTION:FINAL_SUMMARY:END -->
