---
id: TASK-17.1
title: Slice A.1 — fetch_rates() em core/mt5_client.py (OHLC sem quebrar fetch_bars)
status: Done
assignee: []
created_date: '2026-05-13 01:19'
updated_date: '2026-05-13 01:24'
labels:
  - engine
  - mt5
  - ohlc
dependencies: []
parent_task_id: TASK-17
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Adicionar `fetch_rates(symbol, count)` em `core/mt5_client.py` que retorna OHLC + timestamp (wrapper fino sobre `mt5.copy_rates_from_pos`). Também `fetch_rates_range(symbol, dt_start, dt_end)` para backfill histórico.

Manter `fetch_bars(symbol, count) → (closes, times)` intacto para não quebrar callers existentes.

## Por que essa fase é necessária

O `bar_history` hoje é close-only porque `fetch_bars()` em `core/mt5_client.py` devolve apenas `(closes, times)`. Para popular OHLC (necessário para detecção intra-bar de SL/TP), precisamos de uma função que devolva o array completo do MT5.

## Escopo

- `core/mt5_client.py`: adicionar 2 funções novas, sem mudar nada existente.
- `tests/test_mt5_client.py`: cobrir `fetch_rates` e `fetch_rates_range` com mock do módulo `mt5`.

## Não fazer aqui

- Não tocar em `server.py` (vem na A.3).
- Não tocar em `bar_history` schema (vem na A.2).

## Safe durante mercado

Sim — adição puramente aditiva, sem mudar comportamento existente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 fetch_rates(symbol, count) retorna np.ndarray com campos open/high/low/close/time (estrutura nativa do mt5.copy_rates_from_pos)
- [x] #2 fetch_rates_range(symbol, dt_start, dt_end) retorna o mesmo formato para intervalo de datas
- [x] #3 fetch_bars(symbol, count) continua funcionando idêntico a antes (sem mudança de assinatura ou retorno)
- [x] #4 tests/test_mt5_client.py cobre as 2 funções novas com mock do módulo mt5 (assert shape e keys)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Adicionado `fetch_rates(symbol, count)` e `fetch_rates_range(symbol, dt_start, dt_end)` em `core/mt5_client.py` (após `fetch_bars`). Ambos retornam o `np.ndarray` estruturado bruto do MT5 (campos `time/open/high/low/close/tick_volume/spread/real_volume`), ou `None` em erro/empty — mesma semântica de falha de `fetch_bars`.

`fetch_bars` preservado bit-exato (regressão coberta por novo teste `test_fetch_bars_unchanged_returns_tuple`).

`tests/conftest.py` ganhou stubs `mt5.copy_rates_from_pos` e `mt5.copy_rates_range` para permitir monkeypatch nos testes em Linux/CI.

9 testes novos em `tests/test_mt5_client.py` cobrindo: retorno OK com OHLC acessível, propagação de count/timeframe/datas para a API, `None` na API → `None`, array vazio → `None`, e regressão de `fetch_bars`.

28/28 testes do arquivo passam.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice A.1 entregue. Próxima fatia bloqueada por revisão antes de A.2 (ritual slice-by-slice).

**Arquivos tocados:**
- `core/mt5_client.py`: +20 linhas (`fetch_rates`, `fetch_rates_range`).
- `tests/conftest.py`: +2 linhas (stubs `copy_rates_*`).
- `tests/test_mt5_client.py`: +110 linhas (dtype helper + 9 testes novos).

**Verificação:** `pytest tests/test_mt5_client.py -v` → 28 passed.
<!-- SECTION:FINAL_SUMMARY:END -->
