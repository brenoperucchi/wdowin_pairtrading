---
id: TASK-8
title: Replay Execution Timeline — backtest auditável por data
status: Done
assignee: []
created_date: '2026-05-09 07:53'
updated_date: '2026-05-10 06:05'
labels:
  - execution-timeline
  - replay
  - backtest
  - audit
  - pre-live
dependencies: []
references:
  - server.py
  - core/config.py
  - core/execution_timeline.py
  - core/risk_gate.py
  - core/trade_engine.py
  - tests/test_execution_timeline_server.py
  - tests/test_bar_history.py
  - templates/execution_timeline.html
documentation:
  - docs/MOTOR_E_FLUXO_DE_DADOS.md
  - docs/PARAM_PROFILE.md
  - CLAUDE.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Criar um modo Replay para a Execution Timeline, permitindo selecionar um pregão histórico e reconstruir o funil DATA → INDICATORS → ELIGIBILITY → RISK → SIGNAL → ORDER/EXECUTION → EXIT a partir de `bar_history`, sem depender do dashboard live, sem enviar ordens MT5 e sem misturar eventos simulados com a timeline operacional real.

Contexto discutido:
- `/execution-timeline` hoje mostra apenas a timeline live gravada em `execution_timeline`.
- Para validar o motor e explicar dias sem entrada, precisamos simular a timeline bar-a-bar.
- O replay deve usar `bar_history` com `win_price`, `wdo_price`, `di_price`, `z_wdo`, `z_di`, NWE e timestamps.
- `wdo_price`/`di_price` passaram a ser persistidos em `fix(history): persist wdo and di prices`; ainda assim o replay deve validar dados faltantes e emitir DATA/MISSING_* quando aplicável.
- A UI inicial deve ser a página Jinja existente `/execution-timeline`, com modo Live/Replay e seletor de data. O painel React fica fora deste escopo.
- A janela operacional usada pelo replay deve vir de `core/config.py` sem override local. Mudanças de produto como `10:00–17:25` pertencem à TASK-7 e, quando aprovadas, o replay deve refletir automaticamente.
- Para paridade real, o replay deve preferir indicadores persistidos pelo live (`eg_pvalue`, `rho`, `rho_level`, `beta_value`, `beta_delta_pct`) em vez de recompor tudo por uma janela curta. Onde esses campos ainda estiverem ausentes, o replay deve marcar o dado como indisponível ou usar recomputação explicitamente sinalizada como fallback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Página Jinja `/execution-timeline` oferece controle claro de modo `Live` vs `Replay` (tabs, toggle ou botão equivalente). O painel React não faz parte deste card.
- [x] #2 Modo Replay permite escolher uma data de pregão (`YYYY-MM-DD`) e acionar/visualizar o replay dessa data sem misturar eventos com a timeline live.
- [x] #3 Replay grava em isolamento usando banco separado em diretório controlado (`replays/execution_timeline_<date>.db` ou `replays/<run_id>.db`); eventos replay não poluem `trades.db` live.
- [x] #4 Endpoint JSON suporta leitura do replay, por exemplo `/api/execution-timeline?mode=replay&date=YYYY-MM-DD`, mantendo o modo live atual como default.
- [x] #5 Script ou serviço `scripts/replay_execution_timeline.py` reconstrói o funil bar-a-bar a partir de `bar_history` para uma data escolhida.
- [x] #6 Replay reusa as funções centrais existentes sempre que possível: `risk_gate`, `TradeEngine.evaluate`, `record_event`, `load_timeline`, `current_bottleneck` e `current_live_issue`.
- [x] #7 Replay nunca envia ordens MT5, nunca usa `LIVE_ORDERS=True` e roda em DB/sandbox próprio.
- [x] #8 Replay respeita semântica de barra fechada: entradas avaliadas com dados da barra fechada, saídas em modo paper/replay, e timeline com gate pré-entrada quando aplicável.
- [x] #9 Live passa a persistir em `bar_history` os indicadores necessários para replay fiel por barra: `eg_pvalue`, `rho`, `rho_level`, `beta_value`, `beta_delta_pct` (com migration idempotente e escrita no fechamento de barra).
- [x] #10 Replay consome os indicadores persistidos do `bar_history` para montar os gates; recomputação por janela é permitida apenas como fallback explícito e sinalizado no summary/event payload.
- [x] #11 Barras com dados insuficientes em `bar_history` geram eventos DATA específicos (`MISSING_WDO_PRICE`, `MISSING_DI_PRICE`, `MISSING_WIN_PRICE`, `MISSING_EG_PVALUE`, `MISSING_RHO`, `MISSING_BETA` ou equivalente) em vez de falharem silenciosamente.
- [x] #12 Ao final do replay, o script/API retorna resumo com total de barras, barras processadas, barras ignoradas por dado ausente, blockers por fase/reason, trades simulados, PnL paper, `current_bottleneck` e `current_live_issue`.
- [x] #13 Replay usa a janela operacional vigente em `core/config.py` sem hardcode local. Alterar `ENTRY_START/END` ou `FORCE_CLOSE` é escopo da TASK-7, não desta task.
- [x] #14 UI do replay mostra claramente que o usuário está olhando `Replay YYYY-MM-DD`, com auto-refresh desabilitado ou controlado separadamente do live.
- [x] #15 Testes cobrem: isolamento live/replay, replay com dia válido, replay com DI faltante, replay com indicador persistido faltante, ausência de chamada MT5 order_send, e endpoint HTML/JSON em modo replay.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 Rodar `py.exe -3.12 -m pytest tests/ -q` com sucesso.
- [x] #2 Executar replay manual de `2026-05-08` e registrar no final summary: barras processadas, missing DI/WDO, blockers principais e PnL/trades simulados.
- [x] #3 Confirmar que `/execution-timeline` live continua lendo eventos reais após criar/visualizar replay.
- [x] #4 Confirmar que `trades.db` live não recebe eventos replay.
- [x] #5 Registrar no final summary que a alteração de janela `10:00–17:25` ficou fora da TASK-8 e deve ser tratada pela TASK-7.
<!-- DOD:END -->

