---
id: TASK-14.1
title: '[Slice 0] Design contract — schema, env vars, UPSERT/index, rollback'
status: Done
assignee: []
created_date: '2026-05-12 03:26'
updated_date: '2026-05-12 03:38'
labels:
  - migration
  - timescaledb
  - design
dependencies: []
references:
  - docs/migration_bar_history_timescale.md
parent_task_id: TASK-14
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Produzir o **documento de design** da migração antes de qualquer código. Este slice é só doc.

## Entregáveis

- `docs/migration_bar_history_timescale.md` cobrindo:
  - Schema Postgres de `bar_history` (todos os campos atuais do SQLite, tipos equivalentes).
  - Definição da chave primária / índice único compatível com hypertable (time-column obrigatória).
  - Hypertable: `create_hypertable('bar_history', 'ts', chunk_time_interval => INTERVAL '30 days')`.
  - Política de compressão: `compress_chunks` quando chunk >= 90 dias.
  - UPSERT equivalente ao SQLite `INSERT ... ON CONFLICT(timestamp) DO UPDATE SET <col> = COALESCE(EXCLUDED.<col>, bar_history.<col>)`.
  - Env vars: `PG_URI`, `PG_TEST_URI`, `BAR_HISTORY_BACKEND` (`sqlite`|`dual`|`postgres`), default `sqlite`.
  - `.env.example` planejado (sem segredos reais).
  - Rollback: `BAR_HISTORY_BACKEND=sqlite` recoloca app no estado atual; SQLite mantido até cutover concluído.
  - Mapeamento dos **19 call sites** atuais de `bar_history` (read/write), por arquivo + função, com nota de qual SQL é portável e qual precisa de adaptação.

## Definição de pronto

- Doc revisado e aprovado pelo usuário antes de Slice 1 começar.
- Schema final acordado (tipos numéricos, `TIMESTAMPTZ` vs `BIGINT` para `timestamp`, nullability).
- Sem alteração de código nesse slice.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Doc de design entregue em `docs/migration_bar_history_timescale.md` (11 seções).

**Decisões propostas:**
- `timestamp BIGINT` mantém o contrato atual (epoch seconds), PK simples; hypertable partitiona em `BIGINT` com `chunk_time_interval=2592000` (30d).
- Compressão por `segmentby=date_str`, política automática para chunks ≥ 90d.
- UPSERT replica a assimetria do SQLite (todos os campos `COALESCE(existing, new)` exceto `z_di` que é `COALESCE(new, existing)`).
- Driver `psycopg3` sync, sem asyncpg.
- Env vars `BAR_HISTORY_BACKEND` (sqlite|dual|postgres, default sqlite), `PG_URI`, `PG_TEST_URI`.
- Rollback = env switch + restart; SQLite mantido ≥ 30d pós-cutover.

**Inventário de call sites (§8):** 14 lugares mapeados (server.py + 6 scripts + 3 testes). Conclusão: quase 100% das queries são portáveis sem mudança sintática. Atrito apenas em DDL (`ALTER ADD COLUMN`) e `SELECT *` (mitigado por schema com ordem idêntica de coluna).

**Pontos abertos** (§11) aguardando aprovação antes do Slice 1:
1. Incluir `bar_ts TIMESTAMPTZ` gerado já no schema inicial?
2. Confirmar `psycopg3` (sync) como driver.
3. `segmentby=date_str` cobre as leituras ou outra dimensão é desejada?
4. Bootstrap em script único (sem Alembic/Flyway)?
<!-- SECTION:FINAL_SUMMARY:END -->
