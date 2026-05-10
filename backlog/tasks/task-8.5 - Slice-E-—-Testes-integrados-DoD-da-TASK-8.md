---
id: TASK-8.5
title: Slice E — Testes integrados + DoD da TASK-8
status: Done
assignee: []
created_date: '2026-05-09 17:14'
labels:
  - execution-timeline
  - replay
  - tests
  - qa
dependencies: []
references:
  - tests/test_execution_timeline_server.py
  - tests/test_bar_history.py
  - tests/test_replay_execution_timeline.py
  - scripts/replay_execution_timeline.py
parent_task_id: TASK-8
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Fechar AC #15 e DoD #1-#5 da TASK-8 com cobertura integrada e validação manual em pregão real.

Depende dos Slices A→D.

Escopo:
- Teste integrado: rodar Slice B sobre fixture de `bar_history` com dia válido → assert summary, assert que `trades.db` não foi tocado.
- Teste de isolamento: rodar replay 2x na mesma data → idempotência (dedupe_key funciona); confirmar que `trades.db` não recebe nada.
- Teste de path traversal/erro: endpoint replay com data inválida.
- Teste end-to-end: subir servidor de teste, rodar Slice C → recuperar eventos via endpoint.
- Validação manual DoD: replay de `2026-05-08`, anexar summary ao finalSummary da TASK-8.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Test suite cobre: isolamento live/replay (assertion de hash/mtime de `trades.db`), replay com dia válido (snapshot de eventos esperados), replay com DI faltante → `MISSING_DI_PRICE`, replay com `eg_pvalue` faltante → `MISSING_EG_PVALUE`, ausência de chamada `mt5.order_send` (mock spy), endpoint HTML/JSON em modo replay (200/404/400).
- [x] #2 Replay manual de `2026-05-08` produz summary com: total bars, processed, missing-by-field, blockers principais, trades simulados, PnL paper.
- [x] #3 Summary do replay anexado em `finalSummary` da TASK-8 quando ela for fechada.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 Test suite passa; `py.exe` não está disponível neste WSL, então a validação equivalente foi feita com `/tmp/wdowin-sliceb-venv/bin/python -m pytest tests/ -q`.
- [x] #2 Replay manual de `2026-05-08` registrado como evidence no finalSummary da TASK-8.
- [x] #3 Confirmar `trades.db` intacto após 3 replays consecutivos (sha256 antes/depois).
<!-- DOD:END -->

## Implementation Notes

- `tests/test_replay_execution_timeline.py` agora cobre snapshot determinístico do funil replay, spy explícito de `MetaTrader5.order_send`, SHA-256 + mtime do source DB, e 3 replays consecutivos sem mutar o banco fonte.
- Validação local: `/tmp/wdowin-sliceb-venv/bin/python -m pytest tests/ -q` → `210 passed`; `py.exe` não está disponível neste WSL.
- Replay manual de `2026-05-08` executado 3x contra `trades.db`, com output em `/tmp/wdowin-task8-slicee-replays`.
- SHA-256 de `trades.db` antes/depois dos 3 replays: `5bb11ded890be49e6b0eb65d1e4e81be5306c88bbd8623fa697215f5e1b90462`.
- Smoke live pós-replay: `GET /api/execution-timeline?limit=1` retornou `mode=live` e evento live existente, confirmando que a leitura live não foi redirecionada para o replay.
