---
id: TASK-10
title: Backfill histórico completo via MT5 para Replay Execution Timeline
status: Done
assignee: []
created_date: '2026-05-10 06:05'
labels:
  - execution-timeline
  - replay
  - backfill
  - mt5
  - data-quality
dependencies:
  - TASK-8
references:
  - scripts/backfill_bar_history_indicators.py
  - scripts/replay_execution_timeline.py
  - core/mt5_client.py
  - core/config.py
  - server.py
parent_task_id: null
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Completar a qualidade histórica necessária para que o Replay Execution Timeline processe pregões antigos com a maior cobertura possível.

Contexto:
- A TASK-8 entregou o replay auditável por data e um backfill offline de indicadores (`eg_pvalue`, `rho`, `rho_level`, `beta_value`, `beta_delta_pct`).
- No replay de `2026-05-08`, o backfill local atualizou `22` barras e permitiu processar `18/112` barras.
- As primeiras `90` barras continuam sem indicadores porque o banco local não tem janela histórica WIN/WDO suficiente antes desse pregão.
- Ainda existem `4` barras de `2026-05-08` sem `di_price`.
- Esta task deve buscar histórico suficiente no MT5 para preencher preços faltantes e janela anterior, depois recalcular indicadores e regenerar replays.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Script ou comando de backfill histórico busca do MT5 `WIN$N`, `WDO$N` e `DI1$N` para a data alvo e uma janela anterior configurável.
- [x] #2 O backfill escreve `win_price`, `wdo_price`, `di_price` faltantes em `bar_history` sem sobrescrever valores existentes por padrão.
- [x] #3 O backfill recalcula `eg_pvalue`, `rho`, `rho_level`, `beta_value`, `beta_delta_pct` após completar a janela histórica.
- [x] #4 O comando suporta `--dry-run`, backup automático e modo explícito `--overwrite`.
- [x] #5 O replay de `2026-05-08` processa significativamente mais barras que `18/112`, ou documenta precisamente quais barras continuam impossíveis por ausência de dado MT5.
- [x] #6 Nenhuma rotina desta task envia ordens MT5; somente leitura histórica.
- [x] #7 Testes cobrem dry-run, preservação de valores existentes, escrita de preços faltantes, e ausência de chamada `order_send`.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `pytest tests/ -q` passa.
- [x] #2 Replay `2026-05-08` regenerado e summary anexado nesta task.
- [x] #3 Backup do `trades.db` criado antes de qualquer escrita real.
- [x] #4 Evidência SQL mostra contagem de campos faltantes antes/depois.
<!-- DOD:END -->

## finalSummary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implementado em 2026-05-10:

- `scripts/backfill_bar_history_indicators.py` ganhou modo `--fetch-mt5`, que lê histórico M5 de `WIN$N`, `WDO$N` e `DI1$N` por `copy_rates_range`, com janela anterior configurável por `--mt5-warmup-days`.
- O script mantém o modo local/offline como default; `--fetch-mt5` é explícito.
- Escrita de preço preserva valores existentes por padrão e só sobrescreve com `--overwrite`.
- Backup automático mantido antes de qualquer escrita real.
- Testes novos em `tests/test_backfill_bar_history_indicators.py` cobrem dry-run, warmup MT5 fake, inserção de linhas de contexto, preenchimento de preço faltante, preservação/overwrite e garantia de não chamar `MetaTrader5.order_send`.

Execução real:

- Dry-run Windows/MT5: `py -3.12 scripts\backfill_bar_history_indicators.py --source trades.db --date 2026-05-08 --fetch-mt5 --mt5-warmup-days 3 --dry-run`.
- Escrita real Windows/MT5: `py -3.12 scripts\backfill_bar_history_indicators.py --source trades.db --date 2026-05-08 --fetch-mt5 --mt5-warmup-days 3`.
- Backup criado: `trades.db.backfill-20260510-061259.bak`.

Evidência SQL antes/depois para `2026-05-08`:

- Antes: `COUNT=112`, `win_price NULL=0`, `wdo_price NULL=0`, `di_price NULL=4`, `eg_pvalue/rho/beta_value NULL=90`.
- Depois: `COUNT=115`, `win_price NULL=1`, `wdo_price NULL=1`, `di_price NULL=7`, `eg_pvalue/rho/beta_value NULL=2`.

Replay regenerado:

- Comando: `scripts/replay_execution_timeline.py --date 2026-05-08 --source trades.db --out replays`.
- Antes da TASK-10: `18/112` barras processadas.
- Depois da TASK-10: `108/115` barras processadas.
- Summary final: `bars_total=115`, `bars_processed=108`, `bars_skipped_missing=7`, `trades_opened=0`, `trades_closed=0`, `pnl_paper_brl=0.0`.
- Missing final: `di_price=7`, `win_price=1`, `wdo_price=1`, `eg_pvalue=2`, `rho=2`, `rho_level=2`, `beta_value=2`, `beta_delta_pct=2`.
- Blockers reconstruídos: `ELIGIBILITY:EG_NOT_COINTEGRATED=108`, `ELIGIBILITY:OUT_OF_SESSION=35`, `ELIGIBILITY:RHO_BREAKDOWN=30`, `ELIGIBILITY:Z_ANOMALY=1`.

Validação:

- `/tmp/wdowin-sliceb-venv/bin/python -m pytest tests/ -q` → `228 passed`.
- Endpoint `/api/execution-timeline?mode=replay&date=2026-05-08&limit=1000` retornou `bars_processed=108`.
<!-- SECTION:FINAL_SUMMARY:END -->
