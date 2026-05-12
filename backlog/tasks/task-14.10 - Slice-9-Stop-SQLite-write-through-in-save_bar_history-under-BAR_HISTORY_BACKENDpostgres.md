---
id: TASK-14.10
title: >-
  [Slice 9] Stop SQLite write-through in save_bar_history under
  BAR_HISTORY_BACKEND=postgres
status: Done
assignee: []
created_date: '2026-05-12 13:12'
updated_date: '2026-05-12 18:35'
labels:
  - migration
  - timescaledb
  - server
dependencies: []
parent_task_id: TASK-14
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Slice 9 fecha o cutover: hoje `server.py:save_bar_history` escreve SQLite primeiro e espelha pra PG sob `dual`/`postgres` para preservar rollback. Sob `BAR_HISTORY_BACKEND=postgres` o write-through SQLite deixa de existir — só PG é tocado, via `bhdb.upsert_bar(..., backend="postgres", mode="merge")`. `dual` e `sqlite` ficam idênticos.

**Contexto da Slice 8 review:**
- O reviewer flagou (Medium) que docs descreviam `postgres` como "PG-only" mas o live writer mantinha SQLite. Slice 8 ajustou docs (README/CLAUDE/plan) explicitando que Slice 9 faria o flip. Esta task encerra esse débito.

**Experimento Slice 9 (precursor):**
- Validamos via `py.exe -3.12` (Windows) + `psycopg[binary]` que Windows→WSL Postgres funciona em `127.0.0.1:5432` (WSL2 mirrored networking). Conectividade Slice 9 não é problema.
- Tentamos provar paridade MT5-replay vs live-tick para 2026-05-11: **falhou estruturalmente** — `backfill_bar_history_indicators.py` só escreve 5 colunas (eg_pvalue, rho, rho_level, beta_value, beta_delta_pct) e PRICE_COLUMNS; runtime-only columns (nwe_*, spread_*, z_di, z_wdo) são populadas só pelo eval loop ao vivo de `server.py`. Portanto Slice 9 não pode se basear em replay parity — só em validação live.

**Não escopo:**
- Flipar o systemd unit do live service para `BAR_HISTORY_BACKEND=postgres` — ação operacional pertencente ao usuário (decisão de produção, não code change).
- `DROP TABLE bar_history` em `trades.db` — fica para depois de 30 dias de paridade verificada.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 server.py:save_bar_history: sob backend=postgres, NÃO escreve em SQLite — só chama bhdb.upsert_bar com backend=postgres. dual e sqlite inalterados.
- [x] #2 Teste unitário cobre os 3 modos (sqlite, dual, postgres) com fake bhdb client confirmando o caminho certo é tomado em cada caso.
- [x] #3 Suite pytest tests/ verde sem PG_TEST_URI (367+ passed, 14 skipped).
- [x] #4 Suite pytest tests/ verde com PG_TEST_URI (381+ passed).
- [x] #5 Diff revisado antes do commit (ritual slice-by-slice).
<!-- AC:END -->