## finalSummary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Evidence registrada no Slice E em 2026-05-10:

- Testes: `/tmp/wdowin-sliceb-venv/bin/python -m pytest tests/ -q` → `210 passed`; `py.exe` não está disponível neste WSL.
- Replay manual: `scripts/replay_execution_timeline.py --date 2026-05-08 --source trades.db --out /tmp/wdowin-task8-slicee-replays`, executado 3 vezes consecutivas.
- Integridade do `trades.db`: SHA-256 antes/depois dos 3 replays idêntico, `5bb11ded890be49e6b0eb65d1e4e81be5306c88bbd8623fa697215f5e1b90462`.
- Summary `2026-05-08`: `bars_total=112`, `bars_processed=0`, `bars_skipped_missing=112`, `missing_by_field={beta_delta_pct:112, beta_value:112, di_price:4, eg_pvalue:112, rho:112, rho_level:112}`.
- Blockers principais: nenhum blocker de `ELIGIBILITY`/`RISK` foi reconstruído porque todas as barras pararam em `DATA` por falta dos indicadores históricos pré-Slice A; `current_bottleneck=DATA/MISSING_DI_PRICE`, `current_live_issue=none`.
- Trades simulados/PnL: `trades_opened=0`, `trades_closed=0`, `pnl_paper_brl=0.0`.
- Smoke live pós-replay: `GET /api/execution-timeline?limit=1` retornou `mode=live` com eventos reais do `trades.db`, confirmando que replay não substituiu a leitura live.
- Produto: a janela `10:00–17:25` segue fora da TASK-8; a mudança de `ENTRY_START/ENTRY_END` permanece escopo da TASK-7.

Evidence pós-backfill de indicadores em 2026-05-10:

- Script novo: `scripts/backfill_bar_history_indicators.py`, offline, sem MT5, com `--dry-run`, backup automático e escrita apenas em campos `NULL` por padrão.
- Backfill real: `scripts/backfill_bar_history_indicators.py --source trades.db --date 2026-05-08` criou backup `trades.db.backfill-20260510-055246.bak` e atualizou `22` barras com `eg_pvalue`, `rho`, `rho_level`, `beta_value`, `beta_delta_pct`.
- Replay regenerado em `replays/execution_timeline_2026-05-08.db`.
- Summary após backfill: `bars_total=112`, `bars_processed=18`, `bars_skipped_missing=94`, `missing_by_field={beta_delta_pct:90, beta_value:90, di_price:4, eg_pvalue:90, rho:90, rho_level:90}`.
- Blockers reconstruídos nas 18 barras processadas: `ELIGIBILITY:OUT_OF_SESSION=18`, `ELIGIBILITY:RHO_BREAKDOWN=18`, `ELIGIBILITY:EG_NOT_COINTEGRATED=18`.
- Trades simulados/PnL após backfill: `trades_opened=0`, `trades_closed=0`, `pnl_paper_brl=0.0`.
- Limitação restante: as primeiras 90 barras de `2026-05-08` continuam sem indicadores porque o banco local não tem janela histórica WDO suficiente antes desse dia; as 4 barras sem `di_price` exigem backfill específico de DI/MT5.
<!-- SECTION:FINAL_SUMMARY:END -->
