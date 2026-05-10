---
id: TASK-8.3
title: Slice C — Endpoint /api/execution-timeline?mode=replay&date=…
status: To Do
assignee: []
created_date: '2026-05-09 17:14'
labels:
  - execution-timeline
  - replay
  - backend
  - api
dependencies: []
references:
  - server.py
  - core/execution_timeline.py
parent_task_id: TASK-8
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Estender o endpoint existente `/api/execution-timeline` para suportar leitura de DB de replay (`replays/execution_timeline_<date>.db`) sem afetar o modo live, que continua sendo o default.

Depende do Slice B (DB de replay precisa existir).

Escopo:
- Adicionar query params: `mode=live|replay` (default live), `date=YYYY-MM-DD` (obrigatório quando mode=replay).
- Quando `mode=replay`: validar formato da data, montar path `replays/execution_timeline_<date>.db`; se não existir, retornar 404 com payload `{"error":"REPLAY_NOT_FOUND","date":...}`.
- Quando `mode=replay`: ler via `load_timeline(db_path=replay_path, ...)`, `current_bottleneck(db_path=replay_path)`, `current_live_issue(db_path=replay_path)`. Mesmos filtros do live (`phase, status, strategy, event, since, limit`).
- Path traversal guard: rejeitar dates que não casem `^\d{4}-\d{2}-\d{2}$`.
- Não tocar no comportamento default (live continua exatamente como hoje).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `GET /api/execution-timeline` (sem `mode`) mantém comportamento atual: lê de `trades.db`.
- [ ] #2 `GET /api/execution-timeline?mode=replay&date=2026-05-08` lê de `replays/execution_timeline_2026-05-08.db` quando o arquivo existe.
- [ ] #3 `GET /api/execution-timeline?mode=replay&date=2099-01-01` (arquivo inexistente) retorna 404 com `{"error":"REPLAY_NOT_FOUND"}`.
- [ ] #4 `GET /api/execution-timeline?mode=replay&date=../etc/passwd` ou outro padrão não-data retorna 400 com erro de validação.
- [ ] #5 Filtros (`phase, status, strategy, event, limit, since`) funcionam idênticos em modo replay.
- [ ] #6 `current_bottleneck` e `current_live_issue` no payload de replay vem do DB de replay, não do `trades.db`.
- [ ] #7 Teste: endpoint com mode=live não regride; endpoint com mode=replay válido lista eventos do DB esperado; endpoint com mode=replay inexistente retorna 404; endpoint com data malformada retorna 400.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `py.exe -3.12 -m pytest tests/test_execution_timeline_server.py -q` passa.
- [ ] #2 `curl localhost:8080/api/execution-timeline` retorna eventos live; `curl 'localhost:8080/api/execution-timeline?mode=replay&date=2026-05-08'` retorna eventos do DB de replay.
<!-- DOD:END -->
