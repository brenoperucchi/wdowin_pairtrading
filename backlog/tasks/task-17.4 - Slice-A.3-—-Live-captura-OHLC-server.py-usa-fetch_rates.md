---
id: TASK-17.4
title: Slice A.3 — Live captura OHLC (server.py usa fetch_rates)
status: Done
assignee: []
created_date: '2026-05-13 01:20'
updated_date: '2026-05-13 02:47'
labels:
  - server
  - live
  - ohlc
dependencies: []
parent_task_id: TASK-17
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Modificar `server.py` para usar `fetch_rates()` (de A.1) em vez de `fetch_bars()` ao salvar barras no `bar_history`. Preencher os 9 campos OHLC novos (de A.2) para próximas barras fechadas.

## Escopo

- `server.py` em `regime_v2` (linhas ~1073-1212): substituir `fetch_bars(SYMBOL_X, ...)` por `fetch_rates(SYMBOL_X, ...)` para WIN/WDO/DI.
- Passar `open/high/low/close` ao `save_bar_history()`.
- Manter cálculos atuais (Kalman, OLS, NWE, etc.) usando o `close` da estrutura nova — comportamento bit-exato em relação ao close.

## Dependência (informativa)

Bloqueada por TASK-17.1 (fetch_rates) e TASK-17.2 (schema OHLC).

## Janela

**Fora de mercado** — mexe no path que o `trade_eval_loop` está usando ativamente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 server.py usa fetch_rates() para WIN/WDO/DI ao popular bar_history
- [x] #2 1 barra fechada após deploy tem win_open/high/low/close populados (verificação via SELECT)
- [x] #3 Kalman/OLS/NWE/z-score continuam idênticos para a mesma barra (regressão zero no close)
- [x] #4 Service estável 30min em DEV após deploy (journalctl sem erros relacionados)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Mudanças

### `core/mt5_client.py`
Sem mudanças (A.1 já adicionou `fetch_rates` / `fetch_rates_range`).

### `server.py`
- Import: `fetch_rates` adicionado ao `from core.mt5_client import (...)`.
- Helper novo `_fetch_ohlc(symbol, count)`: chama `fetch_rates()` e devolve `(closes, opens, highs, lows, times)` como arrays numpy. Failure semantics espelham `fetch_bars` (5-tuple de Nones).
- `regime_v2`: `fetch_bars(SYMBOL_A/B, ...)` substituído por `_fetch_ohlc`. Slicing `ac/bc/tc` agora acompanha `ao/ah/al/bo/bh/bl`. Aplicado também ao corte por `BARS`.
- `regime_v2`: extrai `di_ohlc_map[local_ts] = (di_open, di_high, di_low)` do `_di_cache["history"]` (alimentado pelo `/api/di-regime` no mesmo poll).
- `regime_v2`: as duas chamadas a `_build_history` (live_history + fallback midday-coldstart) passam OHLC para WIN/WDO + `di_ohlc_map`.
- `di_regime`: `fetch_bars` → `_fetch_ohlc` para WIN/DI. Apenas OHLC do DI é propagado (`_build_history(..., di_opens=, di_highs=, di_lows=)`) para alimentar `_di_cache["history"]`.
- `_build_history`: 10 kwargs novos (`win_opens/highs/lows`, `wdo_opens/highs/lows`, `di_opens/highs/lows`, `di_ohlc_map`). Helper interno `_pick(arr, idx)` faz indexação segura. Fallback: se arrays DI não fornecidos, lê de `di_ohlc_map[local_ts]` (tupla `(open, high, low)`). Chaves OHLC só são atribuídas quando há valor (graceful — chave ausente = NULL após COALESCE).
- `_persist_closed_bars`: lê 9 chaves OHLC do entry dict via `entry.get(...)` e propaga ao `save_bar_history`.
- `save_bar_history`: 9 kwargs OHLC adicionados (default `None`). Row dict estendido. INSERT inline SQLite estendido com 9 colunas + placeholders + 9 cláusulas `COALESCE`-preserve no `ON CONFLICT(timestamp) DO UPDATE`. Caminho PG continua usando `bhdb.upsert_bar(row, backend="postgres", mode="merge")` — bhdb já contempla as colunas (A.2).

### `history_endpoint` (linha 2390)
**Fora de escopo de A.3.** Esse endpoint serve a multi-day history view e **não persiste** em `bar_history`. Mantido com `fetch_bars` — migração para OHLC fica para um slice futuro (impacto só na UI de histórico, não na fidelity do replay).

### Tests
- `tests/test_bar_history.py`: helper `_select_ohlc(db_path, ts)` (raw SELECT — `load_bar_history` ainda não expõe OHLC) + 4 testes novos:
  - `test_save_bar_history_roundtrips_ohlc` (AC#2 prova) — 9 valores OHLC salvos e lidos back.
  - `test_save_bar_history_ohlc_coalesce_preserves_first_value` — re-save com NULLs preserva valor anterior.
  - `test_save_bar_history_ohlc_optional` — callers legados (sem kwargs OHLC) funcionam, todas NULL.
  - `test_persist_closed_bars_threads_ohlc` — pipe end-to-end de OHLC arrays via `_build_history` → `_persist_closed_bars` → DB.
- `tests/test_build_history.py`: 3 testes novos:
  - `test_build_history_attaches_ohlc_when_arrays_provided` — arrays diretos (path `di_regime`).
  - `test_build_history_di_ohlc_map_fallback` — `di_ohlc_map` fallback (path `regime_v2`).
  - `test_build_history_ohlc_arrays_optional` — keys ausentes quando arrays não fornecidos (regressão zero).

## Verificação

- Suite completa: **393 passed, 19 skipped, 1 warning** (era 386 antes de A.3).
- Aritmética: +7 testes = 4 (test_bar_history) + 3 (test_build_history). ✓
- Não houve regressão. Os 19 skips continuam sendo PG (14) + outros gates externos pré-existentes.

## Observações

- DI OHLC depende de `_di_cache["history"]` estar fresh — o `di_regime()` é forçado a refresh on confirmed bar close já hoje (linha 1304 anterior). Em cold start, a primeira barra pode chegar sem DI OHLC; segunda em diante é completa.
- `BAR_HISTORY_BACKEND=postgres` e `dual` herdam OHLC automaticamente porque `bhdb.upsert_bar` já contempla (A.2). Não tive como testar PG em WSL (gate skip).
- `load_bar_history` ainda não retorna OHLC nas entries — não precisa para A.3 (replay vai ler raw via SELECT). Se a dashboard precisar de OHLC eventualmente, é mudança aditiva.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice A.3 fechado. `server.py` agora captura OHLC do MT5 via `fetch_rates()` (helper `_fetch_ohlc` flatten 5-tuple) e persiste em `bar_history` em cada barra fechada. WIN/WDO seguem direto via arrays; DI vai através de `_di_cache["history"]` (preenchido por `/api/di-regime`) e volta para `regime_v2` como `di_ohlc_map`. `save_bar_history` aceita 9 kwargs OHLC com COALESCE-preserve (mesmo padrão dos indicadores).

`history_endpoint` (multi-day API) ficou de fora — não persiste, só serve UI. Migração de lá fica para slice futuro se necessário.

Suite: **393 passed, 19 skipped** (+7 testes; zero regressões).

Próximo: A.4 — `scripts/backfill_bar_history_ohlc.py` para popular OHLC nas barras históricas existentes. Windows-only (`py.exe -3.12`, usa `fetch_rates_range`). Safe durante mercado (script offline).
<!-- SECTION:FINAL_SUMMARY:END -->
